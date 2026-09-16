"""IBKR SDK boundary. No account identifiers leave this adapter.

Callbacks only enqueue observations; the engine owns state and decisions. This
module has no import-time SDK dependency so ordinary verification is offline.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from importlib.metadata import version

SDK_VERSION = "10.50.2"
SDK_URL = "https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip"
SDK_SHA256 = "673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3"


class PaperGateway:
    def __init__(self, observations: queue.Queue, client_id=71):
        if type(client_id) is not int or not 1 <= client_id <= 999:
            raise ValueError("Use a dedicated API client number from 1 to 999.")
        self.observations = observations
        self.client_id = client_id
        self.client = None
        self.thread = None
        self.overflow = threading.Event()
        self._accounts: tuple[str, ...] = ()
        self._attested = False
        self._resume_accounts = ()
        self._pnl_requested = False
        self._next_id = None
        self._contracts = {}
        self._requests = {}
        self._history_requests = {}
        self._request_id = 1000
        self.epoch = 0
        self.sequence = 0
        self._subscription_times = {}
        self._market_rules = {}

    def emit(self, event, **payload):
        self.sequence += 1
        try:
            self.observations.put_nowait(
                {"type": event, "epoch": self.epoch, "sequence": self.sequence, **payload}
            )
        except queue.Full:
            self.overflow.set()
            self._attested = False

    @property
    def paper_context(self):
        return len(self._accounts) == 1 and bool(re.fullmatch(r"DU[0-9]+", self._accounts[0]))

    def attest(self):
        if (
            not self.paper_context
            or self._next_id is None
            or not self.client
            or not self.client.isConnected()
        ):
            raise ValueError("Complete the handshake with exactly one paper account first.")
        self._attested = True
        self._resume_accounts = self._accounts

    @property
    def can_resume_attestation(self):
        return self.paper_context and self._accounts == self._resume_accounts

    def connect(self):
        if self.thread and self.thread.is_alive():
            raise ValueError("A Gateway connection is already active.")
        if version("ibapi") != SDK_VERSION:
            raise ValueError("Install the pinned official IBKR SDK with install-paper-sdk.ps1.")
        if version("protobuf") != "5.29.6":
            raise ValueError("Install the patched SDK dependency set before connecting Gateway.")
        # SDK diagnostics can contain raw account identifiers. Deliberately sink
        # the entire SDK logger tree; the engine journals sanitized observations.
        logger = logging.getLogger("ibapi")
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper

        adapter = self

        class Client(EWrapper, EClient):
            def __init__(self):
                EWrapper.__init__(self)
                EClient.__init__(self, self)

            def nextValidId(self, orderId):
                adapter._next_id = orderId
                adapter.emit("handshake", next_id=orderId, server_version=self.serverVersion())
                self.reqManagedAccts()
                self.reqCurrentTime()

            def managedAccounts(self, accountsList):
                accounts = tuple(a.strip() for a in accountsList.split(",") if a.strip())
                if accounts != adapter._accounts:
                    adapter._attested = False
                adapter._accounts = accounts
                adapter.emit("account_context", paper=adapter.paper_context, count=len(accounts))

            def currentTime(self, time):
                adapter.emit("heartbeat", timestamp=time)

            def connectionClosed(self):
                adapter._attested = False
                adapter.emit("disconnected")

            def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=""):
                # Do not forward free-form broker messages or reject JSON.
                adapter.emit("broker_error", request=reqId, code=errorCode)

            def contractDetails(self, reqId, details):
                contract = details.contract
                if (
                    contract.secType != "STK"
                    or contract.currency != "USD"
                    or contract.primaryExchange
                    not in {"NASDAQ", "NYSE", "ARCA", "AMEX", "BATS", "IEX", "ISLAND"}
                ):
                    return
                adapter._contracts[contract.conId] = contract
                exchanges = details.validExchanges.split(",")
                rules = details.marketRuleIds.split(",")
                rule = next(
                    (
                        r
                        for e, r in zip(exchanges, rules, strict=False)
                        if e == "SMART" and r.isdigit()
                    ),
                    None,
                )
                adapter.emit(
                    "contract",
                    request=reqId,
                    symbol=contract.symbol,
                    conid=contract.conId,
                    exchange=contract.primaryExchange,
                    name=details.longName,
                    min_tick=str(details.minTick),
                    market_rule=int(rule) if rule else None,
                )
                if rule:
                    self.reqMarketRule(int(rule))

            def marketRule(self, marketRuleId, priceIncrements):
                adapter.emit(
                    "market_rule",
                    rule=marketRuleId,
                    increments=[
                        {"low": str(p.lowEdge), "increment": str(p.increment)}
                        for p in priceIncrements
                    ],
                )

            def contractDetailsEnd(self, reqId):
                adapter.emit("contracts_end", request=reqId)

            def position(self, account, contract, position, avgCost):
                adapter.emit(
                    "position",
                    own_account=account in adapter._accounts,
                    conid=contract.conId,
                    symbol=contract.symbol,
                    quantity=str(position),
                    average=str(avgCost),
                )

            def positionEnd(self):
                adapter.emit("positions_end")

            def openOrder(self, orderId, contract, order, orderState, completed=False):
                filled = Decimal(str(order.filledQuantity))
                extra = (
                    {"filled": str(filled)}
                    if filled.is_finite() and 0 <= filled <= 1000000000
                    else {}
                )
                adapter.emit(
                    "open_order",
                    completed=completed,
                    broker_id=orderId,
                    conid=contract.conId,
                    symbol=contract.symbol,
                    action=order.action,
                    quantity=str(order.totalQuantity),
                    order_type=order.orderType,
                    parent_id=order.parentId,
                    client_id=order.clientId,
                    permanent_id=order.permId,
                    own_account=order.account in adapter._accounts,
                    reference=order.orderRef
                    if re.fullmatch(r"oms-[a-f0-9]{32}", order.orderRef or "")
                    else "external",
                    limit=str(order.lmtPrice) if order.orderType == "LMT" else None,
                    status=orderState.status,
                    stop=str(order.auxPrice) if order.orderType == "STP" else None,
                    tif=order.tif,
                    oca_type=order.ocaType,
                    oca_group=order.ocaGroup
                    if re.fullmatch(r"oms-[a-f0-9]{32}", order.ocaGroup or "")
                    else "external",
                    **extra,
                )

            def openOrderEnd(self):
                adapter.emit("orders_end")

            def completedOrder(self, contract, order, orderState):
                self.openOrder(order.orderId, contract, order, orderState, True)

            def completedOrdersEnd(self):
                adapter.emit("completed_orders_end")

            def orderStatus(
                self,
                orderId,
                status,
                filled,
                remaining,
                avgFillPrice,
                permId,
                parentId,
                lastFillPrice,
                clientId,
                whyHeld,
                mktCapPrice,
            ):
                adapter.emit(
                    "order_status",
                    broker_id=orderId,
                    status=status,
                    filled=str(filled),
                    remaining=str(remaining),
                    average=str(avgFillPrice),
                    parent_id=parentId,
                    client_id=clientId,
                    permanent_id=permId,
                )

            def execDetails(self, reqId, contract, execution):
                adapter.emit(
                    "execution",
                    execution_id=execution.execId,
                    own_account=execution.acctNumber in adapter._accounts,
                    broker_id=execution.orderId,
                    client_id=execution.clientId,
                    conid=contract.conId,
                    symbol=contract.symbol,
                    side=execution.side,
                    quantity=str(execution.shares),
                    price=str(execution.price),
                )

            def execDetailsEnd(self, reqId):
                adapter.emit("executions_end")

            def accountSummary(self, reqId, account, tag, value, currency):
                if (
                    account in adapter._accounts
                    and tag in {"NetLiquidation", "AvailableFunds", "GrossPositionValue"}
                    and currency == "USD"
                ):
                    adapter.emit("account_fact", tag=tag, value=value)

            def accountSummaryEnd(self, reqId):
                self.cancelAccountSummary(reqId)
                adapter.emit("account_end")

            def commissionAndFeesReport(self, commissionAndFeesReport):
                report = commissionAndFeesReport
                adapter.emit(
                    "commission",
                    execution_id=report.execId,
                    currency=report.currency,
                    amount=str(report.commissionAndFees),
                )

            def pnl(self, reqId, dailyPnL, unrealizedPnL, realizedPnL):
                adapter.emit(
                    "daily_pnl",
                    daily=str(dailyPnL),
                    unrealized=str(unrealizedPnL),
                    realized=str(realizedPnL),
                )

            def tickByTickAllLast(
                self,
                reqId,
                tickType,
                time,
                price,
                size,
                tickAttribLast,
                exchange,
                specialConditions,
            ):
                if tickType == 1 and not tickAttribLast.pastLimit and not tickAttribLast.unreported:
                    adapter.emit(
                        "tick",
                        conid=adapter._requests.get(reqId),
                        timestamp=time,
                        price=str(price),
                        size=str(size),
                    )

            def tickPrice(self, reqId, tickType, price, attrib):
                if tickType in (1, 2) and price > 0:
                    adapter.emit(
                        "quote",
                        conid=adapter._requests.get(reqId),
                        side="bid" if tickType == 1 else "ask",
                        price=str(price),
                    )

            def marketDataType(self, reqId, marketDataType):
                adapter.emit(
                    "data_type", conid=adapter._requests.get(reqId), live=marketDataType == 1
                )

            def historicalData(self, reqId, bar):
                context = adapter._history_requests.get(reqId)
                if context:
                    adapter.emit(
                        "historical_bar",
                        request=reqId,
                        **context,
                        timestamp=str(bar.date),
                        open=str(bar.open),
                        high=str(bar.high),
                        low=str(bar.low),
                        close=str(bar.close),
                        volume=str(bar.volume),
                    )

            def historicalDataEnd(self, reqId, start, end):
                context = adapter._history_requests.pop(reqId, None)
                if context:
                    adapter.emit("history_end", request=reqId, **context)

        self._attested = False
        self._next_id = None
        self._accounts = ()
        self._requests = {}
        self._history_requests = {}
        self._pnl_requested = False
        self.epoch += 1
        self.client = Client()
        # The host and port are deliberately not configurable to other endpoints.
        self.client.connect("127.0.0.1", 4002, self.client_id)
        self.thread = threading.Thread(target=self.client.run, name="ibkr-callbacks", daemon=True)
        self.thread.start()

    def disconnect(self):
        self._attested = False
        if self.client:
            self.client.disconnect()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)

    def heartbeat(self):
        if self.client:
            self.client.reqCurrentTime()

    def reconcile(self):
        if not self.client or not self.paper_context:
            raise ValueError("A single paper account is required before reconciliation.")
        from ibapi.execution import ExecutionFilter

        self.client.cancelPositions()
        self.client.reqPositions()
        self.client.reqAllOpenOrders()
        self.client.reqCompletedOrders(False)
        self.client.reqExecutions(901, ExecutionFilter())
        self.client.reqAccountSummary(
            902, "All", "NetLiquidation,AvailableFunds,GrossPositionValue"
        )
        if not self._pnl_requested:
            self.client.reqPnL(903, self._accounts[0], "")
            self._pnl_requested = True

    def resolve(self, symbol):
        if not re.fullmatch(r"[A-Z][A-Z0-9. -]{0,14}", symbol):
            raise ValueError("Enter a US stock or ETF symbol.")
        if not self.client or self._next_id is None:
            raise ValueError("Connect Gateway before searching contracts.")
        from ibapi.contract import Contract

        contract = Contract()
        contract.symbol, contract.secType, contract.currency, contract.exchange = (
            symbol,
            "STK",
            "USD",
            "SMART",
        )
        self._request_id += 1
        self.client.reqContractDetails(self._request_id, contract)
        return self._request_id

    def subscribe(self, conid):
        if conid not in self._contracts or not self.client:
            raise ValueError("Resolve this contract first.")
        if conid in self._requests.values():
            return True
        if time.monotonic() - self._subscription_times.get(conid, -100) < 15:
            return False
        if len(set(self._requests.values())) >= 5:
            raise ValueError("Five symbol subscriptions are already active.")
        self._request_id += 1
        tick_request = self._request_id
        self._requests[tick_request] = conid
        self._request_id += 1
        quote_request = self._request_id
        self._requests[quote_request] = conid
        self.client.reqMarketDataType(1)
        self.client.reqMktData(quote_request, self._contracts[conid], "", False, False, [])
        self.client.reqTickByTickData(tick_request, self._contracts[conid], "Last", 0, False)
        self._subscription_times[conid] = time.monotonic()
        return True

    def reset_subscriptions(self):
        for index, request in enumerate(self._requests):
            if self.client:
                if index % 2 == 0:
                    self.client.cancelTickByTickData(request)
                else:
                    self.client.cancelMktData(request)
        self._requests.clear()

    def _require_paper(self):
        if (
            not self._attested
            or not self.paper_context
            or not self.client
            or not self.client.isConnected()
            or self.overflow.is_set()
        ):
            raise ValueError("Verified paper connection required. Reconcile and re-arm.")

    def unsubscribe(self, conid):
        for index, request in list(enumerate(self._requests)):
            if self._requests[request] == conid:
                if self.client:
                    if index % 2 == 0:
                        self.client.cancelTickByTickData(request)
                    else:
                        self.client.cancelMktData(request)
                del self._requests[request]

    def history(self, conid, end="", seconds=60):
        if conid not in self._contracts or not self.client or seconds not in (5, 60):
            raise ValueError("Resolve the contract before requesting candle history.")
        self._request_id += 1
        request = self._request_id
        self._history_requests[request] = {"conid": conid, "seconds": seconds}
        self.client.reqHistoricalData(
            request,
            self._contracts[conid],
            end,
            "3600 S" if seconds == 5 else "1 D",
            "5 secs" if seconds == 5 else "1 min",
            "TRADES",
            1,
            2,
            False,
            [],
        )
        return request

    def submit_exit(self, intent):
        self._require_paper()
        from ibapi.order import Order

        quantity = intent["quantity"]
        if (
            type(quantity) is not int
            or not 1 <= quantity <= 10
            or intent["conid"] not in self._contracts
        ):
            raise ValueError("A resolved owned whole-share position is required.")
        price = Decimal(intent["limit"])
        if not price.is_finite() or price <= 0:
            raise ValueError("A fresh positive exit price is required.")
        order = Order()
        order.orderId, order.action, order.totalQuantity = (
            intent["broker_id"],
            "SELL",
            Decimal(quantity),
        )
        order.orderType, order.lmtPrice = "LMT", float(Decimal(intent["limit"]))
        order.tif, order.outsideRth, order.transmit = "DAY", False, True
        order.account, order.orderRef = self._accounts[0], "oms-" + intent["id"]
        order.ocaGroup, order.ocaType = "oms-" + intent["entry_id"], 2
        self.client.placeOrder(order.orderId, self._contracts[intent["conid"]], order)

    def submit_protection(self, intent):
        self._require_paper()
        from ibapi.order import Order

        quantity = intent["quantity"]
        stop = Decimal(intent["stop"])
        if (
            type(quantity) is not int
            or not 1 <= quantity <= 10
            or not stop.is_finite()
            or stop <= 0
        ):
            raise ValueError(
                "Protection requires a confirmed whole-share quantity and positive stop."
            )
        contract = self._contracts.get(intent["conid"])
        if contract is None or contract.secType != "STK" or contract.currency != "USD":
            raise ValueError("Resolve the supported equity contract first.")
        order = Order()
        order.orderId, order.action, order.orderType = intent["broker_id"], "SELL", "STP"
        order.totalQuantity, order.auxPrice = Decimal(quantity), float(stop)
        order.tif, order.outsideRth, order.transmit = "GTC", False, True
        order.account, order.orderRef = self._accounts[0], "oms-" + intent["id"]
        order.ocaGroup, order.ocaType = "oms-" + intent["entry_id"], 2
        self.client.placeOrder(order.orderId, contract, order)

    def submit_bracket(self, intent):
        self._require_paper()
        from ibapi.order import Order

        contract = self._contracts.get(intent["conid"])
        if contract is None or contract.secType != "STK" or contract.currency != "USD":
            raise ValueError("Resolve the supported equity contract first.")
        quantity = intent["quantity"]
        if type(quantity) is not int or not 1 <= quantity <= 10:
            raise ValueError("Paper orders require 1–10 whole shares.")
        limit, stop = Decimal(intent["limit"]), Decimal(intent["stop"])
        if not 0 < stop < limit or quantity * limit > 1000 or quantity * (limit - stop) > 10:
            raise ValueError("Paper order exceeds its protection or risk limits.")
        base = intent["broker_id"]
        parent = Order()
        parent.orderId, parent.action, parent.orderType = base, "BUY", "LMT"
        parent.totalQuantity, parent.lmtPrice = Decimal(quantity), float(limit)
        deadline = datetime.fromisoformat(intent["expires_at"])
        if not 0 < (deadline - datetime.now(UTC)).total_seconds() <= 31:
            raise ValueError("The durable entry deadline has expired.")
        parent.tif, parent.transmit, parent.outsideRth = "GTD", False, False
        parent.goodTillDate = deadline.astimezone(UTC).strftime("%Y%m%d-%H:%M:%S")
        parent.account = self._accounts[0]
        parent.orderRef = "oms-" + intent["id"]
        children = []
        if intent.get("target"):
            target = Decimal(intent["target"])
            if target <= limit:
                raise ValueError("The profit target must exceed the entry limit.")
            profit = Order()
            profit.orderId, profit.orderType, profit.lmtPrice = base + 1, "LMT", float(target)
            children.append(profit)
        protection = Order()
        protection.orderId, protection.orderType, protection.auxPrice = base + 2, "STP", float(stop)
        children.append(protection)
        for child in children:
            child.action, child.totalQuantity, child.parentId = "SELL", Decimal(quantity), base
            child.tif, child.outsideRth, child.transmit = "GTC", False, child is protection
            child.account, child.orderRef = self._accounts[0], parent.orderRef
            child.ocaGroup, child.ocaType = parent.orderRef, 2
        # Durable dispatch is owned by the caller. An exception at ANY point is
        # uncertain; it must never cause automatic re-transmission of this list.
        for order in [parent, *children]:
            self._require_paper()
            self.client.placeOrder(order.orderId, contract, order)

    def cancel(self, broker_id):
        self._require_paper()
        from ibapi.order_cancel import OrderCancel

        self.client.cancelOrder(broker_id, OrderCancel())
