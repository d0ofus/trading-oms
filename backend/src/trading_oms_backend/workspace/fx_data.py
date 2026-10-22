"""Bounded source-specific FX observations and history; history cannot emit signals."""

import time
from collections import deque
from datetime import UTC, datetime, timedelta

from .data_scheduling import request_progress
from .fx_candles import FXBrokerCandles
from .fx_market import FXSignal
from .fx_observations import CLOCK_BOUND_SECONDS, FXObservations, evaluate
from .fx_policy import BROKER_CANDLES
from .fx_sessions import FXSession
from .graph import number
from .store import Conflict, now


def recent(value, seconds=15):
    try:
        return 0 <= (datetime.now(UTC) - datetime.fromisoformat(value)).total_seconds() <= seconds
    except (ValueError, TypeError):
        return False


class FXData(FXObservations, FXBrokerCandles):
    @staticmethod
    def _fx_now():
        return datetime.now(UTC)

    @staticmethod
    def _fx_display_observation(cache, source, stamp, price):
        # Display aggregation is separate from authorized signal evaluation.
        rows = cache.setdefault("display_live", {}).setdefault(source, {})
        minute = int(stamp.timestamp()) // 60 * 60
        prior = rows[max(rows)] if rows else None
        if minute not in rows:
            if prior:
                prior["complete"] = bool(
                    prior["continuous"]
                    and minute == prior["timestamp"] + 60
                    and stamp.timestamp() - prior["last"] <= 15
                )
            rows[minute] = {
                "timestamp": minute,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "last": stamp.timestamp(),
                "continuous": stamp.timestamp() == minute
                or bool(
                    prior
                    and minute == prior["timestamp"] + 60
                    and stamp.timestamp() - prior["last"] <= 15
                ),
                "complete": False,
            }
        else:
            row = rows[minute]
            row.update(
                high=max(row["high"], price),
                low=min(row["low"], price),
                close=price,
                continuous=row["continuous"] and stamp.timestamp() - row["last"] <= 15,
                last=stamp.timestamp(),
            )
        while len(rows) > 1440:
            del rows[min(rows)]

    def _fx_candles(self, conid, seconds, before, limit, source=None):
        cache = self._fx_cache(conid)
        source = source or cache.get("selected_source", "MIDPOINT")
        if seconds != 60 or source not in {"MIDPOINT", "BID", "ASK"}:
            raise ValueError("FX candles use the selected Midpoint, Bid or Ask one-minute series.")
        rows = {
            int(k): {**v, "complete": True, "source": source + " history"}
            for k, v in cache["sources"].get(source, {}).get("bars", {}).items()
        }
        rows.update(
            {
                k: {**v, "source": source + " live"}
                for k, v in cache.get("display_live", {}).get(source, {}).items()
            }
        )
        broker = cache["sources"].get(source, {})
        if broker.get("persistent"):
            rows = {
                int(k): {**v, "source": "IBKR " + source} for k, v in broker.get("bars", {}).items()
            }
        boundary = datetime.fromisoformat(before).timestamp() if before else float("inf")
        keys = sorted(k for k in rows if k < boundary)[-limit - 1 :]
        items = [
            {
                "timestamp": datetime.fromtimestamp(k, UTC).isoformat(),
                **{p: str(rows[k][p]) for p in ("open", "high", "low", "close")},
                "volume": None,
                "source": rows[k]["source"],
                "complete": rows[k]["complete"] and k + 60 <= datetime.now(UTC).timestamp(),
                "eligibility": "Broker reference; requires a new live crossing."
                if broker.get("persistent")
                else "Display only; authorized live observations determine signals.",
            }
            for k in keys[-limit:]
        ]
        return {
            "items": items,
            "next_cursor": items[0]["timestamp"] if len(keys) > limit else None,
            "signal_source": source,
        }

    def _fx_cache(self, conid):
        if not hasattr(self, "fx_data"):
            self.fx_data = {}
        return self.fx_data.setdefault(conid, {"sources": {}, "feeds": {}, "next_tick": 0})

    def _fx_source(self, conid, source):
        cache = self._fx_cache(conid)
        return cache["sources"].setdefault(source, {"status": "queued", "bars": {}, "attempts": 0})

    def _fx_required_sources(self, conid):
        sources = {
            r["binding"]["execution_plan"]["signal_source"]
            for r in self.store.list("run")
            if self._fx_run(r)
            and r["conid"] == conid
            and not r.get("archived")
            and (
                r.get("armed")
                or r.get("authorization_status") == "temporarily_suspended"
                or number(r.get("position", 0))
            )
        }
        selected = self._fx_cache(conid).get("selected_source")
        sources.update(
            p["binding"]["execution_plan"]["signal_source"]
            for p in self.active_preparations(conid)
            if p["binding"]["execution_plan"].get("signal_source")
        )
        return sources | ({selected} if selected else set()) or {"MIDPOINT"}

    def _fx_prepare_data(self, conid, source, execution_policy=None):
        if conid not in getattr(self, "fx_data", {}) and len(getattr(self, "fx_data", {})) >= 20:
            needed = self._data_dependencies()["contracts"]
            unused = next((c for c in self.fx_data if c not in needed), None)
            if unused is None:
                raise Conflict(
                    "Remove an unused FX subscription before preparing another "
                    "(20-contract cache limit)."
                )
            self.fx_data.pop(unused)
        state = self._fx_source(conid, source)
        if execution_policy == BROKER_CANDLES and not state.get("persistent"):
            if state.get("request") and hasattr(self.broker, "cancel_feed"):
                self.broker.cancel_feed(state["request"])
            state.update(persistent=True, status="queued", bootstrap=False, bars={})
        if conid not in self.data:
            self.subscribe(conid)
        cache = self._fx_cache(conid)
        cache["selected_source"] = source
        for kind in ("fx_bidask", "fx_midpoint") if source == "MIDPOINT" else ("fx_bidask",):
            cache["feeds"].setdefault(kind, {"status": "queued", "attempts": 0})
        for state in (cache["sources"][source], *cache["feeds"].values()):
            if state["status"] == "retired":
                state.update(status="queued", attempts=0, request_state="queued")

    def _fx_data_maintain(self):
        if not self.connected or not self.attested:
            return
        self._fx_drain_observations()
        clock = time.monotonic()
        for conid, cache in getattr(self, "fx_data", {}).items():
            if conid not in self.data:
                continue
            for kind, state in cache["feeds"].items():
                if state["status"] == "retry" and clock >= state.get("retry_at", 0):
                    state["status"] = "queued"
                if state["status"] != "queued" or not self._data_contract_ready(
                    conid, state, clock
                ):
                    continue
                if clock < cache["next_tick"]:
                    self._request_wait(
                        state,
                        "waiting_pacing",
                        "Waiting for same-contract tick request pacing.",
                        cache["next_tick"],
                    )
                    continue
                try:
                    if state.get("request") and hasattr(self.broker, "cancel_feed"):
                        self.broker.cancel_feed(state["request"])
                    request = self.broker.start_feed(conid, kind)
                except Exception as exc:
                    self._data_request_fault(conid, state, exc, kind)
                    continue
                state.update(
                    status="pending",
                    request=request,
                    epoch=self.broker.epoch,
                    request_state="requested",
                    waiting_reason=None,
                    eligible_clock=None,
                )
                cache["next_tick"] = clock + 15.1
            for source, state in cache["sources"].items():
                if state["status"] == "pending" and clock - state.get("started", clock) > 60:
                    if hasattr(self.broker, "cancel_feed"):
                        self.broker.cancel_feed(state["request"])
                    self._fx_data_failure(
                        conid,
                        state,
                        "history",
                        "transient",
                        "FX history request timed out.",
                        source,
                    )
                if state["status"] == "retry" and clock >= state.get("retry_at", 0):
                    state["status"] = "queued"
        self._dispatch_history(clock)

    def _fx_data_failure(self, conid, state, component, reason, detail, source=None):
        if state.get("status") == "failed" and state.get("reason") == reason:
            return
        state.update(status="failed", reason=reason, detail=detail)
        if reason in {"transient", "pacing"} and state.get("attempts", 0) < 3:
            delay = (60, 120, 240) if reason == "pacing" else (15, 30, 60)
            state.update(
                status="retry",
                retry_at=time.monotonic() + delay[state.get("attempts", 0)],
                attempts=state.get("attempts", 0) + 1,
            )
        self.incident(
            "history_feed_failure" if component == "history" else "quote_feed_failure",
            detail,
            conid=conid,
            correlation_key="fx:" + (source or component),
            diagnostic={
                "reason": reason,
                "component": component,
                "signal_source": source,
                "fx": True,
            },
        )
        if component == "history":
            return  # A display download cannot reset a live signal.
        for run in self.store.list("run"):
            if (
                self._fx_run(run)
                and run["conid"] == conid
                and (
                    source in {None, "fx_bidask"}
                    or run["binding"]["execution_plan"]["signal_source"] == source
                    or source == "fx_midpoint"
                    and run["binding"]["execution_plan"]["signal_source"] == "MIDPOINT"
                )
            ):
                self.runtime.pop(run["id"], None)

    def _fx_data_observation(self, event):
        kind, conid = event["type"], event.get("conid")
        if kind == "broker_error" and conid in getattr(self, "fx_data", {}):
            cache = self.fx_data[conid]
            states = [(k, s) for k, s in cache["feeds"].items()] + list(cache["sources"].items())
            for name, state in states:
                if event.get("request") != state.get("request") or event.get(
                    "epoch", self.broker.epoch
                ) != state.get("epoch"):
                    continue
                if event.get("context") == "retired_data":
                    return True
                if hasattr(
                    self.broker, "feed_error_current"
                ) and not self.broker.feed_error_current(event):
                    return True
                self.store.event("fx.feed.diagnostic", event)
                self._fx_data_failure(
                    conid,
                    state,
                    "history" if name in cache["sources"] else "quote",
                    event.get("reason", "unknown"),
                    event.get("detail", "FX data request failed."),
                    name,
                )
                return True
            return False
        source = event.get("signal_source")
        if source and kind in {"historical_bar", "history_end"}:
            state = self._fx_source(conid, source)
            if (
                event.get("request") != state.get("request")
                or state["status"]
                not in ({"pending", "completed"} if state.get("persistent") else {"pending"})
                or event.get("epoch", self.broker.epoch) != state.get("epoch")
                or event.get("epoch", self.broker.epoch) != self.broker.epoch
            ):
                return True
            if state.get("persistent"):
                self._fx_broker_bar(event, state)
                return True
            if kind == "historical_bar":
                try:
                    values = [number(event[k]) for k in ("open", "high", "low", "close")]
                    opening, high, low, close = values
                    if not 0 < low <= min(opening, close) <= max(opening, close) <= high:
                        raise ValueError("Invalid FX candle")
                    stamp = int(event["timestamp"])
                    if stamp % 60 or stamp + 60 > datetime.now(UTC).timestamp():
                        return True  # Ignore an incomplete broker minute.
                except (ValueError, TypeError, KeyError):
                    state["invalid"] = True
                    return True
                state["bars"][event["timestamp"]] = event
                state["received"] = state.get("received", 0) + 1
                while len(state["bars"]) > 2000:
                    del state["bars"][min(state["bars"], key=int)]
            else:
                complete = bool(state.get("received") and not state.get("invalid"))
                state["status"] = "completed" if complete else "failed"
                state["detail"] = (
                    "Matching FX history downloaded."
                    if complete
                    else "No matching FX history was returned."
                )
                state["completed_at"] = now()
                self.store.event(
                    "fx.history.completed",
                    {"conid": conid, "source": source, "count": len(state["bars"])},
                )
                self.data[conid]["history_loaded"] = complete
            return True
        if kind not in {"fx_bidask", "fx_midpoint"}:
            return False
        if conid not in self.data or event.get("epoch", self.broker.epoch) != self.broker.epoch:
            return True
        if hasattr(self.broker, "feed_event_current") and not self.broker.feed_event_current(event):
            return True
        cache = self._fx_cache(conid)
        state = cache["feeds"].get(kind)
        if (
            not state
            or event.get("request") != state.get("request")
            or state.get("epoch") != self.broker.epoch
        ):
            return True
        if state.get("status") == "retired":
            return True
        self._fx_stage_observation(event)
        return True

    def _fx_process_observation(self, event, evaluated_at):
        kind, conid = event["type"], event["conid"]
        cache = self._fx_cache(conid)
        stamp = datetime.fromisoformat(event["source_at"])
        receipt = event["received_at"]
        self.data[conid].update(source_at=stamp.isoformat(), received_at=receipt)
        if kind == "fx_bidask":
            for side in ("bid", "ask"):
                self.quotes.setdefault(conid, {})[side] = {
                    "price": event[side],
                    "received_at": receipt,
                    "source_at": stamp.isoformat(),
                }
        cache.setdefault("observations", deque(maxlen=30000)).append(event)
        prices = (
            {"MIDPOINT": event["price"]}
            if kind == "fx_midpoint"
            else {"BID": event["bid"], "ASK": event["ask"]}
        )
        for basis, price in prices.items():
            self._fx_display_observation(cache, basis, stamp, number(price))
        for run in self.store.list("run"):
            if not self._fx_run(run) or run["conid"] != conid:
                continue
            if kind == "fx_bidask" and run.get("protection_type") == "locally_monitored":
                protection = self.store.get("fx_protection", run["id"]) or {}
                if (
                    self.data[conid].get("live")
                    and number(protection.get("quantity", 0)) > 0
                    and number(event["bid"]) <= number(protection["stop"])
                ):
                    self._fx_request_exit(run, "Local FX bid stop triggered.")
            plan = run["binding"]["execution_plan"]
            selected = plan["signal_source"]
            if self._fx_uses_broker_candles(run) and kind == "fx_bidask" and selected == "MIDPOINT":
                self._fx_evaluate_broker_reference(run)
            if (
                not run.get("armed")
                or run.get("entries", 0)
                or (selected == "MIDPOINT") != (kind == "fx_midpoint")
            ):
                continue
            if self._fx_uses_broker_candles(run):
                self._fx_broker_tick(run, event)
                continue
            if not self._fx_feed_health(conid, run, evaluated_at)["execution_fresh"]:
                self.runtime.pop(run["id"], None)
                continue
            runtime = self._fx_runtime(run)
            session = self._fx_session(run)
            interval = session.interval_start(stamp)
            price = number(event["price"] if selected == "MIDPOINT" else event[selected.lower()])
            trigger = runtime["market"].observe(stamp, price, interval)
            previous = runtime["market"].previous
            runtime["signal_progress"] = {
                "source": selected,
                "price": str(price),
                "observed_at": stamp.isoformat(),
                "reference_candle": previous["candle"] if previous else None,
                "reference_high": previous["high"] if previous else None,
                "comparison": "gt",
                "above_high": price > number(previous["high"]) if previous else None,
            }
            runtime["last_result"] = {
                "values": {
                    node["id"]: runtime["signal_progress"]["above_high"]
                    for node in runtime["graph"].ordered
                }
            }
            if trigger:
                if not self._fx_signal_current(trigger, evaluated_at):
                    self.store.event("fx.signal.expired", {"run_id": run["id"], **trigger})
                    continue
                start = datetime.fromisoformat(trigger["candle"]).timestamp()
                evidence = [e for e in cache["observations"] if e["timestamp"] >= start]
                if (
                    len(cache["observations"]) == cache["observations"].maxlen
                    and cache["observations"][0]["timestamp"] > start
                ):
                    self.disarm(
                        run["id"], "FX signal evidence buffer overflow; review before arming."
                    )
                    return True
                capture = self.store.capture(evidence)
                self._fx_enter(run, trigger, capture)
        return True

    def _fx_signal_current(self, trigger, evaluated_at=None):
        try:
            return (
                datetime.fromisoformat(trigger["triggered_at"])
                <= (evaluated_at or self._fx_now())
                < datetime.fromisoformat(trigger["expires_at"])
            )
        except (KeyError, TypeError, ValueError):
            return False

    def _fx_runtime(self, run, reset=False):
        key = run["id"]
        if reset or key not in self.runtime:
            from .reusable import bind_graph

            self.runtime[key] = {
                "graph": bind_graph(
                    self.store.version(run["strategy_id"], run["version"])["document"],
                    run["binding"],
                ),
                "market": FXSignal(
                    datetime.fromisoformat(
                        run.get("live_after") or run.get("authorized_at") or now()
                    )
                    + timedelta(seconds=CLOCK_BOUND_SECONDS)
                ),
            }
        return self.runtime[key]

    def _fx_session(self, run):
        return FXSession(self.contracts.get(run["conid"], run["binding"]["contract"]))

    def _fx_feed_health(self, conid, run=None, evaluated_at=None):
        at = evaluated_at or self._fx_now()
        cache = self._fx_cache(conid)
        source = (
            run["binding"]["execution_plan"]["signal_source"]
            if run
            else cache.get("selected_source", "MIDPOINT")
        )
        signal_kind = "fx_midpoint" if source == "MIDPOINT" else "fx_bidask"
        quote = self._fx_observation_value(conid, "fx_bidask")
        signal = self._fx_observation_value(conid, signal_kind)
        observations = {"bid/ask": evaluate(quote, at), "signal": evaluate(signal, at)}
        history = cache["sources"].get(source, {})
        issues = []
        for label, evaluation in (
            ("Bid/ask", observations["bid/ask"]),
            (source.title(), observations["signal"]),
        ):
            reason = evaluation["reason"]
            if reason != "fresh":
                issues.append(
                    f"Waiting for clock alignment of {label} observations"
                    if reason == "clock_alignment"
                    else f"Invalid {label} observation; continuity requires recovery"
                    if reason in {"invalid", "malformed_timestamp", "clock_fault", "overflow"}
                    else f"Waiting for fresh timestamped {label} observations"
                )
        live = bool(self.data.get(conid, {}).get("live"))
        if not live:
            issues.append("Waiting for live FX market-data confirmation")
        history_ready = (
            history.get("status") == "completed" and history.get("epoch") == self.broker.epoch
        )
        kinds = ("fx_bidask", "fx_midpoint") if source == "MIDPOINT" else ("fx_bidask",)
        feeds = [cache["feeds"].get(k, {"status": "queued"}) for k in kinds]
        for state in feeds:
            if state["status"] in {"failed", "retry", "retired"}:
                issues.append(state.get("detail", "Required FX stream is unavailable."))
            elif state.get("status") != "healthy" or state.get("epoch") != self.broker.epoch:
                issues.append("Waiting for current timestamped FX stream confirmation")
        # Observation freshness is separate from candle availability. The bound
        # execution policy selects broker-reference or legacy live-minute checks.
        states = feeds
        structural = all(v["structural_valid"] for v in observations.values())
        stream_healthy = (
            live
            and structural
            and all(
                s.get("status") == "healthy" and s.get("epoch") == self.broker.epoch for s in feeds
            )
        )
        reasons = [v["reason"] for v in observations.values()]
        invalid = {"invalid", "malformed_timestamp", "clock_fault", "overflow"}
        blocked = (
            any(s.get("status") in {"failed", "retry", "retired"} for s in states)
            or any(
                s.get("status") in {"healthy", "completed"} and s.get("epoch") != self.broker.epoch
                for s in states
            )
            or bool(invalid.intersection(reasons))
        )
        reason = next((r for r in reasons if r in invalid), None) or (
            "clock_alignment"
            if "clock_alignment" in reasons
            else "stale"
            if "stale" in reasons
            else "missing"
            if "missing" in reasons
            else "fresh"
        )
        return {
            "evaluated_at": at.isoformat(),
            "structural_valid": structural,
            "freshness_reason": reason,
            "observation_status": observations,
            "stream_health": "blocked"
            if blocked
            and any(s.get("status") in {"failed", "retry", "retired"} for s in feeds)
            or bool(invalid.intersection(reasons))
            else "healthy"
            if stream_healthy
            else "checking",
            "feed_health": "blocked" if blocked else "healthy" if stream_healthy else "checking",
            "execution_fresh": not issues,
            "status": "blocked" if blocked else "waiting" if issues else "ready",
            "execution_detail": "; ".join(dict.fromkeys(issues))
            if issues
            else f"Fresh {source} signal and bid/ask observations available.",
            "history_ready": history_ready,
            "ages": {
                f"{label} {part}": value[part]
                for label, value in observations.items()
                for part in ("source", "receipt")
            },
            "signal_source": source,
            "signal_price": signal.get("price")
            if source == "MIDPOINT"
            else signal.get(source.lower()),
            "signal_at": signal.get("source_at"),
            "subscription_health": self.data.get(conid, {}).get("subscription_status"),
        }

    def _fx_execution_status(self, health, run=None):
        runtime = self.runtime.get(run["id"], {}).get("market") if run else None
        previous = getattr(runtime, "previous", None)
        outcome = self._signal_view(run) if run else None
        if health["feed_health"] == "blocked":
            return "blocked", health["execution_detail"]
        if outcome and outcome["state"] in {
            "checking",
            "blocked",
            "submitted",
            "uncertain",
            "broker_rejected",
            "partially_filled",
            "filled",
        }:
            return outcome["state"], outcome["detail"]
        if health["freshness_reason"] == "clock_alignment":
            return "waiting_clock", "Waiting for clock alignment of timestamped observations."
        if not health["execution_fresh"]:
            return "waiting_quotes", health["execution_detail"]
        if run and self._fx_uses_broker_candles(run):
            if self._fx_broker_reference(run, datetime.fromisoformat(health["evaluated_at"])):
                return "ready", (
                    "Armed - waiting for breakout above the completed broker candle."
                    if run.get("armed")
                    else "Completed broker candle ready; authorization required."
                )
            return "waiting_broker_candle", "Waiting for completed broker candle."
        if previous and previous["expires_at"] > health["evaluated_at"]:
            return "ready", "Ready for the next qualifying signal."
        return "waiting_live_minute", "Waiting for a complete live minute after authorization."

    def _fx_reset_data(self):
        self._fx_account_evidence = {}
        for cache in getattr(self, "fx_data", {}).values():
            cache.pop("fx_bidask", None)
            cache.pop("fx_midpoint", None)
            cache.pop("display_live", None)
            cache.pop("pending_observations", None)
            cache.pop("processed", None)
            for state in cache["feeds"].values():
                state.update(status="queued", attempts=0)
            for state in cache["sources"].values():
                state.update(status="queued", attempts=0)
                if state.get("persistent"):
                    state.update(bootstrap=False, bars={})
        for run in self.store.list("run"):
            if self._fx_run(run):
                self.runtime.pop(run["id"], None)

    def _fx_data_view(self, conid, item):
        cache = self._fx_cache(conid)
        runs = [
            r
            for r in self.store.list("run")
            if self._fx_run(r) and r["conid"] == conid and not r.get("archived")
        ]
        runs.sort(key=lambda r: (bool(r.get("armed")), r.get("created_at", "")), reverse=True)
        run = runs[0] if runs else None
        health = self._fx_feed_health(conid, run)
        contract = self.contracts[conid]
        try:
            market_open = FXSession(contract).tradable(
                datetime.fromisoformat(health["evaluated_at"])
            )
        except ValueError:
            market_open = False
            health["execution_detail"] = (
                "Current broker FX schedule is unavailable; refresh broker rules."
            )
        item.update(health)
        if run and self._fx_uses_broker_candles(run):
            reference = self._fx_broker_reference(
                run, datetime.fromisoformat(health["evaluated_at"])
            )
            item.update(
                candle_policy=BROKER_CANDLES,
                broker_reference=reference,
                candle_stream_status=cache["sources"]
                .get(health["signal_source"], {})
                .get("status"),
            )
        execution_state, execution_detail = self._fx_execution_status(health, run)
        item.update(
            execution_state=execution_state,
            execution_detail=execution_detail,
        )
        item.update(
            timing_diagnostics={
                "streams": {
                    k: {name: value for name, value in v.items() if name != "journal_at"}
                    for k, v in cache.get("timing_diagnostics", {}).get("streams", {}).items()
                },
                "transitions": list(cache.get("timing_diagnostics", {}).get("transitions", ())),
                "pending": len(cache.get("pending_observations", ())),
            },
            family="spot_fx",
            currency=contract["currency"],
            base_currency=contract["symbol"],
            price_scale="1",
            quotes=copy_quotes(self.quotes.get(conid, {})),
            feed_status="market_closed"
            if not market_open
            else "fresh"
            if health["execution_fresh"]
            else "waiting_for_quotes",
            session_mode="fx",
            session_open=market_open,
            ready=market_open and health["execution_fresh"],
            history_status="loaded"
            if health["history_ready"]
            else "failed"
            if cache["sources"].get(health["signal_source"], {}).get("status")
            in {"failed", "retry"}
            else "loading",
            candle_source=health["signal_source"],
            price=health["signal_price"],
            fx_sources=[
                {
                    "source": source,
                    "status": state["status"],
                    "bars": len(state["bars"]),
                    "detail": state.get("detail"),
                    **request_progress([state]),
                }
                for source, state in cache["sources"].items()
            ],
            fx_feeds=[
                {
                    "kind": k,
                    "status": s["status"],
                    "detail": s.get("detail"),
                    "retry_available": s["status"] == "failed",
                    **request_progress([s]),
                }
                for k, s in cache["feeds"].items()
            ],
            components=self._fx_feed_projection(conid, {health["signal_source"]}),
            candles={},
            history_loaded=health["history_ready"],
        )
        return item

    def _fx_feed_projection(self, conid, sources=None):
        cache = self._fx_cache(conid)
        sources = sources or self._fx_required_sources(conid)
        groups = {
            "quote": [cache["feeds"].get("fx_bidask", {"status": "queued"})],
            "trade": [
                cache["feeds"].get("fx_midpoint", {"status": "queued"})
                if "MIDPOINT" in sources
                else cache["feeds"].get("fx_bidask", {"status": "queued"})
            ],
            "history": [cache["sources"].get(s, {"status": "queued"}) for s in sources],
        }
        watch = self.components_for(conid)["quote"]
        if watch["status"] == "failed":
            groups["quote"].append(
                {**watch, **(watch.get("diagnostic") or {}), "retry_at": watch.get("retry_at") or 0}
            )
        result = {}
        for component, states in groups.items():
            failures = [s for s in states if s["status"] in {"failed", "retry"}]
            status = (
                "failed"
                if failures
                else "healthy"
                if states and all(s["status"] in {"healthy", "completed"} for s in states)
                else "pending"
            )
            result[component] = {
                "source": "fx_" + component,
                "status": status,
                "diagnostic": {
                    "reason": failures[0].get("reason", "unknown"),
                    "detail": failures[0].get("detail", "FX request unavailable."),
                }
                if failures
                else None,
                "retry_available": any(s["status"] == "failed" for s in states),
                "retry_pending": any(
                    s["status"] == "retry" or s.get("manual_pending") for s in states
                ),
                "retry_in_seconds": min(
                    (
                        s["retry_at"] - time.monotonic()
                        for s in states
                        if (s.get("retry_at") or 0) > time.monotonic()
                    ),
                    default=None,
                ),
                "attempts": max((s.get("attempts", 0) for s in states), default=0),
                "signal_source": next(iter(sources)) if len(sources) == 1 else "MIDPOINT",
                **request_progress(states),
            }
        return result

    def _fx_retry_feeds(self, conid, components, mutation_id, actor):
        fingerprint = {"conid": conid, "components": sorted(set(components)), "actor": actor}
        previous = self.store.get("feed_retry", mutation_id)
        if previous:
            if previous["request"] != fingerprint:
                raise Conflict("Retry identity already belongs to another request.")
            return previous["response"]
        if not components or set(components) - {"quote", "trade", "history"}:
            raise Conflict("Choose failed FX quote, signal or history components.")
        if not self.connected:
            raise Conflict("Reconnect the paper data connection before retrying feeds.")
        cache = self._fx_cache(conid)
        queued = []
        watch = self.components_for(conid)["quote"]
        if (
            "quote" in components
            and watch["status"] == "failed"
            and not watch.get("manual_pending")
        ):
            watch.update(
                retry_at=max(
                    time.monotonic(), watch.get("retry_at") or watch.get("cooldown_until", 0)
                ),
                automatic=False,
                manual_pending=True,
            )
            queued.append("quote")
        for component in sorted(set(components)):
            targets = (
                list(cache["sources"].values())
                if component == "history"
                else [
                    cache["feeds"].get("fx_bidask" if component == "quote" else "fx_midpoint", {})
                ]
            )
            for state in targets:
                if state.get("status") == "failed":
                    state.update(
                        status="retry",
                        attempts=0,
                        retry_at=max(time.monotonic(), state.get("retry_at") or 0),
                    )
                    queued.append(component)
        response = {"conid": conid, "queued": sorted(set(queued)), "armed": False}
        with self.store.transaction() as db:
            self.store.write(
                db, "feed_retry", mutation_id, {"request": fingerprint, "response": response}
            )
            self.store.append(
                db, "fx.retry.requested", {**response, "actor": actor, "mutation_id": mutation_id}
            )
        return response


def copy_quotes(quotes):
    return {key: dict(value) for key, value in quotes.items()}


def age(value):
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(value)).total_seconds()
    except (ValueError, TypeError):
        return None
