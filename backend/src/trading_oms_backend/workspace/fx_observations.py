"""FX observation validity, signed freshness and bounded live clock alignment."""

from collections import deque
from datetime import UTC, datetime

from .graph import number

FRESH_SECONDS = 15
CLOCK_BOUND_SECONDS = 5
PENDING_LIMIT = 4096


def evaluate(value, evaluated_at):
    """No mutation: timing must never become permanent structural invalidity."""
    ages = {}
    for name, key in (("source", "source_at"), ("receipt", "received_at")):
        try:
            ages[name] = (evaluated_at - datetime.fromisoformat(value[key])).total_seconds()
        except (KeyError, ValueError, TypeError):
            ages[name] = None
    valid = bool(value.get("structural_valid", value.get("valid", False)))
    if not value:
        reason = "missing"
    elif not valid:
        reason = "invalid"
    elif value.get("timing_fault"):
        reason = value["timing_fault"]
    elif any(v is None for v in ages.values()):
        reason = "malformed_timestamp"
    elif any(v < -CLOCK_BOUND_SECONDS for v in ages.values()):
        reason = "clock_fault"
    elif any(v > FRESH_SECONDS for v in ages.values()):
        reason = "stale"
    elif any(v < 0 for v in ages.values()) or value.get("pending_alignment"):
        reason = "clock_alignment"
    else:
        reason = "fresh"
    return {"structural_valid": valid, "fresh": reason == "fresh", "reason": reason, **ages}


class FXObservations:
    def _fx_observation_value(self, conid, kind):
        cache = self._fx_cache(conid)
        value = cache.get(kind, {})
        if not value:
            value = next(
                (v for v in cache.get("pending_observations", ()) if v["type"] == kind), {}
            )
        return value

    def _fx_quote_evaluation(self, conid, evaluated_at=None):
        result = evaluate(
            self._fx_observation_value(conid, "fx_bidask"), evaluated_at or self._fx_now()
        )
        state = self._fx_cache(conid)["feeds"].get("fx_bidask", {})
        if state.get("epoch") != self.broker.epoch or state.get("status") != "healthy":
            result.update(fresh=False, reason="stream_unavailable")
        return result

    def _fx_timing_record(self, conid, kind, reason, value, evaluated_at):
        cache = self._fx_cache(conid)
        diagnostics = cache.setdefault(
            "timing_diagnostics", {"streams": {}, "transitions": deque(maxlen=32)}
        )
        stream = diagnostics["streams"].setdefault(kind, {"counts": {}, "reason": None})
        counts = stream["counts"]
        counts[reason] = min(counts.get(reason, 0) + 1, 2147483647)
        try:
            offset = (
                datetime.fromisoformat(value["source_at"])
                - datetime.fromisoformat(value["received_at"])
            ).total_seconds()
        except (KeyError, ValueError, TypeError):
            offset = None
        stream.update(epoch=self.broker.epoch, arrival_offset_seconds=offset)
        if stream["reason"] != reason:
            transition = {
                "kind": kind,
                "reason": reason,
                "at": evaluated_at.isoformat(),
                "epoch": self.broker.epoch,
                "arrival_offset_seconds": offset,
            }
            diagnostics["transitions"].append(transition)
            stream["reason"] = reason
            # At most one transition record per stream per minute, never one per quote.
            last = stream.get("journal_at")
            if reason != "accepted" and (
                last is None or (evaluated_at - last).total_seconds() >= 60
            ):
                self.store.event("fx.timing.transition", {"conid": conid, **transition})
                stream["journal_at"] = evaluated_at

    def _fx_break_continuity(self, conid, kind):
        for run in self.store.list("run"):
            if (
                self._fx_run(run)
                and run["conid"] == conid
                and (
                    kind == "fx_bidask"
                    or run["binding"]["execution_plan"]["signal_source"] == "MIDPOINT"
                )
            ):
                self.runtime.pop(run["id"], None)

    def _fx_accept_observation(self, event, evaluated_at):
        conid, kind = event["conid"], event["type"]
        cache = self._fx_cache(conid)
        state = cache["feeds"][kind]
        previous = cache.get("processed", {}).get(kind)
        if previous and previous[2] > event["timestamp"]:
            self._fx_timing_record(conid, kind, "out_of_order", event, evaluated_at)
            return
        signature = tuple(
            event.get(k) for k in ("epoch", "request", "timestamp", "price", "bid", "ask", "valid")
        )
        if cache.setdefault("processed", {}).get(kind) == signature:
            # Corrected evidence can restore health without replaying an accepted observation.
            cache[kind] = {**event, "pending_alignment": False}
            self._fx_timing_record(conid, kind, "duplicate", event, evaluated_at)
            return
        event = {**event, "pending_alignment": False}
        health = evaluate(event, evaluated_at)
        cache[kind] = event
        if not health["fresh"]:
            self._fx_timing_record(conid, kind, health["reason"], event, evaluated_at)
            self._fx_break_continuity(conid, kind)
            return
        cache["processed"][kind] = signature
        state.update(status="healthy", attempts=0)
        self._fx_timing_record(conid, kind, "accepted", event, evaluated_at)
        self._fx_process_observation(event, evaluated_at)

    def _fx_stage_observation(self, event):
        conid, kind = event["conid"], event["type"]
        cache = self._fx_cache(conid)
        state = cache["feeds"][kind]
        at = self._fx_now()
        self._fx_drain_observations(at)
        try:
            stamp = datetime.fromtimestamp(float(event["timestamp"]), UTC)
            receipt = event.get("received_at") or at.isoformat()
            receipt_time = datetime.fromisoformat(receipt)
            if receipt_time.tzinfo is None:
                raise ValueError("Timestamp timezone missing")
            valid = bool(event.get("valid", True)) and (
                0 < number(event["bid"]) <= number(event["ask"])
                if kind == "fx_bidask"
                else number(event["price"]) > 0
            )
            value = {
                **event,
                "timestamp": stamp.timestamp(),
                "received_at": receipt,
                "source_at": stamp.isoformat(),
                "valid": valid,
                "structural_valid": valid,
            }
        except (ValueError, TypeError, KeyError, OverflowError, OSError):
            value = {**event, "valid": False, "structural_valid": False}
            valid = False
        health = evaluate(value, at)
        if not valid or health["reason"] == "clock_fault":
            if valid:
                value["timing_fault"] = "clock_fault"
            cache[kind] = value
            cache["pending_observations"] = deque(
                v for v in cache.get("pending_observations", ()) if v["type"] != kind
            )
            self._fx_timing_record(conid, kind, health["reason"], value, at)
            self._fx_data_failure(
                conid,
                state,
                "quote",
                "unknown",
                "FX timestamp exceeds the five-second clock-health bound."
                if valid
                else "Invalid or crossed FX observation broke continuity; review after recovery.",
                kind,
            )
            return
        previous = cache.get("processed", {}).get(kind)
        if previous and previous[2] > value["timestamp"]:
            self._fx_timing_record(conid, kind, "out_of_order", value, at)
            return
        state.update(status="healthy", attempts=0)
        if health["reason"] == "clock_alignment":
            pending = cache.setdefault("pending_observations", deque())
            # Preserve within-stream arrival order, including multiple prices in one broker second.
            latest = next((v for v in reversed(pending) if v["type"] == kind), None)
            if latest and latest["timestamp"] > value["timestamp"]:
                self._fx_timing_record(conid, kind, "out_of_order", value, at)
                return
            if len(pending) >= PENDING_LIMIT:
                pending.clear()
                cache[kind] = {**value, "timing_fault": "overflow"}
                self._fx_timing_record(conid, kind, "overflow", value, at)
                self._fx_data_failure(
                    conid,
                    state,
                    "quote",
                    "unknown",
                    "FX clock-alignment buffer overflow; continuity requires recovery.",
                    kind,
                )
                return
            if latest and all(
                latest.get(k) == value.get(k) for k in ("timestamp", "price", "bid", "ask", "valid")
            ):
                self._fx_timing_record(conid, kind, "duplicate", value, at)
                return
            pending.append({**value, "pending_alignment": True})
            self._fx_timing_record(conid, kind, "clock_alignment", value, at)
            return
        self._fx_accept_observation(value, at)

    def _fx_drain_observations(self, evaluated_at=None):
        at = evaluated_at or self._fx_now()
        for conid, cache in getattr(self, "fx_data", {}).items():
            pending = cache.get("pending_observations")
            if not pending:
                continue
            cache["pending_observations"] = deque()
            for event in sorted(pending, key=lambda e: e["timestamp"]):
                state = cache["feeds"].get(event["type"], {})
                if (
                    conid not in self.data
                    or event.get("epoch") != self.broker.epoch
                    or state.get("epoch") != self.broker.epoch
                    or state.get("request") != event.get("request")
                    or state.get("status") in {"retired", "failed", "retry"}
                ):
                    self._fx_timing_record(conid, event["type"], "generation_discard", event, at)
                    continue
                health = evaluate({**event, "pending_alignment": False}, at)
                if health["reason"] == "clock_alignment":
                    cache["pending_observations"].append(event)
                else:
                    self._fx_accept_observation(event, at)
