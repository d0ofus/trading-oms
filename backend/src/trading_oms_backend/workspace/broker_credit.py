"""Nonexecuting credit requests, available only on the paper execution adapter."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from .graph import number

VALIDATION_FIELDS = frozenset(
    {
        "contract_identity",
        "account_context",
        "what_if",
        "order_reference",
        "action",
        "order_type",
        "time_in_force",
        "outside_hours",
        "expiry",
        "trigger_method",
        "quantity",
        "price",
        "margin_values",
        "maintenance_headroom",
        "broker_warning",
        "broker_status",
        "malformed_evidence",
    }
)


def validation_failures(request, contract, order, state, values, account):
    checks = {
        "contract_identity": all(
            getattr(contract, field) == request[key]
            for field, key in (
                ("conId", "conid"),
                ("secType", "sec_type"),
                ("currency", "currency"),
                ("exchange", "route"),
            )
        ),
        "account_context": order.account == account,
        "what_if": order.whatIf is True,
        "order_reference": order.orderRef == "credit-" + request["key"][:24],
        "action": order.action == request["action"],
        "order_type": order.orderType == request["order_type"],
        "time_in_force": order.tif == request["tif"],
        "outside_hours": order.outsideRth == request["outside_rth"]
        or (
            2109 in request.get("informational_codes", [])
            and request["outside_rth"] is True
            and order.outsideRth is False
        ),
        "expiry": order.goodTillDate == request.get("good_till_date", ""),
        "trigger_method": order.triggerMethod == request.get("trigger_method", 0),
        "quantity": number(order.totalQuantity) == number(request["quantity"]),
        "price": order.orderType == "MKT"
        or number(order.lmtPrice if order.orderType == "LMT" else order.auxPrice)
        == number(request["price"]),
        "margin_values": all(v.is_finite() and abs(v) < Decimal("1e12") for v in values.values()),
        "broker_warning": not state.warningText,
        "broker_status": state.status in {"PreSubmitted", "Submitted"},
    }
    checks["maintenance_headroom"] = checks["margin_values"] and values["equity_after"] > max(
        values["initial_after"], values["maintenance_after"]
    )
    return [key for key, passed in checks.items() if not passed]


class PaperCredit:
    def credit_error(self, broker_id, code, message, advanced=""):
        request = self._credit_previews.get(broker_id)
        if not request:
            return False
        if request["status"] != "pending" or request["epoch"] != self.epoch:
            return True
        if code in {2104, 2106, 2107, 2108, 2109, 2158, 2119}:
            # 2109 only normalizes outsideRth; it is not a credit decision.
            codes = request.setdefault("informational_codes", [])
            if code not in codes:
                codes.append(code)
            return True
        from .credit_policy import credit_category

        request["status"] = "rejected"
        self.emit(
            "credit_preview",
            broker_id=broker_id,
            key=request["key"],
            status="rejected",
            code=code,
            category=credit_category(message, advanced),
            reason="broker_rejection",
            received_at=datetime.now(UTC).isoformat(),
        )
        return True

    def validate_credit_intent(self, plan, intent):
        from .credit_policy import POLICY, broker_credit, buying_power_policy
        from .fx_data import recent

        if not broker_credit(plan):
            return
        valuation = intent.get("valuation") or {}
        snapshot = valuation.get("credit_snapshot") or {}
        keys = valuation.get("credit_keys") or []
        if buying_power_policy(plan):
            from .buying_power import validate_capacity

            if (
                valuation.get("funding_policy") != plan["funding_policy"]
                or snapshot.get("epoch") != self.epoch
                or not recent(snapshot.get("checked_at"), 30)
                or keys
            ):
                raise ValueError("Current paper buying-power evidence is required for this entry.")
            validate_capacity(valuation, [])
            return
        if (
            valuation.get("funding_policy") != POLICY
            or valuation.get("funding_mode") not in {"cash", "margin"}
            or snapshot.get("epoch") != self.epoch
            or not recent(snapshot.get("checked_at"), 30)
            or valuation.get("funding_mode") == "margin"
            and (not keys or not snapshot.get("margin_ready"))
        ):
            raise ValueError("Current paper credit evidence is required for this entry.")
        pair = intent.get("prices")
        fx = plan.get("family") == "spot_fx"
        kind = (
            "STP"
            if pair
            else "MKT"
            if fx or (plan.get("kind") == "stock_breakout" and not plan.get("outside_rth"))
            else "LMT"
        )
        expected = {
            "BUY": number(pair["long_entry"] if pair else intent.get("limit", 0)),
            **({"SELL": number(pair["short_entry"])} if pair else {}),
        }
        seen = set()
        for key in keys:
            record = next(
                (
                    p
                    for p in self._credit_previews.values()
                    if p["key"] == key and p.get("status") == "accepted"
                ),
                {},
            )
            action = record.get("action")
            if (
                record.get("epoch") != self.epoch
                or record.get("plan_hash") != plan["hash"]
                or record.get("conid") != plan["conid"]
                or any(
                    record.get(k) != snapshot.get(k) for k in ("revision", "instance", "context")
                )
                or not recent(record.get("received_at"), 180 if pair else 30)
                or number(record.get("quantity", 0)) != number(intent["quantity"])
                or action not in expected
                or action in seen
                or record.get("order_type") != kind
                or record.get("tif") != ("IOC" if fx else "DAY" if kind == "MKT" else "GTD")
                or bool(record.get("outside_rth")) != bool(fx or plan.get("outside_rth"))
                or record.get("trigger_method", 0) != (2 if pair else 0)
                or kind != "MKT"
                and number(record.get("price", 0)) != expected.get(action)
            ):
                raise ValueError("Paper credit evidence differs from the executable entry.")
            seen.add(action)
        if keys and seen != set(expected):
            raise ValueError("Every entry branch requires its own paper credit evidence.")

    def preview_credit(self, request):
        from ibapi.order import Order

        self._require_paper()
        contract = self._contracts.get(request["conid"])
        if (
            not contract
            or contract.secType not in {"STK", "CASH"}
            or contract.secType != request["sec_type"]
            or contract.currency != request["currency"]
            or contract.exchange != request["route"]
            or contract.symbol != request["symbol"]
            or request["epoch"] != self.epoch
            or request["action"] not in {"BUY", "SELL"}
            or request["order_type"] not in {"MKT", "LMT", "STP"}
            or request["tif"] not in {"IOC", "DAY", "GTD"}
            or number(request["quantity"]) <= 0
            or number(request["price"]) <= 0
        ):
            raise ValueError("Credit preview requires a current qualified paper order identity.")
        if contract.secType == "CASH" and (
            contract.exchange != "IDEALPRO"
            or request["order_type"] != "MKT"
            or request["tif"] != "IOC"
        ):
            raise ValueError("Unsupported spot-FX credit preview structure.")
        order = Order()
        order.orderId, order.account = request["broker_id"], self._accounts[0]
        order.action, order.orderType = request["action"], request["order_type"]
        order.totalQuantity, order.tif = number(request["quantity"]), request["tif"]
        order.outsideRth = request["outside_rth"]
        order.goodTillDate = request.get("good_till_date", "")
        order.triggerMethod = request.get("trigger_method", 0)
        if order.orderType == "LMT":
            order.lmtPrice = float(number(request["price"]))
        elif order.orderType == "STP":
            order.auxPrice = float(number(request["price"]))
        order.orderRef = "credit-" + request["key"][:24]
        # No caller argument can turn a preview into an executable order.
        order.whatIf, order.transmit = True, True
        previews = getattr(self, "_credit_previews", {})
        self._credit_previews = previews
        previews[order.orderId] = {**request, "status": "pending"}
        if len(previews) > 200:
            for key in list(previews):
                if len(previews) <= 200:
                    break
                if previews[key]["status"] != "pending":
                    del previews[key]
        self._require_paper()
        self.client.placeOrder(order.orderId, contract, order)

    def credit_observation(self, broker_id, contract, order, state):
        request = self._credit_previews[broker_id]
        if request["epoch"] != self.epoch or request["status"] != "pending":
            return
        values = {}
        accepted = False
        failures = ["malformed_evidence"]
        try:
            values = {
                name: Decimal(getattr(state, field))
                for name, field in {
                    "initial_change": "initMarginChange",
                    "maintenance_change": "maintMarginChange",
                    "initial_after": "initMarginAfter",
                    "maintenance_after": "maintMarginAfter",
                    "equity_after": "equityWithLoanAfter",
                }.items()
            }
            failures = validation_failures(
                request, contract, order, state, values, self._accounts[0]
            )
            accepted = not failures
        except (AttributeError, ValueError, TypeError, InvalidOperation):
            pass
        request["status"] = "accepted" if accepted else "rejected"
        request["received_at"] = datetime.now(UTC).isoformat()
        from .credit_policy import credit_category

        self.emit(
            "credit_preview",
            broker_id=broker_id,
            key=request["key"],
            status=request["status"],
            received_at=request["received_at"],
            **(
                {k: str(v) for k, v in values.items()}
                if accepted
                else {
                    "category": credit_category(getattr(state, "warningText", "")),
                    "reason": "preview_validation_failed",
                    "validation_fields": failures,
                }
            ),
        )
        self.cancel_credit_preview(broker_id)

    def cancel_credit_preview(self, broker_id, expired=False):
        from ibapi.order_cancel import OrderCancel

        if broker_id in self._credit_previews:
            self._require_paper()
            if expired:
                self._credit_previews[broker_id]["status"] = "expired"
            self.client.cancelOrder(broker_id, OrderCancel())
