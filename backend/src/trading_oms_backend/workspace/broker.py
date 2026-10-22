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
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from importlib.metadata import version

from .broker_credit import PaperCredit
from .broker_crypto import PaperCrypto
from .broker_feeds import BrokerFeeds
from .broker_fx import PaperFX
from .broker_oca import PaperOCA
from .broker_snapshots import BrokerSnapshots
from .broker_stocks import PaperStocks
from .broker_valuation import BrokerValuation

SDK_VERSION = "10.50.2"
SDK_URL = "https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip"
SDK_SHA256 = "673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3"


class GatewayData(BrokerSnapshots, BrokerValuation, BrokerFeeds):
    """Read-only SDK transport. Execution exists only in the paper subclass."""

    execution_enabled = False
    crypto = False

    def __init__(self, observations: queue.Queue, client_id=71):
        if type(client_id) is not int or not 1 <= client_id <= 999:
            raise ValueError("Use a dedicated API client number from 1 to 999.")
        self.observations = observations
        self.client_id = client_id
        self.client = None
        self.thread = None
        self.overflow = threading.Event()
        self._accounts: tuple[str, ...] = ()
        self._account_change_requires_reconnect = False
        self._attested = False
        self._resume_accounts = ()
        self._pnl_requested = False
        self._next_id = None
        self._contracts = {}
        self._contract_epochs = {}
        self._requests = {}
        self._fx_requests = {}
        self._account_pending = set()
        self._snapshot_requests = {}
        self._snapshot_serial = 0
        self._request_kinds = {}
        self._search_filters = {}
        self._retired_searches = deque(maxlen=200)
        self._contract_requests = {}
        self._next_subscription = 0.0
        self._history_requests = {}
        self._request_id = 1000
        self.epoch = 0
        self.sequence = 0
        self._subscription_times = {}
        self._market_rules = {}
        self._shortable, self._short_previews = {}, {}
        self._credit_previews = {}
        self._borrow_refresh = {}
        self._oca_leg_groups, self._oca_filled = {}, {}
        self._oca_terminal = set()
        self.init_feeds()
        self.reset_snapshots()

    def emit(self, event, **payload):
        self.sequence += 1
        receipt = (
            {"received_at": datetime.now(UTC).isoformat()}
            if event
            in {
                "tick",
                "quote",
                "quote_size",
                "realtime_bar",
                "account_fact",
                "fx_midpoint",
                "fx_bidask",
            }
            else {}
        )
        try:
            self.observations.put_nowait(
                {
                    "type": event,
                    "epoch": self.epoch,
                    "sequence": self.sequence,
                    **receipt,
                    **payload,
                }
            )
        except queue.Full:
            self.overflow.set()
            self._attested = False

    @property
    def paper_context(self):
        return (
            not self._account_change_requires_reconnect
            and len(self._accounts) == 1
            and bool(re.fullmatch(r"DU[0-9]+", self._accounts[0]))
        )

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
        connection_epoch = self.epoch + 1

        class Client(EWrapper, EClient):
            def __init__(self):
                EWrapper.__init__(self)
                EClient.__init__(self, self)

            def useProtoBuf(self, msgId):
                from ibapi.message import OUT

                # SDK 10.50.2 + Gateway 226 leaves account-summary subscriptions
                # active after protobuf cancellation (322 on the third refresh).
                # The SDK's legacy cancellation was verified on that server.
                # Do not change order messages or other Gateway versions.
                if msgId == OUT.CANCEL_ACCOUNT_SUMMARY and self.serverVersion() == 226:
                    return False
                return super().useProtoBuf(msgId)

            def placeOrder(self, *args, **kwargs):
                if not adapter.execution_enabled:
                    raise ValueError("This data-only connection cannot submit orders.")
                adapter._require_paper()
                return super().placeOrder(*args, **kwargs)

            def cancelOrder(self, *args, **kwargs):
                if not adapter.execution_enabled:
                    raise ValueError("This data-only connection cannot cancel broker orders.")
                adapter._require_paper()
                return super().cancelOrder(*args, **kwargs)

            def placeOrderProtoBuf(self, *args, **kwargs):
                if not adapter.execution_enabled:
                    raise ValueError("This data-only connection cannot submit orders.")
                adapter._require_paper()
                return super().placeOrderProtoBuf(*args, **kwargs)

            def cancelOrderProtoBuf(self, *args, **kwargs):
                if not adapter.execution_enabled:
                    raise ValueError("This data-only connection cannot cancel broker orders.")
                adapter._require_paper()
                return super().cancelOrderProtoBuf(*args, **kwargs)

            def reqGlobalCancel(self, *args, **kwargs):
                raise ValueError("Global broker cancellation is not supported.")

            reqGlobalCancelProtoBuf = reqGlobalCancel

            def exerciseOptions(self, *args, **kwargs):
                raise ValueError("Option exercise is not supported.")

            exerciseOptionsProtoBuf = exerciseOptions

            def reqAutoOpenOrders(self, *args, **kwargs):
                raise ValueError("Automatic broker order binding is not supported.")

            reqAutoOpenOrdersProtoBuf = reqAutoOpenOrders

            def nextValidId(self, orderId):
                if adapter.epoch != connection_epoch:
                    return
                adapter._next_id = orderId
                adapter.emit("handshake", next_id=orderId, server_version=self.serverVersion())
                self.reqManagedAccts()
                self.reqCurrentTime()

            def managedAccounts(self, accountsList):
                if adapter.epoch != connection_epoch:
                    return
                accounts = tuple(a.strip() for a in accountsList.split(",") if a.strip())
                if accounts != adapter._accounts:
                    adapter._attested = False
                    if adapter._accounts:
                        # Uncorrelated position/order callbacks cannot be assigned
                        # safely to a different account on this transport.
                        adapter._account_change_requires_reconnect = True
                adapter._accounts = accounts
                adapter.emit("account_context", paper=adapter.paper_context, count=len(accounts))

            def currentTime(self, time):
                if adapter.epoch != connection_epoch:
                    return
                adapter.emit("heartbeat", timestamp=time)

            def connectionClosed(self):
                if adapter.epoch != connection_epoch:
                    return
                adapter._attested = False
                adapter.emit("disconnected")

            def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=""):
                if adapter.epoch != connection_epoch:
                    return
                if reqId in adapter._fx_requests:
                    adapter.fx_observation(reqId, live=False)
                    return
                if reqId in adapter._oca_leg_groups and errorCode in {
                    103,
                    105,
                    107,
                    109,
                    110,
                    111,
                    113,
                    201,
                    202,
                    320,
                    321,
                    322,
                    323,
                }:
                    # Suppress release immediately, before queued engine reconciliation.
                    adapter._oca_terminal.add(reqId)
                if reqId in adapter._credit_previews and adapter.credit_error(
                    reqId, errorCode, errorString, advancedOrderRejectJson
                ):
                    return
                if reqId in adapter._short_previews and errorCode not in {
                    2104,
                    2106,
                    2107,
                    2108,
                    2158,
                    2119,
                }:
                    adapter._short_previews[reqId]["status"] = "rejected"
                    adapter.emit("short_preview", broker_id=reqId, status="rejected")
                    return
                adapter.data_error(reqId, errorCode, errorString, advancedOrderRejectJson)

            def contractDetails(self, reqId, details):
                if adapter.epoch != connection_epoch or reqId not in adapter._search_filters:
                    return
                filters = adapter._search_filters[reqId]
                if time.monotonic() - filters.get("started", time.monotonic()) >= 30:
                    return
                if filters.get("complete"):
                    return
                if filters.get("count", 0) >= 200:
                    if not filters.get("truncated"):
                        filters["truncated"] = True
                        adapter.emit("contracts_truncated", request=reqId)
                    return
                filters["count"] = filters.get("count", 0) + 1
                contract = details.contract
                crypto = contract.secType == "CRYPTO"
                identity_valid = not filters.get("conid") or (
                    filters["conid"] == contract.conId
                    and (
                        not filters.get("symbol")
                        or filters["symbol"] in {contract.symbol, contract.localSymbol}
                    )
                    and (not filters.get("sec_type") or filters["sec_type"] == contract.secType)
                    and (not filters.get("currency") or filters["currency"] == contract.currency)
                )
                route_valid = (
                    not filters.get("exchange")
                    or filters["exchange"] == contract.exchange
                    or filters["exchange"] in details.validExchanges.split(",")
                )
                if (
                    identity_valid
                    and route_valid
                    and reqId >= adapter._contract_requests.get(contract.conId, -1)
                ):
                    adapter._contracts[contract.conId] = contract
                    adapter._contract_epochs[contract.conId] = connection_epoch
                    adapter._contract_requests[contract.conId] = reqId
                exchanges = details.validExchanges.split(",")
                rules = details.marketRuleIds.split(",")
                rule = next(
                    (
                        r
                        for e, r in zip(exchanges, rules, strict=False)
                        if e == contract.exchange and r.isdigit()
                    ),
                    None,
                )
                adapter.emit(
                    "contract",
                    request=reqId,
                    symbol=contract.symbol,
                    conid=contract.conId,
                    exchange=contract.exchange,
                    routing_exchange=contract.exchange,
                    primary_exchange=contract.primaryExchange,
                    local_symbol=contract.localSymbol,
                    expiry=contract.lastTradeDateOrContractMonth,
                    strike=str(contract.strike) if contract.right else None,
                    right=contract.right or None,
                    trading_class=contract.tradingClass,
                    multiplier=contract.multiplier or None,
                    order_types=details.orderTypes.split(","),
                    time_zone=details.timeZoneId,
                    trading_hours=details.tradingHours,
                    liquid_hours=details.liquidHours,
                    resolved=True,
                    sec_type=contract.secType,
                    currency=contract.currency,
                    name=details.longName,
                    min_tick=str(details.minTick),
                    market_rule=int(rule)
                    if rule
                    else -contract.conId
                    if crypto or contract.secType == "CASH"
                    else None,
                    min_size=str(details.minSize),
                    size_increment=str(details.sizeIncrement),
                    suggested_size_increment=str(details.suggestedSizeIncrement),
                    price_magnifier=details.priceMagnifier,
                    valid_exchanges=exchanges,
                    ineligible=bool(getattr(details, "ineligibilityReasonList", [])),
                )
                if rule:
                    self.reqMarketRule(int(rule))
                elif (crypto or contract.secType == "CASH") and 0 < Decimal(
                    str(details.minTick)
                ) < Decimal("1e12"):
                    adapter.emit(
                        "market_rule",
                        rule=-contract.conId,
                        increments=[{"low": "0", "increment": str(details.minTick)}],
                    )

            def symbolSamples(self, reqId, descriptions):
                if adapter.epoch != connection_epoch or reqId not in adapter._search_filters:
                    return
                filters = adapter._search_filters.get(reqId, {})
                for description in descriptions[:201]:
                    c = description.contract
                    if (
                        filters.get("exchange") not in {None, "", "SMART"}
                        and filters["exchange"] != c.primaryExchange
                    ):
                        continue
                    if any(
                        filters.get(k) and filters[k] != value
                        for k, value in (
                            ("sec_type", c.secType),
                            ("currency", c.currency),
                        )
                    ):
                        continue
                    adapter.emit(
                        "contract_candidate",
                        request=reqId,
                        conid=c.conId,
                        symbol=c.symbol,
                        name=getattr(description, "description", "") or c.symbol,
                        sec_type=c.secType,
                        currency=c.currency,
                        exchange=c.primaryExchange,
                        primary_exchange=c.primaryExchange,
                        resolved=False,
                    )
                adapter.emit("contracts_end", request=reqId)

            def marketRule(self, marketRuleId, priceIncrements):
                if adapter.epoch != connection_epoch:
                    return
                adapter.emit(
                    "market_rule",
                    rule=marketRuleId,
                    increments=[
                        {"low": str(p.lowEdge), "increment": str(p.increment)}
                        for p in priceIncrements
                    ],
                )

            def contractDetailsEnd(self, reqId):
                if adapter.epoch != connection_epoch or reqId not in adapter._search_filters:
                    return
                adapter._search_filters[reqId]["complete"] = True
                adapter.emit("contracts_end", request=reqId)

            def position(self, account, contract, position, avgCost):
                if adapter.epoch != connection_epoch:
                    return
                adapter.position_observation(
                    {
                        "own_account": account in adapter._accounts,
                        "conid": contract.conId,
                        "symbol": contract.symbol,
                        "quantity": str(position),
                        "average": str(avgCost),
                        "sec_type": contract.secType,
                        "currency": contract.currency,
                        "exchange": contract.exchange,
                    }
                )

            def positionMulti(self, reqId, account, modelCode, contract, pos, avgCost):
                if (
                    adapter.epoch != connection_epoch
                    or reqId not in adapter._snapshot_requests
                    or modelCode
                ):
                    return
                adapter.emit(
                    "position",
                    reconciliation_id=adapter._snapshot_requests[reqId],
                    own_account=account in adapter._accounts,
                    conid=contract.conId,
                    symbol=contract.symbol,
                    quantity=str(pos),
                    average=str(avgCost),
                    sec_type=contract.secType,
                    currency=contract.currency,
                    exchange=contract.exchange,
                )

            def positionMultiEnd(self, reqId):
                if adapter.epoch != connection_epoch or reqId not in adapter._snapshot_requests:
                    return
                self.cancelPositionsMulti(reqId)
                adapter.emit("positions_end", reconciliation_id=adapter._snapshot_requests[reqId])

            def positionEnd(self):
                if adapter.epoch != connection_epoch:
                    return
                adapter.positions_complete()

            def openOrder(self, orderId, contract, order, orderState, completed=False):
                if adapter.epoch != connection_epoch:
                    return
                if orderId in adapter._credit_previews:
                    adapter.credit_observation(orderId, contract, order, orderState)
                    return
                if orderId in adapter._short_previews:
                    adapter._preview_observation(orderId, contract, order, orderState)
                    return
                if orderId in adapter._oca_leg_groups and orderState.status in {
                    "Cancelled",
                    "ApiCancelled",
                    "Filled",
                    "Inactive",
                    "Rejected",
                }:
                    adapter._oca_terminal.add(orderId)
                    group, leg = adapter._oca_leg_groups[orderId]
                    if orderState.status == "Filled" and leg.endswith("_entry"):
                        adapter._oca_filled[group].add(leg)
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
                    trigger_method=order.triggerMethod,
                    sec_type=contract.secType,
                    currency=contract.currency,
                    routing_exchange=contract.exchange,
                    outside_rth=bool(order.outsideRth),
                    good_till_date=order.goodTillDate,
                    cash_quantity=str(order.cashQty) if order.cashQty < 1e12 else None,
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
                    if not order.ocaGroup or re.fullmatch(r"oms-[a-f0-9]{32}", order.ocaGroup)
                    else "external",
                    **extra,
                )

            def openOrderEnd(self):
                if adapter.epoch != connection_epoch:
                    return
                adapter.snapshot_end("orders_end")

            def completedOrder(self, contract, order, orderState):
                if adapter.epoch != connection_epoch:
                    return
                self.openOrder(order.orderId, contract, order, orderState, True)

            def completedOrdersEnd(self):
                if adapter.epoch != connection_epoch:
                    return
                adapter.snapshot_end("completed_orders_end")

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
                if adapter.epoch != connection_epoch:
                    return
                if orderId in adapter._short_previews or orderId in adapter._credit_previews:
                    return
                if orderId in adapter._oca_leg_groups and status in {
                    "Cancelled",
                    "ApiCancelled",
                    "Filled",
                    "Inactive",
                    "Rejected",
                }:
                    adapter._oca_terminal.add(orderId)
                    group, leg = adapter._oca_leg_groups[orderId]
                    if status == "Filled" and leg.endswith("_entry"):
                        adapter._oca_filled[group].add(leg)
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
                if adapter.epoch != connection_epoch:
                    return
                if execution.orderId in adapter._oca_leg_groups:
                    group, leg = adapter._oca_leg_groups[execution.orderId]
                    if leg.endswith("_entry"):
                        adapter._oca_filled[group].add(leg)
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
                if adapter.epoch == connection_epoch:
                    adapter.executions_complete(reqId)

            def accountSummary(self, reqId, account, tag, value, currency):
                if adapter.epoch == connection_epoch:
                    adapter.account_snapshot_fact(reqId, account, tag, value, currency)

            def accountUpdateMulti(self, reqId, account, modelCode, key, value, currency):
                if adapter.epoch == connection_epoch:
                    adapter.account_snapshot_fact(
                        reqId,
                        account,
                        key.removeprefix("$LEDGER-"),
                        value,
                        currency,
                        ledger=True,
                        model=modelCode,
                    )

            def accountUpdateMultiEnd(self, reqId):
                if adapter.epoch == connection_epoch:
                    adapter.account_snapshot_end(reqId)

            def accountSummaryEnd(self, reqId):
                if adapter.epoch == connection_epoch:
                    adapter.account_snapshot_end(reqId, summary=True)

            def commissionAndFeesReport(self, commissionAndFeesReport):
                if adapter.epoch != connection_epoch:
                    return
                report = commissionAndFeesReport
                adapter.emit(
                    "commission",
                    execution_id=report.execId,
                    currency=report.currency,
                    amount=str(report.commissionAndFees),
                )

            def pnl(self, reqId, dailyPnL, unrealizedPnL, realizedPnL):
                if adapter.epoch != connection_epoch:
                    return
                adapter.emit(
                    "daily_pnl",
                    request=reqId,
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
                    adapter.emit_feed(
                        "tick",
                        reqId,
                        timestamp=time,
                        price=str(price),
                        size=str(size),
                    )

            def tickByTickMidPoint(self, reqId, stamp, midpoint):
                if adapter.epoch == connection_epoch:
                    adapter.emit_feed("fx_midpoint", reqId, timestamp=stamp, price=str(midpoint))

            def tickByTickBidAsk(
                self, reqId, stamp, bidPrice, askPrice, bidSize, askSize, attributes
            ):
                if adapter.epoch == connection_epoch:
                    adapter.emit_feed(
                        "fx_bidask",
                        reqId,
                        timestamp=stamp,
                        bid=str(bidPrice),
                        ask=str(askPrice),
                        valid=not (attributes.bidPastLow or attributes.askPastHigh),
                    )

            def tickSize(self, reqId, tickType, size):
                if (
                    tickType in {0, 3, 5, 8, 69, 70, 71, 74}
                    and reqId in adapter._requests
                    and Decimal(str(size)) >= 0
                ):
                    side = {
                        0: "bid_size",
                        3: "ask_size",
                        5: "last_size",
                        8: "volume",
                        69: "bid_size",
                        70: "ask_size",
                        71: "last_size",
                        74: "volume",
                    }[tickType]
                    adapter.emit_feed("quote_size", reqId, side=side, value=str(size))
                if tickType == 89 and reqId in adapter._requests:
                    conid = adapter._requests[reqId]
                    quantity = Decimal(str(size))
                    if quantity.is_finite() and quantity >= 0:
                        adapter._shortable[conid] = {
                            "quantity": str(quantity),
                            "at": datetime.now(UTC).isoformat(),
                        }
                        adapter.emit("shortable", conid=conid, quantity=str(quantity))

            def tickPrice(self, reqId, tickType, price, attrib):
                if reqId in adapter._fx_requests:
                    if tickType in {1, 2} and price > 0:
                        adapter.fx_observation(
                            reqId, side="bid" if tickType == 1 else "ask", price=str(price)
                        )
                    elif tickType in {66, 67}:
                        adapter.fx_observation(reqId, live=False)
                    return
                if tickType in (1, 2, 4, 66, 67, 68) and price > 0:
                    adapter.emit_feed(
                        "quote",
                        reqId,
                        side={1: "bid", 2: "ask", 4: "last", 66: "bid", 67: "ask", 68: "last"}[
                            tickType
                        ],
                        price=str(price),
                    )

            def marketDataType(self, reqId, marketDataType):
                if reqId in adapter._fx_requests:
                    adapter.fx_observation(reqId, live=marketDataType == 1)
                    return
                adapter.emit_feed(
                    "data_type",
                    reqId,
                    live=marketDataType == 1,
                    data_type={1: "live", 2: "frozen", 3: "delayed", 4: "delayed_frozen"}.get(
                        marketDataType, "unavailable"
                    ),
                )

            def realtimeBar(self, reqId, stamp, opened, high, low, close, volume, wap, count):
                conid = adapter._requests.get(reqId)
                if conid:
                    adapter.emit_feed(
                        "realtime_bar",
                        reqId,
                        timestamp=str(stamp),
                        seconds=5,
                        open=str(opened),
                        high=str(high),
                        low=str(low),
                        close=str(close),
                        volume=str(volume)
                        if Decimal(str(volume)) >= 0 and adapter._contracts[conid].secType != "CASH"
                        else None,
                    )

            def historicalData(self, reqId, bar):
                context = adapter._history_requests.get(reqId)
                if context:
                    adapter.emit_feed(
                        "historical_bar",
                        reqId,
                        seconds=context["seconds"],
                        history_scope="extended" if context.get("use_rth") is False else "regular",
                        signal_source=context.get("signal_source"),
                        persistent=context.get("persistent", False),
                        timestamp=str(bar.date),
                        open=str(bar.open),
                        high=str(bar.high),
                        low=str(bar.low),
                        close=str(bar.close),
                        volume=str(bar.volume)
                        if Decimal(str(bar.volume)) >= 0
                        and adapter._contracts[context["conid"]].secType != "CASH"
                        else None,
                    )

            def historicalDataUpdate(self, reqId, bar):
                self.historicalData(reqId, bar)

            def historicalDataEnd(self, reqId, start, end):
                context = adapter._history_requests.get(reqId)
                if context:
                    adapter.emit_feed(
                        "history_end",
                        reqId,
                        seconds=context["seconds"],
                        history_scope="extended" if context.get("use_rth") is False else "regular",
                        signal_source=context.get("signal_source"),
                    )
                    if not context.get("persistent"):
                        adapter._history_requests.pop(reqId, None)
                        adapter.retire_feed(reqId, "completed")

        self._attested = False
        self._next_id = None
        self._accounts = ()
        self._account_change_requires_reconnect = False
        self._requests = {}
        self._fx_requests = {}
        self._account_pending = set()
        self._request_kinds = {}
        self._search_filters = {}
        self._retired_searches = deque(maxlen=200)
        self._next_subscription = 0.0
        self._history_requests = {}
        self._pnl_requested = False
        self.init_feeds()
        self.reset_snapshots()
        self.epoch += 1
        self._contract_epochs.clear()
        self._shortable.clear()
        self._short_previews.clear()
        self._credit_previews.clear()
        self._borrow_refresh.clear()
        self.client = Client()
        # The host and port are deliberately not configurable to other endpoints.
        self.client.connect("127.0.0.1", 4002, self.client_id)
        self.thread = threading.Thread(target=self.client.run, name="ibkr-callbacks", daemon=True)
        self.thread.start()

    def disconnect(self):
        self._attested = False
        if self.client:
            self.client.disconnect()
        if (
            self.thread
            and self.thread is not threading.current_thread()
            and self.thread.ident is not None
        ):
            self.thread.join(timeout=3)

    def heartbeat(self):
        if self.client:
            self.client.reqCurrentTime()

    def resolve(self, symbol="", sec_type="", exchange="", currency="", conid=None):
        if not self.client or self._next_id is None:
            raise ValueError("Connect Gateway before searching contracts.")
        if conid is not None and (type(conid) is not int or conid <= 0):
            raise ValueError("Use a positive contract ID.")
        for value in (symbol, sec_type, exchange, currency):
            if (
                not isinstance(value, str)
                or len(value) > 80
                or (value and not re.fullmatch(r"[A-Za-z0-9. /_-]+", value))
            ):
                raise ValueError("Use a symbol/name and valid contract filters.")
        if not symbol and conid is None:
            raise ValueError("Enter a symbol/name or contract ID.")
        from ibapi.contract import Contract

        self._request_id += 1
        request = self._request_id
        self._search_filters[request] = {
            "symbol": symbol,
            "conid": conid,
            "started": time.monotonic(),
            "sec_type": sec_type,
            "exchange": exchange,
            "currency": currency,
        }
        while len(self._search_filters) > 20:
            self._retired_searches.append(next(iter(self._search_filters)))
            del self._search_filters[next(iter(self._search_filters))]
        if not conid and not sec_type and not self.crypto:
            self.client.reqMatchingSymbols(request, symbol)
            return request
        contract = Contract()
        if conid:
            contract.conId = conid
            contract.exchange = exchange
        else:
            contract.symbol = symbol.upper()
            contract.secType = sec_type or ("CRYPTO" if self.crypto else "STK")
            contract.currency = currency or "USD"
            contract.exchange = exchange or (
                "PAXOS"
                if contract.secType == "CRYPTO"
                else "IDEALPRO"
                if contract.secType == "CASH"
                else "SMART"
            )
        self.client.reqContractDetails(request, contract)
        return request

    def retire_search(self, request, discarded):
        self._search_filters.pop(request, None)
        self._retired_searches.append(request)
        for conid in discarded:
            if self._contract_requests.get(conid, request) <= request:
                self._contract_requests.pop(conid, None)
                self._contracts.pop(conid, None)

    def subscribe(self, conid):
        if conid not in self._contracts or not self.client:
            raise ValueError("Resolve this contract first.")
        if conid in self._requests.values():
            return True
        clock = time.monotonic()
        if (
            clock < self._next_subscription
            or clock - self._subscription_times.get(conid, -100) < 15
        ):
            return False
        self._next_subscription = clock + 0.25
        contract = self._contracts[conid]
        for kind in (
            ("quote", "trade")
            if contract.secType in {"STK", "CRYPTO", "FUT"}
            else ("quote",)
            if contract.secType == "CASH" and contract.exchange == "IDEALPRO"
            else ("quote", "bars")
        ):
            self.start_feed(conid, kind)
        self._subscription_times[conid] = clock
        return True

    def reset_subscriptions(self):
        # A Gateway stream reset does not cancel independently paced history jobs.
        for request in tuple(self._requests):
            self.cancel_feed(request)

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
        for request in tuple(self._requests):
            if self._requests[request] == conid:
                self.cancel_feed(request)
        for request, context in tuple(self._history_requests.items()):
            if context["conid"] == conid:
                self.cancel_feed(request)
        for request, context in tuple(self._active_feeds.items()):
            if context["conid"] == conid:
                self.cancel_feed(request)
        for request, context in tuple(self._terminal_feeds.items()):
            if context["conid"] == conid and context["state"] != "cancelled":
                self.retire_feed(request, "superseded")

    def data_contract_ready(self, conid):
        return bool(
            self.client
            and self.client.isConnected()
            and conid in self._contracts
            and self._contract_epochs.get(conid) == self.epoch
        )

    def history(
        self, conid, end="", seconds=60, use_rth=True, signal_source=None, keep_up_to_date=False
    ):
        if keep_up_to_date and (end or seconds != 60 or signal_source is None):
            raise ValueError(
                "Streaming FX candles require one minute, a source and an empty end time."
            )
        if conid not in self._contracts or not self.client or seconds not in (5, 60):
            raise ValueError("Resolve the contract before requesting candle history.")
        if signal_source is not None and (
            signal_source not in {"MIDPOINT", "BID", "ASK"}
            or self._contracts[conid].secType != "CASH"
        ):
            raise ValueError("FX history requires a qualified CASH signal source.")
        self._request_id += 1
        request = self._request_id
        self._history_requests[request] = {
            "conid": conid,
            "seconds": seconds,
            "use_rth": use_rth,
            "signal_source": signal_source,
            "persistent": keep_up_to_date,
        }
        self.register_feed(
            request,
            conid,
            "history",
            seconds=seconds,
            end=end,
            use_rth=use_rth,
            signal_source=signal_source,
        )
        try:
            self.client.reqHistoricalData(
                request,
                self._contracts[conid],
                end,
                "1800 S" if keep_up_to_date else "3600 S" if seconds == 5 else "1 D",
                "5 secs" if seconds == 5 else "1 min",
                signal_source
                or (
                    "AGGTRADES"
                    if self._contracts[conid].secType == "CRYPTO"
                    else "MIDPOINT"
                    if self._contracts[conid].secType == "CASH"
                    else "TRADES"
                ),
                1 if self._contracts[conid].secType == "STK" and use_rth else 0,
                2,
                keep_up_to_date,
                [],
            )
        except Exception:
            self._history_requests.pop(request, None)
            self.retire_feed(request, "failed")
            raise
        return request


class PaxosDataGateway(GatewayData):
    crypto = True

    def __init__(self, observations, client_id=72):
        super().__init__(observations, client_id)

    def reconcile(self):
        raise ValueError(
            "Reconcile local simulation state; broker positions are not simulator holdings."
        )


class PaperGateway(PaperCredit, PaperFX, PaperCrypto, PaperOCA, PaperStocks, GatewayData):
    execution_enabled = True

    def submit_exit(self, intent):
        self._require_paper()
        from ibapi.order import Order

        quantity = (
            Decimal(str(intent["quantity"]))
            if intent.get("pair_recovery") or intent.get("stock_plan")
            else intent["quantity"]
        )
        if (
            (
                not intent.get("stock_plan")
                and not intent.get("pair_recovery")
                and type(quantity) is not int
            )
            or not (0 < quantity and (intent.get("stock_plan") or quantity <= 10))
            or intent["conid"] not in self._contracts
        ):
            raise ValueError("A resolved owned whole-share position is required.")
        if intent.get("stock_plan"):
            self._stock_contract(intent)
        elif intent.get("pair_recovery"):
            self._oca_contract(intent["conid"])
        price = Decimal(intent["limit"])
        if not price.is_finite() or price <= 0:
            raise ValueError("A fresh positive exit price is required.")
        order = Order()
        order.orderId, order.action, order.totalQuantity = (
            intent["broker_id"],
            intent.get("action", "SELL"),
            Decimal(quantity),
        )
        if order.action not in {"BUY", "SELL"}:
            raise ValueError("An exit must sell long holdings or cover short holdings.")
        order.orderType = intent.get("exit_type", "LMT") if intent.get("stock_plan") else "LMT"
        if order.orderType not in {"MKT", "LMT"}:
            raise ValueError("Unsupported stock exit type.")
        if order.orderType == "LMT":
            order.lmtPrice = float(Decimal(intent["limit"]))
        order.tif, order.outsideRth, order.transmit = "DAY", False, True
        deadline = self._stock_extended_deadline(intent)
        if deadline:
            if order.orderType != "LMT":
                raise ValueError("Pre-market exits must be approved limit orders.")
            order.tif, order.outsideRth, order.goodTillDate = "GTD", True, deadline
        order.account, order.orderRef = self._accounts[0], "oms-" + intent["id"]
        if not (intent.get("stock_plan") and intent.get("protection_type") == "locally_monitored"):
            order.ocaGroup, order.ocaType = "oms-" + intent.get("exit_group", intent["entry_id"]), 2
        self.client.placeOrder(order.orderId, self._contracts[intent["conid"]], order)

    def submit_protection(self, intent):
        self._require_paper()
        from ibapi.order import Order

        quantity = (
            Decimal(str(intent["quantity"]))
            if intent.get("pair_recovery") or intent.get("stock_plan")
            else intent["quantity"]
        )
        stop = Decimal(intent["stop"])
        if (
            (
                not intent.get("stock_plan")
                and not intent.get("pair_recovery")
                and type(quantity) is not int
            )
            or not (0 < quantity and (intent.get("stock_plan") or quantity <= 10))
            or not stop.is_finite()
            or stop <= 0
        ):
            raise ValueError(
                "Protection requires a confirmed whole-share quantity and positive stop."
            )
        contract = self._contracts.get(intent["conid"])
        if intent.get("stock_plan"):
            contract = self._stock_contract(intent, entry=intent.get("purpose", "entry") == "entry")
        elif contract is None or contract.secType != "STK" or contract.currency != "USD":
            raise ValueError("Resolve the supported equity contract first.")
        order = Order()
        order.orderId, order.action, order.orderType = (
            intent["broker_id"],
            intent.get("action", "SELL"),
            "STP",
        )
        if order.action not in {"BUY", "SELL"}:
            raise ValueError("Unsupported protective action.")
        order.totalQuantity, order.auxPrice = Decimal(quantity), float(stop)
        order.tif, order.outsideRth, order.transmit = "GTC", False, True
        order.account, order.orderRef = self._accounts[0], "oms-" + intent["id"]
        order.ocaGroup, order.ocaType = "oms-" + intent.get("exit_group", intent["entry_id"]), 2
        self.client.placeOrder(order.orderId, contract, order)

    def submit_bracket(self, intent):
        self._require_paper()
        from ibapi.order import Order

        contract = self._contracts.get(intent["conid"])
        if intent.get("stock_plan"):
            contract = self._stock_contract(intent, entry=intent.get("purpose", "entry") == "entry")
        elif contract is None or contract.secType != "STK" or contract.currency != "USD":
            raise ValueError("Resolve the supported equity contract first.")
        quantity = (
            Decimal(str(intent["quantity"])) if intent.get("stock_plan") else intent["quantity"]
        )
        if not intent.get("stock_plan") and (type(quantity) is not int or not 1 <= quantity <= 10):
            raise ValueError("Paper orders require 1–10 whole shares.")
        limit, stop = Decimal(intent["limit"]), Decimal(intent["stop"])
        if not 0 < stop < limit or (
            not intent.get("stock_plan")
            and (quantity * limit > 1000 or quantity * (limit - stop) > 10)
        ):
            raise ValueError("Paper order exceeds its protection or risk limits.")
        base = intent["broker_id"]
        parent = Order()
        parent.orderId, parent.action, parent.orderType = (
            base,
            "BUY",
            intent.get("entry_type", "LMT"),
        )
        parent.totalQuantity = Decimal(quantity)
        if parent.orderType == "LMT":
            parent.lmtPrice = float(limit)
        deadline = datetime.fromisoformat(intent["expires_at"])
        if not 0 < (deadline - datetime.now(UTC)).total_seconds() <= 31:
            raise ValueError("The durable entry deadline has expired.")
        parent.tif, parent.transmit, parent.outsideRth = "GTD", False, False
        parent.goodTillDate = deadline.astimezone(UTC).strftime("%Y%m%d-%H:%M:%S")
        if parent.orderType == "MKT":
            parent.tif, parent.goodTillDate = "DAY", ""
        parent.account = self._accounts[0]
        parent.orderRef = "oms-" + intent["id"]
        extended_deadline = self._stock_extended_deadline(intent)
        if extended_deadline:
            if parent.orderType != "LMT":
                raise ValueError("Pre-market entries must be approved limit orders.")
            parent.tif, parent.outsideRth, parent.goodTillDate = "GTD", True, extended_deadline
        if intent.get("stock_plan") and intent.get("protection_type") == "locally_monitored":
            parent.transmit = True
            self._require_paper()
            self.client.placeOrder(parent.orderId, contract, parent)
            return
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
