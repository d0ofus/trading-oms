"""Qualified stock order validation at the paper-only SDK boundary."""

from datetime import UTC, datetime

from .graph import digest, number
from .stock_policy import validate_rules


class PaperStocks:
    def _stock_extended_deadline(self, intent):
        from .stock_sessions import StockSession

        plan = intent.get("stock_plan", {})
        if plan.get("session_mode") != "premarket_regular":
            return None
        if not (
            plan.get("version") == 2
            and plan.get("kind") == "stock_breakout"
            and plan.get("protection_type") == "locally_monitored"
            and plan.get("routing_exchange") in {"SMART", "NASDAQ"}
            and plan.get("entry_type") == plan.get("exit_type") == "LMT"
            and plan.get("outside_rth") is True
        ):
            raise ValueError("Unqualified pre-market execution policy.")
        stamp = datetime.now(UTC)
        deadline = datetime.fromisoformat(intent["expires_at"]).replace(microsecond=0)
        if intent["session_contract"].get("conid") != plan["conid"]:
            raise ValueError("Session evidence belongs to another contract.")
        schedule = StockSession(intent["session_contract"], "premarket_regular")
        end = next((b for a, b in schedule.intervals(stamp) if a <= stamp < b), None)
        if end is None or not stamp < deadline <= end:
            raise ValueError("Pre-market order deadline is outside its approved broker interval.")
        return deadline.astimezone(UTC).strftime("%Y%m%d-%H:%M:%S")

    def _stock_contract(self, intent, entry=False):
        self._require_paper()
        plan = intent["stock_plan"]
        if plan.get("hash") != digest({k: v for k, v in plan.items() if k != "hash"}):
            raise ValueError("Invalid stock execution-plan revision.")
        contract = self._contracts.get(intent["conid"])
        if (
            contract is None
            or contract.secType != "STK"
            or contract.conId != plan["conid"]
            or contract.currency != plan["currency"]
            or contract.exchange != plan["routing_exchange"]
        ):
            raise ValueError("Stock order identity differs from its qualified contract.")
        rules = validate_rules({"stock_rules": plan["rules"], "currency": contract.currency})
        quantity = number(intent["quantity"])
        step = number(rules["quantity_increment" if entry else "exit_increment"])
        if (
            quantity <= 0
            or quantity % step
            or entry
            and quantity < number(rules["minimum_quantity"])
        ):
            raise ValueError("Stock order quantity does not satisfy its verified increment.")
        if entry:
            from .broker_credit import PaperCredit

            PaperCredit.validate_credit_intent(self, plan, intent)
            valuation = intent.get("valuation") or {}
            if (
                not valuation.get("checked_at")
                or not 0
                <= (
                    datetime.now(UTC) - datetime.fromisoformat(valuation["checked_at"])
                ).total_seconds()
                <= 15
            ):
                raise ValueError("The reviewed stock valuation is stale.")
            modern = plan.get("risk_policy") == "paper_stock_v2"
            if modern and valuation.get("risk_policy") != plan["risk_policy"]:
                raise ValueError("Stock valuation does not match the approved risk policy.")
            if (
                number(valuation.get("notional", 0)) <= 0
                or number(valuation.get("risk", 0)) <= 0
                or not modern
                and (number(valuation["notional"]) > 1000 or number(valuation["risk"]) > 10)
            ):
                raise ValueError("The stock entry exceeds the USD execution ceilings.")
            if modern:
                from .paper_risk import effective

                sizing, limits = intent["approved_sizing"], intent["risk_limits"]
                cap = effective(sizing["notional"], limits["notional"])
                risk_cap = effective(sizing["risk"], limits["planned_stop_risk"])
                if (
                    (sizing["sizing"] == "fixed" and quantity != number(sizing["shares"]))
                    or cap is not None
                    and number(valuation["notional"]) > cap
                    or risk_cap is not None
                    and number(valuation["risk"]) > risk_cap
                ):
                    raise ValueError(
                        "Stock intent exceeds its approved quantity or optional ceilings."
                    )
            prices = intent.get("prices")
            branches = (
                [
                    (number(prices[s + "_entry"]), number(prices[s + "_stop"]))
                    for s in ("long", "short")
                ]
                if prices
                else [(number(intent["limit"]), number(intent["stop"]))]
            )
            scale, rate = number(rules["price_scale"]), number(valuation["fx_rate"])
            # Match the reservation's Decimal operation order exactly; no float
            # tolerance or differently associated FX multiplication is needed.
            expected_notional = quantity * sum(p * scale for p, _ in branches) * rate
            expected_risk = quantity * (sum(abs(p - s) * scale for p, s in branches) * rate)
            if expected_notional != number(valuation["notional"]) or expected_risk != number(
                valuation["risk"]
            ):
                raise ValueError("Stock intent differs from its durable risk reservation.")
        return contract

    def amend_stock_stop(self, intent, amendment):
        from ibapi.order import Order

        contract = self._stock_contract({**intent, "quantity": amendment["quantity"]})
        if (
            not 0 < number(amendment["quantity"]) <= number(intent["quantity"])
            or amendment["broker_id"] != intent["broker_id"] + 2
        ):
            raise ValueError("Only the original owned protective child may be amended.")
        order = Order()
        order.orderId = amendment["broker_id"]
        order.parentId = intent["broker_id"]
        order.action, order.orderType = "SELL", "STP"
        order.totalQuantity, order.auxPrice = (
            number(amendment["quantity"]),
            float(number(amendment["stop"])),
        )
        order.tif, order.transmit, order.outsideRth = "GTC", True, False
        order.account, order.orderRef = self._accounts[0], "oms-" + intent["id"]
        order.ocaGroup, order.ocaType = order.orderRef, 2
        self._require_paper()
        self.client.placeOrder(order.orderId, contract, order)
