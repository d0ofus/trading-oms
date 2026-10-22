"""Broker-independent strategy transitions and bounded Decimal/whole-share sizing."""

from decimal import ROUND_DOWN

from .graph import number
from .store import Conflict


def evaluate_step(state, context):
    result = state["graph"].evaluate(context, state["previous"])
    condition = result["entry"] is True
    signal = (
        state["seeded"]
        and condition
        and not state["entry"]
        and state["last_bar"] != context["bar_start"]
    )
    state.update(last_result=result, previous=result["values"], entry=condition, seeded=True)
    if signal:
        state["last_bar"] = context["bar_start"]
    return result, signal


def size_entry(settings, profile, limit, stop, available, contract=None):
    if stop is None or not 0 < stop < limit:
        raise Conflict("The protective stop must be positive and below the entry limit.")
    if profile.get("risk_policy") == "paper_stock_v2":
        from .paper_risk import effective

        risk_cap = effective(settings["risk"], profile.get("planned_stop_risk"))
        cap = effective(settings["notional"], profile.get("notional"))
        if settings["sizing"] == "fixed":
            quantity = number(settings["shares"])
        else:
            if risk_cap is None:
                raise Conflict("Risk sizing requires a positive stop-risk budget.")
            quantity = min(risk_cap / (limit - stop), available / limit)
            if cap is not None:
                quantity = min(quantity, cap / limit)
            quantity = quantity.to_integral_value(rounding=ROUND_DOWN)
        if (
            quantity < 1
            or quantity % 1
            or quantity * limit > available
            or (cap is not None and quantity * limit > cap)
            or (risk_cap is not None and quantity * (limit - stop) > risk_cap)
        ):
            raise Conflict("The explicit replay quantity exceeds funding or optional ceilings.")
        return int(quantity)
    risk = min(number(settings["risk"]), number(profile["planned_stop_risk"]))
    notional = min(number(settings["notional"]), number(profile["notional"]), available)
    if settings.get("instrument_profile") == "paxos_crypto":
        if not contract:
            raise Conflict("Qualified crypto quantity increments are required.")
        increment, minimum = (
            number(contract.get("size_increment", 0)),
            number(contract.get("min_size", 0)),
        )
        if increment <= 0 or minimum <= 0:
            raise Conflict("Qualified crypto quantity increments are required.")
        quantity = min(
            notional / limit, risk / (limit - stop), number(profile.get("quantity", "10"))
        )
        if settings["sizing"] == "fixed":
            quantity = min(quantity, number(settings["quantity"]))
        quantity = (quantity / increment).to_integral_value(rounding=ROUND_DOWN) * increment
        if quantity < minimum:
            raise Conflict("The minimum crypto quantity exceeds available funds, notional or risk.")
        return quantity
    quantity = min(profile["shares"], int(notional / limit), int(risk / (limit - stop)))
    if settings["sizing"] == "fixed":
        quantity = min(quantity, settings["shares"])
    if quantity < 1:
        raise Conflict("One share exceeds available funds, notional or planned stop risk.")
    return quantity
