"""Current-generation broker candles and independently authorized live evidence."""

from datetime import UTC, datetime

from .fx_observations import CLOCK_BOUND_SECONDS, evaluate
from .fx_policy import BROKER_CANDLES
from .graph import digest, number


class FXBrokerCandles:
    @staticmethod
    def _fx_uses_broker_candles(run):
        return (run.get("binding") or {}).get("execution_plan", {}).get("policy") == BROKER_CANDLES

    def _fx_broker_bar(self, event, state):
        at = self._fx_now()
        if event["type"] == "history_end":
            state.update(bootstrap=True, status="completed", completed_at=at.isoformat())
            for key, row in state["bars"].items():
                row["complete"] = int(key) + 60 <= at.timestamp()
            state["detail"] = "Broker candle stream established; bootstrap complete."
        else:
            try:
                stamp = int(event["timestamp"])
                opening, high, low, close = [
                    number(event[k]) for k in ("open", "high", "low", "close")
                ]
                if (
                    stamp % 60
                    or stamp > at.timestamp() + CLOCK_BOUND_SECONDS
                    or not 0 < low <= min(opening, close) <= max(opening, close) <= high
                ):
                    raise ValueError("Invalid broker candle")
            except (ValueError, TypeError, KeyError):
                state.update(
                    invalid=True,
                    status="failed",
                    detail="Invalid broker candle; awaiting a new verified stream.",
                )
                return
            if state.get("bootstrap"):
                for key, row in state["bars"].items():
                    if int(key) < stamp:
                        row["complete"] = True
            key = str(stamp)
            complete = bool(
                state.get("bootstrap")
                and (
                    stamp < max((int(k) for k in state["bars"]), default=stamp)
                    or stamp + 60 <= at.timestamp()
                )
            )
            state["bars"][key] = {
                "timestamp": key,
                "open": str(opening),
                "high": str(high),
                "low": str(low),
                "close": str(close),
                "complete": complete,
                "revision": digest(
                    {
                        "epoch": state["epoch"],
                        "request": state["request"],
                        "minute": stamp,
                        "prices": [str(v) for v in (opening, high, low, close)],
                    }
                ),
            }
            state["received"] = state.get("received", 0) + 1
            while len(state["bars"]) > 2000:
                del state["bars"][min(state["bars"], key=int)]
        state["updated_at"] = at.isoformat()
        # A bar alone cannot trigger: only an already retained, post-authorization
        # live observation is eligible, and all its freshness checks are repeated.
        for run in self.store.list("run"):
            if (
                self._fx_uses_broker_candles(run)
                and run["conid"] == event["conid"]
                and run["binding"]["execution_plan"]["signal_source"] == event["signal_source"]
            ):
                self._fx_evaluate_broker_reference(run)

    def _fx_broker_reference(self, run, at):
        source = run["binding"]["execution_plan"]["signal_source"]
        state = self._fx_source(run["conid"], source)
        minute = int(at.timestamp()) // 60 * 60 - 60
        row = state.get("bars", {}).get(str(minute))
        if not (
            state.get("persistent")
            and state.get("bootstrap")
            and state.get("status") == "completed"
            and state.get("epoch") == self.broker.epoch
            and row
            and row.get("complete")
        ):
            return None
        return {
            **row,
            "candle": datetime.fromtimestamp(minute, UTC).isoformat(),
            "expires_at": datetime.fromtimestamp(minute + 120, UTC).isoformat(),
            "request": state["request"],
            "epoch": state["epoch"],
        }

    def _fx_broker_tick(self, run, event):
        runtime = self._fx_runtime(run)
        runtime["pending_tick"] = dict(event)
        runtime["pending_authorization"] = run.get("authorization_id")
        self._fx_evaluate_broker_reference(run)

    def _fx_broker_tick_current(self, run, event, at):
        if not event or not run.get("armed") or event.get("epoch") != self.broker.epoch:
            return False
        try:
            after = datetime.fromisoformat(run.get("live_after") or run["authorized_at"])
            source = datetime.fromisoformat(event["source_at"])
            receipt = datetime.fromisoformat(event["received_at"])
            return (
                source > after
                and receipt > after
                and source.replace(second=0, microsecond=0) == at.replace(second=0, microsecond=0)
                and evaluate(event, at)["reason"] == "fresh"
                and self._fx_session(run).tradable(at)
            )
        except (KeyError, TypeError, ValueError):
            return False

    def _fx_evaluate_broker_reference(self, run):
        if run.get("entries"):
            return
        runtime = self.runtime.get(run["id"], {})
        event = runtime.get("pending_tick")
        at = self._fx_now()
        if runtime.get("pending_authorization") != run.get(
            "authorization_id"
        ) or not self._fx_broker_tick_current(run, event, at):
            runtime.pop("pending_tick", None)
            return
        source = run["binding"]["execution_plan"]["signal_source"]
        reference = self._fx_broker_reference(run, at)
        price = number(event["price"] if source == "MIDPOINT" else event[source.lower()])
        progress = {
            "source": source,
            "price": str(price),
            "observed_at": event["source_at"],
            "reference_candle": reference["candle"] if reference else None,
            "reference_high": reference["high"] if reference else None,
            "reference_revision": reference["revision"] if reference else None,
            "comparison": "gt",
            "above_high": price > number(reference["high"]) if reference else None,
        }
        runtime["signal_progress"] = progress
        runtime["last_result"] = {
            "values": {node["id"]: progress["above_high"] for node in runtime["graph"].ordered}
        }
        if (
            not reference
            or not progress["above_high"]
            or not self._fx_feed_health(run["conid"], run, at)["execution_fresh"]
        ):
            return
        trigger = {
            "candle": reference["candle"],
            "high": reference["high"],
            "price": str(price),
            "triggered_at": event["source_at"],
            "expires_at": reference["expires_at"],
            "reference_revision": reference["revision"],
            "reference_request": reference["request"],
            "epoch": self.broker.epoch,
            "tick": event,
            "authorization_id": run["authorization_id"],
            "authorized_after": run.get("live_after") or run["authorized_at"],
        }
        capture = self.store.capture([{"type": "broker_reference", **reference}, event])
        self._fx_enter(run, trigger, capture)

    def _fx_broker_trigger_current(self, run, trigger):
        at = self._fx_now()
        reference = self._fx_broker_reference(run, at)
        if (
            not reference
            or trigger.get("authorization_id") != run.get("authorization_id")
            or trigger.get("reference_revision") != reference["revision"]
            or trigger.get("reference_request") != reference["request"]
            or trigger.get("epoch") != self.broker.epoch
        ):
            return False
        tick = trigger.get("tick")
        if not self._fx_broker_tick_current(run, tick, at):
            return False
        source = run["binding"]["execution_plan"]["signal_source"]
        current = self._fx_observation_value(
            run["conid"], "fx_midpoint" if source == "MIDPOINT" else "fx_bidask"
        )
        return self._fx_feed_health(run["conid"], run, at)["execution_fresh"] and number(
            current["price"] if source == "MIDPOINT" else current[source.lower()]
        ) > number(reference["high"])
