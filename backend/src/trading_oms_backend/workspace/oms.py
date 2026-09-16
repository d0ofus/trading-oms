"""Shared durable broker-observation reducer for paper and deterministic replay."""

import json
import time
from datetime import UTC, datetime
from decimal import Decimal

from .graph import number
from .protection import order_ids
from .store import now


class OrderLedger:
    def _order_observation(self, event):
        if event.get("client_id", self.broker.client_id) != self.broker.client_id:
            return
        observation = {k: v for k, v in event.items() if k not in {"epoch", "sequence"}}
        old = self.store.get("broker_order", str(event["broker_id"])) or {}
        if (
            old.get("permanent_id")
            and event.get("permanent_id")
            and old["permanent_id"] != event["permanent_id"]
        ):
            self.incident(
                "order_identity_changed",
                "A broker order identity changed. Reconciliation is required.",
            )
            self.reconciled = False
            return
        if old.get("status") == "Filled" and event.get("status") != "Filled":
            return
        self.store.put("broker_order", str(event["broker_id"]), {**old, **observation})
        if {**old, **observation} != old:
            self.store.event("broker.order.observed", observation)
        for order in self.store.orders():
            base = order["broker_id"]
            if event["broker_id"] == base:
                status = event.get("status", "")
                states = {
                    "PendingSubmit": "dispatching",
                    "PreSubmitted": "working",
                    "Submitted": "working",
                    "PendingCancel": "cancel_pending",
                    "Cancelled": "cancelled",
                    "ApiCancelled": "cancelled",
                    "Filled": "filled",
                    "Inactive": "unknown",
                    "Rejected": "rejected",
                }
                state = states.get(status, "unknown")
                if order["state"] == "filled" and state != "filled":
                    return
                # A late fill after a cancel acknowledgement remains a fill.
                self.store.transition(order["id"], state, {"broker_status": status})
                if state in {"rejected", "unknown"}:
                    self.incident(
                        "order_uncertain",
                        "An order was rejected or has unknown state. Reconcile before continuing.",
                    )
                break

    def _execution(self, event):
        self._owned_cache = None
        event = {k: v for k, v in event.items() if k not in {"epoch", "sequence"}}
        if event["client_id"] != self.broker.client_id:
            return
        if event.get("own_account") is False:
            self.incident(
                "foreign_execution", "An execution belongs to an unexpected account context."
            )
            self.reconciled = False
            return
        if (
            event["side"] not in {"BOT", "SLD"}
            or number(event["quantity"]) < 0
            or number(event["price"]) <= 0
        ):
            self.incident(
                "invalid_execution", "A broker execution has invalid side, price or quantity."
            )
            self.reconciled = False
            return
        order = next(
            (o for o in self.store.orders() if event["broker_id"] in order_ids(o)),
            None,
        )
        if not order:
            self.incident(
                "unknown_execution", "An execution cannot be matched to a durable order intent."
            )
            return
        inconsistent = False
        with self.store.transaction() as db:
            old = db.execute(
                "SELECT payload FROM executions WHERE id=?", (event["execution_id"],)
            ).fetchone()
            if old:
                if json.loads(old[0]) != event:
                    inconsistent = True
            else:
                db.execute(
                    "INSERT INTO executions VALUES(?,?,?)",
                    (event["execution_id"], order["id"], json.dumps(event, sort_keys=True)),
                )
                self.store.append(db, "execution.received", {"run_id": order["run_id"], **event})
        if inconsistent:
            self.incident(
                "execution_changed", "A duplicate execution identifier has inconsistent contents."
            )
        elif not old and event["side"] == "BOT":
            run = self.store.get("run", order["run_id"])
            if run:
                run["last_fill_at"] = now()
                self.store.put("run", run["id"], run)
                if run["id"] in self.runtime:
                    self.runtime[run["id"]]["market"].last_entry = datetime.now(UTC)
        self.reconciled = False
        self.next_reconcile = time.monotonic() + 1

    def owned(self):
        if getattr(self, "_owned_cache", None) is not None:
            return self._owned_cache
        orders = {o["id"]: o for o in self.store.orders()}
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM executions ORDER BY rowid").fetchall()
        corrected = {}
        for row in rows:
            event = json.loads(row["payload"])
            parts = event["execution_id"].rsplit(".", 1)
            group, revision = (
                (parts[0], int(parts[1]))
                if len(parts) == 2 and parts[1].isdigit()
                else (event["execution_id"], 0)
            )
            if group not in corrected or revision > corrected[group][0]:
                corrected[group] = (revision, row["order_id"], event)
        positions = {}
        for _, order_id, event in corrected.values():
            order = orders[order_id]
            key = order["run_id"]
            position = positions.setdefault(
                key,
                {
                    "run_id": key,
                    "conid": event["conid"],
                    "symbol": event["symbol"],
                    "quantity": Decimal(0),
                    "cash": Decimal(0),
                    "entry_id": order["payload"].get("entry_id", order_id),
                },
            )
            sign = 1 if event["side"] == "BOT" else -1
            if sign == 1 and position["quantity"] == 0:
                position["entry_id"] = order["payload"].get("entry_id", order_id)
            quantity = number(event["quantity"])
            position["quantity"] += quantity * sign
            position["cash"] -= quantity * number(event["price"]) * sign
        self._owned_cache = positions
        return positions
