"""Serialized, acknowledgement-driven protection repair for reconciled quantities."""

import json
import time
import uuid
from decimal import Decimal

from .graph import number
from .store import now

TERMINAL = {"Filled", "Cancelled", "ApiCancelled", "Rejected"}
ACTIVE = {"Submitted", "PreSubmitted"}


def order_ids(order):
    base, payload = order["broker_id"], order["payload"]
    if payload.get("purpose", "entry") != "entry":
        return {base}
    return {base, base + 2} | ({base + 1} if payload.get("target") else set())


class ProtectionController:
    def _flat_sell_issues(self, owned):
        """A flat position cannot release capacity while a sell outcome is unknown."""
        issues = []
        for entry in self.store.orders():
            if entry["payload"].get("purpose", "entry") != "entry":
                continue
            position = owned.get(entry["run_id"])
            if position and position["quantity"] != 0:
                continue
            if entry["state"] not in {"filled", "cancelled", "rejected"}:
                continue
            related = [
                o for o in self.store.orders() if o["payload"].get("entry_id") == entry["id"]
            ]
            ids = (order_ids(entry) - {entry["broker_id"]}) | {o["broker_id"] for o in related}
            for broker_id in ids:
                observed = self.broker_orders.get(broker_id) or self.store.get(
                    "broker_order", str(broker_id)
                )
                if not observed or observed.get("status") not in TERMINAL:
                    issues.append("A flat position has an active or unconfirmed sell order.")
                    if observed and observed.get("status") in ACTIVE:
                        self._cancel_known_sell(broker_id)
        return issues

    def _reconcile_cancellations(self):
        for request in self.store.list("cancel_request"):
            observed = self.broker_orders.get(request["broker_id"])
            if not observed:
                continue  # Absence is not proof that a cancellation completed.
            if observed.get("status") in TERMINAL:
                request["state"] = "confirmed"
            elif (
                request["state"] == "pending"
                and observed.get("status") in ACTIVE
                and request.get("epoch") != self.broker.epoch
            ):
                # Cancellation is idempotent. Retry only after the new session
                # positively identifies the still-working order; never replace it.
                request["state"] = "queued"
                self.store.event("order.cancel.retry", {"broker_id": request["broker_id"]})
            self.store.put("cancel_request", str(request["broker_id"]), request)
        self._flush_cancellations()

    def _fill_agreement_issues(self):
        with self.store.connect() as db:
            events = [json.loads(row[0]) for row in db.execute("SELECT payload FROM executions")]
        corrected = {}
        for event in events:
            parts = event["execution_id"].rsplit(".", 1)
            group, revision = (
                (parts[0], int(parts[1]))
                if len(parts) == 2 and parts[1].isdigit()
                else (event["execution_id"], 0)
            )
            if group not in corrected or revision > corrected[group][0]:
                corrected[group] = revision, event
        totals = {}
        for _, event in corrected.values():
            totals[event["broker_id"]] = totals.get(event["broker_id"], Decimal(0)) + number(
                event["quantity"]
            )
        issues = []
        for order in self.store.orders():
            for broker_id in order_ids(order):
                observation = (
                    self.broker_orders.get(broker_id)
                    or self.store.get("broker_order", str(broker_id))
                    or {}
                )
                filled = observation.get("filled")
                if (
                    filled is None
                    and broker_id == order["broker_id"]
                    and order["state"] == "filled"
                    and order["payload"].get("purpose", "entry") == "entry"
                ):
                    filled = order["payload"]["quantity"]
                if filled is not None and number(filled) != totals.get(broker_id, Decimal(0)):
                    issues.append("Broker filled quantities and durable executions disagree.")
        return issues

    def _valid_protection(self, position, entry):
        candidates = [(entry["broker_id"] + 2, entry, entry["state"] == "filled")]
        for order in self.store.orders():
            if (
                order["payload"].get("purpose") == "protection"
                and order["payload"].get("entry_id") == entry["id"]
            ):
                candidates.append((order["broker_id"], order, True))
        for broker_id, intent, activated in candidates:
            p = self.broker_orders.get(broker_id, {})
            if (
                activated
                and p.get("status") in ACTIVE
                and p.get("client_id") == self.broker.client_id
                and p.get("own_account") is True
                and p.get("reference") == "oms-" + intent["id"]
                and p.get("conid") == position["conid"]
                and p.get("order_type") == "STP"
                and p.get("action") == "SELL"
                and number(p.get("quantity", 0)) - number(p.get("filled", 0))
                == position["quantity"]
                and p.get("tif") == "GTC"
                and p.get("oca_type") == 2
                and p.get("oca_group") == "oms-" + entry["id"]
                and number(p.get("stop", 0)) == number(entry["payload"]["stop"])
            ):
                return True
        return False

    def _repair_protection(self, position, entry):
        if not self.position_agreement or not self.connected or not self.attested:
            return
        if (
            position["quantity"] != position["quantity"].to_integral_value()
            or not 0 < position["quantity"] <= 10
        ):
            return
        if entry["state"] in {"working", "dispatching"}:
            self.cancel_entry(entry["id"])
            return
        if entry["state"] not in {"filled", "cancelled", "rejected"}:
            return
        related = [o for o in self.store.orders() if o["payload"].get("entry_id") == entry["id"]]
        if any(
            o["state"] in {"reserved", "dispatching", "unknown", "cancel_pending"} for o in related
        ):
            return
        # A missing leg is not proof of a cancellation. Wait for positive terminal
        # observations, including after a restart; never replace an uncertain order.
        sell_ids = (order_ids(entry) - {entry["broker_id"]}) | {o["broker_id"] for o in related}
        waiting = False
        for broker_id in sell_ids:
            observed = self.broker_orders.get(broker_id) or self.store.get(
                "broker_order", str(broker_id)
            )
            if not observed:
                waiting = True
                continue
            if observed.get("status") not in TERMINAL:
                waiting = True
                if observed.get("status") in ACTIVE:
                    self._cancel_known_sell(broker_id)
        if waiting:
            return
        identity = uuid.uuid4().hex
        payload = {
            "purpose": "protection",
            "entry_id": entry["id"],
            "conid": position["conid"],
            "symbol": position["symbol"],
            "quantity": int(position["quantity"]),
            "stop": entry["payload"]["stop"],
        }
        self.store.event(
            "protection.repair.risk_checked",
            {
                "run_id": position["run_id"],
                "quantity": payload["quantity"],
                "position_agreement": True,
                "prior_sell_orders_terminal": True,
            },
        )
        intent = self.store.reserve_order(identity, payload, position["run_id"], self.next_id)
        self.store.mark_dispatch(identity)
        self.store.put(
            "protection_repair",
            entry["id"],
            {"state": "dispatching", "intent_id": identity, "timestamp": now()},
        )
        try:
            self.broker.submit_protection({**payload, **intent})
        except Exception:
            self.store.transition(
                identity, "unknown", {"reason": "protection_dispatch_interrupted"}
            )
            self.incident(
                "protection_uncertain",
                "Protection dispatch is uncertain. Inspect Gateway; do not resend.",
            )
        self.reconciled = False
        self.next_reconcile = time.monotonic() + 1

    def _cancel_known_sell(self, broker_id):
        self._queue_cancel(broker_id, "protection_or_exit")

    def _queue_cancel(self, broker_id, purpose):
        pending = self.store.get("cancel_request", str(broker_id))
        if pending:
            return
        # The durable cancellation record prevents a restart from inventing proof
        # that the request completed. Broker acknowledgements are still required.
        self.store.put(
            "cancel_request",
            str(broker_id),
            {"broker_id": broker_id, "timestamp": now(), "state": "queued"},
        )
        self.store.event("order.cancel.requested", {"broker_id": broker_id, "purpose": purpose})
        self._flush_cancellations()

    def _flush_cancellations(self):
        if not self.connected or not self.attested:
            return
        for request in self.store.list("cancel_request"):
            if request["state"] != "queued":
                continue
            broker_id = request["broker_id"]
            request["state"] = "pending"
            request["epoch"] = self.broker.epoch
            self.store.put("cancel_request", str(broker_id), request)
            try:
                self.broker.cancel(broker_id)
            except Exception:
                self.incident(
                    "cancel_uncertain",
                    "Cancellation is unconfirmed; reconcile before replacing orders.",
                )

    def _identity_issues(self):
        issues = []
        orders = self.store.orders()
        known = {i for order in orders for i in order_ids(order)}
        for key, observed in self.broker_orders.items():
            if key not in known:
                if observed.get("status") not in TERMINAL:
                    issues.append("Unexpected working orders are present.")
                continue
            intent = next(o for o in orders if key in order_ids(o))
            payload = intent["payload"]
            if observed.get("order_type") is None:
                issues.append("Order details are incomplete.")
                continue
            valid = (
                observed.get("client_id") == self.broker.client_id
                and observed.get("own_account") is True
                and observed.get("reference") == "oms-" + intent["id"]
                and observed.get("conid") == payload["conid"]
            )
            prior = self.store.get("broker_order", str(key)) or {}
            if prior.get("permanent_id") and observed.get("permanent_id"):
                valid = valid and prior["permanent_id"] == observed["permanent_id"]
            if key == intent["broker_id"]:
                purpose = payload.get("purpose", "entry")
                expected_type = "STP" if purpose == "protection" else "LMT"
                expected_action = "BUY" if purpose == "entry" else "SELL"
                valid = (
                    valid
                    and observed.get("order_type") == expected_type
                    and observed.get("action") == expected_action
                )
                valid = (
                    valid
                    and Decimal(0) < number(observed.get("quantity", 0)) <= payload["quantity"]
                )
                price = "stop" if purpose == "protection" else "limit"
                valid = valid and number(observed.get(price) or 0) == number(payload[price])
                if purpose == "entry":
                    valid = (
                        valid
                        and number(observed.get("quantity", 0)) == payload["quantity"]
                        and observed.get("tif") == "GTD"
                        and observed.get("parent_id", 0) == 0
                    )
                if purpose != "entry":
                    valid = (
                        valid
                        and observed.get("parent_id", 0) == 0
                        and observed.get("oca_type") == 2
                        and observed.get("oca_group") == "oms-" + payload["entry_id"]
                        and observed.get("tif") == ("GTC" if purpose == "protection" else "DAY")
                    )
            else:
                stop = key == intent["broker_id"] + 2
                valid = (
                    valid
                    and observed.get("action") == "SELL"
                    and observed.get("order_type") == ("STP" if stop else "LMT")
                    and observed.get("parent_id") == intent["broker_id"]
                    and observed.get("tif") == "GTC"
                    and observed.get("oca_type") == 2
                    and observed.get("oca_group") == "oms-" + intent["id"]
                    and Decimal(0) < number(observed.get("quantity", 0)) <= payload["quantity"]
                    and number(observed.get("stop" if stop else "limit") or 0)
                    == number(payload["stop" if stop else "target"])
                )
            if not valid:
                issues.append("Broker order identity or payload differs from the durable intent.")
        for order in orders:
            if (
                order["state"] in {"working", "cancel_pending"}
                and order["broker_id"] not in self.broker_orders
            ):
                self.store.transition(
                    order["id"], "unknown", {"reason": "missing_from_broker_snapshot"}
                )
                issues.append("A locally working order is absent from the broker snapshot.")
        return issues
