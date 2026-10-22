"""Paper FX binding, authorization and serialized entry/protection/exit lifecycle."""

import copy
import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .authorization import RESUME_POLICY
from .credit import CreditPending
from .credit_policy import bind_credit, broker_credit, buying_power_policy
from .fx_data import FXData, recent
from .fx_ledger import ledger, serialized
from .fx_policy import BROKER_CANDLES, compatibility, size_fx
from .fx_sessions import FXSession
from .graph import digest, number
from .oca import price_increment, protection_price, rounded
from .paper_risk import ceiling
from .signal_outcomes import SignalOutcomes
from .stock_policy import fx_rate
from .store import Conflict, now

TERMINAL = {"filled", "cancelled", "rejected"}


class FXController(FXData, SignalOutcomes):
    def _fx_record_warning(self, event):
        order = next(
            (
                o
                for o in self.store.orders()
                if o["broker_id"] == event["request"]
                and o["payload"].get("execution") == "fx_breakout"
            ),
            None,
        )
        if not order:
            return False
        from .fx_order_evidence import audited_update, ensure_backup

        ensure_backup(self.store)
        previous = self.store.get("fx_order_warning", order["id"])
        if not previous or previous.get("state") != "awaiting_confirmation":
            warning = {
                "code": 399,
                "state": "awaiting_confirmation",
                "observed_at": now(),
                "detail": "Broker message 399; awaiting authoritative order confirmation. "
                "Original message is unclassified.",
            }
            audited_update(self.store, "fx_order_warning", order["id"], warning, "fx.order.warning")
            self.invalidate_reconciliation()
        return True

    def _fx_confirm_warning(self, broker_id, observed):
        from .fx_order_evidence import audited_update

        order = next(
            (
                o
                for o in self.store.orders()
                if o["broker_id"] == broker_id and o["payload"].get("execution") == "fx_breakout"
            ),
            None,
        )
        if not order:
            return
        warning = self.store.get("fx_order_warning", order["id"])
        if (
            not warning
            or warning.get("state") != "awaiting_confirmation"
            or observed.get("status_conflict")
        ):
            return
        status = observed.get("status")
        if self._fx_identity(order, observed) or status not in {
            "Submitted",
            "PreSubmitted",
            "Filled",
            "Rejected",
            "Cancelled",
            "ApiCancelled",
        }:
            return
        state = "rejected" if status == "Rejected" else "confirmed"
        updated = {
            **warning,
            "state": state,
            "confirmed_at": now(),
            "broker_status": status,
            "detail": f"Broker confirmed {status}. The original message 399 remains unclassified.",
        }
        audited_update(
            self.store, "fx_order_warning", order["id"], updated, "fx.order.warning_outcome"
        )

    def _fx_warning_view(self, order):
        warning = self.store.get("fx_order_warning", order["id"])
        return warning

    def _fx_note_account_evidence(self, run_id):
        proof = getattr(self, "_fx_account_evidence", {})
        proof[run_id] = (self.broker.epoch, getattr(self, "paper_context_token", None))
        self._fx_account_evidence = proof

    def _fx_account_ready(self, run):
        return getattr(self, "_fx_account_evidence", {}).get(run["id"]) == (
            self.broker.epoch,
            getattr(self, "paper_context_token", None),
        )

    def _fx_order_account_evidence(self, event):
        order = next(
            (
                o
                for o in self.store.orders()
                if o["broker_id"] == event["broker_id"]
                and o["payload"].get("execution") == "fx_breakout"
            ),
            None,
        )
        if order and not self._fx_identity(order, event):
            self._fx_note_account_evidence(order["run_id"])

    @staticmethod
    def _fx_run(run):
        return bool(
            run and (run.get("binding") or {}).get("execution_plan", {}).get("family") == "spot_fx"
        )

    def fx_compatibility(
        self,
        strategy_id,
        version,
        conid,
        protection_type="broker_held",
        session_mode="fx",
        sizing=None,
        funding_policy=None,
        execution_policy=None,
    ):
        published = self.store.version(strategy_id, version)
        contract = self._fx_contract_evidence(conid)
        result = compatibility(contract, published["document"], protection_type, execution_policy)
        result["plan"] = bind_credit(result["plan"], funding_policy)
        result["funding_policy"] = funding_policy
        result["credit_status"] = "automatic_on_review" if funding_policy else "legacy_cash"
        result["refresh_status"] = {"metadata_current": self._fx_metadata_ready(conid)}
        if result["plan"]:
            try:
                values = self._fx_sizing(
                    published["document"]["settings"], sizing or {}, result["plan"]
                )
                ask = self._fx_cache(conid).get("fx_bidask", {}).get("ask")
                if ask and self._fx_feed_health(conid)["execution_fresh"]:
                    reserve = self._fx_funding(result["plan"], values)
                    result["indicative_sizing"] = {
                        **reserve,
                        "notional_usd": reserve["notional"],
                        "stop_risk_usd": reserve["risk"],
                    }
            except Conflict as exc:
                result["arming_requirements"].append(str(exc))
        result["arming_requirements"].append(
            "Current FX session, established subscriptions, required history and reconciled "
            "account evidence are required to authorize. Fresh signal, bid/ask and broker "
            "buying power remain required before entry."
            if funding_policy
            else "Current FX session, fresh selected signal and bid/ask, real currency balances "
            "and reconciliation are required."
        )
        return result

    def _fx_sizing(self, settings, values, plan):
        if set(values) - {"quantity", "notional", "risk", "sizing"}:
            raise Conflict(
                "FX sizing uses explicit base-currency quantity, not shares or a cash budget."
            )
        result = {
            "quantity": plan["rules"]["minimum_quantity"],
            "sizing": "fixed",
            "notional": settings["notional"],
            "risk": settings["risk"],
            **values,
        }
        if result["sizing"] != "fixed":
            raise Conflict("The initial FX policy requires an explicit base-currency quantity.")
        for field in ("notional", "risk"):
            value, published = ceiling(result[field]), ceiling(settings[field])
            if published is not None and (value is None or value > published):
                raise Conflict("FX sizing cannot remove or increase a published ceiling.")
            result[field] = str(value) if value is not None else None
        quantity = number(result["quantity"])
        rules = plan["rules"]
        if (
            quantity < number(rules["minimum_quantity"])
            or quantity % number(rules["quantity_increment"])
            or rules["maximum_quantity"]
            and quantity > number(rules["maximum_quantity"])
        ):
            raise Conflict(
                "Requested base-currency quantity violates the broker minimum or increment."
            )
        self._fx_quantity_guard(plan, quantity)
        result["quantity"] = str(quantity)
        return result

    def _fx_quantity_guard(self, plan, quantity):
        observed = self.store.get("quantity_restriction", str(plan["conid"]) + ":IDEALPRO:MKT:IOC")
        if observed and quantity != quantity.to_integral_value():
            raise Conflict(
                "Broker rejected fractional base-currency quantity (10318) for this IDEALPRO "
                "MKT/IOC contract. Review an explicit whole-unit quantity."
            )

    def _fx_binding(
        self,
        published,
        conid,
        sizing,
        protection,
        revision,
        funding_policy=None,
        execution_policy=None,
    ):
        result = self.fx_compatibility(
            published["strategy_id"],
            published["version"],
            conid,
            protection,
            sizing=sizing,
            funding_policy=funding_policy,
            execution_policy=execution_policy,
        )
        if not result["can_prepare"]:
            raise Conflict(" ".join(result["blockers"]))
        plan = result["plan"]
        if revision != plan["hash"]:
            raise Conflict("Review the current FX execution plan before preparation.")
        binding = {
            "contract": copy.deepcopy(self.contracts[conid]),
            "sizing": self._fx_sizing(published["document"]["settings"], sizing or {}, plan),
            "strategy_hash": published["hash"],
            "session_policy": plan["session_policy"],
            "session_mode": "fx",
            "execution_plan": plan,
        }
        binding["hash"] = digest(binding)
        return binding

    def _fx_binding_valid(self, run):
        published = self.store.version(run["strategy_id"], run["version"])
        plan = run["binding"]["execution_plan"]
        current = compatibility(
            self._fx_contract_evidence(run["conid"]),
            published["document"],
            plan["protection_type"],
            plan["policy"],
        )
        current["plan"] = bind_credit(current["plan"], plan.get("funding_policy"))
        return bool(
            current["plan"]
            and current["plan"]["hash"] == plan["hash"]
            and published["hash"] == run["binding"]["strategy_hash"]
            and run["binding"]["hash"]
            == digest({k: v for k, v in run["binding"].items() if k != "hash"})
        )

    def _fx_contract_evidence(self, conid):
        contract = dict(self.contracts.get(conid, {}))
        contract["price_rules"] = self.market_rules.get(contract.get("market_rule"), [])
        return contract

    def _fx_metadata_ready(self, conid):
        c = self.contracts.get(conid, {})
        try:
            future = any(end > datetime.now(UTC) for _, end in FXSession(c).broker_intervals)
        except ValueError:
            future = False
        ready = (
            future
            and c.get("metadata_instance") == self.process_identity
            and c.get("metadata_epoch") == self.broker.epoch
            and c.get("market_rule") in self.market_rules
            and getattr(self, "_stock_market_rule_context", {}).get(c.get("market_rule"))
            == (self.process_identity, self.broker.epoch)
        )
        if not ready and self.connected and hasattr(self.broker, "resolve"):
            pending = getattr(self, "_fx_metadata_pending", {})
            if time.monotonic() >= pending.get(conid, 0):
                pending[conid] = time.monotonic() + 30
                self.broker.resolve(
                    symbol=c.get("symbol", ""),
                    sec_type="CASH",
                    exchange="IDEALPRO",
                    currency=c.get("currency", ""),
                    conid=conid,
                )
            self._fx_metadata_pending = pending
        return ready

    def _fx_cash(self, currency):
        values = [
            self.currency_facts.get((tag, currency)) for tag in ("CashBalance", "SettledCash")
        ]
        if any(not value or not recent(value.get("received_at"), 30) for value in values):
            raise Conflict(
                f"Fresh real and settled {currency} cash balances are required; "
                "no borrowing is enabled."
            )
        return min(number(value["value"]) for value in values) - self._fx_owned_currency(currency)

    def _fx_owned_currency(self, currency):
        return sum(
            (
                position["quantity"]
                for key, position in self.owned().items()
                if self._fx_run(self.store.get("run", key))
                and self.store.get("run", key)["binding"]["execution_plan"]["base_currency"]
                == currency
            ),
            Decimal(0),
        )

    def _fx_funding(self, plan, sizing, exclude=None, evaluated_at=None):
        self._fx_quantity_guard(plan, number(sizing["quantity"]))
        quote = self._fx_cache(plan["conid"]).get("fx_bidask", {})
        if not self._fx_quote_evaluation(plan["conid"], evaluated_at)["fresh"]:
            raise Conflict("Fresh timestamped FX bid/ask observations are required for funding.")
        rate = fx_rate(plan["currency"], self.fx_quotes.values())
        ask = number(quote["ask"])
        modern_credit = broker_credit(plan)
        native_cash = None if modern_credit else self._fx_cash(plan["currency"])
        reservations = [
            r
            for r in self.store.list("reservation")
            if r.get("active") and r.get("run_id") != exclude
        ]
        reserved = sum(
            (
                number(
                    r.get("currency_reserves", {}).get(
                        plan["currency"],
                        r.get("native_funds", 0) if r.get("currency") == plan["currency"] else 0,
                    )
                )
                for r in reservations
            ),
            Decimal(0),
        )
        # Public first-tier FX commission: 0.20 basis points, USD 2 minimum per order.
        # Reserve both entry and exit; no volume discount is assumed.
        fee_usd = max(Decimal(2), number(sizing["quantity"]) * ask * rate * Decimal("0.00002")) * 2
        fee_currency = getattr(self, "account_base_currency", None)
        if not fee_currency:
            raise Conflict("Broker account base currency is required to reserve FX commissions.")
        quote_fee_rate = fx_rate(plan["currency"], self.fx_quotes.values(), liability=False)
        fee_rate = fx_rate(fee_currency, self.fx_quotes.values(), liability=False)
        fee_native = fee_usd / fee_rate
        result = size_fx(
            plan,
            sizing,
            ask,
            rate,
            None if modern_credit else native_cash - reserved,
            fee_usd / quote_fee_rate if fee_currency == plan["currency"] else Decimal(0),
        )
        currency_reserves = {plan["currency"]: result["native_funds"]}
        if plan["currency"] != fee_currency:
            usd_reserved = sum(
                (
                    number(
                        r.get("currency_reserves", {}).get(
                            fee_currency,
                            r.get("native_funds", 0) if r.get("currency") == fee_currency else 0,
                        )
                    )
                    for r in reservations
                ),
                Decimal(0),
            )
            if not modern_credit and self._fx_cash(fee_currency) - usd_reserved < fee_native:
                raise Conflict(
                    f"Usable {fee_currency} cash is required for FX commission; "
                    "automatic currency conversion is disabled."
                )
            currency_reserves[fee_currency] = str(fee_native)
        result.update(
            currency_reserves=currency_reserves,
            fee_policy="ibkr_fx_first_tier_2026_09",
            fee_reserve_usd=str(fee_usd),
            fee_reserve_native=str(fee_native),
            fee_currency=fee_currency,
            funding_snapshot={
                currency: str(self._fx_cash(currency)) for currency in currency_reserves
            }
            if not modern_credit
            else {},
            funding_revision=getattr(self, "_evidence_revision", 0),
            checked_at=now(),
        )
        if modern_credit:
            return self._credit_assess(
                plan,
                result,
                [
                    {
                        "action": "BUY",
                        "order_type": "MKT",
                        "quantity": result["quantity"],
                        "tif": "IOC",
                        "outside_rth": True,
                        "price": str(ask),
                    }
                ],
                exclude,
            )
        return result

    def _fx_settle_reservations(self):
        # Settled purchase cost is already reflected in current cash. Retain
        # allocation/risk capacity and an exit commission reserve until flat.
        if not self.reconciled:
            return
        with self.store.transaction() as db:
            for order in self.store.orders():
                if (
                    order["payload"].get("execution") != "fx_breakout"
                    or order["state"] not in TERMINAL
                ):
                    continue
                reservation = self.store.read(db, "reservation", order["id"])
                if (
                    not reservation
                    or not reservation.get("active")
                    or reservation.get("purchase_settled")
                ):
                    continue
                currency = reservation["fee_currency"]
                fee = number(reservation["fee_reserve_native"]) / 2
                reservation.update(currency_reserves={currency: str(fee)}, purchase_settled=True)
                self.store.write(db, "reservation", order["id"], reservation)
                self.store.append(
                    db,
                    "fx.reservation.cash_settled",
                    {
                        "order_id": order["id"],
                        "currency": currency,
                        "remaining_fee_reserve": str(fee),
                        "allocation_capacity_retained": True,
                    },
                )

    def _fx_healthy_wait(self, run):
        return self._fx_feed_health(run["conid"], run)["feed_health"] == "healthy"

    def _fx_checks(self, run, dispatch=False):
        from .engine import check

        plan = run["binding"]["execution_plan"]
        health = self._fx_feed_health(run["conid"], run)
        quiet_policy = plan.get("authorization_policy") == "quiet_fx_v1"
        can_wait = quiet_policy and health["feed_health"] == "healthy"
        session = self._fx_session(run).tradable(datetime.now(UTC))
        bounds = self._fx_session(run).bounds(datetime.now(UTC))
        settings = self.store.version(run["strategy_id"], run["version"])["document"]["settings"]
        entry_open = bool(
            bounds
            and datetime.now(UTC) < bounds[1] - timedelta(minutes=settings["exit_before_close"])
        )
        checks = [
            check(
                "fx_policy",
                "Paper FX execution enabled",
                os.environ.get("OMS_DISABLE_FX_ARM") != "1"
                and (
                    plan["policy"] != BROKER_CANDLES
                    or os.environ.get("OMS_DISABLE_FX_BROKER_CANDLES_ARM") != "1"
                ),
                "New FX arming is disabled by the rollback setting.",
            ),
            check(
                "verified_build",
                "Verified application build",
                self.code_verified,
                "Run the verification gate for this build.",
            ),
            check(
                "fx_binding",
                "Approved FX contract and policy",
                self._fx_binding_valid(run),
                "Contract identity or execution policy changed; prepare a new binding.",
            ),
            check(
                "fx_metadata",
                "Current FX broker rules",
                self._fx_metadata_ready(run["conid"]),
                "Waiting for current contract metadata and price increments.",
            ),
            check(
                "fx_session",
                "FX session open",
                session,
                "Waiting for the qualified broker FX session.",
            ),
            check(
                "fx_entry_window",
                "FX entry window open",
                entry_open,
                "Wait for an eligible FX session before its published session-exit window.",
            ),
            check(
                "fx_data",
                "FX feed and history",
                health["execution_fresh"],
                health["execution_detail"],
            ),
        ]
        data_check = checks[-1]
        data_check.update(stable=True, authorization_ready=health["execution_fresh"])
        execution_state, execution_detail = self._fx_execution_status(health, run)
        data_check.update(
            feed_health=health["feed_health"],
            execution_state=execution_state,
            observation_ages=health["ages"],
            evaluated_at=health["evaluated_at"],
            structural_valid=health["structural_valid"],
            freshness_reason=health["freshness_reason"],
            signal_source=plan["signal_source"],
            execution_detail=execution_detail,
        )
        if not health["execution_fresh"]:
            data_check.update(
                status="waiting" if can_wait else "blocked",
                remediation=None,
                authorization_ready=bool(can_wait and not dispatch),
            )
        if self._fx_uses_broker_candles(run):
            stream = self._fx_source(run["conid"], plan["signal_source"])
            checks.append(
                check(
                    "fx_candle_stream",
                    "Broker one-minute candle stream",
                    bool(
                        stream.get("persistent")
                        and stream.get("bootstrap")
                        and stream.get("status") == "completed"
                        and stream.get("epoch") == self.broker.epoch
                    ),
                    stream.get("detail") or "Waiting for the broker candle subscription.",
                )
            )
        if self._fx_uses_broker_candles(run):
            reference_ready = bool(self._fx_broker_reference(run, datetime.now(UTC)))
            requirement = check(
                "fx_reference",
                "Completed broker reference minute",
                reference_ready,
                "Waiting for completed broker candle.",
            )
            requirement.update(
                stable=True,
                authorization_ready=not dispatch,
                status="ready" if reference_ready else "waiting",
                remediation=None,
            )
            checks.append(requirement)
        funding_title = (
            "Broker buying power and quantity"
            if broker_credit(plan)
            else "Funded base-currency quantity"
        )
        try:
            if broker_credit(plan):
                self._credit_account(buying_power=buying_power_policy(plan))
            if not health["execution_fresh"]:
                checks.append(
                    {
                        **check(
                            "fx_funding", funding_title, False, "Waiting for quote evidence.", None
                        ),
                        "status": "waiting",
                        "stable": True,
                        "depends_on": "fx_data",
                        "authorization_ready": bool(can_wait and not dispatch),
                    }
                )
                reserve = None
            else:
                reserve = self._fx_funding(
                    plan,
                    run["binding"]["sizing"],
                    run["id"] if dispatch else None,
                    datetime.fromisoformat(health["evaluated_at"]),
                )
            if reserve is not None:
                checks.append(
                    check(
                        "fx_funding",
                        funding_title,
                        True,
                        f"Funding {reserve['native_funds']} {plan['currency']}; "
                        f"commission reserve {reserve['fee_reserve_native']} "
                        f"{reserve['fee_currency']} "
                        "(included in funding when the currencies match).",
                    )
                )
                checks[-1]["funding"] = {
                    k: reserve[k]
                    for k in (
                        "funding_mode",
                        "credit_status",
                        "funding_revision",
                        "credit_reserve",
                        "maintenance_reserve",
                        "buying_power_allocation",
                        "buying_power_allocation_native",
                        "allocation_currency",
                    )
                    if k in reserve
                }
                if broker_credit(plan):
                    allocation = reserve.get(
                        "buying_power_allocation", reserve.get("credit_reserve")
                    )
                    checks[-1]["detail"] += (
                        f" Funding: {reserve['funding_mode']}; "
                        f"USD {allocation} "
                        "buying power allocated."
                    )
        except (ValueError, TypeError, KeyError) as exc:
            status = getattr(exc, "status", "blocked")
            checks.append(
                {
                    **check("fx_funding", funding_title, False, str(exc), None),
                    "status": status,
                    "stable": True,
                    "authorization_ready": False,
                }
            )
            if broker_credit(plan) and status in {"blocked", "unsupported"}:
                checks[-1]["detail"] += (
                    " Review the broker account diagnostics in Settings "
                    "before changing quantity or funding."
                )
                checks[-1]["remediation"] = "/settings"
            # A price-dependent credit preview is automatic work. Account evidence
            # itself must already be complete before quiet authorization.
            if isinstance(exc, CreditPending) and "credit preview" in str(exc):
                checks[-1]["authorization_ready"] = bool(can_wait and not dispatch)
        checks[-1]["stable"] = True
        if not dispatch:
            orders = [o for o in self.store.orders() if o["run_id"] == run["id"]]
            flat = not number(self.owned().get(run["id"], {}).get("quantity", 0))
            clear = flat and not any(o["state"] not in TERMINAL for o in orders)
            clear = clear and not any(
                r.get("active") and r.get("run_id") == run["id"]
                for r in self.store.list("reservation")
            )
            checks.append(
                check(
                    "fx_ownership",
                    "FX ownership reconciled",
                    clear and not run.get("armed"),
                    "Disarm and reconcile previous orders and currency allocations "
                    "before a new authorization.",
                )
            )
        for item in checks:
            item["scope"] = {"type": "run", "key": run["id"]}
            item["evidence_revision"] = getattr(self, "_evidence_revision", 0)
            item["blocking_stages"] = (
                [] if item.get("authorization_ready", item["passed"]) else ["authorization"]
            ) + ([] if item["passed"] else ["dispatch"])
            if not item["passed"] and item["code"] in {"fx_session", "fx_entry_window"}:
                item.update(status="waiting", remediation=None)
            if item["status"] in {"waiting", "checking"}:
                item["category"] = "progress"
        return checks

    def _fx_arm_preview(self, ids, profile_id, profile_version, unattended):
        from .engine import check

        if len(set(ids)) != len(ids) or not 1 <= len(ids) <= 5 or unattended:
            raise Conflict("Review one to five distinct supervised paper FX runs.")
        selected = [self.store.get("run", key) for key in ids]
        if any(not self._fx_run(r) or r.get("archived") for r in selected):
            raise Conflict("Review FX runs separately from other execution policies.")
        for run in selected:
            if run["conid"] in self.data:
                self._fx_prepare_data(
                    run["conid"],
                    run["binding"]["execution_plan"]["signal_source"],
                    run["binding"]["execution_plan"]["policy"],
                )
        self.refresh_incidents()
        profile = {
            "id": "fx_selected",
            "version": 1,
            "name": "Paper FX — selected base quantity",
            "runs": 5,
            "notional": None,
            "planned_stop_risk": None,
            "entry_timeout": 30,
            "risk_policy": "paper_stock_v2",
            "fx_units": None,
        }
        if not self.store.get("risk_profile", "fx_selected:1"):
            self.store.put("risk_profile", "fx_selected:1", profile)
        if profile_id not in {
            "smoke",
            "qualified",
            "stock_smoke",
            "stock_qualified",
            "stock_selected",
            "stock_one_lot",
            "fx_selected",
        } or (profile_id == "fx_selected" and profile_version not in {None, 1}):
            raise Conflict("Select the paper FX explicit-quantity profile.")
        checks = self.readiness(selected)
        bounds = []
        cutoffs = []
        for run in selected:
            checks.extend(
                {
                    **c,
                    "code": c["code"] + "_" + run["id"],
                    **(
                        {"depends_on": c["depends_on"] + "_" + run["id"]}
                        if c.get("depends_on")
                        else {}
                    ),
                }
                for c in self._fx_checks(run)
            )
            session = self._fx_session(run).bounds(datetime.now(UTC))
            if session:
                bounds.append(session[1])
                minutes = self.store.version(run["strategy_id"], run["version"])["document"][
                    "settings"
                ]["exit_before_close"]
                cutoffs.append(session[1] - timedelta(minutes=minutes))
        reserved_runs = {r["run_id"] for r in self.store.list("reservation") if r.get("active")}
        others = sum(
            bool(
                r.get("armed")
                or number(r.get("position", 0))
                or r["id"] in reserved_runs
                or r.get("authorization_status") == "temporarily_suspended"
            )
            for r in self.store.list("run")
            if r["id"] not in ids
        )
        checks.append(
            check(
                "capacity",
                "Shared five-run capacity",
                others + len(ids) <= 5,
                "At most five active runs share the workspace.",
            )
        )
        holds = self.incidents.applicable(selected)
        recoveries = self.incident_recoveries(selected)
        eligible = all(c.get("authorization_ready", c["passed"]) for c in checks)
        eligible_after = (
            all(
                c.get("authorization_ready", c["passed"])
                for c in checks
                if c["code"] != "incidents"
            )
            and 0 < len(holds) <= 200
            and all(h.get("restriction") == "ready_for_release" for h in holds)
        )
        fingerprint = digest(
            {
                "instance": self.process_identity,
                "context": getattr(self, "paper_context_token", None),
                "runs": [(r["id"], r["binding"]["hash"], r.get("entries", 0)) for r in selected],
                "profile": profile,
                "recoveries": [(h["id"], h["revision"]) for h in holds],
                "resume": RESUME_POLICY,
                "commission_currency": getattr(self, "account_base_currency", None),
            }
        )
        expires = min(bounds).isoformat() if len(bounds) == len(selected) else now()
        return {
            "review_fingerprint": fingerprint,
            "policy_replacement": self.policy_replacement_preview(selected),
            "review_instance": self.process_identity,
            "resume_policy": RESUME_POLICY,
            "eligible": eligible,
            "can_authorize": eligible,
            "can_dispatch": all(c["passed"] for c in checks),
            "eligible_after_recovery_ack": eligible_after,
            "recoveries": recoveries,
            "checks": checks,
            "runs": selected,
            "limits": profile,
            "expires_at": expires,
            "entry_cutoff": min(cutoffs).isoformat() if len(cutoffs) == len(selected) else None,
            "crypto_entries": [],
            "paired_entries": [],
            "summaries": [
                {"run_id": r["id"], **self.store.version(r["strategy_id"], r["version"])}
                for r in selected
            ],
            "environment": self.environment.name,
            "session_policy": "idealpro_fx_week_v1",
            "authorization": "supervised_paper_session",
        }

    def _fx_guard(self, run):
        return bool(
            run.get("armed")
            and run.get("fx_policy_revision") == run["binding"]["execution_plan"]["policy"]
            and run.get("funding_currency") == getattr(self, "account_base_currency", None)
            and run.get("expires_at", "") > now()
            and all(
                c["passed"] for c in self.readiness([run]) + self._fx_checks(run, dispatch=True)
            )
        )

    def _fx_enter(self, run, trigger, capture):
        run = self.store.get("run", run["id"])
        if run.get("entries", 0):
            return
        self._signal_detect(run, trigger, capture)
        if not self._fx_signal_current(trigger):
            self._signal_outcome(run, "expired", "FX signal window is not current.")
            self.store.event(
                "fx.entry.blocked",
                {
                    "run_id": run["id"],
                    "trigger": trigger,
                    "reason": "FX signal window is not current.",
                },
            )
            return
        plan = run["binding"]["execution_plan"]
        if self._fx_uses_broker_candles(run) and not self._fx_broker_trigger_current(run, trigger):
            self._signal_outcome(
                run, "expired", "Broker reference or fresh live crossing is no longer current."
            )
            return
        if broker_credit(plan) and run.get("armed") and not run.get("entries"):
            try:
                self._fx_funding(plan, run["binding"]["sizing"])
            except CreditPending as exc:
                self._signal_outcome(run, "checking", str(exc))
                if trigger.get("expires_at", "") > now():
                    pending = getattr(self, "_fx_credit_signals", {})
                    pending[run["id"]] = {
                        "trigger": trigger,
                        "capture": capture,
                        "authorization": run["authorization_id"],
                    }
                    self._fx_credit_signals = pending
                return
            except Conflict as exc:
                self._signal_outcome(run, "blocked", str(exc))
                return
        if run.get("entries", 0) or not self._fx_guard(run):
            failures = [
                c["detail"]
                for c in self.readiness([run]) + self._fx_checks(run, dispatch=True)
                if not c["passed"]
            ]
            reason = (
                "; ".join(dict.fromkeys(failures))
                or "Current authorization or account context does not permit entry."
            )
            self._signal_outcome(run, "blocked", reason)
            return
        try:
            reserve = self._fx_funding(plan, run["binding"]["sizing"])
        except Conflict as exc:
            self._signal_outcome(
                run, "checking" if isinstance(exc, CreditPending) else "blocked", str(exc)
            )
            return
        rules = self.market_rules[self.contracts[run["conid"]]["market_rule"]]
        ask = number(self._fx_cache(run["conid"])["fx_bidask"]["ask"])
        stop = protection_price(ask, "long", rules)
        payload = {
            "execution": "fx_breakout",
            "purpose": "entry",
            "conid": run["conid"],
            "symbol": run["symbol"],
            "quantity": reserve["quantity"],
            "currency": plan["currency"],
            "fx_plan": plan,
            "approved_sizing": run["binding"]["sizing"],
            "risk_limits": run["limits"],
            "entry_type": "MKT",
            "limit": str(ask),
            "stop": str(stop),
            "protection_type": plan["protection_type"],
            "protection_intent": True,
            "timeout": 30,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            "capture": capture,
            "signal": trigger,
            "price_rules": rules,
            "valuation": reserve,
        }
        key = digest({"run": run["id"], "authorization": run["authorization_id"], "entry": 1})[:32]
        baseline = self._fx_baseline()
        payload["currency_baseline"] = baseline
        try:
            reserved = self.store.reserve_order(key, payload, run["id"], self.next_id, reserve)
        except Conflict as exc:
            self._signal_outcome(run, "blocked", str(exc))
            return
        if not reserved["created"]:
            return
        self.store.event("fx.signal", {"run_id": run["id"], **trigger, "capture": capture})
        if not self.guard_entry_dispatch(key):
            self._signal_outcome(
                run,
                "blocked",
                "Final dispatch validation failed; no order transmitted.",
                order_id=key,
            )
            return
        self._fx_transmit(payload, reserved)
        state = self.store.orders()
        uncertain = any(o["id"] == key and o["state"] == "unknown" for o in state)
        self._signal_outcome(
            run,
            "uncertain" if uncertain else "submitted",
            "Awaiting broker reconciliation."
            if uncertain
            else "Paper order transmitted; awaiting broker outcome.",
            order_id=key,
        )

    def _fx_transmit(self, payload, reserved):
        if not reserved.get("created"):
            return
        self.store.mark_dispatch(reserved["id"])
        try:
            self.broker.submit_fx({**payload, **reserved})
        except Exception:
            self.store.transition(reserved["id"], "unknown", {"reason": "dispatch_interrupted"})
            self.incident(
                "dispatch_uncertain",
                "FX submission outcome is unknown. Reconcile; never resend this order.",
            )
        self.invalidate_reconciliation()

    def _fx_baseline(self):
        current = ledger(self.store)
        return {
            "balances": {
                currency: item["value"]
                for (tag, currency), item in self.currency_facts.items()
                if tag == "CashBalance"
            },
            "flows": serialized(current["flows"]),
            "at": now(),
        }

    def _fx_cash_issues(self):
        baseline = self.store.get("fx_ledger", "baseline")
        if not baseline:
            return []
        current = ledger(self.store)
        issues = []
        permitted_debits = self._credit_debit_currencies()
        if current["missing_commissions"]:
            issues.append("FX commissions are awaiting broker evidence.")
        if any(
            p["quantity"] and not self._fx_account_ready(self.store.get("run", key))
            for key, p in current["runs"].items()
        ):
            issues.append("Current broker FX order/execution ownership evidence is required.")
        for currency in set(baseline["flows"]) | set(current["flows"]):
            actual = self.currency_facts.get(("CashBalance", currency))
            expected = (
                number(baseline["balances"].get(currency, 0))
                + current["flows"].get(currency, Decimal(0))
                - number(baseline["flows"].get(currency, 0))
            )
            # Broker currency balances are rounded to display precision; tolerate
            # one minor currency unit, not a quantity-sized discrepancy.
            tolerance = Decimal(1) if currency == "JPY" else Decimal("0.01")
            if (
                not actual
                or not recent(actual.get("received_at"), 30)
                or abs(number(actual["value"]) - expected) > tolerance
            ):
                issues.append(
                    f"Real {currency} balance differs from the execution-derived FX ledger; "
                    "reconcile external cash changes."
                )
            if (
                actual
                and currency not in permitted_debits
                and (
                    number(actual["value"]) < 0
                    or number(actual["value"]) < self._fx_owned_currency(currency)
                )
            ):
                issues.append(
                    f"{currency} cash cannot cover the owned FX allocations and charges; "
                    "new entries require account recovery."
                )
        snapshot = serialized(current)
        if self.store.get("fx_ledger", "projection") != snapshot:
            self.store.put("fx_ledger", "projection", snapshot)
            self.store.event("fx.ledger.reconciled", {"ledger": snapshot, "issues": issues})
        return issues

    def _fx_provisional(self, position, entry):
        if entry["payload"].get("execution") != "fx_breakout":
            return False
        request = self.store.get("exit_request", position["run_id"]) or {}
        started = request.get("requested_at") or entry["created_at"]
        return recent(started, 30)

    def _fx_identity(self, intent, observed):
        from .fx_order_evidence import quantity_evidence

        payload = intent["payload"]
        purpose = payload["purpose"]
        required = {
            "conid",
            "own_account",
            "client_id",
            "reference",
            "quantity",
            "order_type",
            "action",
            "tif",
            "sec_type",
            "currency",
            "routing_exchange",
        }
        if not required <= observed.keys():
            return ["Awaiting complete broker FX order details."]
        expected_type = {"entry": "MKT", "protection": "STP", "exit": "LMT"}[purpose]
        checks = {
            "paper account": observed["own_account"] is True,
            "client identity": observed["client_id"] == self.broker.client_id,
            "order reference": observed["reference"] == "oms-" + intent["id"],
            "contract": observed["conid"] == payload["conid"],
            "security type": observed["sec_type"] == "CASH",
            "currency": observed["currency"] == payload["fx_plan"]["currency"],
            "route": observed["routing_exchange"] == "IDEALPRO",
            "side": observed["action"] == ("BUY" if purpose == "entry" else "SELL"),
            "order type": observed["order_type"] == expected_type,
            "quantity evidence": number(
                quantity_evidence(self.store, intent, observed)["effective"] or 0
            )
            == number(payload["quantity"]),
            "time-in-force": observed["tif"]
            == {"entry": "IOC", "protection": "GTC", "exit": "GTD"}[purpose],
        }
        if purpose == "protection":
            checks["bid/ask trigger method"] = observed.get("trigger_method") == 4
            checks["stop price"] = number(observed.get("stop", 0)) == number(payload["stop"])
        if purpose == "exit":
            from .premarket import broker_deadline

            checks["limit price"] = number(observed.get("limit", 0)) == number(payload["limit"])
            checks["expiry"] = broker_deadline(
                observed.get("good_till_date")
            ) == datetime.fromisoformat(payload["expires_at"]).replace(microsecond=0)
        failures = [label for label, valid in checks.items() if not valid]
        return (
            ["Broker FX order differs from the durable intent: " + ", ".join(failures) + "."]
            if failures
            else []
        )

    def _fx_sync(self, run):
        if not self._fx_run(run):
            return
        orders = [o for o in self.store.orders() if o["run_id"] == run["id"]]
        entries = [o for o in orders if o["payload"].get("purpose") == "entry"]
        if not entries:
            return
        entry = max(entries, key=lambda o: (o["created_at"], o["broker_id"]))
        allocation = ledger(self.store)["runs"].get(run["id"], {})
        qty = allocation.get("quantity", Decimal(0))
        if qty < 0:
            failure = {"entry_id": entry["id"], "quantity": str(qty)}
            if self.store.get("fx_ownership_failure", run["id"]) != failure:
                self.store.put("fx_ownership_failure", run["id"], failure)
                self.incident(
                    "fx_ownership",
                    "FX executions exceed the run's currency allocation. New entries are blocked.",
                )
            return
        if qty and allocation.get("bought"):
            intent = self.store.get("fx_exit_intent", run["id"]) or {}
            if intent.get("entry_id") == entry["id"] and not self.store.get(
                "exit_request", run["id"]
            ):
                self.store.put("exit_request", run["id"], intent)
                self.store.event("fx.exit.resumed", {"run_id": run["id"], "entry_id": entry["id"]})
            average = allocation["cost"] / allocation["bought"]
            reservation = self.store.get("reservation", entry["id"]) or {}
            if buying_power_policy(reservation):
                actual = allocation["cost"] * number(entry["payload"]["valuation"]["fx_rate"])
                if actual > number(reservation["notional"]):
                    reservation.update(
                        notional=str(actual),
                        buying_power_allocation=str(
                            actual + number(reservation["fee_reserve_usd"])
                        ),
                    )
                    self.store.put("reservation", entry["id"], reservation)
                    self.store.event(
                        "fx.fill.allocation_updated",
                        {
                            "entry_id": entry["id"],
                            "notional": str(actual),
                            "buying_power_allocation": reservation["buying_power_allocation"],
                        },
                    )
            rules = entry["payload"]["price_rules"]
            stop = protection_price(average, "long", rules)
            state = self.store.get("fx_protection", run["id"]) or {}
            updated = {
                **state,
                "entry_id": entry["id"],
                "quantity": str(qty),
                "stop": str(stop),
                "average": str(average),
                "run_id": run["id"],
                "type": run["protection_type"],
                "state": "awaiting_verification",
            }
            if updated != state:
                self.store.put("fx_protection", run["id"], updated)
                self.store.event("fx.protection.updated", updated)
            if entry["state"] not in TERMINAL:
                self._queue_cancel(entry["broker_id"], "entry", "partial_fill")
            self._fx_protect(run, entry, qty, stop)
        elif entry["state"] in TERMINAL and self.reconciled:
            if run.get("armed") and entry["created_at"] >= run.get("authorized_at", ""):
                self.disarm(
                    run["id"],
                    "Trade completed."
                    if allocation.get("bought")
                    else "Entry completed with no fill.",
                )

    def _fx_active_sells(self, run):
        return [
            o
            for o in self.store.orders()
            if o["run_id"] == run["id"]
            and o["payload"].get("purpose") in {"exit", "protection"}
            and o["state"] not in TERMINAL
        ]

    def _fx_protect(self, run, entry, quantity, stop):
        if not self._fx_account_ready(run):
            return
        if self.store.get("exit_request", run["id"]):
            self._fx_exit_maintain(run)
            return
        plan = run["binding"]["execution_plan"]
        if plan["protection_type"] == "locally_monitored":
            quote = self._fx_cache(run["conid"]).get("fx_bidask", {})
            if (
                self.connected
                and self.data.get(run["conid"], {}).get("live")
                and self._fx_quote_evaluation(run["conid"])["fresh"]
                and number(quote["bid"]) <= stop
            ):
                self._fx_request_exit(run, "Local FX bid stop triggered.")
            return
        active = self._fx_active_sells(run)
        if active:
            for order in active:
                if (
                    number(order["payload"]["quantity"]) != quantity
                    or number(order["payload"].get("stop", 0)) != stop
                ):
                    self._queue_cancel(order["broker_id"], "protection", "fx_protection_resize")
            return
        if (
            not self.connected
            or not self.attested
            or not self._fx_session(run).tradable(datetime.now(UTC))
        ):
            return
        # Initial fill protection does not wait for the account refresh. Any
        # replaced/terminal sell must first have reconciled executions.
        old_sells = [
            o
            for o in self.store.orders()
            if o["run_id"] == run["id"] and o["payload"].get("purpose") in {"protection", "exit"}
        ]
        if old_sells and not self._fx_replacement_ready(old_sells):
            return
        self._fx_sell(run, entry, quantity, "protection", stop)

    def _fx_sell(self, run, entry, quantity, purpose, price):
        plan = run["binding"]["execution_plan"]
        if not self._fx_account_ready(run):
            raise Conflict("Current broker evidence must establish this run's currency ownership.")
        if quantity <= 0 or quantity % number(plan["rules"]["exit_increment"]):
            failure = {"entry_id": entry["id"], "quantity": str(quantity)}
            if self.store.get("fx_residual_failure", run["id"]) != failure:
                self.store.put("fx_residual_failure", run["id"], failure)
                self.incident(
                    "fx_residual",
                    "Remaining FX quantity cannot use the qualified exit increment. "
                    "Inspect broker protection.",
                )
            return
        owned = self.owned().get(run["id"], {}).get("quantity", Decimal(0))
        if quantity > owned or self._fx_active_sells(run):
            raise Conflict("FX sells cannot overlap or exceed confirmed owned currency.")
        bounds = self._fx_session(run).bounds(datetime.now(UTC))
        if not bounds:
            return
        expires = min(datetime.now(UTC) + timedelta(seconds=10), bounds[1]).replace(microsecond=0)
        orders = [o for o in self.store.orders() if o["run_id"] == run["id"]]
        key = digest({"entry": entry["id"], "purpose": purpose, "sequence": len(orders)})[:32]
        payload = {
            "execution": "fx_breakout",
            "purpose": purpose,
            "entry_id": entry["id"],
            "conid": run["conid"],
            "symbol": run["symbol"],
            "currency": plan["currency"],
            "fx_plan": plan,
            "quantity": str(quantity),
            "action": "SELL",
            "stop": str(price),
            "limit": str(price),
            "exit_type": "LMT",
            "timeout": 10,
            "expires_at": expires.isoformat(),
            "good_till_date": expires.strftime("%Y%m%d-%H:%M:%S"),
            "price_increment": str(price_increment(price, entry["payload"]["price_rules"])),
        }
        reserved = self.store.reserve_order(key, payload, run["id"], self.next_id)
        self.store.event(
            "fx.exit.risk_checked",
            {
                "run_id": run["id"],
                "purpose": purpose,
                "quantity": str(quantity),
                "owned_quantity": str(owned),
                "overlapping_sells": False,
                "price": str(price),
                "policy": plan["policy"],
            },
        )
        self._fx_transmit(payload, reserved)

    def _fx_request_exit(self, run, reason):
        if not self.store.get("exit_request", run["id"]):
            entry = max(
                (
                    o
                    for o in self.store.orders()
                    if o["run_id"] == run["id"] and o["payload"].get("purpose") == "entry"
                ),
                key=lambda o: (o["created_at"], o["broker_id"]),
                default=None,
            )
            request = {
                "reason": reason,
                "requested_at": now(),
                "fx": True,
                "entry_id": entry["id"] if entry else None,
            }
            self.store.put("exit_request", run["id"], request)
            self.store.put("fx_exit_intent", run["id"], request)
            self.store.event("fx.exit.requested", {"run_id": run["id"], **request})
        if run.get("armed"):
            self.disarm(run["id"], reason)
        self._fx_exit_maintain(self.store.get("run", run["id"]))
        return {"state": "exit_requested", "run_id": run["id"]}

    def _fx_replacement_ready(self, orders):
        evidence = self.reconciliation_evidence or {}
        return bool(
            self.connected
            and self.attested
            and orders
            and self._fx_ownership_agrees(self.store.get("run", orders[0]["run_id"]))
            and evidence.get("completed_at")
            and evidence.get("evidence_revision") == getattr(self, "_evidence_revision", 0)
            and not self._identity_issues()
            and not self._fill_agreement_issues()
            and all(o["state"] in TERMINAL for o in orders)
            and all(
                (self.store.get("broker_order", str(o["broker_id"])) or {}).get(
                    "terminal_observed_at", "z"
                )
                <= evidence.get("started_at", "")
                for o in orders
            )
        )

    def _fx_ownership_agrees(self, run):
        currency = run["binding"]["execution_plan"]["base_currency"]
        balance = self.currency_facts.get(("CashBalance", currency), {})
        if buying_power_policy(run["binding"]["execution_plan"]):
            baseline = self.store.get("fx_ledger", "baseline") or {}
            flows = ledger(self.store)["flows"]
            expected = (
                number(baseline.get("balances", {}).get(currency, 0))
                + flows.get(currency, Decimal(0))
                - number(baseline.get("flows", {}).get(currency, 0))
            )
            tolerance = Decimal(1) if currency == "JPY" else Decimal("0.01")
            return bool(
                self._fx_account_ready(run)
                and baseline
                and balance
                and recent(balance.get("received_at"), 30)
                and abs(number(balance["value"]) - expected) <= tolerance
            )
        return bool(
            self._fx_account_ready(run)
            and balance
            and recent(balance.get("received_at"), 30)
            and number(balance["value"]) >= self._fx_owned_currency(currency)
        )

    def _fx_exit_maintain(self, run):
        request = self.store.get("exit_request", run["id"])
        if not request:
            return
        qty = self.owned().get(run["id"], {}).get("quantity", Decimal(0))
        orders = [o for o in self.store.orders() if o["run_id"] == run["id"]]
        entries = [o for o in orders if o["payload"].get("purpose") == "entry"]
        if not entries or qty <= 0:
            return
        entry = max(entries, key=lambda o: (o["created_at"], o["broker_id"]))
        orders = [
            o
            for o in orders
            if o["id"] == entry["id"] or o["payload"].get("entry_id") == entry["id"]
        ]
        for order in orders:
            if order["state"] in {"working", "dispatching", "reserved"}:
                purpose = order["payload"]["purpose"]
                if purpose != "exit" or datetime.now(UTC) >= datetime.fromisoformat(
                    order["payload"]["expires_at"]
                ):
                    self._queue_cancel(order["broker_id"], "exit", "fx_exit_requested")
        if (
            not request.get("alerted")
            and (
                datetime.now(UTC) - datetime.fromisoformat(request["requested_at"])
            ).total_seconds()
            >= 30
        ):
            self.store.put("exit_request", run["id"], {**request, "alerted": True})
            self.store.put("fx_exit_intent", run["id"], {**request, "alerted": True})
            self.incident(
                "fx_exit_unfilled",
                "FX exit remains unfilled after 30 seconds. "
                "Inspect the remaining currency position.",
            )
        if not self._fx_replacement_ready(orders) or not self._fx_session(run).tradable(
            datetime.now(UTC)
        ):
            return
        if any(o["state"] == "rejected" for o in orders):
            # A rejection cannot silently select a new method. The existing
            # explicit incident review plus a post-failure reconciliation is
            # required before retrying this same approved exit method.
            if self.incidents.applicable([run]) or not self.reconciled:
                return
        quote = self._fx_cache(run["conid"]).get("fx_bidask", {})
        if (
            not self.data.get(run["conid"], {}).get("live")
            or not self._fx_quote_evaluation(run["conid"])["fresh"]
        ):
            return
        bid = rounded(number(quote["bid"]), entry["payload"]["price_rules"], False)
        self._fx_sell(run, entry, qty, "exit", bid)

    def _fx_valid_protection(self, position, entry):
        run = self.store.get("run", position["run_id"])
        return self._fx_protection_assessment(run, position)["state"] == "active"

    def _fx_protection_assessment(self, run, position=None):
        from .fx_protection import assess

        return assess(
            self, run, position if position is not None else self.owned().get(run["id"], {})
        )

    def _fx_maintain(self):
        self._fx_data_maintain()
        self._signal_maintain()
        for run in self.store.list("run"):
            if not self._fx_run(run):
                continue
            self._fx_readiness_transition(run)
            pending = getattr(self, "_fx_credit_signals", {}).get(run["id"])
            if pending:
                trigger = pending["trigger"]
                runtime = self.runtime.get(run["id"], {}).get("market")
                if (
                    not run.get("armed")
                    or run.get("entries")
                    or trigger["expires_at"] <= now()
                    or pending["authorization"] != run.get("authorization_id")
                    or not runtime
                    or not runtime.previous
                    or runtime.previous["candle"] != trigger["candle"]
                ):
                    self._fx_credit_signals.pop(run["id"], None)
                elif self._fx_feed_health(run["conid"], run)["execution_fresh"]:
                    source = run["binding"]["execution_plan"]["signal_source"]
                    quote = self._fx_cache(run["conid"])[
                        "fx_midpoint" if source == "MIDPOINT" else "fx_bidask"
                    ]
                    price = number(quote["price" if source == "MIDPOINT" else source.lower()])
                    if quote["source_at"] > trigger["triggered_at"] and price > number(
                        trigger["high"]
                    ):
                        self._fx_enter(run, trigger, pending["capture"])
            self._fx_sync(run)
            position = self.owned().get(run["id"], {})
            minutes = self.store.version(run["strategy_id"], run["version"])["document"][
                "settings"
            ]["exit_before_close"]
            if (
                position.get("quantity")
                and run.get("expires_at")
                and datetime.now(UTC)
                >= datetime.fromisoformat(run["expires_at"]) - timedelta(minutes=minutes)
            ):
                self._fx_request_exit(
                    run, "Approved FX session ended; exit at the next eligible broker session."
                )
            if self.store.get("exit_request", run["id"]):
                self._fx_exit_maintain(run)

    def _fx_readiness_transition(self, run):
        if not run.get("armed") or run.get("entries"):
            return
        health = self._fx_feed_health(run["conid"], run)
        state = (
            "fresh"
            if health["execution_fresh"]
            else "waiting"
            if self._fx_healthy_wait(run)
            else "blocked"
        )
        transitions = getattr(self, "_fx_readiness_states", {})
        prior = transitions.get(run["id"])
        key = (state, self.broker.epoch, run.get("authorization_id"))
        if prior != key:
            if len(transitions) >= 20 and run["id"] not in transitions:
                transitions.pop(next(iter(transitions)))
            transitions[run["id"]] = key
            self._fx_readiness_states = transitions
            cache = self._fx_cache(run["conid"])
            self.store.event(
                "fx.readiness.changed",
                {
                    "run_id": run["id"],
                    "state": state,
                    "epoch": self.broker.epoch,
                    "observations": {
                        k: {
                            field: cache.get(k, {}).get(field)
                            for field in ("source_at", "received_at")
                        }
                        for k in ("fx_bidask", "fx_midpoint")
                    },
                },
            )
        if state != "fresh" and not self._fx_uses_broker_candles(run):
            self.runtime.pop(run["id"], None)
        reason = (
            None
            if state == "fresh"
            else (
                f"Armed — waiting for fresh {run['binding']['execution_plan']['signal_source']} "
                "and bid/ask."
                if state == "waiting"
                else health["execution_detail"]
            )
        )
        if run.get("blocking_reason") != reason:
            run["blocking_reason"] = reason
            self.store.put("run", run["id"], run)

    def _fx_protection_view(self, run_ids=None):
        result = []
        for state in self.store.list("fx_protection"):
            if run_ids is not None and state["run_id"] not in run_ids:
                continue
            run = self.store.get("run", state["run_id"])
            position = self.owned().get(run["id"], {})
            plan = run["binding"]["execution_plan"]
            verification = self._fx_protection_assessment(run, position)
            result.append(
                {
                    **state,
                    "quantity": str(position.get("quantity", 0)),
                    "base_currency": plan["base_currency"],
                    "currency": plan["currency"],
                    "family": "spot_fx",
                    "status": verification["state"],
                    "verification": verification,
                }
            )
        return result

    def _fx_allocation(self, run):
        return serialized(ledger(self.store)["runs"].get(run["id"])) if self._fx_run(run) else None
