"""One current signal outcome per run; transitions remain in the append-only journal."""

from .graph import digest, number
from .store import now


class SignalOutcomes:
    def _signal_detect(self, run, trigger, capture):
        identity = digest(
            {
                "run": run["id"],
                "authorization": run.get("authorization_id"),
                "candle": trigger.get("candle", trigger.get("triggered_at")),
            }
        )
        with self.store.transaction() as db:
            previous = self.store.read(db, "signal_outcome", run["id"])
            if previous and previous["id"] == identity:
                return previous
            record = {
                "id": identity,
                "run_id": run["id"],
                "authorization_id": run.get("authorization_id"),
                "binding_hash": (run.get("binding") or {}).get("hash"),
                "trigger": trigger,
                "capture": capture,
                "state": "detected",
                "detail": "Qualifying live signal detected.",
                "updated_at": now(),
            }
            self.store.write(db, "signal_outcome", run["id"], record)
            self.store.append(db, "signal.detected", record)
        return record

    def _signal_outcome(self, run, state, detail, **evidence):
        with self.store.transaction() as db:
            record = self.store.read(db, "signal_outcome", run["id"])
            if not record or record.get("authorization_id") != run.get("authorization_id"):
                return
            if record.get("order_id") and not evidence.get("order_id"):
                return  # A replay cannot overwrite a submitted order's lifecycle.
            changes = {"state": state, "detail": detail, **evidence}
            if all(record.get(k) == v for k, v in changes.items()):
                return
            record.update(**changes, updated_at=now())
            self.store.write(db, "signal_outcome", run["id"], record)
            self.store.append(db, "signal.outcome", record)
        self._overview_cache = None

    def _signal_maintain(self):
        orders = {o["id"]: o for o in self.store.orders()}
        for record in self.store.list("signal_outcome"):
            run = self.store.get("run", record["run_id"])
            if not run or run.get("authorization_id") != record.get("authorization_id"):
                continue
            order = orders.get(record.get("order_id"))
            if not order:
                if record["state"] in {"detected", "checking", "blocked"} and (
                    record["trigger"].get("expires_at", "9999") <= now() or not run.get("armed")
                ):
                    self._signal_outcome(
                        run,
                        "expired",
                        "Signal expired; waiting for a new eligible signal.",
                        last_reason=record["detail"],
                    )
                continue
            diagnostic = self.order_diagnostics(order)
            state = order["state"]
            fills = self._oca_executions(order)
            entry_ids = {order["broker_id"]}
            if order["payload"].get("leg_ids"):
                entry_ids = {
                    v for k, v in order["payload"]["leg_ids"].items() if k.endswith("_entry")
                }
            quantity = sum(
                (number(e["quantity"]) for e in fills if e["broker_id"] in entry_ids), number(0)
            )
            outcome = (
                "filled"
                if quantity >= number(order["payload"]["quantity"])
                else "partially_filled"
                if quantity > 0
                else "broker_rejected"
                if diagnostic.get("rejection") or state == "rejected"
                else "cancelled"
                if state == "cancelled"
                else "uncertain"
                if state == "unknown"
                else "checking"
                if state == "reserved"
                else "submitted"
            )
            self._signal_outcome(
                run,
                outcome,
                "Entry allocated; awaiting dispatch."
                if state == "reserved"
                else diagnostic["status_label"],
                order_id=order["id"],
                filled_quantity=str(quantity),
                rejection=diagnostic.get("rejection"),
            )

    def _signal_view(self, run):
        record = self.store.get("signal_outcome", run["id"])
        if record and record.get("authorization_id") == run.get("authorization_id"):
            return record
        return None

    def _signal_run_view(self, run):
        outcome = self._signal_view(run)
        progress = self.runtime.get(run["id"], {}).get("signal_progress")
        health = (
            self._run_feed_health(run)
            if run.get("conid")
            else {
                "execution_fresh": False,
                "execution_detail": "No bound instrument is available.",
            }
        )
        result = {
            **run,
            "signal_outcome": outcome,
            "signal_progress": progress,
            "required_inputs": {
                "ready": health["execution_fresh"],
                "detail": health["execution_detail"],
                "evaluated_at": health.get("evaluated_at", now()),
            },
        }
        if run.get("armed") and run.get("state") == "armed":
            state = outcome.get("state") if outcome else None
            result["display_state"] = (
                "Signal detected — checking account"
                if state == "checking"
                else "Entry blocked: " + outcome["detail"]
                if state == "blocked"
                else "Armed — waiting for inputs"
                if not health["execution_fresh"]
                else "Armed — waiting for breakout"
                if run.get("execution") in {"fx_breakout", "stock_breakout"}
                else "Armed — waiting for strategy signal"
            )
            result["blocking_reason"] = outcome["detail"] if state == "blocked" else None
        return result
