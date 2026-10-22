"""Explicit one-shot connection test using the ordinary durable paper OMS."""

import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from .contracts import capabilities
from .graph import number, templates
from .sessions import NY, execution_bounds
from .store import Conflict, now


class PaperConnectionTest:
    def connection_diagnostics(self, conid):
        from .engine import check

        quotes = self.quotes.get(conid, {})
        data = self.data.get(conid, {})
        fresh = all(
            side in quotes
            and 0
            <= (
                datetime.now(UTC) - datetime.fromisoformat(quotes[side]["received_at"])
            ).total_seconds()
            <= 15
            and number(quotes[side]["price"]) > 0
            for side in ("bid", "ask")
        )
        checks = self.readiness() + [
            check(
                "contract",
                "Resolved stock or ETF",
                not self.environment.crypto
                and "long_bracket" in capabilities(self.contracts.get(conid, {}))["executions"],
                "Resolve a symbol in Settings.",
            ),
            check(
                "entitlement",
                "Real-time quote entitlement",
                data.get("live"),
                "Subscribe to real-time quotes for this paper login.",
            ),
            check(
                "quotes",
                "Fresh bid and ask",
                fresh,
                "Current bid/ask observations are required; unchanged prices are acceptable.",
            ),
            check(
                "spread",
                "Valid quote spread",
                fresh and number(quotes["ask"]["price"]) >= number(quotes["bid"]["price"]),
                "Crossed or invalid quotes block the test.",
            ),
            check(
                "verified_build",
                "Verified application build",
                self.code_verified,
                "Run scripts/verify.ps1 on this build.",
            ),
        ]
        return {
            "checks": checks,
            "eligible": all(c["passed"] for c in checks),
            "quotes": quotes,
            "last_trade_at": data.get("received_at"),
            "symbol": self.contracts.get(conid, {}).get("symbol"),
            "tests": self.store.list("paper_connection_test"),
        }

    def paper_test_preview(self, conid, trading_hours="extended"):
        from .engine import check

        if trading_hours not in {"regular", "extended"}:
            raise ValueError("Select regular or extended stock hours.")
        diagnostics = self.connection_diagnostics(conid)
        stamp = datetime.now(UTC)
        day = stamp.astimezone(NY).date().isoformat()
        bounds = execution_bounds(day, trading_hours, self.contracts.get(conid))
        checks = diagnostics["checks"]
        checks.append(
            check(
                "execution_window",
                "Broker execution session open",
                bounds and bounds[0] <= stamp < bounds[1] - timedelta(minutes=15),
                "A closed market supports connection checks only. Submit during an "
                "eligible regular or pre/post-market session.",
            )
        )
        active = [
            r for r in self.store.list("run") if r.get("armed") or number(r.get("position", 0)) > 0
        ]
        outstanding = any(
            o["state"] not in {"filled", "cancelled", "rejected"} for o in self.store.orders()
        )
        checks.append(
            check(
                "test_capacity",
                "One supervised run only",
                not active and not outstanding,
                "Disarm other runs and finish their orders/positions before this "
                "one-share smoke test.",
            )
        )
        prices = None
        if diagnostics["eligible"]:
            bid = number(diagnostics["quotes"]["bid"]["price"])
            rules = self.market_rules.get(self.contracts[conid].get("market_rule"), [])

            def rounded(price):
                tick = next(
                    (number(r["increment"]) for r in reversed(rules) if price >= number(r["low"])),
                    Decimal(0),
                )
                if tick <= 0:
                    raise Conflict("Broker price-increment rules are unavailable.")
                return (price / tick).to_integral_value(rounding=ROUND_DOWN) * tick, tick

            try:
                _, tick = rounded(bid)
                limit, _ = rounded(bid - max(bid * Decimal("0.01"), tick * 10))
                stop, _ = rounded(limit - 1)
                stop_limit, _ = rounded(stop - Decimal("0.10"))
                if not 0 < stop_limit < stop < limit <= 1000:
                    raise Conflict(
                        "Select a symbol whose one-share limit and $1 stop fit the paper limits."
                    )
                prices = {
                    "limit": str(limit),
                    "stop": str(stop),
                    "stop_limit": str(stop_limit) if trading_hours == "extended" else None,
                }
            except ValueError as exc:
                checks.append(check("prices", "Test prices", False, str(exc)))
        identity = uuid.uuid4().hex
        result = {
            "id": identity,
            "conid": conid,
            "symbol": diagnostics["symbol"],
            "trading_hours": trading_hours,
            "session_date": day,
            "valid_from": bounds[0].isoformat() if bounds else None,
            "expires_at": bounds[1].isoformat() if bounds else None,
            "preview_expires_at": (stamp + timedelta(seconds=15)).isoformat(),
            "instance": self.process_identity,
            "epoch": self.broker.epoch,
            "paper_context": getattr(self, "paper_context_token", None),
            "contract": dict(self.contracts.get(conid, {})),
            "prices": prices,
            "quantity": 1,
            "checks": checks,
            "eligible": bool(prices) and all(c["passed"] for c in checks),
        }
        self.store.put("paper_test_preview", identity, result)
        return result

    def start_paper_test(self, preview_id, actor="local-operator"):
        prior = self.store.get("paper_connection_test", preview_id)
        if prior:
            return prior
        preview = self.store.get("paper_test_preview", preview_id)
        if not preview or not preview["eligible"] or preview["preview_expires_at"] <= now():
            raise Conflict("Refresh and review a current eligible paper-test preview.")
        if (
            preview.get("instance") != self.process_identity
            or preview.get("epoch") != self.broker.epoch
            or preview.get("paper_context") != getattr(self, "paper_context_token", None)
            or preview.get("contract") != self.contracts.get(preview["conid"])
        ):
            raise Conflict("Paper context or contract changed. Refresh the paper-test preview.")
        current = self.paper_test_preview(preview["conid"], preview["trading_hours"])
        if not current["eligible"]:
            raise Conflict("Readiness changed. Refresh the paper-test preview.")
        if number(preview["prices"]["limit"]) > number(current["prices"]["limit"]):
            raise Conflict(
                "The reviewed limit is no longer sufficiently below bid. Refresh the preview."
            )
        graph = templates()[1]["document"]
        graph["schema_version"] = 4
        graph["settings"].update(
            symbol=preview["symbol"],
            sizing="fixed",
            shares=1,
            max_entries=1,
            trading_hours=preview["trading_hours"],
            stop_limit_offset="0.10",
        )
        draft = self.store.save_draft(None, "Paper connection test", graph, 0)
        draft["diagnostic_only"] = True
        self.store.put("draft", draft["id"], draft)
        version = self.store.publish(draft["id"], draft["revision"])
        key = uuid.uuid4().hex
        run = {
            "id": key,
            "name": "Paper connection test",
            "strategy_id": draft["id"],
            "version": version["version"],
            "conid": preview["conid"],
            "symbol": preview["symbol"],
            "position": "0",
            "state": "armed",
            "armed": True,
            "entries": 0,
            "risk": "10",
            "protected": False,
            "diagnostic_test": preview_id,
            "session_date": preview["session_date"],
            "trading_hours": preview["trading_hours"],
            "valid_from": preview["valid_from"],
            "expires_at": preview["expires_at"],
            "limits": self.store.get("risk_profile", "smoke:1"),
            "created_at": now(),
            "execution": "long_bracket",
            "session_policy": "xnys",
            "protection_type": "broker_held",
            "authorization_status": "authorized",
            "authorization_instance": self.process_identity,
            "authorization_context": getattr(self, "paper_context_token", None),
            "authorization_id": preview_id,
            "authorized_at": now(),
            "live_after": now(),
            "epoch": self.broker.epoch,
        }
        trial = {
            "id": preview_id,
            "run_id": key,
            "symbol": preview["symbol"],
            "state": "submitting",
            "started_at": now(),
            "cancel_by": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        }
        with self.store.transaction() as db:
            self.store.write(db, "run", key, run)
            self.store.write(db, "paper_connection_test", preview_id, trial)
            self.store.append(
                db,
                "paper_test.authorized",
                {
                    "run_id": key,
                    "preview_id": preview_id,
                    "quantity": 1,
                    "actor": actor,
                    "strategy_hash": version["hash"],
                    "prices": preview["prices"],
                    "protection_type": "broker_held",
                },
            )
        capture = self.store.capture({"source": "operator_paper_test", "preview": preview})
        bounds = self._run_bounds(run)
        try:
            self._enter(
                run,
                {
                    "stop": number(preview["prices"]["stop"]),
                    "target": None,
                    "test_limit": preview["prices"]["limit"],
                },
                {"minutes_to_close": (bounds[1] - datetime.now(UTC)).total_seconds() / 60},
                capture,
            )
        except Exception:
            # A failure may have happened after dispatch: preserve its run and intent.
            self.disarm(key, "Paper test interrupted. Inspect its durable order state.")
            trial["state"] = "recovery_required"
            self.store.put("paper_connection_test", preview_id, trial)
            raise
        # Do not cancel until acknowledgement + five seconds; tick evaluation
        # excludes diagnostic runs, and their entry count is bounded to one.
        return trial

    def _maintain_paper_tests(self):
        for trial in self.store.list("paper_connection_test"):
            previous = dict(trial)
            position = self.owned().get(trial["run_id"], {}).get("quantity", 0)
            if not position and trial["state"] in {
                "cancelled_verified",
                "cancelled_without_ack",
                "rejected_verified",
                "filled_then_closed",
            }:
                continue
            orders = [
                o
                for o in self.store.orders()
                if o["run_id"] == trial["run_id"] and o["payload"].get("purpose") == "entry"
            ]
            if not orders:
                continue
            order = orders[0]
            if position:
                trial["state"] = "position_requires_attention"
                trial["fill_observed"] = True
                if self.store.get("run", trial["run_id"]).get("armed"):
                    self.disarm(
                        trial["run_id"],
                        "Unexpected test fill. Verify protection and close the owned position.",
                    )
            elif order["state"] in {"unknown", "dispatching"}:
                trial["state"] = "recovery_required"
            elif order["state"] == "working":
                if not trial.get("acknowledged_at"):
                    trial["acknowledged_at"] = now()
                    trial["cancel_by"] = min(
                        trial["cancel_by"], (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
                    )
                    self.store.event("paper_test.acknowledged", {"run_id": trial["run_id"]})
                trial["state"] = "acknowledged"
                if now() >= trial["cancel_by"]:
                    self.disarm(trial["run_id"], "Paper test cancellation requested.")
                    trial["state"] = "cancel_pending"
            elif (
                order["state"] in {"filled", "cancelled", "rejected"}
                and self.reconciled
                and time.monotonic() - self.reconciled_at < 30
            ):
                reservation = self.store.get("reservation", order["id"]) or {}
                if not reservation.get("active"):
                    trial["state"] = (
                        "cancelled_verified"
                        if order["state"] == "cancelled" and trial.get("acknowledged_at")
                        else "filled_then_closed"
                        if trial.get("fill_observed")
                        else "cancelled_without_ack"
                        if order["state"] == "cancelled"
                        else "rejected_verified"
                    )
                    self.disarm(trial["run_id"], "Paper test finished flat with terminal orders.")
                    self.store.event(
                        "paper_test.finished", {"run_id": trial["run_id"], "state": trial["state"]}
                    )
            if previous != trial:
                self.store.put("paper_connection_test", trial["id"], trial)
