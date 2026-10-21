"""Operator lifecycle actions executed only by the engine owner."""

import time
from datetime import UTC, datetime, timedelta

from .graph import number
from .protection import TERMINAL, order_ids
from .store import Conflict, now


class OperatorActions:
    def incident_detail(self, identity):
        item = self.store.get("incident", identity)
        if not item:
            raise ValueError("Incident not found.")
        recovered = (
            self.connected
            and self.attested
            and self.reconciled
            and time.monotonic() - self.reconciled_at < 30
        )
        reason = "Connect, verify paper context and reconcile first."
        evidence = item.get("recovery", {})
        if identity == "engine_fault":
            recovered = (
                recovered
                and evidence.get("operation_retested", False)
                and time.monotonic() - self._fault_at >= 30
            )
            reason = (
                "Successfully repeat the failed operation, allow 30 healthy seconds, "
                "and reconcile. Historical faults without diagnostic context require "
                "a successful setup recheck."
            )
        elif identity == "broker_321":
            recovered = recovered and evidence.get("rechecked", False)
            reason = "Recheck the rejected operation and complete a fresh reconciliation."
        elif identity == "history_timeout":
            recovered = recovered and all(d.get("warm") for d in self.data.values())
            reason = "Wait for every subscribed history repair to complete."
        elif identity == "callback_overflow":
            recovered = recovered and not self.broker.overflow.is_set()
        elif identity == "clock_skew":
            recovered = recovered and self.clock_ok
        return {**item, "can_resolve": bool(recovered), "remediation": reason}

    def recheck_incident(self, identity):
        item = self.incident_detail(identity)
        if not self.connected or not self.attested:
            raise Conflict("Connect and verify the paper context before rechecking.")
        # Read-only requests only. Recheck never authorizes or resends an order.
        self.broker.heartbeat()
        self.begin_reconcile()
        item["recovery"] = {"requested_at": now(), "epoch": self.broker.epoch}
        self.store.put(
            "incident",
            identity,
            {k: v for k, v in item.items() if k not in {"can_resolve", "remediation"}},
        )
        self.store.event("incident.recheck.requested", {"id": identity})
        return self.incident_detail(identity)

    def _operation_succeeded(self, operation):
        item = self.store.get("incident", "engine_fault")
        if (
            item
            and not item.get("resolved")
            and not item.get("recovery", {}).get("operation_retested")
            and item.get("diagnostic", {}).get("operation") == operation
        ):
            item.setdefault("recovery", {})["operation_retested"] = True
            self.store.put("incident", "engine_fault", item)

    def _reconciliation_recovery(self):
        for item in self.store.list("incident"):
            evidence = item.get("recovery", {})
            if (
                evidence.get("rechecked")
                or not evidence.get("requested_at")
                or evidence.get("epoch") != self.broker.epoch
            ):
                continue
            if evidence["requested_at"] < item.get("last_seen", item["timestamp"]):
                continue
            evidence["rechecked"] = True
            if item["id"] == "engine_fault" and not item.get("diagnostic"):
                # Legacy faults had no context. Require a new process and a full
                # successful connection/reconciliation cycle, not just a click.
                evidence["operation_retested"] = self._legacy_fault_restart
            item["recovery"] = evidence
            self.store.put("incident", item["id"], item)

    def removal_preview(self, key):
        run = self.store.get("run", key)
        if not run:
            raise ValueError("Run not found.")
        orders = [o for o in self.store.orders() if o["run_id"] == key]
        position = self.owned().get(key, {}).get("quantity", 0)
        reason = None
        if number(run.get("position", 0)) or position:
            reason = "Close the owned position and reconcile before removing this run."
        elif any(o["state"] in {"unknown", "dispatching", "reserved"} for o in orders):
            reason = "An order outcome is uncertain. Resolve it before removing this run."
        elif orders and (not self.reconciled or time.monotonic() - self.reconciled_at >= 30):
            reason = "Fresh broker reconciliation is required before removal."
        return {
            "eligible": reason is None,
            "reason": reason,
            "run": run,
            "will_cancel": any(o["state"] in {"working", "cancel_pending"} for o in orders),
        }

    def remove_run(self, key):
        preview = self.removal_preview(key)
        if not preview["eligible"]:
            raise Conflict(preview["reason"])
        run = preview["run"]
        if run.get("archived"):
            return run
        self.disarm(key, "Run removal requested.")
        run = self.store.get("run", key)
        run["removal_pending"] = True
        self.store.put("run", key, run)
        self.store.event("run.removal.requested", {"run_id": key})
        self._finish_removals()
        return self.store.get("run", key)

    def _finish_removals(self):
        for run in self.store.list("run"):
            if not run.get("removal_pending"):
                continue
            key = run["id"]
            orders = [o for o in self.store.orders() if o["run_id"] == key]
            if not self.removal_preview(key)["eligible"]:
                continue
            if any(o["state"] not in {"filled", "cancelled", "rejected"} for o in orders):
                continue
            if any((self.store.get("reservation", o["id"]) or {}).get("active") for o in orders):
                continue
            if any(
                (self.broker_orders.get(i) or self.store.get("broker_order", str(i)) or {}).get(
                    "status"
                )
                not in TERMINAL
                for o in orders
                for i in order_ids(o)
            ):
                continue
            if self.store.get("exit_request", key):
                continue
            run.update(
                archived=True,
                archived_at=now(),
                removal_pending=False,
                state="completed",
                armed=False,
            )
            self.store.put("run", key, run)
            self.store.event("run.archived", {"run_id": key})
            self.runtime.pop(key, None)

    def _run_bounds(self, run, stamp=None):
        from .sessions import NY, execution_bounds

        stamp = stamp or datetime.now(UTC)
        return execution_bounds(
            run.get("session_date", stamp.astimezone(NY).date().isoformat()),
            run.get("trading_hours", "regular"),
            self.contracts.get(run["conid"]),
        )

    def _session_permission(self, run, stamp=None):
        stamp = stamp or datetime.now(UTC)
        bounds = self._run_bounds(run, stamp)
        return bool(
            bounds
            and bounds[0] <= stamp < bounds[1] - timedelta(minutes=15)
            and run.get("valid_from", "") <= stamp.isoformat() < run.get("expires_at", "")
        )
