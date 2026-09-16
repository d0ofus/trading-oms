"""Broker-independent strategy transitions and bounded whole-share sizing."""

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


def size_entry(settings, profile, limit, stop, available):
    if stop is None or not 0 < stop < limit:
        raise Conflict("The protective stop must be positive and below the entry limit.")
    risk = min(number(settings["risk"]), number(profile["planned_stop_risk"]))
    notional = min(number(settings["notional"]), number(profile["notional"]), available)
    quantity = min(profile["shares"], int(notional / limit), int(risk / (limit - stop)))
    if settings["sizing"] == "fixed":
        quantity = min(quantity, settings["shares"])
    if quantity < 1:
        raise Conflict("One share exceeds available funds, notional or planned stop risk.")
    return quantity
