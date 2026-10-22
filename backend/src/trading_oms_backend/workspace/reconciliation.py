"""Staged broker snapshots, separate from the last verified operational view."""

import time

from .graph import number


class Reconciliation:
    def reconciliation_progress(self):
        expected = {
            "positions_end",
            "orders_end",
            "completed_orders_end",
            "executions_end",
            "account_end",
        }
        missing = sorted(expected - self.reconcile_parts) if self.reconcile_inflight else []
        return {
            "status": "checking" if missing else "ready" if self.reconciled else "waiting",
            "missing": missing,
            "detail": "Waiting for broker snapshot: " + ", ".join(missing)
            if missing
            else "Account snapshot complete."
            if self.reconciled
            else "Waiting for current account evidence.",
            "evidence_revision": getattr(self, "_evidence_revision", 0),
            "retries": getattr(self, "_reconciliation_retries", 0),
        }

    def _maintain_reconciliation(self, clock):
        if not self.reconcile_inflight or clock <= self.reconcile_deadline:
            return
        # No new uncorrelated request can overtake a missing completion marker.
        # Keep the transport, continuous position subscription and market feeds alive.
        self.reconciled = False
        missing = self.reconciliation_progress()["missing"]
        attempts = getattr(self, "_reconciliation_retries", 0) + 1
        self._reconciliation_retries = attempts
        self.reconcile_deadline = clock + min(120, 15 * 2 ** min(attempts, 3))
        retry = getattr(self.broker, "retry_reconciliation", None)
        if retry:
            retry(missing)
        if attempts == 1 or getattr(self, "_last_snapshot_missing", None) != missing:
            self.store.event(
                "reconciliation.waiting",
                {
                    "id": self._reconciliation_started["id"],
                    "missing": missing,
                    "transport_retained": True,
                    "automatic_retry": True,
                },
            )
        self._last_snapshot_missing = missing

    def invalidate_reconciliation(self):
        self.reconciled = False
        self._evidence_revision = getattr(self, "_evidence_revision", 0) + 1
        self.next_reconcile = min(getattr(self, "next_reconcile", 0), time.monotonic() + 1)

    def _stage_reconciliation(self):
        self._pending_snapshot = {
            "positions": {},
            "broker_orders": {},
            "facts": {},
            "currency_facts": {},
        }
        self._reconciliation_started["evidence_revision"] = getattr(self, "_evidence_revision", 0)
        self.broker.reconciliation_id = self._reconciliation_started["id"]
        if time.monotonic() - self.reconciled_at >= 30:
            self.reconciled = self.position_agreement = False

    def _snapshot_event_current(self, event):
        if event.get("epoch", self.broker.epoch) != self.broker.epoch:
            return False
        generation = event.get("reconciliation_id")
        if generation is not None and generation != (self._reconciliation_started or {}).get("id"):
            return False
        return True

    def _snapshot_account_fact(self, event):
        pending = getattr(self, "_pending_snapshot", None) if self.reconcile_inflight else None
        tag = event["tag"]
        previous = self.currency_facts.get((tag, event.get("currency", "USD")), {})
        if (
            self.reconciled
            and previous
            and (
                tag
                in {
                    "AvailableFunds",
                    "BuyingPower",
                    "ExcessLiquidity",
                    "EquityWithLoanValue",
                    "CashBalance",
                    "SettledCash",
                }
                and number(event["value"]) < number(previous["value"])
                or tag in {"GrossPositionValue", "InitMarginReq", "MaintMarginReq"}
                and number(event["value"]) > number(previous["value"])
            )
        ):
            # New adverse funding/exposure evidence cannot be hidden behind the
            # still-fresh old snapshot. Existing position protection stays known.
            self.invalidate_reconciliation()
        original = self.facts, self.currency_facts
        if pending is not None:
            self.facts, self.currency_facts = pending["facts"], pending["currency_facts"]
        try:
            if self.environment.crypto:
                self.facts[event["tag"]] = event["value"]
                self.pnl_currency = "USD"
            else:
                self._stock_fact(event)
        finally:
            if pending is not None:
                self.facts, self.currency_facts = original

    def _snapshot_position(self, event):
        pending = getattr(self, "_pending_snapshot", None) if self.reconcile_inflight else None
        previous = self.positions.get(event["conid"], {})
        if self.reconciled and (
            number(previous.get("quantity", 0)) != number(event["quantity"])
            or event.get("own_account") is not True
        ):
            self.invalidate_reconciliation()
            self.position_agreement = False
        (pending["positions"] if pending is not None else self.positions)[event["conid"]] = event

    def _snapshot_order(self, key, event):
        pending = getattr(self, "_pending_snapshot", None) if self.reconcile_inflight else None
        if pending is not None:
            pending["broker_orders"][key] = event

    def _publish_snapshot(self):
        pending = getattr(self, "_pending_snapshot", None)
        self._pending_snapshot = None
        if pending is None:
            return True  # Compatible direct/simulator reconciliation.
        started = self._reconciliation_started
        if started["epoch"] != self.broker.epoch or started["evidence_revision"] != getattr(
            self, "_evidence_revision", 0
        ):
            self.reconcile_inflight = False
            self.reconciled = self.position_agreement = False
            self.next_reconcile = time.monotonic()
            self.store.event(
                "reconciliation.superseded",
                {
                    "id": started["id"],
                    "reason": "State changed during snapshot; collect fresh evidence.",
                },
            )
            return False
        self.positions, self.broker_orders = pending["positions"], pending["broker_orders"]
        self.facts, self.currency_facts = pending["facts"], pending["currency_facts"]
        return True
