"""Idempotent data-only preparation shared by every run entry point."""

import time
import uuid


class Preparation:
    def active_preparations(self, conid=None):
        self._refresh_preparation_leases()
        values = getattr(
            self, "_preparation_leases", getattr(self, "_preparation_dependencies", {})
        ).values()
        return [
            v
            for v in values
            if v.get("expires_clock", 0) > time.monotonic()
            and (conid is None or v["conid"] == conid)
        ]

    def release_preparation(self, lease_id):
        from collections import deque

        retired = getattr(self, "_retired_preparation_leases", deque(maxlen=100))
        self._retired_preparation_leases = retired
        retired.append(lease_id)
        getattr(self, "_preparation_leases", {}).pop(lease_id, None)
        self._refresh_preparation_leases()
        return {"released": True}

    def _refresh_preparation_leases(self):
        leases = getattr(self, "_preparation_leases", {})
        for key, value in list(leases.items()):
            if value["expires_clock"] <= time.monotonic():
                leases.pop(key)
        if hasattr(self, "_preparation_leases"):
            self._preparation_dependencies = {v["conid"]: v for v in leases.values()}

    def verify_paper_context(self):
        if self.attested or not self.connected or not self.broker.paper_context:
            return
        if getattr(self, "operator_disconnected", False):
            return
        self.broker.attest()  # Adapter enforces single DU account and completed handshake.
        self.attested = True
        if not getattr(self, "paper_context_token", None):
            self.paper_context_token = uuid.uuid4().hex
        self.store.event(
            "paper.context.verified", {"epoch": self.broker.epoch, "method": "adapter_guards"}
        )

    def prepare_context(
        self,
        conid,
        session_mode="regular",
        strategy_id=None,
        version=None,
        lease_id=None,
        execution_policy=None,
    ):
        if lease_id in getattr(self, "_retired_preparation_leases", ()):
            return {"status": "cancelled", "detail": "Preparation was closed."}
        if getattr(self, "operator_disconnected", False):
            return {
                "status": "blocked",
                "detail": "Operator disconnected. Connect to resume preparation.",
            }
        if not self.connected:
            if not self.requested_connection:
                self.connect()
            return {
                "status": "checking",
                "detail": "Waiting for the configured paper Gateway handshake.",
            }
        self.verify_paper_context()
        if not self.attested:
            return {"status": "blocked", "detail": "A verified single paper account is required."}
        contract = self.contracts.get(conid)
        if not contract or contract.get("resolved") is False:
            return {
                "status": "blocked",
                "detail": "Select an exact resolved contract; ambiguous listings need a selection.",
            }
        if strategy_id is not None:
            from .stock_strategies import requirements

            published = self.store.version(strategy_id, version)
            if published["document"]["schema_version"] == 9:
                from .fx_policy import compatibility

                result = compatibility(
                    contract, published["document"], "locally_monitored", execution_policy
                )
                if result["plan"] is None:
                    return {"status": "blocked", "detail": " ".join(result["blockers"])}
                self._fx_prepare_data(
                    conid, published["document"]["settings"]["signal_source"], execution_policy
                )
            if published["document"]["schema_version"] in (7, 8, 9):
                if published["document"]["schema_version"] == 9:
                    from .fx_strategies import requirements
                dependencies = getattr(self, "_preparation_dependencies", {})
                if len(dependencies) >= 20 and conid not in dependencies:
                    dependencies.pop(next(iter(dependencies)))
                dependencies[conid] = {
                    "conid": conid,
                    "expires_clock": time.monotonic() + 30,
                    "binding": {
                        "execution_plan": {
                            "policy": execution_policy,
                            "requirements": requirements(published["document"]),
                            "session_mode": session_mode,
                            **(
                                {
                                    "signal_source": published["document"]["settings"][
                                        "signal_source"
                                    ]
                                }
                                if published["document"]["schema_version"] == 9
                                else {}
                            ),
                        }
                    },
                }
                self._preparation_dependencies = dependencies
                if lease_id:
                    leases = getattr(self, "_preparation_leases", {})
                    if len(leases) >= 20 and lease_id not in leases:
                        leases.pop(next(iter(leases)))
                    leases[lease_id] = dependencies[conid]
                    self._preparation_leases = leases
                    self._refresh_preparation_leases()
        if conid not in self.data:
            self.subscribe(conid)
        if session_mode == "premarket_regular":
            self._premarket_queue(conid)
        if contract["currency"] != "USD" and hasattr(self.broker, "subscribe_fx"):
            self.broker.subscribe_fx(contract["currency"])
        fee_currency = getattr(self, "account_base_currency", None)
        if (
            contract.get("sec_type") == "CASH"
            and fee_currency
            and fee_currency != "USD"
            and hasattr(self.broker, "subscribe_fx")
        ):
            self.broker.subscribe_fx(fee_currency)
        if contract.get("sec_type") == "STK":
            self._resolve_stock_rules(conid, automatic=True)
        if not self.reconcile_inflight and (
            not self.reconciled or time.monotonic() - self.reconciled_at > 15
        ):
            self.begin_reconcile()
        return {
            "status": "checking",
            "detail": (
                "Subscriptions, required history, contract evidence and "
                "account reconciliation are managed automatically."
            ),
        }
