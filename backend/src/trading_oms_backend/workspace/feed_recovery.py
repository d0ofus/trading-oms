"""Single-owner component recovery. Data retries cannot authorize or place orders."""

import time
from datetime import UTC, datetime

from .broker_feeds import REASONS
from .data_scheduling import request_progress
from .store import Conflict, now

COMPONENTS = ("quote", "trade", "history")
DELAYS = {"transient": (15, 30, 60), "pacing": (60, 120, 240)}


class FeedRecovery:
    def init_feed_recovery(self):
        self.feed_components = {}
        self.history_units = {}
        self.history_request_units = {}
        self.history_contract_jobs = {}

    def components_for(self, conid):
        return self.feed_components.setdefault(
            conid, {kind: {"status": "pending", "attempts": 0} for kind in COMPONENTS}
        )

    def register_history_jobs(self, jobs):
        for job in jobs:
            self.history_units.setdefault(job, {"status": "queued", "attempts": 0})
            if self.history_units[job]["status"] == "retired":
                self.history_units[job].update(status="queued", attempts=0, request_state="queued")
            self.history_contract_jobs.setdefault(job[0], set()).add(job)

    def contract_history(self, conid):
        return [self.history_units[job] for job in self.history_contract_jobs.get(conid, ())]

    def history_complete(self, conid):
        return all(unit["status"] == "completed" for unit in self.contract_history(conid))

    def history_started(self, request, job, *, repair=False):
        self.register_history_jobs([job])
        unit = self.history_units[job]
        unit.update(status="pending", request=request, repair=repair or unit.get("repair", False))
        if unit["repair"]:
            self.repair_requests[request] = job[0]
        unit.pop("retry_at", None)
        self.history_request_units[request] = job

    def history_finished(self, request):
        job = self.history_request_units.pop(request, None)
        if job:
            self.history_units[job].update(status="completed", diagnostic=None, attempts=0)
            self.update_history_component(job[0])

    def update_history_component(self, conid):
        units = self.contract_history(conid)
        if not units:
            return
        state = self.components_for(conid)["history"]
        failed = [u for u in units if u["status"] == "failed"]
        state["progress"] = {
            key: sum(u["status"] == key for u in units)
            for key in ("queued", "pending", "completed", "failed")
        }
        state["status"] = (
            "failed"
            if failed
            else "pending"
            if any(u["status"] != "completed" for u in units)
            else "healthy"
        )
        if failed:
            state["diagnostic"] = failed[-1].get("diagnostic")
        elif state["status"] == "healthy":
            state["diagnostic"] = None
        if conid in self.data:
            self.data[conid]["history_failed"] = bool(failed)

    def fail_feed(self, event):
        conid = event.get("conid")
        if conid not in self.data:
            return
        component = {"bars": "trade"}.get(event.get("request_kind"), event.get("request_kind"))
        if component not in COMPONENTS:
            self.incident("market_data_failure", "Unclassified data request failed.", conid=conid)
            self._data_gap(conid, "Unclassified data request failed.")
            return
        reason = event.get("reason", "unknown")
        if reason not in REASONS:
            reason = "unknown"
        diagnostic = {
            "code": event["code"],
            "reason": reason,
            "detail": REASONS[reason],
            "request": event["request"],
            "request_kind": event.get("request_kind"),
            "generation": event.get("generation"),
            "parameters": event.get("parameters", {}),
            "at": now(),
        }
        state = self.components_for(conid)[component]
        target = state
        if component == "history":
            request = event["request"]
            job = self.history_request_units.pop(request, None)
            if job is None:
                parameters = event.get("parameters", {})
                job = (conid, parameters.get("end", ""), parameters.get("seconds", 60))
                self.register_history_jobs([job])
            target = self.history_units[job]
            self.history_pending.pop(request, None)
            self.repair_requests.pop(request, None)
        target.update(status="failed", diagnostic=diagnostic)
        attempts = target.get("attempts", 0)
        delays = DELAYS.get(reason)
        target["retry_at"] = (
            time.monotonic() + delays[attempts] if delays and attempts < 3 else None
        )
        target["automatic"] = target["retry_at"] is not None
        state.update(status="failed", diagnostic=diagnostic)
        if component == "history":
            self.update_history_component(conid)
        elif component == "quote":
            self.data[conid].update(live=False, subscription_status="rejected")
        regular_history = (
            component == "history"
            and event.get("parameters", {}).get("use_rth") is True
            and self.contracts.get(conid, {}).get("sec_type") == "STK"
        )
        self.incident(
            "regular_history_feed_failure" if regular_history else f"{component}_feed_failure",
            (
                f"IBKR {component} request returned code {event['code']}. "
                if event["code"]
                else "The historical request timed out locally. "
            )
            + diagnostic["detail"],
            conid=conid,
            diagnostic=diagnostic,
        )
        self._data_gap(
            conid,
            f"{component.title()} feed failed: {diagnostic['detail']}",
            regular_history_only=regular_history,
            routine_recovery=reason in DELAYS,
            history_only=component == "history",
        )
        self.store.event(
            "market.component.failed", {"conid": conid, "component": component, **diagnostic}
        )

    def feed_observed(self, event):
        conid, kind = event.get("conid"), event["type"]
        if conid not in self.feed_components:
            return
        component = "trade" if kind in {"tick", "realtime_bar"} else "quote"
        if kind not in {"tick", "realtime_bar", "quote"}:
            return
        try:
            age = (
                datetime.now(UTC) - datetime.fromisoformat(event.get("received_at", now()))
            ).total_seconds()
        except (ValueError, TypeError):
            return
        if not 0 <= age <= 15:
            return
        state = self.components_for(conid)[component]
        if state["status"] != "failed":
            state.update(status="healthy", diagnostic=None, attempts=0, observed_at=now())
            if component == "quote":
                self.data[conid]["subscription_status"] = "subscribed"

    def retry_feeds(self, conid, components, mutation_id, actor="local-operator"):
        if conid in getattr(self, "fx_data", {}):
            return self._fx_retry_feeds(conid, components, mutation_id, actor)
        chosen = sorted(set(components))
        fingerprint = {"conid": conid, "components": chosen}
        prior = self.store.get("feed_retry", mutation_id)
        if prior:
            if prior["request"] != fingerprint:
                raise Conflict("This retry identity belongs to a different request.")
            return prior["response"]
        if not chosen or any(c not in COMPONENTS for c in chosen) or conid not in self.data:
            raise Conflict("Select failed components of a subscribed contract.")
        if not self.connected:
            raise Conflict("Reconnect the paper data connection before retrying feeds.")
        states = self.components_for(conid)
        queued = []
        extended = getattr(self, "premarket_history", {}).get(conid, {})
        if "history" in chosen and extended.get("status") == "failed":
            extended.update(status="queued", attempts=0)
            queued.append("history")
        for component in chosen:
            targets = (
                self.contract_history(conid) if component == "history" else [states[component]]
            )
            for target in targets:
                if target["status"] != "failed" or target.get("manual_pending"):
                    continue
                # Manual retries respect an existing backoff/cooldown.
                target.update(
                    retry_at=max(
                        time.monotonic(), target.get("retry_at") or target.get("cooldown_until", 0)
                    ),
                    automatic=False,
                    manual_pending=True,
                )
                if component not in queued:
                    queued.append(component)
        response = {"conid": conid, "queued": queued, "armed": False}
        with self.store.transaction() as db:
            self.store.write(
                db, "feed_retry", mutation_id, {"request": fingerprint, "response": response}
            )
            self.store.append(
                db,
                "market.retry.requested",
                {**response, "actor": actor, "mutation_id": mutation_id},
            )
        return response

    def maintain_feed_retries(self, clock):
        if not self.connected:
            return
        for conid, states in self.feed_components.items():
            for component in ("quote", "trade"):
                state = states[component]
                if (
                    state["status"] != "failed"
                    or state.get("retry_at") is None
                    or clock < state["retry_at"]
                ):
                    continue
                if not self._data_contract_ready(conid, state, clock):
                    continue
                try:
                    if self.broker.retry_feed(conid, component) is False:
                        continue
                except Exception as exc:
                    self._data_request_fault(conid, state, exc, component + "_retry")
                    continue
                self._retry_started(conid, component, state, clock)
            for job in self.history_contract_jobs.get(conid, ()):
                unit = self.history_units[job]
                if (
                    unit["status"] == "failed"
                    and unit.get("retry_at") is not None
                    and clock >= unit["retry_at"]
                ):
                    self._retry_started(conid, "history", unit, clock)
                    unit["status"] = "queued"
                    if job not in self.history_jobs:
                        self.history_jobs.append(job)
            self.update_history_component(conid)

    def _retry_started(self, conid, component, state, clock):
        state["attempts"] = state.get("attempts", 0) + 1 if state.get("automatic") else 0
        state.update(
            status="pending", retry_at=None, manual_pending=False, cooldown_until=clock + 15
        )
        self.store.event(
            "market.retry.started",
            {
                "conid": conid,
                "component": component,
                "automatic": state.get("automatic", False),
                "attempt": state["attempts"],
            },
        )

    def feed_projection(self, conid):
        if conid in getattr(self, "fx_data", {}):
            return self._fx_feed_projection(conid)
        result = {}
        for component, state in self.feed_components.get(conid, {}).items():
            targets = (
                [u for u in self.contract_history(conid) if u["status"] == "failed"]
                if component == "history"
                else [state]
            )
            due = [t["retry_at"] for t in targets if t.get("retry_at") is not None]
            result[component] = {
                "source": "realtime_bars"
                if component == "trade"
                and self.contracts.get(conid, {}).get("sec_type")
                not in {None, "STK", "CRYPTO", "FUT"}
                else component,
                "status": state["status"],
                "diagnostic": state.get("diagnostic"),
                "progress": state.get("progress"),
                "retry_available": state["status"] == "failed"
                and not any(t.get("manual_pending") for t in targets),
                "retry_pending": bool(due),
                "retry_in_seconds": max(0, min(due) - time.monotonic()) if due else None,
                "attempts": max((t.get("attempts", 0) for t in targets), default=0),
                **request_progress(
                    self.contract_history(conid) if component == "history" else [state]
                ),
            }
        return result

    def forget_feeds(self, conid):
        for request, (_, owner) in tuple(self.history_pending.items()):
            if owner == conid:
                self.history_pending.pop(request)
                self.repair_requests.pop(request, None)
                self.history_request_units.pop(request, None)
        self.history_units = {j: u for j, u in self.history_units.items() if j[0] != conid}
        self.history_contract_jobs.pop(conid, None)
        self.feed_components.pop(conid, None)
