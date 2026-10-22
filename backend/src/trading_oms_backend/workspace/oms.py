"""Shared durable broker-observation reducer for paper and deterministic replay."""

import json
import time
from datetime import UTC, datetime
from decimal import Decimal

from .graph import number
from .oca import is_pair, pair_legs
from .order_status import CANCEL_REASONS, PENDING, STATES, project_status
from .protection import order_ids
from .rejections import safe_rejection
from .store import now


class OrderLedger:
    def invalidate_reconciliation(self):
        # Replay has no asynchronous snapshot; the live engine overrides this.
        self.reconciled = False

    def _initial_quantity_rejection(self, broker_id):
        order = next((o for o in self.store.orders() if o["broker_id"] == broker_id), None)
        observed = self.store.get("broker_order", str(broker_id)) or {}
        if (
            not order
            or order["state"] not in {"dispatching", "unknown", "cancel_pending", "rejected"}
            or observed.get("permanent_id")
            or observed.get("status") in {"Submitted", "PreSubmitted", "Filled"}
            or observed.get("status_conflict")
        ):
            return False
        with self.store.connect() as db:
            return not db.execute(
                "SELECT 1 FROM executions WHERE order_id=? LIMIT 1", (order["id"],)
            ).fetchone()

    def _record_quantity_rejection(self, broker_id):
        order = next(o for o in self.store.orders() if o["broker_id"] == broker_id)
        payload = order["payload"]
        if payload.get("execution") != "fx_breakout" or payload.get("purpose") != "entry":
            return
        evidence = {
            "conid": payload["conid"],
            "route": "IDEALPRO",
            "order_type": "MKT",
            "tif": "IOC",
            "code": 10318,
            "order_id": order["id"],
            "quantity": payload["quantity"],
        }
        key = str(payload["conid"]) + ":IDEALPRO:MKT:IOC"
        if self.store.get("quantity_restriction", key) != evidence:
            with self.store.transaction() as db:
                self.store.write(db, "quantity_restriction", key, evidence)
                self.store.append(db, "contract.quantity_rejection.observed", evidence)

    def _reconcile_quantity_rejections(self):
        """Correct only proven initial validation rejects after a complete fresh snapshot."""
        started = self._reconciliation_started or {}
        if (
            not self.attested
            or started.get("epoch") != self.broker.epoch
            or len(self.reconcile_parts) != 5
        ):
            return
        for order in self.store.orders():
            if (
                order["payload"].get("execution") != "fx_breakout"
                or order["payload"].get("purpose") != "entry"
                or order["state"] not in {"unknown", "dispatching", "cancel_pending", "rejected"}
            ):
                continue
            if (
                not self._initial_quantity_rejection(order["broker_id"])
                or order["broker_id"] in self.broker_orders
            ):
                continue
            with self.store.connect() as db:
                rejection = db.execute(
                    "SELECT sequence,timestamp FROM events WHERE type='broker.message' "
                    "AND timestamp>=? AND json_extract(payload,'$.request')=? "
                    "AND json_extract(payload,'$.code')=10318 ORDER BY sequence LIMIT 1",
                    (order["created_at"], order["broker_id"]),
                ).fetchone()
                dispatch = db.execute(
                    "SELECT sequence,timestamp FROM events WHERE type='order.dispatch.started' "
                    "AND json_extract(payload,'$.id')=? ORDER BY sequence LIMIT 1",
                    (order["id"],),
                ).fetchone()
                accepted = db.execute(
                    "SELECT 1 FROM events WHERE type='broker.order.observed' AND timestamp>=? "
                    "AND json_extract(payload,'$.broker_id')=? "
                    "AND (json_extract(payload,'$.status') "
                    "IN ('Submitted','PreSubmitted','Filled') "
                    "OR json_extract(payload,'$.permanent_id')>0) LIMIT 1",
                    (order["created_at"], order["broker_id"]),
                ).fetchone()
            if (
                not rejection
                or not dispatch
                or accepted
                or rejection[0] <= dispatch[0]
                or not 0
                <= (
                    datetime.fromisoformat(rejection[1]) - datetime.fromisoformat(dispatch[1])
                ).total_seconds()
                <= 30
                or started.get("started_at", "") <= rejection[1]
            ):
                continue
            proof = {
                "order_id": order["id"],
                "broker_id": order["broker_id"],
                "rejection_sequence": rejection[0],
                "dispatch_sequence": dispatch[0],
                "reconciliation_id": started["id"],
                "epoch": self.broker.epoch,
            }
            prior = self.store.get("quantity_rejection_reconciled", order["id"])
            if not prior:
                self.store.backup(self.store.directory / "backups")
                self._record_quantity_rejection(order["broker_id"])
                if order["state"] != "rejected":
                    self._order_observation(
                        {
                            "broker_id": order["broker_id"],
                            "client_id": self.broker.client_id,
                            "status": "Rejected",
                            "rejection_code": 10318,
                            "rejection": safe_rejection({"code": 10318}),
                        }
                    )
                with self.store.transaction() as db:
                    self.store.write(db, "quantity_rejection_reconciled", order["id"], proof)
                    self.store.append(db, "order.validation_rejection.reconciled", proof)
                    cancel = self.store.read(db, "cancel_request", str(order["broker_id"]))
                    if cancel:
                        self.store.write(
                            db,
                            "cancel_request",
                            str(order["broker_id"]),
                            {
                                **cancel,
                                "state": "confirmed",
                                "outcome": "initial_validation_rejected",
                            },
                        )
                    protection = self.store.read(db, "fx_protection", order["run_id"])
                    if protection and protection.get("state") == "awaiting_fill":
                        self.store.write(
                            db,
                            "fx_protection",
                            order["run_id"],
                            {
                                **protection,
                                "state": "closed",
                                "reason": "initial_validation_rejected",
                            },
                        )
                self.disarm(
                    order["run_id"],
                    "Broker rejected entry: 10318 - fractional quantity unsupported.",
                )

    def _order_failure(self, order, observed, state):
        """Persist semantic failure identity with its hold, independent of callback shape."""
        rejection = (
            safe_rejection(observed.get("rejection"))
            if observed.get("rejection_code") in {201, 10318}
            else None
        )
        failure = {"state": "rejected" if rejection else state, "rejection": rejection}
        key = f"{order['id']}:{observed['broker_id']}"
        with self.store.transaction() as db:
            previous = self.store.read(db, "order_failure", key)
            if (
                previous
                and previous["failure"] == failure
                and not previous.get("intervening_working")
            ):
                return
            context = {
                "order_id": order["id"],
                "run_id": order["run_id"],
                "broker_id": observed["broker_id"],
            }
            detail = (
                "Broker rejected an order. " + rejection["detail"]
                if rejection
                else "An order has unknown broker state. Reconcile before continuing."
            )
            item = self.incidents.raise_in(
                db,
                "order_uncertain",
                detail,
                self.process_identity,
                correlation_key=key,
                order_context=context,
                rejection=rejection,
                refinement=bool(previous) and not previous.get("intervening_working"),
                new_failure=bool(previous and previous.get("intervening_working")),
            )
            self.store.write(
                db, "order_failure", key, {"failure": failure, "episode_id": item["id"]}
            )
        self.invalidate_reconciliation()
        self._overview_cache = None

    def _order_failure_progress(self, order, observed):
        key = f"{order['id']}:{observed['broker_id']}"
        with self.store.transaction() as db:
            previous = self.store.read(db, "order_failure", key)
            if previous and not previous.get("intervening_working"):
                self.store.write(
                    db, "order_failure", key, {**previous, "intervening_working": True}
                )

    def _order_observation(self, event):
        if event.get("client_id", self.broker.client_id) != self.broker.client_id:
            return
        observation = {
            k: v for k, v in event.items() if k not in {"epoch", "sequence", "reconciliation_id"}
        }
        old = self.store.get("broker_order", str(event["broker_id"])) or {}
        projected, disposition = project_status(old, observation)
        from .fx_order_evidence import record

        record(self.store, event, projected)
        if projected.get("status") in {"Filled", "Cancelled", "ApiCancelled", "Rejected"} and (
            old.get("status") != projected.get("status")
            or old.get("filled") != projected.get("filled")
            or not old.get("terminal_observed_at")
        ):
            projected["terminal_observed_at"] = now()
        if getattr(self, "reconciled", False) and any(
            old.get(k) != projected.get(k)
            for k in (
                "status",
                "filled",
                "remaining",
                "own_account",
                "conid",
                "action",
                "quantity",
                "parent_id",
                "reference",
                "stop",
            )
        ):
            self.invalidate_reconciliation()
        if (
            old.get("permanent_id")
            and event.get("permanent_id")
            and old["permanent_id"] != event["permanent_id"]
        ):
            self.store.event(
                "broker.order.observed", {**observation, "disposition": "identity_conflict"}
            )
            self.incident(
                "order_identity_changed",
                "A broker order identity changed. Reconciliation is required.",
            )
            self.invalidate_reconciliation()
            projected = {**old, "status_conflict": True}
            self.store.put("broker_order", str(event["broker_id"]), projected)
            return projected
        self.store.put("broker_order", str(event["broker_id"]), projected)
        self.store.event("broker.order.observed", {**observation, "disposition": disposition})
        if disposition == "conflict":
            self.invalidate_reconciliation()
            self.incident(
                "order_status_conflict",
                "Broker status conflicts with a terminal order. "
                "Reconcile fresh order details and executions.",
            )
        for order in self.store.orders():
            base = order["broker_id"]
            if (
                event["broker_id"] in order_ids(order)
                and projected.get("status") in {"Submitted", "PreSubmitted"}
                and not projected.get("status_conflict")
                and not projected.get("rejection_code")
                and disposition == "applied"
            ):
                self._order_failure_progress(order, projected)
            if event["broker_id"] in order_ids(order) and (
                is_pair(order["payload"]) or event["broker_id"] != base
            ):
                leg_state = STATES.get(projected.get("status"), "unknown")
                if leg_state in {"unknown", "rejected"} or event.get("rejection_code") in {
                    201,
                    10318,
                }:
                    self._order_failure(order, projected, leg_state)
                return projected  # Protection/group state is derived from all legs and fills.
            if event["broker_id"] == base:
                status = projected.get("status", "")
                state = STATES.get(status, "unknown")
                cancellation = self.store.get("cancel_request", str(base)) or {}
                # The OMS cancellation intent stays latched even if a fresh broker
                # snapshot says working. Keep that actual broker status so reconnect
                # reconciliation can retry the cancellation in the new connection.
                if state in {"working", "dispatching"} and (
                    order["state"] == "cancel_pending"
                    or cancellation.get("state") in {"queued", "pending"}
                ):
                    state = "cancel_pending"
                if order["state"] == "filled" and state != "filled":
                    return projected
                # A late fill after a cancel acknowledgement remains a fill.
                if state != order["state"]:
                    self.store.transition(order["id"], state, {"broker_status": status})
                if state in {"rejected", "unknown"} or event.get("rejection_code") in {201, 10318}:
                    self._order_failure(order, projected, state)
                if (
                    order["payload"].get("execution") == "crypto_breakout"
                    and self._crypto_identity_status(order, projected) == "mismatch"
                ):
                    self.invalidate_reconciliation()
                    self.next_reconcile = time.monotonic() + 1
                    self.incident(
                        "order_identity_changed",
                        "Crypto broker order details differ from the durable paper intent. "
                        "Reconcile before continuing.",
                    )
                break
        return projected

    def order_diagnostics(self, order):
        observed = self.store.get("broker_order", str(order["broker_id"])) or {}
        cancellation = self.store.get("cancel_request", str(order["broker_id"])) or {}
        reason = cancellation.get("reason")
        state = order["state"]
        status = observed.get("status")
        pending = state == "dispatching" and status in PENDING
        label = (
            "Awaiting broker acknowledgment" if pending else state.replace("_", " ").capitalize()
        )
        if order["payload"].get("execution") == "crypto_breakout":
            identity = self._crypto_identity_status(order, observed)
        elif order["payload"].get("execution") == "fx_breakout":
            issues = self._fx_identity(order, observed)
            identity = (
                "verified"
                if not issues
                else "pending"
                if issues[0].startswith("Awaiting")
                else "mismatch"
            )
        else:
            identity = "not_evaluated"
        cancellation_detail = CANCEL_REASONS.get(reason)
        if cancellation and not cancellation_detail:
            cancellation_detail = "Application cancellation; historical reason unavailable"
        rejection = (
            safe_rejection(observed.get("rejection"))
            if observed.get("rejection_code") in {201, 10318}
            else None
        )
        if rejection:
            with self.store.connect() as db:
                fills = db.execute(
                    "SELECT 1 FROM executions WHERE order_id=? LIMIT 1", (order["id"],)
                ).fetchone()
            purpose = "entry" if order["payload"].get("purpose", "entry") == "entry" else "exit"
            if fills:
                outcome = "confirmed executions recorded"
            elif (
                self.reconciled
                and state in {"cancelled", "rejected"}
                and not observed.get("status_conflict")
            ):
                outcome = "no fill"
            else:
                outcome = "execution outcome awaiting reconciliation"
            label = f"Broker rejected {purpose} — {outcome}; final broker status: {status}"
            if rejection["code"] == 10318:
                label = f"Broker rejected: 10318 - fractional quantity unsupported; {outcome}."
        return {
            **self._order_diagnostic_evidence(order, observed),
            "broker_status": status,
            "acknowledgment_pending": pending,
            "status_label": label,
            "identity_status": identity,
            "status_conflict": bool(observed.get("status_conflict")),
            "cancellation_reason": reason,
            "cancellation_detail": cancellation_detail,
            "rejection": rejection,
        }

    def _order_diagnostic_evidence(self, order, observed):
        if order["payload"].get("execution") != "fx_breakout":
            return {}
        from .fx_order_evidence import quantity_evidence

        return {
            "quantity_evidence": quantity_evidence(self.store, order, observed),
            "warning": self._fx_warning_view(order),
        }

    def _execution(self, event):
        self._owned_cache = None
        event = {
            k: v for k, v in event.items() if k not in {"epoch", "sequence", "reconciliation_id"}
        }
        if event["client_id"] != self.broker.client_id:
            return
        if event.get("own_account") is False:
            self.incident(
                "foreign_execution", "An execution belongs to an unexpected account context."
            )
            self.invalidate_reconciliation()
            return
        if (
            event["side"] not in {"BOT", "SLD"}
            or number(event["quantity"]) < 0
            or number(event["price"]) <= 0
        ):
            self.incident(
                "invalid_execution", "A broker execution has invalid side, price or quantity."
            )
            self.invalidate_reconciliation()
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
        if order["payload"].get("execution") == "crypto_breakout" and (
            event["conid"] != order["payload"]["conid"]
            or event["side"] != ("BOT" if order["payload"]["purpose"] == "entry" else "SLD")
        ):
            self.incident(
                "crypto_execution_identity",
                "A crypto execution has an unexpected side or contract.",
            )
            self.invalidate_reconciliation()
            return
        if order["payload"].get("execution") == "fx_breakout" and (
            event["conid"] != order["payload"]["conid"]
            or event["side"] != ("BOT" if order["payload"]["purpose"] == "entry" else "SLD")
        ):
            self.incident(
                "fx_execution_identity", "FX execution differs from its durable contract or side."
            )
            self.invalidate_reconciliation()
            return
        if order["payload"].get("stock_plan") and (
            event["conid"] != order["payload"]["conid"]
            or (
                not is_pair(order["payload"])
                and event["side"]
                != (
                    "BOT"
                    if order["payload"].get("purpose", "entry") == "entry"
                    and event["broker_id"] == order["broker_id"]
                    else "BOT"
                    if order["payload"].get("action") == "BUY"
                    else "SLD"
                )
            )
        ):
            self.incident(
                "stock_execution_identity",
                "A stock execution differs from its durable contract or side.",
            )
            self.invalidate_reconciliation()
            return
        if is_pair(order["payload"]):
            leg = next(
                leg
                for leg in pair_legs({**order["payload"], "id": order["id"]}).values()
                if leg["broker_id"] == event["broker_id"]
            )
            if (
                event["side"] != ("BOT" if leg["action"] == "BUY" else "SLD")
                or event["conid"] != order["payload"]["conid"]
            ):
                self.incident(
                    "oca_execution_identity",
                    "A paired execution has unexpected side or contract identity.",
                )
                self.invalidate_reconciliation()
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
        if (
            not inconsistent
            and order["payload"].get("execution") == "fx_breakout"
            and event.get("own_account") is True
        ):
            self._fx_note_account_evidence(order["run_id"])
        if not inconsistent and not old and event["side"] == "BOT":
            run = self.store.get("run", order["run_id"])
            if run:
                run["last_fill_at"] = now()
                self.store.put("run", run["id"], run)
                if run["id"] in self.runtime:
                    self.runtime[run["id"]]["market"].last_entry = datetime.now(UTC)
        if not old or inconsistent:
            self._owned_cache = None
            self.invalidate_reconciliation()
            self.position_agreement = False
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
                    "currency": order["payload"].get(
                        "currency",
                        (order["payload"].get("stock_plan") or {}).get("currency", "USD"),
                    ),
                },
            )
            sign = 1 if event["side"] == "BOT" else -1
            if position["quantity"] == 0 and (sign == 1 or is_pair(order["payload"])):
                position["entry_id"] = order["payload"].get("entry_id", order_id)
                position["direction"] = "long" if sign == 1 else "short"
            quantity = number(event["quantity"])
            position["quantity"] += quantity * sign
            scale = number(
                (order["payload"].get("stock_plan") or {}).get("rules", {}).get("price_scale", 1)
            )
            position["cash"] -= quantity * number(event["price"]) * sign * scale
        self._owned_cache = positions
        return positions
