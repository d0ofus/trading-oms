"""Account-scoped paper credit evidence and serialized funding reservations."""

import json
import os
import time
from decimal import Decimal

from .buying_power import BuyingPower, validate_capacity
from .credit_policy import CREDIT_DETAILS, POLICY, broker_credit, buying_power_policy
from .fx_data import recent
from .graph import GraphError, digest, number
from .stock_policy import fx_rate
from .store import Conflict, now


class CreditPending(Conflict):
    status = "checking"


class CreditUnsupported(Conflict):
    status = "unsupported"


def pending_credit(active, reflected, field="credit_reserve"):
    return sum(
        (
            number(r.get("fee_reserve_usd", 0))
            if r.get("reservation_id") in reflected
            else number(r.get(field, r.get("notional", 0)))
            for r in active
        ),
        Decimal(0),
    )


def pending_currency(active, reflected, currency):
    return sum(
        (
            number(
                r.get("credit_fee_currencies", {}).get(currency, 0)
                if r.get("reservation_id") in reflected
                else r.get("currency_reserves", {}).get(
                    currency, r.get("native_funds", 0) if r.get("currency") == currency else 0
                )
            )
            for r in active
        ),
        Decimal(0),
    )


def validate_reservation(db, store, reservation, exclude=None):
    """Recheck account capacity inside the order/reservation transaction."""
    if not broker_credit(reservation):
        return
    snapshot = reservation["credit_snapshot"]
    if not recent(snapshot.get("checked_at"), 30):
        raise Conflict("Broker buying-power evidence expired before reservation.")
    active = [
        {**json.loads(row[1]), "reservation_id": row[0]}
        for row in db.execute("SELECT id,payload FROM documents WHERE kind='reservation'")
        if json.loads(row[1]).get("active") and row[0] != exclude
    ]
    if buying_power_policy(reservation):
        validate_capacity(reservation, active)
        return
    reflected = set(snapshot["reflected_reservations"])
    for field, balance in (("credit_reserve", "available"), ("maintenance_reserve", "excess")):
        if pending_credit(active, reflected, field) + number(reservation[field]) > number(
            snapshot[balance]
        ):
            raise Conflict("Concurrent reservations exceed broker buying power.")
    if reservation["funding_mode"] == "cash":
        for currency, amount in reservation["currency_reserves"].items():
            reserved = pending_currency(active, reflected, currency)
            if reserved + number(amount) > number(reservation["funding_snapshot"][currency]):
                raise Conflict("Concurrent reservations exceed usable currency funds.")


class CreditController(BuyingPower):
    def _credit_account_issues(self):
        if not self._credit_debit_currencies():
            return []
        currency = getattr(self, "account_base_currency", None)
        for tag in ("AvailableFunds", "ExcessLiquidity"):
            fact = self.currency_facts.get((tag, currency))
            if fact and recent(fact.get("received_at"), 30) and number(fact["value"]) < 0:
                return [
                    "Broker reports a buying-power or maintenance shortfall "
                    "after approved borrowing."
                ]
        return []

    def _claim_credit_slot(self):
        # Persist pacing across restart. One queue also covers legacy short previews.
        with self.store.transaction() as db:
            previous = self.store.read(db, "workspace", "credit_pacing") or {}
            if recent(previous.get("requested_at"), 60) or previous.get("requested_at", "") > now():
                return False
            self.store.write(db, "workspace", "credit_pacing", {"requested_at": now()})
        self._credit_next_request = time.monotonic() + 60
        return True

    def _credit_dispatch_ready(self, run, order):
        plan = (run.get("binding") or {}).get("execution_plan") or {}
        if not broker_credit(plan):
            return True
        try:
            valuation = order["payload"].get("valuation") or {}
            snapshot = self._credit_account(buying_power=buying_power_policy(plan))
            if valuation.get("funding_policy") != plan["funding_policy"] or any(
                valuation.get("credit_snapshot", {}).get(k) != snapshot[k]
                for k in ("revision", "epoch", "instance", "context")
            ):
                return False
            keys = valuation.get("credit_keys", [])
            if valuation.get("funding_mode") == "margin" and (
                not keys or not snapshot["margin_ready"]
            ):
                return False
            for key in keys:
                evidence = self.store.get("credit_evidence", key) or {}
                if evidence.get("status") != "accepted" or not recent(
                    evidence.get("received_at"), 180 if order["payload"].get("prices") else 30
                ):
                    return False
            with self.store.transaction() as db:
                validate_reservation(
                    db, self.store, {**valuation, "credit_snapshot": snapshot}, order["id"]
                )
            return True
        except Conflict:
            return False

    def _credit_debit_currencies(self):
        from .fx_ledger import executions

        result = set()
        for order, _ in executions(self.store):
            valuation = order["payload"].get("valuation") or {}
            if broker_credit(valuation) and valuation.get("funding_mode") in {
                "margin",
                "broker_decision",
            }:
                result.update(valuation.get("projected_currency_debits", {}))
                plan = order["payload"].get("fx_plan") or {}
                if buying_power_policy(plan):
                    # A bought currency can offset an existing debit. Closing
                    # the owned trade restores that debit; it need not create
                    # a positive aggregate cash balance to establish ownership.
                    result.add(plan["base_currency"])
        return result

    def _credit_account(self, buying_power=False):
        if not self.connected or not self.attested or not self.broker.paper_context:
            raise Conflict("Verified paper context is required for broker buying power.")
        if not self.reconciled or time.monotonic() - self.reconciled_at >= 30:
            raise CreditPending("Waiting for current account and ownership reconciliation.")
        currency = getattr(self, "account_base_currency", None)
        if not currency:
            raise CreditPending("Waiting for the broker account valuation currency.")
        values = {}
        for tag in (
            "AvailableFunds",
            "ExcessLiquidity",
            "EquityWithLoanValue",
            "InitMarginReq",
            "MaintMarginReq",
            "BuyingPower",
        ):
            fact = self.currency_facts.get((tag, currency))
            if fact and recent(fact.get("received_at"), 30):
                try:
                    value = number(fact["value"])
                    if abs(value) < Decimal("1e12"):
                        values[tag] = value
                except GraphError:
                    pass
        if "AvailableFunds" not in values:
            raise CreditPending("Waiting for current broker buying-power evidence.")
        if buying_power:
            for tag in ("BuyingPower", "ExcessLiquidity"):
                if tag not in values:
                    raise CreditPending(f"Waiting for current broker {tag} evidence.")
        margin_ready = (
            all(
                k in values
                for k in (
                    "AvailableFunds",
                    "ExcessLiquidity",
                    "EquityWithLoanValue",
                    "InitMarginReq",
                    "MaintMarginReq",
                )
            )
            and values.get("EquityWithLoanValue", 0) > 0
        )
        rate = fx_rate(currency, self.fx_quotes.values(), liability=False)
        liability_rate = fx_rate(currency, self.fx_quotes.values(), liability=True)
        if values["AvailableFunds"] <= 0 or values.get("ExcessLiquidity", 1) <= 0:
            raise Conflict("Broker buying power or maintenance headroom is insufficient.")
        reflected = []
        # Only a verified post-dispatch snapshot can already include an order's
        # margin. Draft/unsubmitted reservations must still reduce headroom.
        proof = self.reconciliation_evidence or {}
        started = proof.get("started_at", "")
        with self.store.connect() as db:
            orders = db.execute(
                "SELECT id,state,created_at FROM outbox WHERE id IN "
                "(SELECT id FROM documents WHERE kind='reservation' "
                "AND json_extract(payload,'$.active')=1)"
            ).fetchall()
        for order in orders:
            if order["state"] in {"working", "partially_filled", "filled", "cancelled", "rejected"}:
                if order["created_at"] < started:
                    reflected.append(order["id"])
        if buying_power:
            reflected = self._buying_power_reflected()
        return {
            "available": str(values["AvailableFunds"] * rate),
            # Without margin fields, this fallback supports only fully reserved,
            # settled-cash purchases. It is never evidence of borrowing capacity.
            "excess": str(values.get("ExcessLiquidity", values["AvailableFunds"]) * rate),
            "margin_ready": margin_ready,
            "base_currency": currency,
            "rate": str(liability_rate),
            "capacity_rate": str(rate),
            **({"buying_power": str(values["BuyingPower"] * rate)} if buying_power else {}),
            "revision": getattr(self, "_evidence_revision", 0),
            "epoch": self.broker.epoch,
            "instance": self.process_identity,
            "context": getattr(self, "paper_context_token", None),
            "reflected_reservations": reflected,
            "checked_at": now(),
        }

    def _credit_assess(self, plan, valuation, orders, exclude=None):
        if buying_power_policy(plan):
            return self._buying_power_assess(plan, valuation, exclude)
        if os.environ.get("OMS_DISABLE_BROKER_CREDIT_ARM") == "1":
            raise Conflict("New broker-credit entries are disabled by the rollback setting.")
        snapshot = self._credit_account()
        with self.store.connect() as db:
            active = [
                {**json.loads(r[1]), "reservation_id": r[0]}
                for r in db.execute("SELECT id,payload FROM documents WHERE kind='reservation'")
                if json.loads(r[1]).get("active") and json.loads(r[1]).get("run_id") != exclude
            ]
        reflected = set(snapshot["reflected_reservations"])
        cash = {}
        reserves = valuation["currency_reserves"]
        cash_ready = True
        for currency, requested in reserves.items():
            facts = [
                self.currency_facts.get((tag, currency)) for tag in ("CashBalance", "SettledCash")
            ]
            if any(not f or not recent(f.get("received_at"), 30) for f in facts):
                cash_ready = False
                continue
            cash[currency] = str(
                min(number(f["value"]) for f in facts) - self._fx_owned_currency(currency)
            )
            pending = pending_currency(active, reflected, currency)
            cash_ready = cash_ready and number(cash[currency]) - pending >= number(requested)
        cost = number(valuation["notional"]) + number(valuation.get("fee_reserve_usd", 0))
        available = number(snapshot["available"]) - pending_credit(active, reflected)
        excess = number(snapshot["excess"]) - pending_credit(
            active, reflected, "maintenance_reserve"
        )
        cash_ready = cash_ready and cost <= min(available, excess)
        keys = []
        credit = maintenance = cost
        mode = "cash"
        # Short-sale credit is required even if the long branch is cash funded.
        if not cash_ready or any(o["action"] == "SELL" for o in orders):
            if not snapshot["margin_ready"]:
                raise CreditPending("Waiting for current broker margin evidence.")
            if not hasattr(self.broker, "preview_credit"):
                raise CreditUnsupported(
                    "Broker credit preview is unavailable for this execution adapter."
                )
            estimates = []
            for order in orders:
                request = {
                    **order,
                    "conid": plan["conid"],
                    "currency": plan["currency"],
                    "sec_type": "CASH" if plan.get("family") == "spot_fx" else "STK",
                    "symbol": self.contracts[plan["conid"]]["symbol"],
                    "route": plan["routing_exchange"],
                    "epoch": self.broker.epoch,
                    "instance": self.process_identity,
                    "context": snapshot["context"],
                    "revision": snapshot["revision"],
                    "plan_hash": plan["hash"],
                }
                # Absolute GTD time is enforced anew by the dispatch/session guard.
                # Credit describes economic terms, not permission to replay a signal.
                key = digest(
                    {
                        k: v
                        for k, v in request.items()
                        if k != "good_till_date" and (k != "price" or order["order_type"] != "MKT")
                    }
                )
                request["key"] = key
                request["priority"] = getattr(self, "_credit_priority", 0)
                evidence = self.store.get("credit_evidence", key) or {}
                # Two sequential branch previews cannot both be younger than one
                # account pacing interval. The same terms and state revision must
                # still match, and live account capacity is always rechecked.
                lifetime = 180 if len(orders) > 1 else 30
                if (
                    evidence.get("status") == "rejected"
                    and evidence.get("revision") == snapshot["revision"]
                ):
                    raise Conflict(
                        evidence.get("detail")
                        or "Broker credit preview rejected this quantity or order structure."
                    )
                if not (
                    evidence.get("status") == "accepted"
                    and recent(evidence.get("received_at"), lifetime)
                ):
                    if getattr(self, "_credit_collecting", False):
                        demands = getattr(self, "_credit_demands", {})
                        if len(demands) < 20:
                            demands[key] = request
                        self._credit_demands = demands
                    raise CreditPending(
                        "Checking broker buying power; credit preview is queued or in progress."
                    )
                estimates.append(evidence)
                keys.append(key)
            credit = sum(
                (max(Decimal(0), number(e["initial_change"])) for e in estimates), Decimal(0)
            ) * number(snapshot["rate"])
            maintenance = sum(
                (max(Decimal(0), number(e["maintenance_change"])) for e in estimates), Decimal(0)
            ) * number(snapshot["rate"])
            credit += number(valuation.get("fee_reserve_usd", 0))
            maintenance += number(valuation.get("fee_reserve_usd", 0))
            if credit > available or maintenance > excess:
                raise Conflict(
                    "Broker credit requirement exceeds current available margin after reservations."
                )
            mode = "margin" if not cash_ready else "cash"
        return {
            **valuation,
            "funding_policy": POLICY,
            "funding_mode": mode,
            "credit_status": "ready",
            "credit_keys": keys,
            "credit_reserve": str(credit),
            "credit_fee_currencies": {
                valuation.get("fee_currency", plan["currency"]): str(
                    number(valuation["fee_reserve_native"])
                    if valuation.get("fee_reserve_native") is not None
                    else number(valuation.get("fee_reserve_usd", 0)) / number(valuation["fx_rate"])
                )
            },
            "maintenance_reserve": str(maintenance),
            "credit_snapshot": snapshot,
            "funding_revision": snapshot["revision"],
            "funding_snapshot": cash,
            "projected_currency_debits": dict(reserves),
            "currency_reserves": reserves if mode == "cash" else {},
            "checked_at": now(),
        }

    def _credit_observe(self, event):
        item = self.store.get("credit_evidence", event.get("key", ""))
        if (
            not item
            or item.get("status") != "pending"
            or any(
                (
                    item["broker_id"] != event.get("broker_id"),
                    item["epoch"] != self.broker.epoch,
                    event.get("epoch", self.broker.epoch) != self.broker.epoch,
                    item["instance"] != self.process_identity,
                    item["revision"] != getattr(self, "_evidence_revision", 0),
                    item.get("context") != getattr(self, "paper_context_token", None),
                )
            )
        ):
            return
        fields = {
            k: event[k]
            for k in (
                "status",
                "received_at",
                "initial_change",
                "maintenance_change",
                "initial_after",
                "maintenance_after",
                "equity_after",
            )
            if k in event
        }
        item.update(fields)
        if isinstance(event.get("code"), int):
            item["broker_code"] = event["code"]
        if event.get("reason") in {"broker_rejection", "preview_validation_failed"}:
            item["validation_reason"] = event["reason"]
        from .broker_credit import VALIDATION_FIELDS

        item["validation_fields"] = sorted(
            {
                v
                for v in (event.get("validation_fields") or [])[:20]
                if isinstance(v, str) and v in VALIDATION_FIELDS
            }
        )
        try:
            values = [
                number(item[name])
                for name in (
                    "initial_change",
                    "maintenance_change",
                    "initial_after",
                    "maintenance_after",
                    "equity_after",
                )
            ]
            valid = all(abs(value) < Decimal("1e12") for value in values) and values[4] > max(
                values[2:4]
            )
        except (KeyError, ValueError, TypeError):
            valid = False
        if not valid or not recent(item.get("received_at"), 30):
            item["status"] = "rejected"
        if item["status"] != "accepted":
            category = event.get("category", "unknown")
            category = (
                category if isinstance(category, str) and category in CREDIT_DETAILS else "unknown"
            )
            item.update(
                status="rejected",
                category=category,
                detail=CREDIT_DETAILS[category],
            )
            if item.get("validation_reason") == "preview_validation_failed":
                item["detail"] += (
                    " Failed checks: "
                    + ", ".join(v.replace("_", " ") for v in item["validation_fields"])
                    + "."
                )
        self.store.put("credit_evidence", item["key"], item)
        self.store.event("credit.preview.observed", item)

    def _credit_maintain(self):
        if not self.connected or not self.reconciled or not self.attested:
            return
        for item in self.store.list("credit_evidence"):
            if item.get("status") == "pending" and not recent(item.get("requested_at"), 30):
                item.update(status="expired")
                self.store.put("credit_evidence", item["key"], item)
                self.store.event("credit.preview.expired", {"key": item["key"]})
                if hasattr(self.broker, "cancel_credit_preview"):
                    self.broker.cancel_credit_preview(item["broker_id"], expired=True)
        self._credit_demands = {}
        self._credit_collecting = True
        try:
            for run in self.store.list("run"):
                plan = (run.get("binding") or {}).get("execution_plan") or {}
                if (
                    not broker_credit(plan)
                    or buying_power_policy(plan)
                    or run.get("archived")
                    or run.get("entries")
                    or not (
                        run.get("armed")
                        or run.get("state") == "ready"
                        and (
                            recent(run.get("created_at"), 60)
                            or time.monotonic()
                            - getattr(self, "_credit_review_interest", {}).get(run["id"], 0)
                            < 6
                        )
                    )
                ):
                    continue
                self._credit_priority = int(bool(run.get("armed")))
                try:
                    if self._fx_run(run):
                        self._fx_funding(plan, run["binding"]["sizing"])
                    else:
                        modern = plan.get("risk_policy") == "paper_stock_v2"
                        self._stock_checks(
                            run,
                            run.get("limits")
                            or {
                                "notional": None if modern else "1000",
                                "planned_stop_risk": None if modern else "10",
                                "entry_timeout": 30,
                                **({"risk_policy": "paper_stock_v2"} if modern else {}),
                            },
                        )
                except Conflict:
                    pass
        finally:
            self._credit_collecting = False
        clock = time.monotonic()
        if clock < getattr(self, "_credit_next_request", 0):
            return
        for key, request in sorted(
            self._credit_demands.items(),
            key=lambda pair: (
                -pair[1].get("priority", 0),
                (self.store.get("credit_evidence", pair[0]) or {}).get("requested_at", ""),
            ),
        ):
            prior = self.store.get("credit_evidence", key) or {}
            if prior.get("status") == "pending" and recent(prior.get("requested_at"), 30):
                continue
            if not self._claim_credit_slot():
                return
            request = {
                **request,
                "broker_id": self.store.allocate_broker_id(self.next_id),
                "status": "pending",
                "requested_at": now(),
            }
            with self.store.transaction() as db:
                self.store.write(db, "credit_evidence", key, request)
                self.store.append(db, "credit.preview.requested", request)
                db.execute(
                    "DELETE FROM documents WHERE kind='credit_evidence' AND rowid NOT IN "
                    "(SELECT rowid FROM documents WHERE kind='credit_evidence' "
                    "ORDER BY rowid DESC LIMIT 200)"
                )
            try:
                self.broker.preview_credit(request)
            except Exception:
                request.update(
                    status="rejected",
                    detail="Broker credit preview could not start; refresh the paper connection.",
                )
                self.store.put("credit_evidence", key, request)
                self.store.event("credit.preview.failed", {"key": key, "detail": request["detail"]})
            break
