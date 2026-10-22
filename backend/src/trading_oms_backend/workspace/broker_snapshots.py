"""Single-account read subscriptions. These methods cannot transmit orders."""

import threading


class BrokerSnapshots:
    def reset_snapshots(self):
        self._snapshot_lock = threading.RLock()
        self._position_snapshot = {}
        self._positions_requested = self._positions_complete = False
        self._positions_generation = None
        self._uncorrelated = {}
        self._snapshot_requests = {}
        self._account_pending = set()
        self._pnl_request = None

    def read_request_id(self):
        # All read work uses the adapter's existing monotonic ID space.
        self._request_id += 1
        return self._request_id

    def position_observation(self, payload):
        with self._snapshot_lock:
            self._position_snapshot[payload["conid"]] = payload
            self.emit("position", **payload)

    def positions_complete(self):
        with self._snapshot_lock:
            if not self._positions_requested or self._positions_complete:
                return
            self._positions_complete = True
            self.emit("positions_end", reconciliation_id=self._positions_generation)

    def snapshot_end(self, component):
        with self._snapshot_lock:
            if component in self._uncorrelated:
                self.emit(component, reconciliation_id=self._uncorrelated.pop(component))

    def _request_accounts(self, generation):
        pending = tuple(self._account_pending)
        self._account_pending = set()  # Fence retired callbacks before cancellation.
        for request in pending:
            kind = self._request_kinds.pop(request, None)
            if kind == "account_summary":
                self.client.cancelAccountSummary(request)
            elif kind == "account_ledger":
                self.client.cancelAccountUpdatesMulti(request)
            self._snapshot_requests.pop(request, None)
        for request, kind in list(self._request_kinds.items()):
            if kind in {"account_summary", "account_ledger"}:
                self._snapshot_requests.pop(request, None)
                self._request_kinds.pop(request, None)
        summary, ledger = self.read_request_id(), self.read_request_id()
        self._account_pending = {summary, ledger}
        self._snapshot_requests.update({summary: generation, ledger: generation})
        self._request_kinds.update({summary: "account_summary", ledger: "account_ledger"})
        self.client.reqAccountSummary(
            summary,
            "All",
            "NetLiquidation,AvailableFunds,BuyingPower,AccountType,GrossPositionValue,"
            "InitMarginReq,MaintMarginReq,EquityWithLoanValue,ExcessLiquidity",
        )
        self.client.reqAccountUpdatesMulti(ledger, self._accounts[0], "", True)

    def _request_executions(self, generation):
        from ibapi.execution import ExecutionFilter

        for request in list(self._snapshot_requests):
            if self._request_kinds.get(request) == "snapshot_executions":
                self._snapshot_requests.pop(request, None)
                self._request_kinds.pop(request, None)
        request = self.read_request_id()
        self._snapshot_requests[request] = generation
        self._request_kinds[request] = "snapshot_executions"
        self.client.reqExecutions(request, ExecutionFilter())

    def reconcile(self):
        if not self.client or not self.paper_context:
            raise ValueError("A single paper account is required before reconciliation.")
        with self._snapshot_lock:
            if self._uncorrelated:
                raise ValueError("Wait for the outstanding uncorrelated account snapshot.")
            self._snapshot_serial += 1
            generation = getattr(self, "reconciliation_id", None)
            if self._positions_complete:
                for position in self._position_snapshot.values():
                    self.emit("position", reconciliation_id=generation, **position)
                self.emit("positions_end", reconciliation_id=generation)
            elif not self._positions_requested:
                self._positions_requested = True
                self._positions_generation = generation
                self.client.reqPositions()
            self._uncorrelated = {
                "orders_end": generation,
                "completed_orders_end": generation,
            }
            self.client.reqAllOpenOrders()
            self.client.reqCompletedOrders(False)
            self._request_executions(generation)
            self._request_accounts(generation)
            if not self._pnl_requested:
                self._pnl_request = self.read_request_id()
                self.client.reqPnL(self._pnl_request, self._accounts[0], "")
                self._pnl_requested = True

    def retry_reconciliation(self, missing):
        """Only correlated requests can be retried without ambiguous late markers."""
        if not self.client or not self.paper_context:
            return
        with self._snapshot_lock:
            generation = getattr(self, "reconciliation_id", None)
            if "executions_end" in missing:
                self._request_executions(generation)
            if "account_end" in missing:
                self._request_accounts(generation)

    def account_snapshot_end(self, request, summary=False):
        with self._snapshot_lock:
            if request not in self._account_pending:
                return
            self._account_pending.discard(request)
            if not self._account_pending:
                self.emit("account_end", reconciliation_id=self._snapshot_requests.get(request))
        if summary:
            self.client.cancelAccountSummary(request)
        else:
            self.client.cancelAccountUpdatesMulti(request)

    def account_snapshot_fact(
        self, request, account, tag, value, currency, *, ledger=False, model=""
    ):
        with self._snapshot_lock:
            allowed = (
                {"CashBalance", "SettledCash"}
                if ledger
                else {
                    "NetLiquidation",
                    "AvailableFunds",
                    "BuyingPower",
                    "AccountType",
                    "GrossPositionValue",
                    "CashBalance",
                    "SettledCash",
                    "InitMarginReq",
                    "MaintMarginReq",
                    "EquityWithLoanValue",
                    "ExcessLiquidity",
                }
            )
            if (
                request not in self._account_pending
                or request not in self._snapshot_requests
                or account not in self._accounts
                or not self.paper_context
                or model
                or tag not in allowed
            ):
                return
            self.emit(
                "account_fact",
                tag=tag,
                value=value,
                currency=currency,
                reconciliation_id=self._snapshot_requests[request],
            )

    def executions_complete(self, request):
        with self._snapshot_lock:
            if (
                self._request_kinds.get(request) == "snapshot_executions"
                and request in self._snapshot_requests
            ):
                self.emit("executions_end", reconciliation_id=self._snapshot_requests[request])
