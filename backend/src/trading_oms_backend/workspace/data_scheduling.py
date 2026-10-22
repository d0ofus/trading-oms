"""Dependency-scoped, generation-aware data work; never authorizes or sends orders."""

import json
import time
from datetime import UTC, datetime, timedelta

from .dependencies import dependency, operation_active
from .graph import number
from .incidents import safe_fault
from .premarket import premarket


def request_progress(states):
    """Additive presentation of request work, distinct from execution freshness."""
    states = list(states)
    failed = next((s for s in states if s.get("status") in {"failed", "retry"}), None)
    queued = next((s for s in states if s.get("status") == "queued"), None)
    state = failed or queued or next(iter(states), {})
    status = (
        "failed"
        if failed
        else state.get("request_state", "queued")
        if queued
        else "complete"
        if states and all(s.get("status") == "completed" for s in states)
        else "receiving"
        if states and all(s.get("status") == "healthy" for s in states)
        else "requested"
        if any(s.get("status") == "pending" for s in states)
        else "queued"
    )
    due = state.get("eligible_clock")
    remaining = max(0, due - time.monotonic()) if due is not None else 0
    return {
        "request_state": status,
        "waiting_reason": state.get("waiting_reason") if queued or failed else None,
        "next_eligible_at": (datetime.now(UTC) + timedelta(seconds=remaining)).isoformat()
        if remaining > 0
        else None,
    }


class DataScheduling:
    def _data_dependencies(self, db=None):
        self._refresh_preparation_leases()
        if db is None:
            with self.store.connect() as connection:
                return self._data_dependencies(connection)

        def records(kind):
            return [
                json.loads(r[0])
                for r in db.execute("SELECT payload FROM documents WHERE kind=?", (kind,))
            ]

        runs = records("run")
        by_id = {r["id"]: r for r in runs}
        needed = set()
        priority = set()
        reasons = {}

        def require(conid, reason):
            reasons.setdefault(conid, []).append(reason)
            if reason.get("run_id"):
                needed.add(reason["run_id"])

        for conid, position in self.positions.items():
            # CASH pair positions can be the broker's editable virtual portfolio.
            # Real FX allocations are established by owned(), below. Unknown
            # security types remain conservative dependencies.
            sec_type = position.get("sec_type") or self.contracts.get(conid, {}).get("sec_type")
            if sec_type != "CASH" and number(position.get("quantity", 0)):
                priority.add(conid)
                require(
                    conid,
                    dependency(
                        "account_position",
                        "A reconciled security position needs this feed.",
                        quantity=position["quantity"],
                    ),
                )
        for run in runs:
            if run.get("armed") or run.get("authorization_status") == "temporarily_suspended":
                needed.add(run["id"])
                require(
                    run["conid"],
                    dependency(
                        "authorization", "The run has an active or suspended authorization.", run
                    ),
                )
            if number(run.get("position", 0)):
                needed.add(run["id"])
                priority.add(run["conid"])
                require(
                    run["conid"],
                    dependency(
                        "owned_position",
                        "The run owns an open position.",
                        run,
                        quantity=run["position"],
                    ),
                )
        for position in self.owned().values():
            if number(position.get("quantity", 0)):
                needed.add(position["run_id"])
                priority.add(position["conid"])
                require(
                    position["conid"],
                    dependency(
                        "executions",
                        "Confirmed executions establish remaining owned quantity.",
                        by_id.get(position["run_id"]),
                        quantity=str(position["quantity"]),
                    ),
                )
        for row in db.execute("SELECT run_id,state,payload FROM outbox"):
            order = {"run_id": row[0], "state": row[1], "payload": json.loads(row[2])}
            if order["state"] not in {"filled", "cancelled", "rejected"}:
                needed.add(order["run_id"])
                conid = order["payload"].get("conid") or by_id.get(order["run_id"], {}).get("conid")
                if conid:
                    priority.add(conid)
                require(
                    conid,
                    dependency(
                        "order",
                        "An order is working, cancelling or uncertain.",
                        by_id.get(order["run_id"]),
                        state=order["state"],
                        order_id=order["payload"].get("id"),
                    ),
                )
        for reservation in records("reservation"):
            if reservation.get("active"):
                needed.add(reservation.get("run_id"))
                if reservation.get("conid"):
                    priority.add(reservation["conid"])
                run = by_id.get(reservation.get("run_id"))
                conid = reservation.get("conid") or (run or {}).get("conid")
                if conid:
                    require(
                        conid,
                        dependency("reservation", "An active order reservation remains.", run),
                    )
        operations = db.execute(
            "SELECT kind,id,payload FROM documents WHERE kind IN "
            "('exit_request','incident_cancel','stock_protection','crypto_protection','fx_protection')"
        ).fetchall()
        for kind, key, payload in operations:
            operation = json.loads(payload)
            if operation_active(kind, operation):
                needed.add(operation.get("run_id", key))
                run = by_id.get(operation.get("run_id", key))
                conid = operation.get("conid") or (run or {}).get("conid")
                if conid:
                    require(
                        conid,
                        dependency(
                            kind,
                            "Outstanding " + kind.replace("_", " ") + " work requires this feed.",
                            run,
                        ),
                    )
                if operation.get("conid"):
                    priority.add(operation["conid"])
        active = {s["conid"] for s in records("subscription") if s.get("active")}
        active.update(self.data)
        prepared = getattr(self, "_preparation_dependencies", {})
        for conid, preparation in list(prepared.items()):
            if preparation.get("expires_clock", float("inf")) <= time.monotonic():
                prepared.pop(conid, None)
        for conid in prepared:
            require(
                conid,
                dependency(
                    "preparation",
                    "An open preparation is using this instrument.",
                    action="preparation",
                ),
            )
        active.update(prepared)
        required_runs = [r for r in runs if r["id"] in needed]
        active.update(r["conid"] for r in required_runs)
        priority.update(
            by_id[k]["conid"] for k in needed if k in by_id and not by_id[k].get("armed")
        )
        return {
            "contracts": active | priority,
            "priority": priority,
            "runs": required_runs,
            "reasons": reasons,
            "premarket": {
                r["conid"]
                for r in runs
                if premarket(r)
                and (r["id"] in needed or (not r.get("archived") and r["conid"] in active))
            }
            | {r["conid"] for r in self.active_preparations() if premarket(r)},
        }

    @staticmethod
    def _request_wait(state, reason, detail, due=None):
        state.update(request_state=reason, waiting_reason=detail, eligible_clock=due)

    def _data_contract_ready(self, conid, state, clock):
        if not self.connected:
            self._request_wait(state, "waiting_connection", "Waiting for broker connection.")
            return False
        contract = self.contracts.get(conid, {})
        ready = getattr(self.broker, "data_contract_ready", None)
        if ready(conid) if ready else bool(contract and contract.get("resolved") is not False):
            return True
        self._request_wait(state, "waiting_contract", "Waiting for contract resolution.")
        pending = getattr(self, "_data_resolving", {})
        self._data_resolving = pending
        prior = pending.get(conid, {})
        if prior.get("epoch") != self.broker.epoch or clock >= prior.get("after", 0):
            pending[conid] = {"epoch": self.broker.epoch, "after": clock + 30}
            try:
                self.broker.resolve(
                    conid=conid,
                    exchange=contract.get("routing_exchange", contract.get("exchange", "")),
                )
            except Exception as exc:
                self._data_request_fault(conid, state, exc, "contract_resolution")
        return False

    def _data_request_fault(self, conid, state, exc, scope):
        state.update(
            status="failed",
            request_state="failed",
            retry_at=None,
            eligible_clock=None,
            reason="unknown",
            waiting_reason="This data request failed to start; inspect its component diagnostics.",
            detail="This data request failed to start; inspect its component diagnostics.",
        )
        self.incident(
            "data_request_failure",
            "A contained data request failed to start. Other requests continue.",
            conid=conid,
            correlation_key=scope,
            diagnostic={**safe_fault(exc, "data_request:" + scope), "conid": conid},
        )

    def _retire_data_jobs(self, dependencies=None):
        deps = dependencies or self._data_dependencies()
        for job, state in self.history_units.items():
            if job[0] not in deps["contracts"] and state["status"] != "completed":
                self._retire_data_state(job[0], state)
        self.history_jobs = [j for j in self.history_jobs if j[0] in deps["contracts"]]
        for conid, state in getattr(self, "premarket_history", {}).items():
            if conid not in deps["premarket"] and state["status"] != "completed":
                self._retire_data_state(conid, state)
        for conid, cache in getattr(self, "fx_data", {}).items():
            if conid not in deps["contracts"]:
                cache.pop("pending_observations", None)
                cache.pop("processed", None)
                cache.pop("fx_bidask", None)
                cache.pop("fx_midpoint", None)
                cache.pop("display_live", None)
                for state in (*cache["sources"].values(), *cache["feeds"].values()):
                    if state["status"] != "retired" and (
                        state.get("persistent") or state["status"] != "completed"
                    ):
                        self._retire_data_state(conid, state)
        self._data_resolving = {
            c: s for c, s in getattr(self, "_data_resolving", {}).items() if c in deps["contracts"]
        }
        return deps

    def _retire_data_state(self, conid, state):
        if state["status"] == "retired":
            return
        request = state.pop("request", None)
        state.update(status="retired", retry_at=None, eligible_clock=None)
        if request is not None:
            self.history_pending.pop(request, None)
            self.history_request_units.pop(request, None)
            self.repair_requests.pop(request, None)
            if hasattr(self.broker, "cancel_feed"):
                try:
                    self.broker.cancel_feed(request)
                except Exception as exc:
                    self._data_request_fault(conid, state, exc, "retire")
        self.store.event("market.request.retired", {"conid": conid, "request": request})

    def _history_pending_count(self):
        return (
            len(self.history_pending)
            + sum(s["status"] == "pending" for s in getattr(self, "premarket_history", {}).values())
            + sum(
                s["status"] == "pending"
                for c in getattr(self, "fx_data", {}).values()
                for s in c["sources"].values()
            )
        )

    def _dispatch_history(self, clock):
        if not self.connected:
            return
        while self.history_request_times and clock - self.history_request_times[0] >= 600:
            self.history_request_times.popleft()
        jobs = []
        for job in self.history_jobs:
            self.register_history_jobs([job])
            jobs.append((job[0], "regular", job, self.history_units[job]))
        for conid, state in getattr(self, "premarket_history", {}).items():
            jobs.append((conid, "extended", None, state))
        for conid, cache in getattr(self, "fx_data", {}).items():
            if conid in self.data:
                jobs.extend(
                    (conid, "fx", source, state) for source, state in cache["sources"].items()
                )
        if not any(j[3]["status"] == "queued" for j in jobs):
            return
        priority = self._data_dependencies()["priority"]
        served = getattr(self, "_history_served", {})
        self._history_served = served
        jobs.sort(key=lambda j: (j[0] not in priority, served.get((j[0], j[1]), 0)))
        for conid, scope, key, state in jobs:
            if state["status"] != "queued":
                continue
            if not self._data_contract_ready(conid, state, clock):
                continue
            due = max(self.next_history, state.get("retry_at") or 0)
            if len(self.history_request_times) >= 55:
                due = max(due, self.history_request_times[0] + 600)
            if self._history_pending_count() >= 2 or clock < due:
                self._request_wait(
                    state,
                    "waiting_pacing",
                    "Waiting for shared history request capacity or pacing.",
                    due if due > clock else None,
                )
                continue
            try:
                if scope == "regular":
                    request = (
                        self.broker.history(*key, use_rth=False)
                        if self.legacy_extended_history(conid)
                        else self.broker.history(*key)
                    )
                else:
                    request = self.broker.history(
                        conid,
                        use_rth=False,
                        **(
                            {
                                "signal_source": key,
                                **({"keep_up_to_date": True} if state.get("persistent") else {}),
                            }
                            if scope == "fx"
                            else {}
                        ),
                    )
            except Exception as exc:
                self._data_request_fault(conid, state, exc, scope + "_history")
                if scope == "regular":
                    self.update_history_component(conid)
                continue
            state.update(
                status="pending",
                request=request,
                epoch=self.broker.epoch,
                started=clock,
                request_state="requested",
                waiting_reason=None,
                eligible_clock=None,
            )
            if scope == "regular":
                self.history_jobs.remove(key)
                self.history_started(request, key, repair=state.get("repair", False))
                self.history_pending[request] = (clock, conid)
            elif scope == "fx":
                state.update(received=0, invalid=False)
                if state.get("persistent"):
                    state.update(bars={}, bootstrap=False)
                    for run in self.store.list("run"):
                        if self._fx_uses_broker_candles(run) and run.get("conid") == conid:
                            self.runtime.get(run["id"], {}).pop("pending_tick", None)
            else:
                state["received"] = 0
            self.history_request_times.append(clock)
            self.next_history = clock + 2.1
            served[(conid, scope)] = clock
        self._history_served = {
            k: v for k, v in served.items() if any(j[0] == k[0] and j[1] == k[1] for j in jobs)
        }
