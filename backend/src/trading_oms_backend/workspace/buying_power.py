"""Paper account buying-power allocations, not estimates of broker margin."""

import os
from decimal import Decimal

from .credit_policy import BUYING_POWER_POLICY
from .graph import number
from .store import Conflict


def allocated(active, reflected):
    return sum(
        (
            number(r.get("fee_reserve_usd", 0))
            if r.get("reservation_id") in reflected
            else number(r["buying_power_allocation"])
            if r.get("buying_power_allocation") is not None
            else number(r.get("notional", 0)) + number(r.get("fee_reserve_usd", 0))
            for r in active
        ),
        Decimal(0),
    )


def validate_capacity(reservation, active):
    snapshot = reservation["credit_snapshot"]
    amount = number(reservation["buying_power_allocation"])
    expected = number(reservation["notional"]) + number(reservation.get("fee_reserve_usd", 0))
    if amount != expected or amount <= 0 or reservation.get("funding_mode") != "broker_decision":
        raise Conflict("Buying-power allocation differs from the approved order value.")
    if number(snapshot["available"]) <= 0 or number(snapshot["excess"]) <= 0:
        raise Conflict("Broker account headroom is insufficient.")
    used = allocated(active, set(snapshot["reflected_reservations"]))
    if amount + used > number(snapshot["buying_power"]):
        raise Conflict("Concurrent entries exceed broker buying power after allocations.")


class BuyingPower:
    def _buying_power_assess(self, plan, valuation, exclude=None):
        if os.environ.get("OMS_DISABLE_PAPER_BUYING_POWER_ARM") == "1":
            raise Conflict("New paper buying-power entries are disabled by the rollback setting.")
        snapshot = self._credit_account(buying_power=True)
        active = [
            {**r, "reservation_id": key}
            for key, r in self._active_funding_reservations()
            if r.get("run_id") != exclude
        ]
        allocation = number(valuation["notional"]) + number(valuation.get("fee_reserve_usd", 0))
        result = {
            **valuation,
            "funding_policy": BUYING_POWER_POLICY,
            "funding_mode": "broker_decision",
            "credit_status": "ready",
            "credit_keys": [],
            "credit_snapshot": snapshot,
            "funding_revision": snapshot["revision"],
            "buying_power_allocation": str(allocation),
            "buying_power_allocation_native": str(allocation / number(snapshot["capacity_rate"])),
            "allocation_currency": snapshot["base_currency"],
            "funding_snapshot": {},
            "currency_reserves": {},
            "projected_currency_debits": dict(valuation.get("currency_reserves", {})),
            "checked_at": snapshot["checked_at"],
        }
        validate_capacity(result, active)
        return result

    def _active_funding_reservations(self):
        import json

        with self.store.connect() as db:
            return [
                (key, json.loads(raw))
                for key, raw in db.execute(
                    "SELECT id,payload FROM documents WHERE kind='reservation'"
                )
                if json.loads(raw).get("active")
            ]

    def _buying_power_reflected(self):
        proof = self.reconciliation_evidence or {}
        started = proof.get("started_at", "")
        if (
            not proof.get("ready")
            or not started
            or proof.get("instance") != self.process_identity
            or proof.get("epoch") != self.broker.epoch
        ):
            return []
        reflected = []
        from .protection import order_ids

        for order in self.store.orders():
            if order["state"] not in {
                "working",
                "partially_filled",
                "filled",
                "cancelled",
                "rejected",
            }:
                continue
            with self.store.connect() as db:
                dispatched = db.execute(
                    "SELECT timestamp FROM events WHERE type='order.dispatch.started' "
                    "AND json_extract(payload,'$.id')=? ORDER BY sequence DESC LIMIT 1",
                    (order["id"],),
                ).fetchone()
            if not dispatched or dispatched[0] >= started:
                continue
            observations = [self.broker_orders.get(k, {}) for k in order_ids(order)]
            if observations and all(
                o.get("own_account") is True
                and o.get("status")
                in {
                    "Submitted",
                    "PreSubmitted",
                    "Filled",
                    "Cancelled",
                    "ApiCancelled",
                    "Rejected",
                    "Inactive",
                }
                and not o.get("status_conflict")
                and o.get("terminal_observed_at", "") < started
                for o in observations
            ):
                reflected.append(order["id"])
        return reflected
