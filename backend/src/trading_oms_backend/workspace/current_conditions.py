"""Current relevance of durable episodes; historical records are not readiness."""

import time

from .incidents import CONTRACT_CODES, ROUTINE, SERVICE_RECOVERY, affects


def classification(code):
    if code == "broker_notice":
        return "diagnostic", "info"
    if (
        code in CONTRACT_CODES
        or code in SERVICE_RECOVERY
        or code in {"connectivity", "broker_2110", "data_request_failure"}
    ):
        return "operational", "warning"
    if code in {"run_configuration", "broker_credit_shortfall"}:
        return "requirement", "warning"
    return "critical", "critical"


class CurrentConditions:
    def current_condition(self, item, runs=None, db=None):
        code = item["code"]
        category, severity = classification(code)
        dependencies = (
            self._data_dependencies(db)
            if category == "operational" or item["scope"]["type"] not in {"account", "workspace"}
            else {"runs": [], "priority": set()}
        )
        selected = runs if runs is not None else dependencies["runs"] + self.active_preparations()
        relevant = item["scope"]["type"] in {"account", "workspace"} or any(
            affects(item, r) for r in selected
        )
        if category == "diagnostic":
            relevant = False
        if code in {"watchdog", "clock_skew"} and item.get("instance") != self.process_identity:
            # Current watchdog and clock health are independent startup checks.
            relevant = False
        if item["scope"]["type"] == "contract":
            conid = int(item["scope"]["key"])
            optional_history = (
                "history" in code
                or code == "data_request_failure"
                and "history" in (item.get("diagnostic") or {}).get("operation", "")
            ) and not any(
                self._requires_downloaded_history(r) for r in selected if r.get("conid") == conid
            )
            relevant = relevant or conid in dependencies["priority"] and not optional_history
        if code in SERVICE_RECOVERY or code in {"connectivity", "broker_2110"}:
            # A service observation without an execution/preparation dependency
            # belongs in diagnostics. Connection progress has its own status.
            relevant = bool(selected or dependencies["priority"])
            if code == "broker_2105":
                relevant = any(self._requires_downloaded_history(r) for r in selected)
            elif code == "broker_2157":
                relevant = any(
                    not self.contracts.get(r.get("conid"), {}).get("resolved") for r in selected
                )
        active = relevant and item["restriction"] != "released"
        return {
            **item,
            "category": category,
            "severity": severity,
            "current_relevance": "required" if relevant else "diagnostic_only",
            "actionable": active,
            "blocking_stages": ["authorization", "dispatch"] if active else [],
            "automatic_recovery": category != "critical" or code in ROUTINE,
            "evidence_revision": getattr(self, "_evidence_revision", 0),
            "remediation": {
                "automatic": category != "critical",
                "action": "inspect_orders" if item.get("order_context") else "inspect_condition",
                "detail": item.get("recovery_detail") or item["detail"],
            },
        }

    @staticmethod
    def _requires_downloaded_history(run):
        plan = (run.get("binding") or {}).get("execution_plan", {})
        if plan.get("policy") == "idealpro_broker_candles_v2":
            return True
        if (
            plan.get("kind") == "fx_breakout"
            or plan.get("signal_source")
            or plan.get("requirements", {}).get("kind") in {"fx_breakout", "stock_breakout"}
        ):
            return False
        return plan.get("requirements", {}).get("history", True)

    def _conclusive_recovery(self, item, db):
        """Never infer a submitted order's outcome from its absence."""
        code = item["code"]
        if code in ROUTINE | SERVICE_RECOVERY.keys() | CONTRACT_CODES:
            return True
        if code == "engine_fault":
            return self.corrected_fault_recoverable(item, db)
        if code in {
            "order_uncertain",
            "dispatch_uncertain",
            "protection_uncertain",
            "protection_rejected",
            "broker_201",
        }:
            from .protection import ACTIVE, TERMINAL, order_ids

            context = item.get("order_context") or {}
            orders = self.store.orders()
            if context.get("order_id"):
                orders = [o for o in orders if o["id"] == context["order_id"]]
            if not orders:
                return False
            return all(
                o["state"] in {"filled", "cancelled", "rejected", "working"}
                and all(
                    (
                        (self.broker_orders.get(i) or {}).get("status") in TERMINAL | ACTIVE
                        and not (self.broker_orders.get(i) or {}).get("status_conflict")
                    )
                    or (
                        o["state"] == "rejected"
                        and i == o["broker_id"]
                        and self.reconciled
                        and bool(self.store.get("quantity_rejection_reconciled", o["id"]))
                        and not self.broker_orders.get(i)
                    )
                    for i in ({context["broker_id"]} if context.get("broker_id") else order_ids(o))
                )
                for o in orders
            )
        # A completed successful post-failure reconciliation explicitly checks
        # these invariants (including protection and fill/ownership agreement).
        return code in {
            "missing_protection",
            "fx_account_balance",
            "fx_ownership",
            "broker_credit_shortfall",
            "account_context",
            "foreign_account",
            "execution_conflict",
            "unknown_order",
            "external_order",
            "premarket_exit_pending",
            "callback_overflow",
            "monitoring_unavailable",
            "clock_skew",
        } and bool(self.reconciled and time.monotonic() - self.reconciled_at < 30)
