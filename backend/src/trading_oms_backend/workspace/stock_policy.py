"""Decimal stock economics and evidence checks, without broker side effects."""

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal

from .graph import digest, number
from .stock_fees import AUTO_REFERENCE, branch_fees
from .stock_sessions import stock_calendar
from .stock_strategies import requirements
from .store import Conflict

POLICY_VERSION = 1
RULE_FIELDS = {
    "revision",
    "source",
    "reference",
    "calendar",
    "quantity_increment",
    "minimum_quantity",
    "exit_increment",
    "price_scale",
    "same_day_resale",
    "broker_protection",
    "native_oca",
    "local_protection",
    "fractional_protection",
    "fee_reserve",
    "currency",
}


def validate_rules(contract):
    r = contract.get("stock_rules") or {}
    if set(r) != RULE_FIELDS or r["source"] not in {
        "ibkr_contract",
        "operator_verified",
        "official_reference",
    }:
        raise Conflict("Verified stock lot, price, session and protection rules are required.")
    if r["reference"] not in {
        "TWS contract details",
        "IBKR contract search",
        "Exchange specification",
        "IBKR contract metadata",
        "US share policy v1",
        AUTO_REFERENCE,
    }:
        raise Conflict("Choose a supported instrument-rule reference.")
    if (
        type(r["revision"]) is not int
        or r["revision"] < 1
        or r["currency"] != contract.get("currency")
    ):
        raise Conflict("Instrument-rule revision or currency does not match the contract.")
    for field in ("quantity_increment", "minimum_quantity", "exit_increment", "price_scale"):
        if number(r[field]) <= 0:
            raise Conflict("Positive qualified quantity and price conventions are required.")
    if number(r["minimum_quantity"]) % number(r["quantity_increment"]) or number(
        r["quantity_increment"]
    ) % number(r["exit_increment"]):
        raise Conflict("Minimum, entry increment and exit increment must agree.")
    for field in (
        "same_day_resale",
        "broker_protection",
        "native_oca",
        "local_protection",
        "fractional_protection",
    ):
        if type(r[field]) is not bool:
            raise Conflict("Stock execution capabilities require explicit evidence.")
    if (
        min(number(r["quantity_increment"]), number(r["exit_increment"])) < 1
        and not r["fractional_protection"]
    ):
        raise Conflict("Fractional entry, protection and exits are not qualified.")
    if number(r["fee_reserve"]) < 0:
        raise Conflict("A non-negative fee reserve is required.")
    stock_calendar(r["calendar"])
    return r


def compatibility(contract, document, protection="broker_held", session_mode="regular"):
    needs = requirements(document)
    blockers, status = [], "needs_qualification"
    if contract.get("sec_type") != "STK" or contract.get("resolved") is False:
        if contract.get("sec_type") == "CASH":
            return {
                "status": "incompatible",
                "requirements": needs,
                "plan": None,
                "blockers": [
                    "This published definition requires a STK contract. For IDEALPRO currency "
                    "pairs, create and explicitly publish an FX copy of Previous-minute "
                    "Long-only Breakout in Studio."
                ],
            }
        blockers.append(
            "Select a resolved share-based STK contract; "
            "other asset families are outside this implementation."
        )
        status = "incompatible"
    try:
        r = validate_rules(contract)
    except (ValueError, KeyError, TypeError) as exc:
        blockers.append(str(exc))
        return {
            "status": "unknown" if status != "incompatible" else status,
            "blockers": blockers,
            "requirements": needs,
            "plan": None,
        }
    if contract.get("multiplier") not in (None, "", "1", "1.0"):
        blockers.append("This contract does not have qualified share-based economics.")
    if not r["same_day_resale"]:
        blockers.append(
            "Same-day resale is unavailable; these intraday exit rules cannot be satisfied."
        )
    if contract.get("ineligible"):
        blockers.append("IBKR reports that this account is ineligible for the contract.")
        status = "temporarily_blocked"
    if (
        min(number(r["quantity_increment"]), number(r["exit_increment"])) < 1
        and contract.get("routing_exchange", contract.get("exchange")) != "SMART"
    ):
        blockers.append("Fractional stock orders require a qualified SMART workflow.")
    if session_mode not in {"regular", "premarket_regular"}:
        blockers.append("Select a supported trading session.")
    extended = session_mode == "premarket_regular"
    if extended and not (
        needs["kind"] == "stock_breakout"
        and contract.get("currency") == "USD"
        and contract.get("primary_exchange") in {"NASDAQ", "NYSE", "ARCA"}
        and contract.get("routing_exchange", contract.get("exchange")) in {"SMART", "NASDAQ"}
        and protection == "locally_monitored"
        and all(
            number(r[k]) == 1
            for k in ("minimum_quantity", "quantity_increment", "exit_increment", "price_scale")
        )
        and contract.get("trading_hours")
        and contract.get("liquid_hours")
        and contract.get("time_zone") in {"US/Eastern", "America/New_York", "EST5EDT"}
    ):
        blockers.append(
            "Pre-market requires the long-only breakout, qualified US whole shares, "
            "SMART/NASDAQ routing, current schedules and explicitly approved local protection."
        )
    if protection not in {"broker_held", "locally_monitored"}:
        blockers.append("Choose broker-held or explicitly reviewed local protection.")
    types = set(contract.get("order_types", []))
    required = {"LMT", "STP"} if protection == "broker_held" else {"LMT", "MKT"}
    if needs["kind"] == "stock_breakout":
        required.add("MKT")
        if protection == "locally_monitored":
            required.discard("LMT")
    if extended:
        required = {"LMT"}
    if not required <= types:
        blockers.append("Required entry, exit or protective order types are not reported by IBKR.")
    if protection == "broker_held" and not r["broker_protection"]:
        blockers.append("Broker-held protection and partial/odd-lot exits are not verified.")
    if protection == "locally_monitored" and not r["local_protection"]:
        blockers.append("Local protection and partial/odd-lot exits are not verified.")
    if needs["native_oca"] and (not r["native_oca"] or protection != "broker_held"):
        blockers.append(
            "This strategy requires native protected OCA with overfill protection; "
            "local cancellation is not equivalent."
        )
    if not contract.get("market_rule"):
        blockers.append("Exchange price-increment rules are missing.")
    plan = {
        "version": POLICY_VERSION,
        "kind": needs["kind"],
        "conid": contract.get("conid"),
        "currency": contract.get("currency"),
        "risk_currency": "USD",
        "rules": dict(r),
        "protection_type": protection,
        "session_policy": "stock:" + r["calendar"],
        "requirements": needs,
        "routing_exchange": contract.get("routing_exchange", contract.get("exchange")),
    }
    if document["schema_version"] == 8:
        from .paper_risk import POLICY

        plan["risk_policy"] = POLICY
    if extended:
        plan.update(
            version=2,
            session_mode=session_mode,
            session_policy="stock:us_premarket_regular:v1",
            entry_type="LMT",
            exit_type="LMT",
            outside_rth=True,
            exit_retry_seconds=10,
            unfilled_exit_alert_seconds=30,
        )
    plan["hash"] = digest(plan)
    return {
        "status": status if not blockers or status == "temporarily_blocked" else "incompatible",
        "blockers": blockers,
        "requirements": needs,
        "plan": plan,
    }


def fx_rate(currency, quotes, stamp=None, liability=True):
    if currency == "USD":
        return Decimal(1)
    stamp = stamp or datetime.now(UTC)
    for q in quotes:
        if {q.get("base"), q.get("quote")} != {currency, "USD"}:
            continue
        try:
            age = (stamp - datetime.fromisoformat(q["received_at"])).total_seconds()
            bid, ask = number(q["bid"]), number(q["ask"])
            if not 0 <= age <= 60 or not 0 < bid <= ask or q.get("live") is not True:
                continue
            return (
                (ask if liability else bid)
                if q["base"] == currency
                else 1 / (bid if liability else ask)
            )
        except (ValueError, KeyError, TypeError):
            continue
    raise Conflict(
        f"A fresh live {currency}/USD valuation quote is required (maximum age 60 seconds)."
    )


def size_stock(
    settings, profile, contract, branches, rate, available_usd, available_native, *, policy=None
):
    r = validate_rules(contract)
    scale, step, minimum = (
        number(r[k]) for k in ("price_scale", "quantity_increment", "minimum_quantity")
    )
    if rate <= 0 or not branches or any(p <= 0 or s <= 0 or p == s for p, s in branches):
        raise Conflict("Valid entry, stop and currency values are required.")
    cost = sum((p * scale for p, _ in branches), Decimal(0))
    risk = sum((abs(p - s) * scale for p, s in branches), Decimal(0)) * rate
    fees = number(r["fee_reserve"]) * len(branches)
    if policy == "paper_stock_v2":
        return _explicit_stock(
            settings,
            profile,
            contract,
            branches,
            rate,
            available_usd,
            available_native,
            cost,
            risk,
            step,
            minimum,
        )
    cap = min(number(settings["notional"]), number(profile["notional"]), Decimal(1000))
    risk_cap = min(number(settings["risk"]), number(profile["planned_stop_risk"]), Decimal(10))
    candidates = [cap / (cost * rate), risk_cap / risk]
    if available_usd is not None:
        candidates.append((available_usd / rate - fees) / cost)
    if available_native is not None:
        candidates.append((available_native - fees) / cost)
    quantity = min(candidates)
    if profile.get("stock_units") is not None:
        quantity = min(quantity, number(profile["stock_units"]) * minimum)
    if settings["sizing"] == "fixed":
        quantity = min(quantity, number(settings["shares"]))
    quantity = (max(Decimal(0), quantity) / step).to_integral_value(rounding=ROUND_DOWN) * step
    # Reserve fees at the largest candidate first; reducing quantity cannot increase
    # this conservative reserve. Never expand sizing to pay a minimum commission.
    fees = branch_fees(contract, quantity, [p for p, _ in branches])
    funding = [
        v
        for v in (available_usd / rate if available_usd is not None else None, available_native)
        if v is not None
    ]
    if funding:
        quantity = min(quantity, max(Decimal(0), min(funding) - fees) / cost)
    quantity = (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step
    if quantity < minimum:
        raise Conflict(
            f"The minimum {minimum} shares requires {minimum * cost} {contract['currency']} "
            "plus fees; it exceeds an approved quantity, funding, USD notional or stop-risk limit."
        )
    return quantity, {
        "conid": contract["conid"],
        "symbol": contract["symbol"],
        "currency": contract["currency"],
        "risk": str(quantity * risk),
        "notional": str(quantity * cost * rate),
        "native_funds": str(quantity * cost + fees),
        "fx_rate": str(rate),
        "fee_reserve_usd": str(fees * rate),
    }


def _explicit_stock(
    settings,
    profile,
    contract,
    branches,
    rate,
    available_usd,
    available_native,
    cost,
    risk,
    step,
    minimum,
):
    from .paper_risk import POLICY, effective

    cap = effective(settings["notional"], profile["notional"])
    risk_cap = effective(settings["risk"], profile["planned_stop_risk"])
    if settings["sizing"] == "fixed":
        quantity = number(settings["shares"])
    else:
        if risk_cap is None:
            raise Conflict("Risk sizing requires a positive stop-risk budget.")
        candidates = [risk_cap / risk]
        if available_usd is not None:
            candidates.append(available_usd / (cost * rate))
        if available_native is not None:
            candidates.append(available_native / cost)
        if cap is not None:
            candidates.append(cap / (cost * rate))
        quantity = (min(candidates) / step).to_integral_value(rounding=ROUND_DOWN) * step
    if quantity < minimum or quantity % step:
        raise Conflict("The requested quantity does not satisfy the minimum and legal increment.")
    if (
        profile.get("stock_units") is not None
        and quantity > number(profile["stock_units"]) * minimum
    ):
        raise Conflict("The requested quantity exceeds the selected one-lot profile.")
    fees = branch_fees(contract, quantity, [p for p, _ in branches])
    funding = [
        v
        for v in (available_usd / rate if available_usd is not None else None, available_native)
        if v is not None
    ]
    if settings["sizing"] == "risk" and funding:
        quantity = min(quantity, max(Decimal(0), min(funding) - fees) / cost)
        quantity = (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step
        fees = branch_fees(contract, quantity, [p for p, _ in branches])
    notional, planned, funds = quantity * cost * rate, quantity * risk, quantity * cost + fees
    if (
        quantity < minimum
        or (available_native is not None and funds > available_native)
        or (available_usd is not None and funds * rate > available_usd)
    ):
        raise Conflict(
            f"Requested quantity {quantity} requires {funds} {contract['currency']} "
            "including fees; insufficient available funds."
        )
    if (cap is not None and notional > cap) or (risk_cap is not None and planned > risk_cap):
        raise Conflict(
            "Requested quantity exceeds the approved notional or planned stop-risk ceiling."
        )
    return quantity, {
        "conid": contract["conid"],
        "symbol": contract["symbol"],
        "currency": contract["currency"],
        "risk": str(planned),
        "notional": str(notional),
        "native_funds": str(funds),
        "fx_rate": str(rate),
        "fee_reserve_usd": str(fees * rate),
        "risk_policy": POLICY,
    }
