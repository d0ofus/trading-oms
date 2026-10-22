"""Automatic broker/reference stock conventions; no inferred fractional permission."""

from .graph import number
from .stock_fees import AUTO_REFERENCE, fee_reserve

REFERENCE = AUTO_REFERENCE
US_LISTINGS = {"NASDAQ", "NYSE", "ARCA"}


def resolve_rules(contract, fee=None, *, automatic=False):
    old = contract.get("stock_rules")
    if old and old.get("reference") not in {REFERENCE, "US share policy v1"} and not automatic:
        return old, {
            k: {"source": old["source"], "reference": old["reference"], "revision": old["revision"]}
            for k in old
        }
    route = contract.get("routing_exchange", contract.get("exchange"))
    currency = contract.get("currency")
    if not (
        contract.get("sec_type") == "STK"
        and contract.get("resolved") is not False
        and contract.get("multiplier") in (None, "", "1", "1.0")
        and contract.get("price_magnifier", 1) == 1
    ):
        return None, {}
    us = (
        currency == "USD"
        and contract.get("primary_exchange") in US_LISTINGS
        and route in {"SMART", *US_LISTINGS}
    )
    hk = currency == "HKD" and contract.get("primary_exchange") == "SEHK" and route == "SEHK"
    minimum = step = "1"
    try:
        if us:
            if any(
                contract.get(k) and number(contract[k]) > 1 for k in ("min_size", "size_increment")
            ):
                return None, {}
        elif hk:
            ref = contract.get("reference_data") or {}
            minimum, step = contract.get("min_size"), contract.get("size_increment")
            if not (
                ref.get("status") == "ready"
                and ref.get("currency") == currency
                and str(ref.get("symbol", "")).lstrip("0")
                == str(contract.get("symbol", "")).lstrip("0")
                and minimum
                and step
                and ref.get("board_lot")
                and number(minimum) == number(step) == number(ref["board_lot"])
                and number(step) >= 1
                and number(step) % 1 == 0
            ):
                return None, {}
        else:
            return None, {}
    except (ValueError, TypeError):
        return None, {}
    types = set(contract.get("order_types", []))
    r = {
        "revision": 2,
        "source": "official_reference",
        "reference": REFERENCE,
        "currency": currency,
        "calendar": "XNYS" if us else "XHKG",
        "minimum_quantity": str(minimum),
        "quantity_increment": str(step),
        "exit_increment": str(step),
        "price_scale": "1",
        "fee_reserve": str(fee_reserve(currency, number(minimum), 0)),
        "same_day_resale": True,
        "broker_protection": {"LMT", "STP"} <= types,
        "local_protection": "MKT" in types,
        "native_oca": {"OCA", "LMT", "STP"} <= types,
        "fractional_protection": False,
    }
    evidence = {
        k: {
            "source": "ibkr_contract"
            if hk and k in {"minimum_quantity", "quantity_increment"}
            else "documented_support",
            "reference": REFERENCE,
            "revision": 2,
            "route": route,
            "quantity_mode": "whole_shares" if us else "board_lots",
            "session": "regular",
        }
        for k in r
        if k not in {"revision", "source", "reference"}
    }
    if hk:
        for k in ("minimum_quantity", "quantity_increment", "exit_increment"):
            evidence[k]["corroboration"] = contract["reference_data"]
    evidence["fee_reserve"].update(
        source="funding_policy", reference="Round-trip fee reserve v2; refreshed for actual sizing"
    )
    return r, evidence
