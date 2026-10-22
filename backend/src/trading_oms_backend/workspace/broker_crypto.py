"""Paper-only PAXOS MKT IOC boundary. No native crypto stops are claimed."""

from decimal import Decimal

from .graph import number


class PaperCrypto:
    def submit_crypto(self, intent):
        self._require_paper()
        contract = self._contracts.get(intent["conid"])
        if not contract or not (
            contract.secType == "CRYPTO"
            and contract.symbol in {"BTC", "ETH"}
            and contract.exchange == "PAXOS"
            and contract.currency == "USD"
        ):
            raise ValueError("Only resolved BTC/ETH USD PAXOS paper contracts are supported.")
        from ibapi.order import Order

        order = Order()
        order.orderId = intent["broker_id"]
        order.orderRef = "oms-" + intent["id"]
        order.account = self._accounts[0]
        order.orderType, order.tif, order.transmit = "MKT", "IOC", True
        if intent["purpose"] == "entry":
            cash = number(intent["cash_quantity"])
            if not 0 < cash <= 1000 or intent.get("protection_type") != "locally_monitored":
                raise ValueError(
                    "A bounded cash budget and persisted local protection plan are required."
                )
            order.action = "BUY"
            order.totalQuantity = Decimal(0)
            order.cashQty = float(cash)
        elif intent["purpose"] == "exit":
            quantity = number(intent["quantity"])
            if quantity <= 0:
                raise ValueError("A positive confirmed owned crypto quantity is required.")
            order.action, order.totalQuantity = "SELL", quantity
        else:
            raise ValueError("Unsupported crypto paper intent.")
        self.client.placeOrder(order.orderId, contract, order)
