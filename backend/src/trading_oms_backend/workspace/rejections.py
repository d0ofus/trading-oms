"""Bounded broker rejection classification. Private input never leaves this boundary."""

import json

EXPLANATIONS = {
    "fractional_quantity": "Fractional quantity unsupported for this contract and order structure.",
    "permissions": (
        "Broker reports missing trading permissions or an account eligibility restriction. "
        "Check the rejected order in TWS and the account's trading permissions."
    ),
    "acknowledgment_required": (
        "Broker requires an acknowledgment or account confirmation. Review the specific "
        "requirement in TWS; the application will not override it."
    ),
    "insufficient_funds": (
        "Broker reports insufficient funds or buying power for this order. "
        "Check the applicable paper-account funds in TWS."
    ),
    "minimum_size": (
        "Broker reports an order below its minimum size or value. Check the contract "
        "requirement; the application will not increase the approved budget."
    ),
    "unsupported_parameters": (
        "Broker reports an unsupported or invalid order parameter. "
        "Inspect the order type, time in force and contract requirements."
    ),
    "unavailable_capability": (
        "Broker reports that this trading capability is unavailable for the account or "
        "environment. Confirm paper execution availability with IBKR."
    ),
    "unknown": (
        "Broker rejected the order, but a safe specific explanation is unavailable. "
        "Inspect the rejection explanation in TWS before another attempt."
    ),
}
ADVANCED_CODES = {"IBDBUYTX", "MOBILEPH"}


def safe_rejection(value=None):
    """Rebuild even internal diagnostics from allowlisted values before persistence."""
    value = value if isinstance(value, dict) else {}
    category = value.get("category")
    if not isinstance(category, str) or category not in EXPLANATIONS:
        category = "unknown"
    code = 10318 if value.get("code") == 10318 else 201
    if code == 10318:
        category = "fractional_quantity"
    codes = value.get("advanced_codes")
    codes = codes if isinstance(codes, list) else []
    return {
        "code": code,
        "category": category,
        "detail": EXPLANATIONS[category],
        "available": category != "unknown",
        "advanced_codes": sorted(
            {v for v in codes[:16] if isinstance(v, str) and v in ADVANCED_CODES}
        ),
    }


def classify_order_rejection(message, advanced="", code=201):
    if code == 10318:
        return safe_rejection({"code": 10318})
    texts = [message] if isinstance(message, str) and len(message) <= 4096 else []
    codes = set()
    if isinstance(advanced, str) and 0 < len(advanced) <= 16384:
        try:
            root = json.loads(advanced)
        except (ValueError, RecursionError):
            root = None
        pending = [(root, 0)]
        for _ in range(128):
            if not pending:
                break
            item, depth = pending.pop()
            if depth > 8:
                continue
            if isinstance(item, dict):
                for key, val in list(item.items())[:32]:
                    if key in {"errorMessage", "errorMsg", "message", "reason", "text"}:
                        if isinstance(val, str) and len(val) <= 4096:
                            texts.append(val)
                    if key in {"8229", "errorTags"} and isinstance(val, str):
                        codes.update(
                            v.strip() for v in val.split(",")[:16] if v.strip() in ADVANCED_CODES
                        )
                    if isinstance(val, (dict, list)):
                        pending.append((val, depth + 1))
            elif isinstance(item, list):
                pending.extend((v, depth + 1) for v in item[:32])
    text = " ".join(texts).lower()
    rules = {
        "unavailable_capability": (
            "not supported in paper",
            "not available in paper",
            "not supported for this account",
            "not available for this account",
            "paper trading is not supported",
        ),
        "permissions": (
            "no trading permission",
            "trading permissions",
            "not eligible",
            "customer ineligible",
            "no opening trades",
        ),
        "acknowledgment_required": (
            "order is not confirmed",
            "acknowledgment required",
            "acknowledgement required",
            "must acknowledge",
            "must accept",
            "confirmation required",
        ),
        "insufficient_funds": (
            "insufficient funds",
            "insufficient buying power",
            "insufficient cash",
            "cash available",
            "insufficient equity",
            "exceeds available funds",
        ),
        "minimum_size": (
            "minimum order size",
            "minimum order value",
            "minimum trade size",
            "minimum trade value",
            "minimum cash quantity",
            "below the minimum",
        ),
        "unsupported_parameters": (
            "invalid time in force",
            "invalid tif",
            "unsupported order type",
            "invalid order type",
            "invalid order parameter",
            "invalid cash quantity",
            "invalid quantity",
            "not supported for this contract",
        ),
    }
    matches = {category for category, phrases in rules.items() if any(p in text for p in phrases)}
    if codes:
        matches.add("acknowledgment_required")
    # Ambiguous private input never becomes a guessed remediation.
    category = matches.pop() if len(matches) == 1 else "unknown"
    return safe_rejection({"category": category, "advanced_codes": sorted(codes)})
