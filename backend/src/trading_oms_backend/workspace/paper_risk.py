"""Versioned optional monetary ceilings; absence never implies unlimited quantity."""

from .graph import number
from .store import Conflict

POLICY = "paper_stock_v2"


def ceiling(value):
    if value is None:
        return None
    result = number(value)
    if result <= 0:
        raise Conflict("An optional monetary ceiling must be positive or None.")
    return result


def effective(*values):
    limits = [ceiling(value) for value in values if value is not None]
    return min(limits) if limits else None


def sizing_settings(settings, values, minimum, increment):
    if set(values) - {"shares", "notional", "risk", "sizing"}:
        raise Conflict("Unsupported stock sizing field.")
    result = {
        "shares": minimum,
        **{k: settings[k] for k in ("notional", "risk", "sizing")},
        **values,
    }
    quantity = number(result["shares"])
    if quantity < number(minimum) or quantity % number(increment):
        raise Conflict("The requested quantity must satisfy the minimum and legal increment.")
    result["shares"] = str(quantity)
    if result["sizing"] != settings["sizing"]:
        raise Conflict("Sizing mode must match the published strategy.")
    for key in ("notional", "risk"):
        limit, published = ceiling(result[key]), ceiling(settings[key])
        if published is not None and (limit is None or limit > published):
            raise Conflict("Run sizing cannot exceed a published monetary ceiling.")
        result[key] = str(limit) if limit is not None else None
    if result["sizing"] == "risk" and result["risk"] is None:
        raise Conflict("Risk sizing requires a positive stop-risk budget.")
    return result
