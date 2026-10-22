"""Schema-7 contract binding, currency valuation and qualified stock execution."""

import copy
import os
import time
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal

from .credit_policy import bind_credit, broker_credit
from .graph import digest, number
from .oca import protection_price
from .oca_engine import fresh
from .premarket import premarket
from .stock_fees import AUTO_REFERENCE, branch_fees
from .stock_policy import compatibility, fx_rate, size_stock, validate_rules
from .stock_references import StockReferences
from .store import Conflict, now


class StockController(StockReferences):
    def _resolve_stock_rules(self, conid, *, automatic=False):
        from .stock_rules import resolve_rules

        c = self.contracts.get(conid, {})
        if c.get("primary_exchange") == "SEHK":
            c["reference_data"] = self.stock_reference(c)
        fee_key = c.get("currency", "") + ":" + c.get("routing_exchange", c.get("exchange", ""))
        fee = self.store.get("stock_fee", fee_key)
        rules, evidence = resolve_rules(c, fee, automatic=automatic)
        if automatic and not rules:
            c.pop("stock_rules", None)
            c.pop("stock_rule_evidence", None)
        if not rules and (c.get("stock_rules") or {}).get("reference") == "US share policy v1":
            c.pop("stock_rules", None)
            c.pop("stock_rule_evidence", None)
        if rules:
            c["stock_rules"] = rules
            c["stock_rule_evidence"] = evidence
            if rules.get("reference") == AUTO_REFERENCE:
                if self.store.get("automatic_stock_rules", str(conid)) != rules:
                    self.store.backup(self.store.directory / "backups")
                    with self.store.transaction() as db:
                        self.store.write(db, "automatic_stock_rules", str(conid), rules)
                        self.store.append(
                            db,
                            "stock.rules.derived",
                            {"conid": conid, "rules": rules, "evidence": evidence},
                        )
        return rules, evidence, fee

    def stock_fee(self, conid, amount, revision, actor):
        c = self.contracts.get(conid, {})
        if c.get("sec_type") != "STK" or c.get("resolved") is False:
            raise Conflict("Resolve a stock before recording its reusable fee allowance.")
        value = number(amount)
        if not 0 <= value <= 10000:
            raise ValueError(
                "Use a non-negative fee allowance no greater than 10,000 native units."
            )
        key = c["currency"] + ":" + c.get("routing_exchange", c.get("exchange", ""))
        self.store.backup(self.store.directory / "backups")
        with self.store.transaction() as db:
            old = self.store.read(db, "stock_fee", key) or {}
            if revision != old.get("revision", 0):
                raise Conflict("Fee allowance changed. Refresh before saving.")
            record = {"amount": str(value), "revision": revision + 1, "actor": actor}
            self.store.write(db, "stock_fee", key, record)
            self.store.append(db, "stock.fee.recorded", {"key": key, **record})
        for identity, contract in self.contracts.items():
            if contract.get("currency") == c["currency"] and contract.get(
                "routing_exchange", contract.get("exchange")
            ) == c.get("routing_exchange", c.get("exchange")):
                self._resolve_stock_rules(identity)
        for run in self.store.list("run"):
            if self._stock_run(run) and run.get("armed") and not self._binding_valid(run):
                self.disarm(run["id"], "Contract policy changed. Prepare and review a new binding.")
        return record

    def _stock_display_units(self, run_id):
        binding = (self.store.get("run", run_id) or {}).get("binding") or {}
        return {
            "currency": binding.get("contract", {}).get("currency", "USD"),
            "price_scale": binding.get("execution_plan", {})
            .get("rules", {})
            .get("price_scale", "1"),
        }

    def _stock_run(self, run):
        plan = (run.get("binding") or {}).get("execution_plan") if run else None
        return bool(plan and plan.get("family") != "spot_fx")

    def stock_rules(self, conid, rules, actor="local-operator"):
        contract = self.contracts.get(conid, {})
        if contract.get("sec_type") != "STK" or contract.get("resolved") is False:
            raise Conflict("Resolve a share-based stock contract first.")
        previous = self.store.get("stock_rules", str(conid)) or {}
        record = dict(rules)
        if record.get("revision") != previous.get("revision", 0) + 1:
            raise Conflict("Contract rules changed. Refresh before recording new evidence.")
        validate_rules({**contract, "stock_rules": record})
        self.store.backup(self.store.directory / "backups")
        with self.store.transaction() as db:
            self.store.write(db, "stock_rules", str(conid), record)
            self.store.append(
                db, "stock.rules.verified", {"conid": conid, "rules": record, "actor": actor}
            )
        automatic_current = (self.contracts[conid].get("stock_rules") or {}).get(
            "reference"
        ) == AUTO_REFERENCE
        if not automatic_current:
            self.contracts[conid]["stock_rules"] = record
        for run in self.store.list("run"):
            if (
                self._stock_run(run)
                and run["conid"] == conid
                and run.get("armed")
                and run["binding"]["execution_plan"]["rules"]["reference"] != AUTO_REFERENCE
            ):
                self.disarm(run["id"], "Contract rules changed. Prepare a new binding and review.")
        return record

    def stock_compatibility(
        self,
        strategy_id,
        version,
        conid,
        protection_type="broker_held",
        session_mode="regular",
        sizing=None,
        funding_policy=None,
        execution_policy=None,
    ):
        document = self.store.version(strategy_id, version)["document"]
        if document["schema_version"] == 9:
            return self.fx_compatibility(
                strategy_id,
                version,
                conid,
                protection_type,
                session_mode,
                sizing,
                funding_policy,
                execution_policy,
            )
        if document["schema_version"] not in (7, 8):
            raise Conflict("Convert an explicit schema-7 copy before preparing a stock binding.")
        rules, evidence, fee = self._resolve_stock_rules(conid, automatic=True)
        result = compatibility(
            self.contracts.get(conid, {}), document, protection_type, session_mode
        )
        result["plan"] = bind_credit(result["plan"], funding_policy)
        c = self.contracts.get(conid, {})
        ref = c.get("reference_data") or {}
        result["resolution_status"] = "ready" if rules else "unsupported"
        if not rules:
            message = (
                "Automatic execution policy is unavailable for this listing, "
                "route or price convention."
            )
            if c.get("primary_exchange") == "SEHK":
                message = (
                    "IBKR quantity rules and the current HKEX board lot "
                    "must be available and agree."
                )
                if ref.get("status") != "ready":
                    message = ref.get("detail") or "Waiting for current HKEX lot-size reference."
                    result["resolution_status"] = (
                        "checking" if ref.get("status") == "pending" else "unsupported"
                    )
            if c.get("sec_type") == "STK":
                result["blockers"] = [message]
        result["refresh_status"] = {
            "reference": ref.get("status", "documented_policy"),
            "metadata_current": self.stock_metadata_ready(conid),
        }
        if rules and rules.get("fee_reserve") == "":
            result["blockers"] = ["Record the reusable fee allowance for this currency and route."]
        if result.get("plan") and not result["blockers"]:
            qualification = self.store.get("stock_qualification", result["plan"]["hash"]) or {}
            directions = ("long", "short") if result["requirements"]["short"] else ("long",)
            if all(qualification.get(direction) for direction in directions):
                result["status"] = "compatible"
        result["rules"] = self.contracts.get(conid, {}).get("stock_rules")
        result.update(
            evidence=evidence, fee_policy=fee, arming_requirements=[], indicative_sizing=None
        )
        result["funding_policy"] = funding_policy
        result["credit_status"] = "automatic_on_review" if funding_policy else "legacy_cash"
        result["fee_policy"] = {
            "revision": 2,
            "source": "automatic",
            "detail": "Conservative round-trip funding reserve, not a commission quote.",
        }
        fields = [
            "calendar",
            "minimum_quantity",
            "quantity_increment",
            "exit_increment",
            "price_scale",
            "fee_reserve",
            "same_day_resale",
        ]
        fields.append(
            "broker_protection" if protection_type == "broker_held" else "local_protection"
        )
        if result["requirements"]["native_oca"]:
            fields.append("native_oca")
        result["field_requirements"] = [
            {
                "field": k,
                "available": bool(rules and rules.get(k) not in (None, "", False)),
                "evidence": evidence.get(k),
            }
            for k in fields
        ]
        modern = document["schema_version"] == 8
        if not result["blockers"]:
            values = {**document["settings"], "shares": rules["minimum_quantity"], **(sizing or {})}
            try:
                if values["sizing"] != document["settings"]["sizing"]:
                    raise Conflict("Preserve the published sizing method.")
                if modern:
                    from .paper_risk import sizing_settings

                    values = sizing_settings(
                        document["settings"],
                        sizing,
                        rules["minimum_quantity"],
                        rules["quantity_increment"],
                    )
                for key, maximum in () if modern else (("notional", 1000), ("risk", 10)):
                    if (
                        not 0
                        < number(values[key])
                        <= min(number(document["settings"][key]), maximum)
                    ):
                        raise Conflict("Sizing cannot exceed the published USD ceiling.")
                step, minimum = (
                    number(rules["quantity_increment"]),
                    number(rules["minimum_quantity"]),
                )
                requested = number(values["shares"])
                if values["sizing"] == "fixed" and (requested < minimum or requested % step):
                    raise Conflict(f"Use at least {minimum} shares in increments of {step}.")
                quote = self.quotes.get(conid, {}).get("ask", {})
                currency = self.contracts[conid]["currency"]
                try:
                    rate = fx_rate(currency, self.fx_quotes.values())
                except Conflict as exc:
                    result["arming_requirements"].append(str(exc))
                    rate = None
                if fresh(quote) and rate:
                    price = number(quote["price"]) * number(rules["price_scale"])
                    count = 2 if result["requirements"]["short"] else 1
                    cost = price * count * rate
                    ceiling = number(values["notional"]) if values["notional"] is not None else None
                    if price <= 0:
                        raise Conflict("A positive indicative ask is required.")
                    quantity = (
                        requested
                        if modern and values["sizing"] == "fixed"
                        else (
                            (
                                (
                                    ceiling
                                    if ceiling is not None
                                    else number(values["risk"]) / Decimal("0.01")
                                )
                                / cost
                                / step
                            ).to_integral_value(rounding=ROUND_DOWN)
                            * step
                        )
                    )
                    stop_risk = None
                    if (
                        result["requirements"]["kind"] == "stock_breakout"
                        and not (modern and values["sizing"] == "fixed")
                        and values["risk"] is not None
                    ):
                        quantity = min(
                            quantity,
                            (
                                number(values["risk"]) / (cost * Decimal("0.01")) / step
                            ).to_integral_value(rounding=ROUND_DOWN)
                            * step,
                        )
                    if values["sizing"] == "fixed":
                        quantity = min(quantity, requested)
                    if result["requirements"]["kind"] == "stock_breakout":
                        stop_risk = str(quantity * cost * Decimal("0.01"))
                    native_minimum = minimum * price * count
                    minimum_fees = branch_fees(c, minimum, [number(quote["price"])] * count)
                    result["minimum_lot"] = {
                        "quantity": str(minimum),
                        "currency": currency,
                        "native_notional": str(native_minimum),
                        "notional_usd": str(minimum * cost),
                        "fee_reserve": str(minimum_fees),
                        "native_funds": str(native_minimum + minimum_fees),
                        "published_ceiling_usd": document["settings"]["notional"],
                        "stop_risk_usd": str(minimum * cost * Decimal("0.01"))
                        if result["requirements"]["kind"] == "stock_breakout"
                        else None,
                    }
                    if modern and (
                        (ceiling is not None and quantity * cost > ceiling)
                        or (
                            stop_risk is not None
                            and values["risk"] is not None
                            and number(stop_risk) > number(values["risk"])
                        )
                    ):
                        raise Conflict(
                            "Requested quantity exceeds the published or selected monetary ceiling."
                        )
                    if quantity < minimum:
                        raise Conflict(
                            f"Minimum {minimum} shares requires approximately "
                            f"{minimum * cost:.2f} USD notional; it exceeds the selected "
                            "budget or stop-risk limit. Publish an explicitly reviewed "
                            "higher ceiling or select another instrument."
                        )
                    result["indicative_sizing"] = {
                        "quantity": str(quantity),
                        "notional_usd": str(quantity * cost),
                        "stop_risk_usd": stop_risk,
                        "native_funds": str(
                            quantity * price * count
                            + branch_fees(c, quantity, [number(quote["price"])] * count)
                        ),
                        "currency": currency,
                        "observed_at": quote["received_at"],
                    }
                else:
                    result["arming_requirements"].append(
                        "Fresh prices and valuation are required before arming; "
                        "preparation does not authorize an order."
                    )
                result["arming_requirements"].append(
                    "Current paper context, broker buying power, feed readiness, session, "
                    "protection and risk checks are revalidated when arming."
                )
            except (ValueError, KeyError, TypeError) as exc:
                result["blockers"].append(str(exc))
        result["preparation_blockers"] = list(result["blockers"])
        result["can_prepare"] = not result["blockers"]
        if (
            result.get("minimum_lot")
            and (sizing or {}).get("notional", document["settings"]["notional"]) is not None
        ):
            if number(result["minimum_lot"]["notional_usd"]) > number(
                (sizing or {}).get("notional", document["settings"]["notional"])
            ):
                result["resolution_status"] = "budget_requirement"
        return result

    def _stock_binding(
        self,
        published,
        conid,
        sizing,
        protection,
        revision,
        session_mode="regular",
        funding_policy=None,
    ):
        contract = self.contracts[conid]
        result = self.stock_compatibility(
            published["strategy_id"],
            published["version"],
            conid,
            protection,
            session_mode,
            sizing,
            funding_policy,
        )
        if result["blockers"]:
            raise Conflict(" ".join(result["blockers"]))
        plan = result["plan"]
        if revision != plan["hash"]:
            raise Conflict("Review the current contract compatibility and execution-plan revision.")
        settings = published["document"]["settings"]
        values = dict(sizing or {})
        if set(values) - {"shares", "notional", "risk", "sizing"}:
            raise Conflict("Unsupported stock sizing field.")
        values = {
            "shares": plan["rules"]["minimum_quantity"],
            **{k: settings[k] for k in ("notional", "risk", "sizing")},
            **values,
        }
        quantity = number(values["shares"])
        if quantity <= 0 or quantity % number(plan["rules"]["quantity_increment"]):
            raise Conflict("Use a positive quantity in the verified stock increment.")
        values["shares"] = str(quantity)
        if values["sizing"] != settings["sizing"]:
            raise Conflict("Run sizing must preserve the published sizing rule.")
        modern = published["document"]["schema_version"] == 8
        if modern:
            from .paper_risk import sizing_settings

            values = sizing_settings(
                settings,
                sizing,
                plan["rules"]["minimum_quantity"],
                plan["rules"]["quantity_increment"],
            )
        for key, maximum in () if modern else (("risk", 10), ("notional", 1000)):
            if not 0 < number(values[key]) <= min(number(settings[key]), maximum):
                raise Conflict("Sizing cannot exceed the published USD ceiling.")
            values[key] = str(number(values[key]))
        binding = {
            "contract": copy.deepcopy(contract),
            "sizing": values,
            "strategy_hash": published["hash"],
            "session_policy": plan["session_policy"],
            "execution_plan": plan,
        }
        if session_mode != "regular":
            binding["session_mode"] = session_mode
        binding["hash"] = digest(binding)
        return binding

    def _stock_fact(self, event):
        if event["tag"] == "AccountType":
            # Informational only: account type is never proof of order permission.
            value = str(event["value"]).upper()
            if value in {"CASH", "MARGIN", "PORTFOLIO MARGIN", "INDIVIDUAL"}:
                self.currency_facts[("AccountType", "META")] = {
                    "value": value,
                    "received_at": event.get("received_at", now()),
                }
            return
        currency = event.get("currency", "USD")
        if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
            return
        if event["tag"] == "NetLiquidation":
            self.pnl_currency = currency
            self.account_base_currency = currency
        self.currency_facts[(event["tag"], currency)] = {
            "value": event["value"],
            "received_at": event.get("received_at", now()),
        }
        if currency != "USD" and hasattr(self.broker, "subscribe_fx"):
            self.broker.subscribe_fx(currency)
        self._stock_normalize_facts()

    def _stock_fx(self, event):
        key = (event["base"], event["quote"])
        record = self.fx_quotes.setdefault(key, {"base": key[0], "quote": key[1]})
        if event.get("side"):
            record[event["side"]] = event["price"]
            record[event["side"] + "_at"] = event["received_at"]
        if "live" in event:
            record["live"] = event["live"]
        if record.get("bid_at") and record.get("ask_at"):
            record["received_at"] = min(record["bid_at"], record["ask_at"])
        self._stock_normalize_facts()

    def _stock_normalize_facts(self):
        for tag in ("NetLiquidation", "AvailableFunds", "GrossPositionValue"):
            candidates = [
                (currency, value)
                for (name, currency), value in self.currency_facts.items()
                if name == tag and fresh(value, seconds=60)
            ]
            candidates.sort(key=lambda pair: pair[0] != "USD")
            for currency, value in candidates:
                try:
                    rate = fx_rate(
                        currency, self.fx_quotes.values(), liability=tag == "GrossPositionValue"
                    )
                except Conflict:
                    continue
                self.facts[tag] = str(number(value["value"]) * rate)
                break  # Summary values are totals, never add currency-translated copies.
            else:
                self.facts.pop(tag, None)

    def _stock_size(self, run, branches, profile=None):
        if broker_credit(run["binding"]["execution_plan"]):
            return self._stock_credit_size(run, branches, profile)
        contract = run["binding"]["contract"]
        currency = contract["currency"]
        rate = fx_rate(currency, self.fx_quotes.values())
        cash = self.currency_facts.get(("CashBalance", currency), {})
        settled = self.currency_facts.get(("SettledCash", currency), {})
        tags = (
            ("AvailableFunds",)
            if run["binding"]["execution_plan"].get("risk_policy") == "paper_stock_v2"
            else ("AvailableFunds", "GrossPositionValue")
        )
        for tag in tags:
            if (
                self.currency_facts
                and any(k[0] == tag for k in self.currency_facts)
                and not any(
                    k[0] == tag and fresh(v, seconds=60) for k, v in self.currency_facts.items()
                )
            ):
                raise Conflict("Fresh account funds and exposure observations are required.")
        if not fresh(cash, seconds=60) or not fresh(settled, seconds=60):
            raise Conflict(
                f"Fresh settled cash and cash balance in {currency} are required; "
                "no currency conversion or borrowing is performed."
            )
        reservations = [r for r in self.store.list("reservation") if r.get("active")]

        def current_rate(reservation):
            if not reservation.get("currency"):
                return Decimal(1)
            return fx_rate(reservation["currency"], self.fx_quotes.values()) / number(
                reservation["fx_rate"]
            )

        reserved = sum(
            (
                (number(r["notional"]) + number(r.get("fee_reserve_usd", 0))) * current_rate(r)
                for r in reservations
            ),
            Decimal(0),
        )
        reserved_risk = sum((number(r["risk"]) * current_rate(r) for r in reservations), Decimal(0))
        native_reserved = sum(
            (
                number(
                    r.get("currency_reserves", {}).get(
                        currency, r.get("native_funds", 0) if r.get("currency") == currency else 0
                    )
                )
                for r in reservations
            ),
            Decimal(0),
        )
        native = min(number(cash["value"]), number(settled["value"])) - native_reserved
        native -= self._fx_owned_currency(currency)
        modern = run["binding"]["execution_plan"].get("risk_policy") == "paper_stock_v2"
        available = min(
            number(self.facts.get("AvailableFunds", 0)) - reserved,
            Decimal(5000) - number(self.facts.get("GrossPositionValue", 5001)) - reserved,
        )
        limits = dict(profile or run["limits"])
        if modern:
            available = number(self.facts.get("AvailableFunds", 0)) - reserved
        else:
            limits["planned_stop_risk"] = str(
                min(
                    number(limits["planned_stop_risk"]),
                    max(Decimal(0), Decimal(50) - reserved_risk),
                )
            )
        qualification = (
            self.store.get("stock_qualification", run["binding"]["execution_plan"]["hash"]) or {}
        )
        required = {"long", "short"} if self._paired_run(run) else {"long"}
        if not modern and not all(qualification.get(k) for k in required):
            limits["stock_units"] = 1
        return size_stock(
            run["binding"]["sizing"],
            limits,
            contract,
            branches,
            rate,
            available,
            native,
            policy=run["binding"]["execution_plan"].get("risk_policy"),
        )

    def _stock_checks(self, run, profile=None):
        from .engine import check

        checks = []
        stage, title, status = "rules", "Contract policy and schedule", "unsupported"
        try:
            contract = run["binding"]["contract"]
            if contract["stock_rules"]["reference"] == AUTO_REFERENCE:
                if os.environ.get("OMS_DISABLE_AUTOMATIC_STOCK_ARM") == "1":
                    raise Conflict("Automatic-policy arming is disabled by the rollback setting.")
                self._resolve_stock_rules(run["conid"], automatic=True)
                if not self.stock_metadata_ready(run["conid"]):
                    raise Conflict(
                        "Refreshing current broker contract rules and session schedule; "
                        "review again when ready."
                    )
                if (
                    contract["currency"] == "HKD"
                    and (self.contracts[run["conid"]].get("reference_data") or {}).get("status")
                    != "ready"
                ):
                    raise Conflict("Current official HKEX lot reference is unavailable.")
            if not self._binding_valid(run):
                raise Conflict("Contract policy changed; prepare a new run binding.")
            if premarket(run) and os.environ.get("OMS_DISABLE_PREMARKET_ARM") == "1":
                raise Conflict(
                    "New pre-market arming is disabled by the operator rollback setting."
                )
            checks.append(
                check(
                    "stock_rules_" + run["id"],
                    title,
                    True,
                    "Current contract identity and execution rules agree.",
                )
            )
            stage, title, status = "session", "Approved stock session", "waiting"
            if premarket(run) and not self._run_history_ready(run):
                raise Conflict("Complete independent extended-hours history before arming.")
            if not self._stock_session(run).tradable(datetime.now(UTC)):
                raise Conflict(
                    "Outside a qualified liquid trading interval (including scheduled breaks)."
                )
            checks.append(
                check(
                    "stock_session_" + run["id"],
                    title,
                    True,
                    "Within the approved exchange interval.",
                )
            )
            stage, title, status = "valuation", "Prices for stock sizing", "waiting"
            quote = self.quotes.get(run["conid"], {}).get("ask", {})
            if not fresh(quote):
                raise Conflict("A fresh ask is required for indicative stock sizing.")
            ask = number(quote["price"])
            graph = self._runtime(run)
            stop = (graph.get("last_result") or {}).get("stop")
            if run["execution"] in {"stock_breakout", "oca_breakout"}:
                stop = protection_price(
                    ask, "long", self.market_rules.get(contract.get("market_rule"), [])
                )
            if stop is None:
                raise Conflict("Wait for this strategy's protective-stop inputs.")
            branches = [(ask, stop)]
            if self._paired_run(run):
                market = graph["market"]
                if not market.closed:
                    raise Conflict("Wait for a completed candle before reviewing OCA sizing.")
                from .oca import pair_prices

                candle = market.closed[-1]
                prices = pair_prices(
                    candle.high, candle.low, self.market_rules.get(contract.get("market_rule"), [])
                )
                branches = [
                    (number(prices[s + "_entry"]), number(prices[s + "_stop"]))
                    for s in ("long", "short")
                ]
            stage, title, status = "funding", "Broker buying power and quantity", "blocked"
            quantity, reservation = self._stock_size(run, branches, profile)
            detail = (
                f"{quantity} shares; {reservation['native_funds']} "
                f"{contract['currency']} estimated funding; "
                f"USD {reservation['notional']} notional and "
                f"USD {reservation['risk']} planned stop risk."
            )
            if broker_credit(run["binding"]["execution_plan"]):
                allocation = reservation.get(
                    "buying_power_allocation", reservation.get("credit_reserve")
                )
                detail += (
                    f" Funding: {reservation['funding_mode']}; "
                    f"USD {allocation} "
                    "buying power allocated."
                )
            if self._paired_run(run) and not self._oca_borrow_ready(run["conid"], quantity):
                raise Conflict("Fresh sufficient shortable quantity is required for both branches.")
            checks.append(
                {
                    **check(
                        "stock_" + run["id"],
                        title,
                        True,
                        detail,
                    ),
                    "funding": {
                        k: reservation[k]
                        for k in (
                            "funding_mode",
                            "credit_status",
                            "funding_revision",
                            "credit_reserve",
                            "buying_power_allocation",
                            "buying_power_allocation_native",
                            "allocation_currency",
                            "maintenance_reserve",
                        )
                        if k in reservation
                    },
                }
            )
        except ValueError as exc:
            status = getattr(exc, "status", status)
            if "Refreshing current broker" in str(exc):
                status = "checking"
            checks.append(
                {
                    **check("stock_" + stage + "_" + run["id"], title, False, str(exc), None),
                    "status": status,
                }
            )
        return checks

    def _stock_credit_size(self, run, branches, profile=None):
        from datetime import timedelta

        from .oca import rounded

        plan, contract = run["binding"]["execution_plan"], run["binding"]["contract"]
        limits = dict(profile or run["limits"])
        rate = fx_rate(contract["currency"], self.fx_quotes.values())
        if plan.get("risk_policy") != "paper_stock_v2":
            qualification = self.store.get("stock_qualification", plan["hash"]) or {}
            required = {"long", "short"} if self._paired_run(run) else {"long"}
            if not all(qualification.get(k) for k in required):
                limits["stock_units"] = 1
        quantity, reserve = size_stock(
            run["binding"]["sizing"],
            limits,
            contract,
            branches,
            rate,
            None,
            None,
            policy=plan.get("risk_policy"),
        )
        reserve.update(currency_reserves={contract["currency"]: reserve["native_funds"]})
        orders = []
        for index, (price, _) in enumerate(branches):
            paired = self._paired_run(run)
            kind = (
                "STP"
                if paired
                else "MKT"
                if run["execution"] == "stock_breakout" and not premarket(run)
                else "LMT"
            )
            order = {
                "action": "SELL" if index else "BUY",
                "order_type": kind,
                "quantity": str(quantity),
                "price": str(price),
                "outside_rth": premarket(run),
                "tif": "DAY" if kind == "MKT" else "GTD",
            }
            if paired:
                candidate = self.store.get("oca_candidate", run["id"]) or {}
                deadline = candidate.get("expires_at")
                if not deadline:
                    deadline = (
                        datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
                    ).isoformat()
                order.update(
                    good_till_date=datetime.fromisoformat(deadline).strftime("%Y%m%d-%H:%M:%S"),
                    trigger_method=2,
                )
            elif kind == "LMT":
                price = rounded(
                    price, self.market_rules.get(contract.get("market_rule"), []), premarket(run)
                )
                order["price"] = str(price)
                deadlines = getattr(self, "_credit_deadlines", {})
                stamp = datetime.now(UTC)
                deadlines = {k: v for k, v in deadlines.items() if v > stamp}
                if len(deadlines) >= 50 and run["id"] not in deadlines:
                    deadlines.pop(min(deadlines, key=deadlines.get))
                previous = deadlines.get(run["id"])
                if not previous or previous <= stamp:
                    interval = next(
                        (b for a, b in self._stock_session(run).intervals(stamp) if a <= stamp < b),
                        stamp,
                    )
                    trigger = self.store.get("stock_trigger", run["id"]) or {}
                    timeout = min(
                        30,
                        limits.get("entry_timeout", 30),
                        self.store.version(run["strategy_id"], run["version"])["document"][
                            "settings"
                        ]["entry_timeout"],
                    )
                    previous = min(
                        stamp + timedelta(seconds=timeout),
                        interval,
                        datetime.fromisoformat(
                            trigger.get(
                                "expires_at", (stamp + timedelta(seconds=timeout)).isoformat()
                            )
                        ),
                    )
                    deadlines[run["id"]] = previous.replace(microsecond=0)
                    self._credit_deadlines = deadlines
                order["good_till_date"] = deadlines[run["id"]].strftime("%Y%m%d-%H:%M:%S")
                reserve["credit_order_deadline"] = deadlines[run["id"]].isoformat()
            orders.append(order)
        return quantity, self._credit_assess(plan, reserve, orders, run["id"])

    def _stock_payload(self, run, reservation=None):
        return {
            "stock_plan": run["binding"]["execution_plan"],
            "approved_sizing": run["binding"]["sizing"],
            "risk_limits": run.get("limits"),
            "currency": run["binding"]["contract"]["currency"],
            "price_scale": run["binding"]["execution_plan"]["rules"]["price_scale"],
            "binding_hash": run["binding"]["hash"],
            "authorization_id": run.get("authorization_id"),
            "valuation": {**reservation, "checked_at": now()} if reservation else None,
        }

    def _stock_candidate(self, run, state, context, capture):
        # Reuse the proven live-minute latch, stored separately from legacy crypto.
        if state["market"].closed and not state["market"].live_candle_eligible(
            state["market"].closed[-1], datetime.now(UTC)
        ):
            return
        self._crypto_candidate(run, state, context, capture, namespace="stock")

    def _stock_trade(self, event):
        if not self.connected or not self.attested or not self.position_agreement:
            return
        for run in self.store.list("run"):
            if not self._stock_run(run) or run["conid"] != event["conid"]:
                continue
            if not self._stock_session(run).tradable(
                datetime.fromtimestamp(event["timestamp"], UTC)
            ):
                continue
            position = self.owned().get(run["id"])
            plan = self.store.get("stock_protection", run["id"]) or {}
            if position and position["quantity"] > 0:
                if (
                    run["protection_type"] == "locally_monitored"
                    and self._stock_valid_local(position)
                    and (
                        number(event["price"]) <= number(plan["stop"])
                        or plan.get("target")
                        and number(event["price"]) >= number(plan["target"])
                    )
                ):
                    self._request_exit(run["id"])
                continue
            if run["execution"] != "stock_breakout":
                continue
            trigger = self.store.get("stock_trigger", run["id"]) or {}
            if not (
                run.get("armed")
                and not run["entries"]
                and trigger.get("state") in {"monitoring", "credit_wait"}
                and trigger.get("authorization_id") == run.get("authorization_id")
                and trigger["expires_at"] > now()
            ):
                continue
            if datetime.fromtimestamp(event["timestamp"], UTC) < datetime.fromisoformat(
                trigger["started_at"]
            ) or event.get("sequence") == trigger.get("after_sequence"):
                continue
            if number(event["price"]) < number(trigger["high"]):
                continue
            if premarket(run):
                interval = self._stock_session(run).interval_start(
                    datetime.fromtimestamp(event["timestamp"], UTC)
                )
                if interval is None or datetime.fromisoformat(trigger["candle"]) < interval:
                    trigger.update(
                        state="skipped",
                        reason="Session interval changed; wait for a new live minute.",
                    )
                    self.store.put("stock_trigger", run["id"], trigger)
                    continue
            if trigger["state"] != "credit_wait":
                trigger.update(state="triggered" if self._crypto_fresh(run["conid"]) else "skipped")
                self.store.put("stock_trigger", run["id"], trigger)
                self.store.event("strategy.stock.crossing", trigger)
            if trigger["state"] == "skipped":
                continue
            self._signal_detect(
                run,
                {
                    **trigger,
                    "crossing_price": str(event["price"]),
                    "triggered_at": datetime.fromtimestamp(event["timestamp"], UTC).isoformat(),
                },
                trigger["capture"],
            )
            rules = self.market_rules.get(run["binding"]["contract"].get("market_rule"), [])
            try:
                stop = protection_price(
                    number(self.quotes[run["conid"]]["ask"]["price"]), "long", rules
                )
                self._enter(
                    run,
                    {"stop": stop, "target": None},
                    {
                        "minutes_to_close": (
                            datetime.fromisoformat(run["expires_at"]) - datetime.now(UTC)
                        ).total_seconds()
                        / 60
                    },
                    trigger["capture"],
                )
            except ValueError as exc:
                from .credit import CreditPending

                if isinstance(exc, CreditPending):
                    self._signal_outcome(run, "checking", str(exc))
                    if trigger["state"] != "credit_wait":
                        trigger["state"] = "credit_wait"
                        self.store.put("stock_trigger", run["id"], trigger)
                        self.store.event("stock.entry.credit_wait", {"run_id": run["id"]})
                    continue
                self._signal_outcome(run, "blocked", str(exc))
                self.disarm(run["id"], str(exc))
                self.store.event("risk.blocked", {"run_id": run["id"], "reason": str(exc)})

    def _stock_sync(self):
        for position in self.owned().values():
            run = self.store.get("run", position["run_id"])
            if not self._stock_run(run) or self._paired_run(run):
                continue
            entry = next(o for o in self.store.orders() if o["id"] == position["entry_id"])
            if position["quantity"] <= 0:
                continue
            # Ledger average derives only from authoritative execution reports.
            fills = self._oca_executions(entry)
            buys = [e for e in fills if e["side"] == "BOT" and e["broker_id"] == entry["broker_id"]]
            quantity = sum((number(e["quantity"]) for e in buys), Decimal(0))
            if not quantity:
                continue
            average = sum(number(e["quantity"]) * number(e["price"]) for e in buys) / quantity
            stop = entry["payload"]["stop"]
            if run["execution"] == "stock_breakout":
                try:
                    stop = str(protection_price(average, "long", entry["payload"]["price_rules"]))
                except ValueError:
                    self.incident(
                        "protection_uncertain",
                        "The actual stock fill cannot produce a valid 1% stop with the approved "
                        "increments. Preserve existing protection and review the owned position.",
                    )
            plan = {
                "run_id": run["id"],
                "currency": run["binding"]["contract"]["currency"],
                "price_scale": run["binding"]["execution_plan"]["rules"]["price_scale"],
                "entry_id": entry["id"],
                "quantity": str(position["quantity"]),
                "stop": stop,
                "average": str(average),
                "target": entry["payload"].get("target"),
                "type": run["protection_type"],
            }
            reservation = self.store.get("reservation", entry["id"]) or {}
            conversion = number(entry["payload"]["stock_plan"]["rules"]["price_scale"]) * number(
                entry["payload"]["valuation"]["fx_rate"]
            )
            actual_notional = quantity * average * conversion
            actual_risk = quantity * abs(average - number(stop)) * conversion
            if reservation and (
                actual_notional > number(reservation["notional"])
                or actual_risk > number(reservation["risk"])
            ):
                actual_fees = branch_fees(run["binding"]["contract"], quantity, [average])
                native_actual = (
                    quantity
                    * average
                    * number(entry["payload"]["stock_plan"]["rules"]["price_scale"])
                    + actual_fees
                )
                reservation.update(
                    notional=str(max(actual_notional, number(reservation["notional"]))),
                    risk=str(max(actual_risk, number(reservation["risk"]))),
                    native_funds=str(max(native_actual, number(reservation["native_funds"]))),
                    fee_reserve_usd=str(
                        max(
                            number(reservation.get("fee_reserve_usd", 0)),
                            actual_fees * number(entry["payload"]["valuation"]["fx_rate"]),
                        )
                    ),
                )
                if reservation.get("funding_policy") == "paper_buying_power_v1":
                    reservation["buying_power_allocation"] = str(
                        number(reservation["notional"]) + number(reservation["fee_reserve_usd"])
                    )
                self.store.put("reservation", entry["id"], reservation)
                self.store.event(
                    "stock.fill.reservation_updated",
                    {
                        "entry_id": entry["id"],
                        "risk": reservation["risk"],
                        "notional": reservation["notional"],
                    },
                )
                from .paper_risk import effective

                cap = effective(run["binding"]["sizing"]["notional"], run["limits"].get("notional"))
                risk_cap = effective(
                    run["binding"]["sizing"]["risk"], run["limits"].get("planned_stop_risk")
                )
                if (cap is not None and actual_notional > cap) or (
                    risk_cap is not None and actual_risk > risk_cap
                ):
                    self.incident(
                        "stock_fill_gap_limit",
                        "A confirmed stock fill exceeded its planned USD budget. Protection "
                        "remains active; review actual exposure before new entries.",
                    )
            if self.store.get("stock_protection", run["id"]) != plan:
                self.store.put("stock_protection", run["id"], plan)
                self.store.event("stock.protection.planned", {"run_id": run["id"], **plan})
            if entry["state"] in {"working", "dispatching"} and quantity < number(
                entry["payload"]["quantity"]
            ):
                self.cancel_entry(entry["id"], reason="partial_fill")

    def _stock_valid_local(self, position):
        plan = self.store.get("stock_protection", position["run_id"]) or {}
        return bool(
            self.connected
            and self.attested
            and self.position_agreement
            and self._crypto_fresh(position["conid"])
            and plan.get("entry_id") == position["entry_id"]
            and number(plan.get("quantity", 0)) == position["quantity"] > 0
            and number(plan.get("stop", 0)) > 0
        )

    def _stock_local_suspended(self, position):
        run = self.store.get("run", position["run_id"])
        if not self.connected or not self.attested or not self.position_agreement:
            return True
        if not self._stock_session(run).tradable(datetime.now(UTC)):
            return False  # A scheduled closure is not a broken subscription.
        return not self._stock_valid_local(position)

    def _stock_provisional(self, position, entry):
        if not entry["payload"].get("stock_plan"):
            return False
        if entry["payload"].get("protection_type") == "locally_monitored":
            plan = self.store.get("stock_protection", position["run_id"]) or {}
            # Missing protection is a fault; an existing plan suspended by an
            # outage remains recoverable without inventing an exit.
            return bool(plan.get("entry_id") == entry["id"] and number(plan.get("stop", 0)) > 0)
        observed = self.broker_orders.get(entry["broker_id"] + 2, {})
        amendment = self.store.get("stock_amendment", entry["id"]) or {}
        run = self.store.get("run", position["run_id"]) or {}
        return bool(
            observed.get("status") in {"Submitted", "PreSubmitted"}
            and observed.get("own_account") is True
            and observed.get("client_id") == self.broker.client_id
            and observed.get("reference") == "oms-" + entry["id"]
            and observed.get("conid") == position["conid"]
            and number(observed.get("quantity", 0)) - number(observed.get("filled", 0))
            == position["quantity"]
            and (
                fresh(amendment, "requested_at", 10)
                or not amendment
                and fresh(run, "last_fill_at", 10)
            )
        )

    def _stock_expected_prices(self, entry, stop):
        prices = {number(entry["payload"]["stop" if stop else "target"])}
        amendment = self.store.get("stock_amendment", entry["id"]) or {}
        if stop and amendment:
            prices.add(number(amendment["stop"]))
            prices.add(number(amendment["previous_stop"]))
        return prices

    def _stock_amend(self, position, entry):
        if not self.position_agreement or not self.connected or not self.attested:
            return True
        observed = self.broker_orders.get(entry["broker_id"] + 2, {})
        plan = self.store.get("stock_protection", position["run_id"]) or {}
        if not plan or observed.get("status") not in {"Submitted", "PreSubmitted"}:
            return False
        if (
            observed.get("conid") != position["conid"]
            or observed.get("own_account") is not True
            or observed.get("reference") != "oms-" + entry["id"]
        ):
            return True
        if entry["state"] not in {"filled", "cancelled", "rejected"}:
            self.cancel_entry(entry["id"], reason="partial_fill")
            return True
        prior = self.store.get("stock_amendment", entry["id"])
        if prior and (
            number(observed.get("stop", 0)) != number(prior["stop"])
            or number(observed.get("quantity", 0)) != number(prior["quantity"])
        ):
            return True  # Never overwrite an unacknowledged amendment or its existing stop.
        amendment = {
            "broker_id": entry["broker_id"] + 2,
            "quantity": str(position["quantity"]),
            "stop": plan["stop"],
            "previous_stop": str(observed["stop"]),
            "requested_at": now(),
        }
        self.store.put("stock_amendment", entry["id"], amendment)
        self.store.event("stock.protection.amendment", {"entry_id": entry["id"], **amendment})
        try:
            self.broker.amend_stock_stop({**entry["payload"], **entry}, amendment)
        except Exception:
            self.incident(
                "protection_uncertain",
                "Stock protection amendment is uncertain. Existing protection is retained; "
                "reconcile before any new entries.",
            )
        self.next_reconcile = time.monotonic() + 1
        return True

    def _stock_protection_view(self, run_ids=None):
        result = []
        for plan in self.store.list("stock_protection"):
            if run_ids is not None and plan["run_id"] not in run_ids:
                continue
            position = self.owned().get(plan["run_id"], {})
            run = self.store.get("run", plan["run_id"]) or {}
            waiting_session = bool(
                plan["type"] == "locally_monitored"
                and self.connected
                and self.attested
                and self.position_agreement
                and not self._stock_session(run).tradable(datetime.now(UTC))
            )
            result.append(
                {
                    **plan,
                    "status": "closed"
                    if not position.get("quantity")
                    else "waiting_for_session"
                    if waiting_session
                    else "active"
                    if (
                        self._stock_valid_local(position)
                        if plan["type"] == "locally_monitored"
                        else run.get("protected")
                    )
                    else "suspended"
                    if plan["type"] == "locally_monitored"
                    else "awaiting_acknowledgment",
                }
            )
        return result

    def _stock_reconciled(self):
        if not self.reconciled:
            return
        for run in self.store.list("run"):
            if not self._stock_run(run):
                continue
            position = self.owned().get(run["id"])
            if position and position["quantity"]:
                entry = next(o for o in self.store.orders() if o["id"] == position["entry_id"])
                if self._valid_protection(position, entry):
                    self.store.put(
                        "stock_trial",
                        entry["id"],
                        {
                            "protected": True,
                            "direction": "long" if position["quantity"] > 0 else "short",
                        },
                    )
                continue
            for entry in self.store.orders():
                if (
                    entry["run_id"] != run["id"]
                    or entry["payload"].get("purpose") != "entry"
                    or entry["state"] not in {"filled", "cancelled", "rejected"}
                ):
                    continue
                trial = self.store.get("stock_trial", entry["id"]) or {}
                from .broker import PaperGateway

                if (
                    type(self.broker) is PaperGateway
                    and trial.get("protected")
                    and not trial.get("complete")
                ):
                    trial["complete"] = True
                    self.store.put("stock_trial", entry["id"], trial)
                    key = run["binding"]["execution_plan"]["hash"]
                    evidence = self.store.get("stock_qualification", key) or {}
                    evidence[trial["direction"]] = {"entry_id": entry["id"], "timestamp": now()}
                    self.store.put("stock_qualification", key, evidence)
                    self.store.event(
                        "stock.paper.qualified",
                        {"plan": key, "entry_id": entry["id"], "direction": trial["direction"]},
                    )
                if (
                    run["execution"] == "stock_breakout"
                    and run.get("armed")
                    and entry["payload"].get("authorization_id") == run.get("authorization_id")
                ):
                    self.disarm(
                        run["id"],
                        "Trade completed; review and manually arm again."
                        if trial
                        else self._crypto_no_fill_reason(entry),
                    )
