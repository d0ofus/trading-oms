"""Bounded, redacted data-request lifecycle at the SDK boundary.

Raw broker text is classified here and is never retained or emitted. Request IDs
are monotonically allocated within a connection; together with its epoch they
also identify the generation. Retired IDs cannot deliver observations to a retry.
"""

import threading
import time
from collections import OrderedDict
from functools import wraps

INFORMATIONAL = {2104, 2106, 2107, 2108, 2158, 2109, 2119}
REASONS = {
    "permissions": "Check this account's market-data permissions and entitlements.",
    "session_conflict": "Resolve the conflicting market-data login/session before retrying.",
    "pacing": "IBKR request pacing limit reached; waiting before retry.",
    "unavailable_data": "The requested data is unavailable; inspect contract and range support.",
    "unsupported_request": "This data request is unsupported; check contract/API capabilities.",
    "transient": "The data service is temporarily unavailable; a paced retry is scheduled.",
    "expected_cancellation": "Acknowledgment for a retired data request; no active feed changed.",
    "unknown": "The broker cause is unknown. Inspect TWS/Gateway diagnostics before retrying.",
}


def classify_data_error(code, message):
    text = str(message)[:4096].lower()
    reason = "unknown"
    if any(s in text for s in ("different ip", "another ip", "competing live session")):
        reason = "session_conflict"
    elif code in {354, 10167, 10168, 10186} or any(
        s in text for s in ("no market data permissions", "not subscribed", "permission denied")
    ):
        reason = "permissions"
    elif "pacing" in text or "max number of tick-by-tick" in text:
        reason = "pacing"
    elif any(s in text for s in ("unsupported", "not supported")):
        reason = "unsupported_request"
    elif any(s in text for s in ("query returned no data", "no historical data")):
        reason = "unavailable_data"
    elif any(s in text for s in ("temporarily unavailable", "connection broken", "timed out")):
        reason = "transient"
    return {"reason": reason, "detail": REASONS[reason]}


def synchronized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._feed_lock:
            return method(self, *args, **kwargs)

    return call


class BrokerFeeds:
    def init_feeds(self):
        if not hasattr(self, "_feed_lock"):
            self._feed_lock = threading.RLock()
        self._active_feeds = {}
        self._terminal_feeds = OrderedDict()

    @synchronized
    def register_feed(self, request, conid, kind, **parameters):
        self._active_feeds[request] = {
            "request": request,
            "conid": conid,
            "request_kind": kind,
            "generation": request,
            "parameters": parameters,
            "state": "active",
        }

    @synchronized
    def feed_context(self, request):
        return self._active_feeds.get(request) or self._terminal_feeds.get(request)

    @synchronized
    def retire_feed(self, request, state):
        context = self._active_feeds.pop(request, None) or self._terminal_feeds.pop(request, None)
        if context:
            self._terminal_feeds[request] = {**context, "state": state}
            while len(self._terminal_feeds) > 1024:
                self._terminal_feeds.popitem(last=False)

    @synchronized
    def feed_event_current(self, event):
        if event.get("epoch", self.epoch) != self.epoch:
            return False
        if "generation" not in event:
            return True  # Historical fixtures and non-data observations retain their interface.
        context = self.feed_context(event.get("request"))
        return bool(
            context
            and context["generation"] == event["generation"]
            and context["state"] in {"active", "completed"}
        )

    @synchronized
    def feed_error_current(self, event):
        if event.get("epoch", self.epoch) != self.epoch:
            return False
        if event.get("generation") is None:
            return True
        context = self.feed_context(event.get("request"))
        return bool(
            context
            and context["state"] in {"active", "failed"}
            and context["generation"] == event["generation"]
        )

    @synchronized
    def emit_feed(self, event, request, **payload):
        context = self._active_feeds.get(request)
        if context:
            self.emit(
                event,
                request=request,
                generation=context["generation"],
                conid=context["conid"],
                **payload,
            )

    @synchronized
    def data_error(self, request, code, message, advanced=""):
        from .rejections import classify_order_rejection
        from .service_status import service_diagnostic

        context = None if code in {201, 10318} else self.feed_context(request)
        diagnostic = (
            {"rejection": classify_order_rejection(message, advanced, code)}
            if code in {201, 10318}
            else classify_data_error(code, message)
        )
        if code == 399:
            # 399 is an order-message envelope, not a definite rejection code.
            # Raw text (potentially containing account data) never leaves here.
            diagnostic = {"warning": {"code": 399, "category": "unclassified_order_message"}}
        retired = bool(context and context["state"] != "active")
        if context and context["state"] == "cancelled" and code in {300, 162, 366}:
            # 162 only denotes cancellation when the message explicitly confirms it.
            if code != 162 or "cancel" in str(message)[:4096].lower():
                diagnostic = {
                    "reason": "expected_cancellation",
                    "detail": REASONS["expected_cancellation"],
                }
        self.emit(
            "broker_error",
            request=request,
            code=code,
            context="broker"
            if code in {201, 10318}
            else ("retired_data" if retired else "market_data")
            if context
            else "pnl"
            if request == getattr(self, "_pnl_request", 903) and self._pnl_requested
            else "search"
            if request in self._search_filters
            else "retired_search"
            if request in getattr(self, "_retired_searches", ())
            else "account_snapshot"
            if request in getattr(self, "_snapshot_requests", {})
            else "broker",
            conid=context["conid"] if context else None,
            request_kind=context["request_kind"] if context else "unknown",
            generation=context["generation"] if context else None,
            parameters=context["parameters"] if context else {},
            service=service_diagnostic(code, message),
            **diagnostic,
        )
        if context and not retired and code not in INFORMATIONAL | {201, 10318}:
            self.retire_feed(request, "failed")
            self._history_requests.pop(request, None)

    @synchronized
    def _retire_for_cancel(self, request):
        context = self.feed_context(request)
        if not context:
            return None
        self.retire_feed(request, "cancelled")  # Fence before the cancellation callback.
        self._requests.pop(request, None)
        self._request_kinds.pop(request, None)
        self._history_requests.pop(request, None)
        return context["request_kind"]

    def cancel_feed(self, request):
        kind = self._retire_for_cancel(request)
        if kind is None:
            return
        # Never hold the lifecycle lock while calling the SDK/socket writer.
        if self.client:
            method = {
                "trade": "cancelTickByTickData",
                "fx_midpoint": "cancelTickByTickData",
                "fx_bidask": "cancelTickByTickData",
                "quote": "cancelMktData",
                "bars": "cancelRealTimeBars",
                "history": "cancelHistoricalData",
            }[kind]
            getattr(self.client, method)(request)

    def start_feed(self, conid, kind):
        self._request_id += 1
        request = self._request_id
        contract = self._contracts[conid]
        self._requests[request], self._request_kinds[request] = conid, kind
        self.register_feed(request, conid, kind)
        try:
            self._send_feed(request, contract, kind)
        except Exception:
            self._requests.pop(request, None)
            self._request_kinds.pop(request, None)
            self.retire_feed(request, "failed")
            raise
        return request

    def _send_feed(self, request, contract, kind):
        if kind == "quote":
            self.client.reqMarketDataType(1)
            self.client.reqMktData(
                request, contract, "236" if contract.secType == "STK" else "", False, False, []
            )
        elif kind == "trade":
            self.client.reqTickByTickData(request, contract, "Last", 0, False)
        elif kind in {"fx_midpoint", "fx_bidask"}:
            if contract.secType != "CASH" or contract.exchange != "IDEALPRO":
                raise ValueError("FX observations require a resolved IDEALPRO CASH contract.")
            self.client.reqTickByTickData(
                request, contract, "MidPoint" if kind == "fx_midpoint" else "BidAsk", 0, False
            )
        else:
            self.client.reqRealTimeBars(
                request,
                contract,
                5,
                "MIDPOINT" if contract.secType == "CASH" else "TRADES",
                False,
                [],
            )

    def retry_feed(self, conid, component):
        kind = (
            "bars"
            if component == "trade"
            and self._contracts[conid].secType not in {"STK", "CRYPTO", "FUT"}
            else component
        )
        clock = time.monotonic()
        if (
            clock < self._next_subscription
            or clock - self._subscription_times.get(conid, -100) < 15
        ):
            return False
        for request in tuple(self._requests):
            if self._requests[request] == conid and self._request_kinds[request] == kind:
                self.cancel_feed(request)
        self.start_feed(conid, kind)
        self._subscription_times[conid] = clock
        self._next_subscription = clock + 0.25
        return True
