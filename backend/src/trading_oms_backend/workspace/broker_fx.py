"""Explicit paper-only spot-currency orders. Never used by the data-only adapter."""

from datetime import UTC, datetime

from .fx_policy import BROKER_CANDLES, CURRENCIES, POLICY
from .graph import digest, number


class PaperFX:
    def submit_fx(self, intent):
        self._require_paper()
        plan = intent.get("fx_plan") or {}
        contract = self._contracts.get(intent.get("conid"))
        if (
            not contract
            or contract.secType != "CASH"
            or contract.exchange != "IDEALPRO"
            or contract.symbol not in CURRENCIES
            or contract.currency not in CURRENCIES
            or plan.get("base_currency") != contract.symbol
            or plan.get("currency") != contract.currency
            or plan.get("conid") != intent.get("conid")
            or plan.get("policy") not in {POLICY, BROKER_CANDLES}
            or plan.get("hash") != digest({k: v for k, v in plan.items() if k != "hash"})
            or intent.get("execution") != "fx_breakout"
        ):
            raise ValueError("FX order identity must match its immutable IDEALPRO paper plan.")
        rules, purpose = plan["rules"], intent["purpose"]
        quantity = number(intent["quantity"])
        step = number(rules["quantity_increment" if purpose == "entry" else "exit_increment"])
        if quantity <= 0 or quantity % step:
            raise ValueError("FX quantity must use its qualified base-currency increment.")
        from ibapi.order import Order

        order = Order()
        order.orderId, order.orderRef = intent["broker_id"], "oms-" + intent["id"]
        order.account, order.totalQuantity, order.transmit = self._accounts[0], quantity, True
        # IDEALPRO CASH has no stock regular/outside-hours distinction (2109).
        order.outsideRth = False
        if purpose == "entry":
            from .broker_credit import PaperCredit

            PaperCredit.validate_credit_intent(self, plan, intent)
            if plan["policy"] == BROKER_CANDLES:
                from .fx_observations import evaluate

                signal = intent.get("signal") or {}
                observation = signal.get("tick") or {}
                at = datetime.now(UTC)
                try:
                    reference = datetime.fromisoformat(signal["candle"])
                    authorized = datetime.fromisoformat(signal["authorized_after"])
                    valid = (
                        signal["epoch"] == self.epoch
                        and observation["conid"] == intent["conid"]
                        and observation["epoch"] == self.epoch
                        and bool(signal["reference_revision"])
                        and bool(signal["authorization_id"])
                        and int(reference.timestamp()) == int(at.timestamp()) // 60 * 60 - 60
                        and datetime.fromisoformat(observation["source_at"]) > authorized
                        and datetime.fromisoformat(observation["received_at"]) > authorized
                        and evaluate(observation, at)["reason"] == "fresh"
                        and number(signal["price"]) > number(signal["high"])
                    )
                except (KeyError, ValueError, TypeError):
                    valid = False
                if not valid:
                    raise ValueError("Current broker reference and authorized fresh tick required.")
            valuation = intent.get("valuation") or {}
            sizing = intent.get("approved_sizing") or {}
            limits = intent.get("risk_limits") or {}
            from .paper_risk import effective

            checked = valuation.get("checked_at")
            if (
                not checked
                or not 0
                <= (datetime.now(UTC) - datetime.fromisoformat(checked)).total_seconds()
                <= 15
            ):
                raise ValueError("Fresh reviewed FX valuation is required before transmission.")
            cap = effective(sizing.get("notional"), limits.get("notional"))
            risk_cap = effective(sizing.get("risk"), limits.get("planned_stop_risk"))
            if (
                quantity != number(sizing.get("quantity", 0))
                or valuation.get("risk_policy") != plan["risk_policy"]
                or number(valuation.get("notional", 0)) <= 0
                or number(valuation.get("risk", 0)) <= 0
                or cap is not None
                and number(valuation["notional"]) > cap
                or risk_cap is not None
                and number(valuation["risk"]) > risk_cap
            ):
                raise ValueError("FX entry exceeds the approved quantity or optional ceilings.")
            if (
                not intent.get("protection_intent")
                or quantity < number(rules["minimum_quantity"])
                or rules["maximum_quantity"]
                and quantity > number(rules["maximum_quantity"])
                or (plan["entry_type"], plan["entry_tif"]) != ("MKT", "IOC")
            ):
                raise ValueError(
                    "A permitted quantity and persisted FX protection plan are required."
                )
            order.action, order.orderType, order.tif = "BUY", "MKT", "IOC"
        elif purpose == "protection":
            if plan["protection_type"] != "broker_held" or plan["stop_trigger_method"] != 4:
                raise ValueError("Bid/ask broker stop protection must be approved explicitly.")
            order.action, order.orderType, order.tif = "SELL", "STP", "GTC"
            order.triggerMethod, order.auxPrice = 4, float(number(intent["stop"]))
        elif purpose == "exit":
            from .premarket import broker_deadline

            deadline = broker_deadline(intent.get("good_till_date"))
            if deadline is None or not 0 < (deadline - datetime.now(UTC)).total_seconds() <= 10:
                raise ValueError("FX exit requires a current broker-enforced ten-second deadline.")
            order.action, order.orderType, order.tif = "SELL", "LMT", "GTD"
            order.lmtPrice = float(number(intent["limit"]))
            order.goodTillDate = intent["good_till_date"]
        else:
            raise ValueError("Unsupported paper FX order purpose.")
        if purpose != "entry":
            price = number(intent["stop" if purpose == "protection" else "limit"])
            if price <= 0 or price % number(
                intent.get("price_increment", rules["price_increment"])
            ):
                raise ValueError("FX broker price must be positive and use a valid increment.")
        self.client.placeOrder(order.orderId, contract, order)
