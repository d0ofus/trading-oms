"""Explicit opposing-entry groups; legacy long brackets retain their lifecycle."""

from decimal import ROUND_CEILING, ROUND_DOWN, Decimal

from .graph import number
from .store import Conflict

LEG_OFFSETS = {"long_entry": 0, "long_stop": 1, "short_entry": 2, "short_stop": 3}


def is_pair(payload):
    return payload.get("execution") == "oca_breakout"


def price_increment(price, rules):
    tick = number(next((r["increment"] for r in reversed(rules) if price >= number(r["low"])), 0))
    if tick <= 0:
        raise Conflict("Qualified price increments are required for both entries and stops.")
    return tick


def rounded(price, rules, up):
    tick = price_increment(price, rules)
    result = (price / tick).to_integral_value(rounding=ROUND_CEILING if up else ROUND_DOWN) * tick
    # A rounded value can cross a market-rule price boundary.
    tick = price_increment(result, rules)
    return (result / tick).to_integral_value(rounding=ROUND_CEILING if up else ROUND_DOWN) * tick


def protection_price(average, direction, rules):
    long = direction == "long"
    stop = rounded(average * (Decimal("0.99") if long else Decimal("1.01")), rules, long)
    if stop <= 0 or (stop >= average if long else stop <= average):
        raise Conflict("The 1% protection distance is smaller than a valid price increment.")
    return stop


def pair_prices(high, low, rules):
    if not 0 < low < high:
        raise Conflict("The completed live candle needs a positive range.")
    high, low = rounded(high, rules, True), rounded(low, rules, False)
    return {
        "long_entry": str(high),
        "short_entry": str(low),
        "long_stop": str(protection_price(high, "long", rules)),
        "short_stop": str(protection_price(low, "short", rules)),
    }


def size_pair(settings, profile, prices, available, contract):
    high, low = number(prices["long_entry"]), number(prices["short_entry"])
    unit_risk = high - number(prices["long_stop"]) + number(prices["short_stop"]) - low
    risk = min(number(settings["risk"]), number(profile["planned_stop_risk"]), Decimal(10))
    notional = min(
        number(settings["notional"]), number(profile["notional"]), available, Decimal(1000)
    )
    crypto = settings.get("instrument_profile") == "paxos_crypto"
    increment = number(contract.get("size_increment", 0)) if crypto else Decimal(1)
    minimum = number(contract.get("min_size", 0)) if crypto else Decimal(1)
    if increment <= 0 or minimum <= 0:
        raise Conflict("Qualified quantity increments are required.")
    quantity = min(
        risk / unit_risk,
        notional / (high + low),
        number(profile.get("quantity", "10") if crypto else profile["shares"]),
    )
    if settings["sizing"] == "fixed":
        quantity = min(quantity, number(settings["quantity"] if crypto else settings["shares"]))
    quantity = (quantity / increment).to_integral_value(rounding=ROUND_DOWN) * increment
    if quantity < minimum:
        raise Conflict(
            "Both entry branches exceed the combined funds, notional or stop-risk budget."
        )
    return quantity, {
        "symbol": settings["symbol"],
        "risk": str(quantity * unit_risk),
        "notional": str(quantity * (high + low)),
    }


def pair_legs(intent):
    """Return four fully described legs, with stable references on each bracket."""
    ids = intent["leg_ids"]
    result = {}
    for name in LEG_OFFSETS:
        direction, purpose = name.split("_")
        entry = purpose == "entry"
        action = "BUY" if (direction == "long") == entry else "SELL"
        result[name] = {
            "broker_id": ids[name],
            "action": action,
            "order_type": "STP",
            "stop": intent["prices"][name],
            "quantity": str(intent["quantity"]),
            "parent_id": 0 if entry else ids[direction + "_entry"],
            "tif": "GTD" if entry else "GTC",
            "oca_type": 1 if entry else 2,
            "oca_group": "oms-" + (intent["id"] if entry else intent["exit_groups"][direction]),
            "reference": "oms-" + intent["id"],
            "purpose": "entry" if entry else "protection",
            "direction": direction,
            "group_id": intent["id"],
            "leg": name,
        }
    return result
