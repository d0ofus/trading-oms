"""Spot-currency economics and automatic evidence, isolated from share rules."""

from decimal import Decimal

from .fx_sessions import POLICY as SESSION_POLICY
from .fx_sessions import FXSession
from .fx_strategies import requirements
from .graph import digest, number
from .store import Conflict

POLICY = "idealpro_funded_fx_v1"
BROKER_CANDLES = "idealpro_broker_candles_v2"
# Versioned IBKR standard-size reference; actual smaller-order precision comes from
# the resolved contract. These are base units, never a universal USD minimum.
STANDARD = {
    "AUD": ("25000", "6000000"),
    "USD": ("25000", "7000000"),
    "CAD": ("25000", "6000000"),
    "CHF": ("25000", "6000000"),
    "CNH": ("150000", "40000000"),
    "DKK": ("150000", "40000000"),
    "EUR": ("20000", "6000000"),
    "GBP": ("20000", "5000000"),
    "HKD": ("200000", "50000000"),
    "JPY": ("2500000", "550000000"),
    "MXN": ("300000", "70000000"),
    "NOK": ("150000", "35000000"),
    "NZD": ("35000", "8000000"),
    "SEK": ("175000", "40000000"),
    "SGD": ("35000", "8000000"),
    "ZAR": ("350000", "100000000"),
}
CURRENCIES = set(STANDARD) | {
    "AED",
    "BRL",
    "CZK",
    "HUF",
    "ILS",
    "KRW",
    "MYR",
    "PLN",
    "RON",
    "SAR",
    "TRY",
    "TWD",
}


def compatibility(contract, document, protection="broker_held", execution_policy=None):
    execution_policy = execution_policy or POLICY
    if execution_policy not in {POLICY, BROKER_CANDLES}:
        raise Conflict("Unsupported FX execution policy.")
    needs = requirements(document)
    result = {
        "status": "needs_qualification",
        "resolution_status": "ready",
        "blockers": [],
        "requirements": needs,
        "plan": None,
        "rules": None,
        "evidence": {},
        "arming_requirements": [],
        "indicative_sizing": None,
        "field_requirements": [],
    }
    try:
        if (
            contract.get("sec_type") != "CASH"
            or contract.get("resolved") is False
            or contract.get("routing_exchange", contract.get("exchange")) != "IDEALPRO"
            or contract.get("symbol") not in CURRENCIES
            or contract.get("currency") not in CURRENCIES
            or contract.get("symbol") == contract.get("currency")
        ):
            raise Conflict(
                "Select a resolved IDEALPRO spot-currency pair; "
                "metals and other assets are unsupported."
            )
        if contract.get("ineligible"):
            raise Conflict("IBKR reports this account is ineligible for the selected FX contract.")
        values = {}
        for field in ("min_size", "size_increment", "min_tick"):
            try:
                value = number(contract.get(field))
            except (ValueError, TypeError):
                value = Decimal(0)
            if value <= 0:
                raise Conflict(
                    f"IBKR FX {field.replace('_', ' ')} evidence is unavailable; "
                    "refresh broker rules."
                )
            values[field] = value
        if values["min_size"] % values["size_increment"]:
            raise Conflict("IBKR FX minimum and quantity increment conflict.")
        schedule = FXSession(contract)
        if not schedule.broker_intervals:
            raise Conflict("Current broker FX trading intervals are required.")
        if protection not in {"broker_held", "locally_monitored"}:
            raise Conflict("Choose broker-held or explicitly reviewed local protection.")
        needed = {"MKT", "LMT"} | ({"STP"} if protection == "broker_held" else set())
        if not needed <= set(contract.get("order_types", [])):
            raise Conflict(
                "Required FX market entry, exit or protective order types are not reported by IBKR."
            )
        standard, maximum = STANDARD.get(contract["symbol"], (None, None))
        if standard is None:
            raise Conflict(
                "Published IDEALPRO size-policy coverage is unavailable for this base currency."
            )
        rules = {
            "minimum_quantity": str(values["min_size"]),
            "quantity_increment": str(values["size_increment"]),
            "exit_increment": str(values["size_increment"]),
            "exit_minimum": str(values["size_increment"]),
            "residual_policy": "idealpro_smaller_currency_orders_v1",
            "price_increment": str(values["min_tick"]),
            "standard_minimum": standard,
            "maximum_quantity": maximum,
            "reference": "IBKR FX contract and spot-currency policy 2026-09",
            "revision": 1,
        }
        plan = {
            "family": "spot_fx",
            "version": 1,
            "policy": execution_policy,
            "risk_policy": "paper_stock_v2",
            "conid": contract["conid"],
            "base_currency": contract["symbol"],
            "currency": contract["currency"],
            "routing_exchange": "IDEALPRO",
            "sec_type": "CASH",
            "rules": rules,
            "kind": "fx_breakout",
            "signal_source": needs["signal_source"],
            "breakout_comparison": "gt",
            "session_policy": SESSION_POLICY,
            "session_mode": "fx",
            "time_zone": contract["time_zone"],
            "market_rule": contract.get("market_rule"),
            "price_rules": contract.get("price_rules", []),
            "protection_type": protection,
            "entry_type": "MKT",
            "entry_tif": "IOC",
            "exit_type": "LMT",
            "stop_trigger_method": 4,
            "requirements": needs,
        }
        if execution_policy == BROKER_CANDLES:
            plan.update(
                reference_policy="latest_completed_broker_minute",
                candle_source=plan["signal_source"],
            )
        plan["hash"] = digest(plan)
        result.update(plan=plan, rules=rules)
        result["evidence"] = {
            "quantity": "IBKR contract metadata",
            "calendar": SESSION_POLICY,
            "execution": execution_policy,
            "qualification": "documented; broker acceptance not established",
        }
    except (ValueError, TypeError, KeyError) as exc:
        result["blockers"].append(str(exc))
        result.update(status="incompatible", resolution_status="unsupported")
    result["can_prepare"] = not result["blockers"]
    result["preparation_blockers"] = list(result["blockers"])
    return result


def size_fx(plan, sizing, ask, rate, available, fees):
    quantity = number(sizing["quantity"])
    rules = plan["rules"]
    if (
        quantity < number(rules["minimum_quantity"])
        or quantity % number(rules["quantity_increment"])
        or rules["maximum_quantity"]
        and quantity > number(rules["maximum_quantity"])
    ):
        raise Conflict("The requested base-currency quantity violates IBKR FX size rules.")
    if min(ask, rate) <= 0 or fees < 0:
        raise Conflict("Fresh positive FX prices and fee valuation are required.")
    native = quantity * ask
    notional, risk = native * rate, native * rate * Decimal("0.01")
    if available is not None and native + fees > available:
        raise Conflict(
            f"Requested quantity requires {native + fees} {plan['currency']}; "
            "insufficient usable funds."
        )
    if (sizing.get("notional") is not None and notional > number(sizing["notional"])) or (
        sizing.get("risk") is not None and risk > number(sizing["risk"])
    ):
        raise Conflict("Requested FX quantity exceeds a published or reviewed monetary ceiling.")
    return {
        "quantity": str(quantity),
        "notional": str(notional),
        "risk": str(risk),
        "native_funds": str(native + fees),
        "fee_reserve": str(fees),
        "fx_rate": str(rate),
        "currency": plan["currency"],
        "base_currency": plan["base_currency"],
        "conid": plan["conid"],
        "symbol": plan["base_currency"],
        "risk_policy": "paper_stock_v2",
    }
