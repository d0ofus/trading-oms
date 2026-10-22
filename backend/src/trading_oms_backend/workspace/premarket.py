"""Explicit pre-market policy helpers and isolated, paced historical coverage."""

import os
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .graph import number
from .oca import rounded
from .stock_sessions import StockSession
from .store import Conflict


def premarket(run):
    return (
        (run or {}).get("binding", {}).get("execution_plan", {}).get("session_mode")
        == "premarket_regular"
        if (run or {}).get("binding")
        else False
    )


def broker_deadline(value):
    """Normalize documented UTC/IANA broker GTD representations; unknown zones fail closed."""
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 17 and value[8] == "-":
            return datetime.strptime(value, "%Y%m%d-%H:%M:%S").replace(tzinfo=UTC)
        parts = value.split()
        if len(parts) == 3:
            zone = "America/New_York" if parts[2] in {"US/Eastern", "EST5EDT"} else parts[2]
            if zone not in {"America/New_York", "UTC", "GMT"}:
                return None
            return (
                datetime.strptime(" ".join(parts[:2]), "%Y%m%d %H:%M:%S")
                .replace(tzinfo=ZoneInfo(zone))
                .astimezone(UTC)
            )
    except (ValueError, TypeError):
        pass
    return None


class PremarketController:
    def _stock_session(self, run):
        contract = dict(run["binding"]["contract"])
        current = self.contracts.get(run["conid"], {})
        for field in ("trading_hours", "liquid_hours"):
            contract[field] = current.get(field, "")
        return StockSession(contract, run["binding"].get("session_mode", "regular"))

    def _run_history_ready(self, run):
        if not self._requires_downloaded_history(run):
            return True
        if self._fx_run(run):
            return self._fx_feed_health(run["conid"], run)["history_ready"]
        if premarket(run):
            h = getattr(self, "premarket_history", {}).get(run["conid"], {})
            return (
                h.get("status") == "completed"
                and h.get("epoch") == self.broker.epoch
                and h.get("day") == datetime.now(ZoneInfo("America/New_York")).date().isoformat()
            )
        return bool(self.data.get(run["conid"], {}).get("warm"))

    def _run_feed_health(self, run):
        return self.feed_health(run["conid"], run)

    def _premarket_queue(self, conid, force=False):
        if not hasattr(self, "premarket_history"):
            self.premarket_history = {}
        old = self.premarket_history.get(conid, {})
        day = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        if (
            not force
            and old.get("status") != "retired"
            and old.get("day") == day
            and old.get("epoch") == self.broker.epoch
        ):
            return
        if (
            old.get("request")
            and old.get("status") == "pending"
            and hasattr(self.broker, "cancel_feed")
        ):
            self.broker.cancel_feed(old["request"])
        self.premarket_history[conid] = {
            "day": day,
            "epoch": self.broker.epoch,
            "status": "queued",
            "bars": old.get("bars", {60: {}, 5: {}}),
            "attempts": 0,
        }

    def _premarket_maintain(self, clock):
        if not self.connected:
            return
        runs = [
            r
            for r in self.store.list("run")
            if premarket(r) and (not r.get("archived") or number(r.get("position", 0)))
        ]
        dependencies = self._data_dependencies()
        for conid in dependencies["premarket"]:
            self._premarket_queue(conid)
        self._retire_data_jobs(dependencies)
        states = getattr(self, "premarket_history", {})
        for conid, h in states.items():
            if h["status"] == "pending" and clock - h["started"] > 120:
                if hasattr(self.broker, "cancel_feed"):
                    self.broker.cancel_feed(h["request"])
                self._premarket_history_failure(conid, 0, "transient")
            if h["status"] == "failed" and h.get("retry_at") and clock >= h["retry_at"]:
                h.update(status="queued", attempts=h.get("attempts", 0) + 1)
        self._dispatch_history(clock)
        for run in runs:
            request = self.store.get("exit_request", run["id"])
            if not request or not self.owned().get(run["id"], {}).get("quantity"):
                continue
            if (
                datetime.now(UTC) - datetime.fromisoformat(request["requested_at"])
            ).total_seconds() >= 30 and not request.get("alerted"):
                self.store.put("exit_request", run["id"], {**request, "alerted": True})
                self.incident(
                    "premarket_exit_pending",
                    "Protective/manual exit remains unfilled after 30 seconds. "
                    "Fresh-bid limit retries continue only after cancellation and "
                    "reconciliation; inspect TWS and remaining ownership.",
                    run=run,
                )

    def _premarket_history_failure(self, conid, code, reason):
        from .feed_recovery import DELAYS

        h = self.premarket_history[conid]
        delays = DELAYS.get(reason)
        attempt = h.get("attempts", 0)
        h.update(
            status="failed",
            detail=(
                f"Pre-market history failed (code {code}, {reason}). "
                "Retry failed feeds after addressing broker diagnostics."
            ),
            retry_at=time.monotonic() + delays[attempt] if delays and attempt < 3 else None,
        )
        self.store.event(
            "market.premarket_history.failed", {"conid": conid, "code": code, "reason": reason}
        )
        self.incident(
            "premarket_history_feed_failure",
            h["detail"],
            conid=conid,
            diagnostic={
                "code": code,
                "reason": reason,
                "request_kind": "history",
                "session_mode": "premarket_regular",
            },
        )

    def _premarket_observation(self, event):
        if event["type"] not in {"historical_bar", "history_end", "broker_error"}:
            return False
        if event["type"] == "broker_error" and event.get("context") not in {
            "market_data",
            "retired_data",
        }:
            return False
        if event["type"] == "broker_error" and event.get("code") in {
            201,
            1100,
            1101,
            1102,
            1300,
            502,
            504,
        }:
            return False
        match = next(
            (
                (c, h)
                for c, h in getattr(self, "premarket_history", {}).items()
                if h.get("request") == event.get("request")
                and h.get("epoch") == event.get("epoch", self.broker.epoch)
            ),
            None,
        )
        if not match:
            return event.get("history_scope") == "extended" or (
                event.get("context") in {"market_data", "retired_data"}
                and event.get("parameters", {}).get("use_rth") is False
            )
        conid, h = match
        if (
            event["type"] == "broker_error"
            and hasattr(self.broker, "feed_error_current")
            and not self.broker.feed_error_current(event)
        ):
            return True
        if h["status"] != "pending":
            return True
        if event["type"] == "historical_bar":
            try:
                prices = [number(event[k]) for k in ("open", "high", "low", "close")]
                stamp = datetime.fromtimestamp(int(event["timestamp"]), UTC)
                if (
                    stamp > datetime.now(UTC)
                    or min(prices) <= 0
                    or prices[2] > min(prices[0], prices[3])
                    or prices[1] < max(prices[0], prices[3])
                ):
                    raise ValueError("Invalid historical bar")
            except (ValueError, TypeError, KeyError, OverflowError, OSError):
                self._premarket_history_failure(conid, 0, "invalid_history")
                return True
            if len(h["bars"][60]) < 2000:
                h["bars"][60][event["timestamp"]] = event
                h["received"] = h.get("received", 0) + 1
        elif event["type"] == "history_end":
            if not h["bars"][60] or h.get("received") == 0:
                self._premarket_history_failure(conid, 0, "unavailable")
            else:
                h.update(
                    status="completed",
                    detail="Extended-hours history downloaded; waiting for complete live candles.",
                )
                self.store.event(
                    "market.premarket_history.completed",
                    {"conid": conid, "bars": len(h["bars"][60]), "retrospective_entries": False},
                )
                for run in self.store.list("run"):
                    if (
                        premarket(run)
                        and run["conid"] == conid
                        and self._requires_downloaded_history(run)
                    ):
                        self.runtime.pop(run["id"], None)
        else:
            self._premarket_history_failure(
                conid, event.get("code", 0), event.get("reason", "unknown")
            )
        return True

    def _premarket_entry(self, run, payload):
        if os.environ.get("OMS_DISABLE_PREMARKET_ARM") == "1":
            raise Conflict("New pre-market entries are disabled by the operator rollback setting.")
        stamp = datetime.now(UTC)
        intervals = self._stock_session(run).intervals(stamp)
        end = next((b for a, b in intervals if a <= stamp < b), None)
        trigger = self.store.get("stock_trigger", run["id"]) or {}
        if not end or not trigger.get("expires_at"):
            raise Conflict(
                "A current eligible live-minute trigger and broker session are required."
            )
        deadline = min(
            end,
            datetime.fromisoformat(trigger["expires_at"]),
            stamp + timedelta(seconds=30),
            datetime.fromisoformat(payload["expires_at"]),
        )
        if deadline <= stamp:
            raise Conflict("The pre-market entry generation has expired.")
        payload.update(
            entry_type="LMT",
            expires_at=deadline.isoformat(),
            timeout=(deadline - stamp).total_seconds(),
            session_contract=self._stock_session(run).contract,
        )

    def _premarket_exit_payload(self, run, payload):
        stamp = datetime.now(UTC)
        quote = self.quotes.get(run["conid"], {}).get("bid", {})
        from .oca_engine import fresh

        if not fresh(quote) or number(quote.get("price", 0)) <= 0:
            raise Conflict("A fresh positive bid is required for a pre-market limit exit.")
        end = next(
            (b for a, b in self._stock_session(run).intervals(stamp) if a <= stamp < b), None
        )
        if end is None:
            raise Conflict(
                "Exit remains requested; waiting for the next approved broker trading interval."
            )
        payload.update(
            exit_type="LMT",
            expires_at=end.isoformat(),
            protection_type="locally_monitored",
            session_contract=self._stock_session(run).contract,
        )
        payload["limit"] = str(
            rounded(
                number(payload["limit"]),
                self.market_rules.get(run["binding"]["contract"].get("market_rule"), []),
                False,
            )
        )
