"""Paper-only SDK operations for protected opposing stop entries."""

import copy
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from .graph import number
from .oca import pair_legs


class PaperOCA:
    def refresh_shortable(self, conid):
        self._require_paper()
        if time.monotonic() - self._borrow_refresh.get(conid, -100) < 15:
            return False
        requests = [
            request
            for index, (request, identity) in enumerate(self._requests.items())
            if identity == conid
            and self._request_kinds.get(request, "quote" if index % 2 == 1 else "trade") == "quote"
        ]
        if not requests:
            return False
        self._borrow_refresh[conid] = time.monotonic()
        for request in requests:
            self.client.cancelMktData(request)
            self.client.reqMktData(request, self._contracts[conid], "236", False, False, [])
        return True

    def _oca_contract(self, conid):
        self._require_paper()
        contract = self._contracts.get(conid)
        if contract is None or contract.secType != "STK" or contract.currency != "USD":
            raise ValueError("Paired paper orders require a resolved USD equity contract.")
        return contract

    def preview_short(self, request):
        from ibapi.order import Order

        contract = (
            self._stock_contract(request)
            if request.get("stock_plan")
            else self._oca_contract(request["conid"])
        )
        quantity, price = number(request["quantity"]), number(request["price"])
        if (
            not request.get("stock_plan")
            and (not 1 <= quantity <= 10 or quantity != quantity.to_integral_value())
        ) or price <= 0:
            raise ValueError(
                "Short credit preview requires 1–10 whole shares and a positive trigger."
            )
        order = Order()
        order.orderId, order.action, order.orderType = request["broker_id"], "SELL", "STP"
        order.totalQuantity, order.auxPrice = quantity, float(price)
        order.account, order.tif, order.outsideRth = self._accounts[0], "DAY", False
        # whatIf is never an executable request. Raw margin/warning/account text stays here.
        order.whatIf, order.transmit = True, True
        self._short_previews[request["broker_id"]] = {**request, "status": "pending"}
        self._require_paper()
        self.client.placeOrder(order.orderId, contract, order)

    def _preview_observation(self, broker_id, contract, order, order_state):
        preview = self._short_previews[broker_id]
        accepted = False
        try:
            initial = Decimal(order_state.initMarginChange)
            maintenance = Decimal(order_state.maintMarginAfter)
            equity = Decimal(order_state.equityWithLoanAfter)
            accepted = (
                contract.conId == preview["conid"]
                and order.account == self._accounts[0]
                and order.whatIf
                and order.action == "SELL"
                and order.orderType == "STP"
                and number(order.totalQuantity) == number(preview["quantity"])
                and number(order.auxPrice) == number(preview["price"])
                and all(
                    v.is_finite() and abs(v) < Decimal("1e12")
                    for v in (initial, maintenance, equity)
                )
                and initial >= 0
                and 0 <= maintenance <= equity
                and not order_state.warningText
                and order_state.status in {"PreSubmitted", "Submitted"}
            )
        except (InvalidOperation, ValueError, TypeError, AttributeError):
            pass
        preview.update(
            status="accepted" if accepted else "rejected", received_at=datetime.now(UTC).isoformat()
        )
        self.emit("short_preview", broker_id=broker_id, status=preview["status"])

    def _oca_order(self, intent, leg, transmit=False):
        from ibapi.order import Order

        order = Order()
        order.orderId, order.action, order.orderType = leg["broker_id"], leg["action"], "STP"
        order.totalQuantity, order.auxPrice = number(leg["quantity"]), float(number(leg["stop"]))
        order.parentId, order.tif = leg["parent_id"], leg["tif"]
        order.ocaGroup, order.ocaType = leg["oca_group"], leg["oca_type"]
        order.account, order.orderRef = self._accounts[0], leg["reference"]
        order.outsideRth, order.transmit, order.triggerMethod = False, transmit, 2  # Last trade.
        if leg["purpose"] == "entry":
            order.goodTillDate = (
                datetime.fromisoformat(intent["expires_at"])
                .astimezone(UTC)
                .strftime("%Y%m%d-%H:%M:%S")
            )
        return order

    def submit_pair(self, intent):
        contract = (
            self._stock_contract(intent, entry=True)
            if intent.get("stock_plan")
            else self._oca_contract(intent["conid"])
        )
        quantity, prices = number(intent["quantity"]), intent["prices"]
        high, low = number(prices["long_entry"]), number(prices["short_entry"])
        long_stop, short_stop = number(prices["long_stop"]), number(prices["short_stop"])
        if (
            (
                not intent.get("stock_plan")
                and (quantity != quantity.to_integral_value() or not 1 <= quantity <= 10)
            )
            or not 0 < long_stop < high
            or not 0 < low < short_stop
            or low >= high
            or (
                not intent.get("stock_plan")
                and (
                    quantity * (high + low) > 1000
                    or quantity * (high - long_stop + short_stop - low) > 10
                )
            )
        ):
            raise ValueError(
                "Paired paper entries exceed combined quantity, protection or risk limits."
            )
        if (
            not 0
            < (datetime.fromisoformat(intent["expires_at"]) - datetime.now(UTC)).total_seconds()
            <= 60
        ):
            raise ValueError("The paired entry deadline expired.")
        previews = [
            p
            for p in self._short_previews.values()
            if p["conid"] == intent["conid"]
            and number(p["quantity"]) == quantity
            and number(p["price"]) == low
            and p.get("status") == "accepted"
            and p.get("epoch") == self.epoch
            and 0
            <= (datetime.now(UTC) - datetime.fromisoformat(p["received_at"])).total_seconds()
            <= 60
        ]
        borrow = self._shortable.get(intent["conid"], {})
        if (
            not previews
            or number(borrow.get("quantity", 0)) < quantity
            or not borrow.get("at")
            or not 0
            <= (datetime.now(UTC) - datetime.fromisoformat(borrow["at"])).total_seconds()
            <= 60
        ):
            raise ValueError(
                "Fresh short borrow and an accepted paper credit preview are required."
            )
        legs = pair_legs(intent)
        ids = [leg["broker_id"] for leg in legs.values()]
        if len(set(ids)) != 4 or any(i in self._oca_leg_groups for i in ids):
            raise ValueError("Paired order IDs must be unique and must not be retransmitted.")
        self._oca_filled[intent["id"]] = set()
        for name, leg in legs.items():
            self._oca_leg_groups[leg["broker_id"]] = (intent["id"], name)
        staged = {name: self._oca_order(intent, leg) for name, leg in legs.items()}
        for order in staged.values():
            self._require_paper()
            self.client.placeOrder(order.orderId, contract, copy.deepcopy(order))
        for side in ("long", "short"):
            fills = self._oca_filled[intent["id"]]
            if not fills and any(key in self._oca_terminal for key in ids):
                # A rejected/cancelled staged branch invalidates the whole pair.
                # Never release the other branch while waiting for engine callbacks.
                for direction in ("long", "short"):
                    self.cancel(legs[direction + "_entry"]["broker_id"])
                return
            if (
                (fills and side + "_entry" not in fills)
                or legs[side + "_entry"]["broker_id"] in self._oca_terminal
                or legs[side + "_stop"]["broker_id"] in self._oca_terminal
            ):
                self.cancel(legs[side + "_entry"]["broker_id"])
                continue
            protection = staged[side + "_stop"]
            protection.transmit = True
            self._require_paper()
            self.client.placeOrder(protection.orderId, contract, copy.deepcopy(protection))

    def amend_protection(self, intent, amendment):
        contract = (
            self._stock_contract(intent)
            if intent.get("stock_plan")
            else self._oca_contract(intent["conid"])
        )
        if intent.get("pair_recovery"):
            leg = {
                "broker_id": intent["broker_id"],
                "purpose": "protection",
                "action": intent["action"],
                "quantity": intent["quantity"],
                "stop": intent["stop"],
                "parent_id": 0,
                "tif": "GTC",
                "oca_type": 2,
                "oca_group": "oms-" + intent["exit_group"],
                "reference": "oms-" + intent["id"],
            }
        else:
            leg = next(
                (
                    item
                    for item in pair_legs(intent).values()
                    if item["broker_id"] == amendment["broker_id"]
                ),
                None,
            )
        if not leg or leg["purpose"] != "protection":
            raise ValueError("Only the known paired protective stop may be amended.")
        quantity, stop = number(amendment["quantity"]), number(amendment["stop"])
        if not 0 < quantity <= number(intent["quantity"]) or stop <= 0:
            raise ValueError("Protection cannot exceed the confirmed entry quantity.")
        leg.update(quantity=str(quantity), stop=str(stop))
        order = self._oca_order(intent, leg, True)
        self._require_paper()
        self.client.placeOrder(order.orderId, contract, order)
