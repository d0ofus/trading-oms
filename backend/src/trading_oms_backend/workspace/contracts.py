"""Contract identity and deliberately narrow broker execution capabilities."""

from .graph import number

US_EXCHANGES = {"NASDAQ", "NYSE", "ARCA", "AMEX", "BATS", "IEX", "ISLAND"}


def capabilities(contract):
    if (
        contract.get("sec_type") == "CASH"
        and contract.get("routing_exchange", contract.get("exchange")) == "IDEALPRO"
    ):
        from .fx_policy import CURRENCIES

        if contract.get("symbol") in CURRENCIES and contract.get("currency") in CURRENCIES:
            return {
                "executions": ["fx_breakout"],
                "unsupported_reason": None,
                "session_policy": "idealpro_fx_week_v1",
                "protection_type": "broker_held",
                "candle_source": "MIDPOINT",
            }
    security = contract.get("sec_type")
    crypto = (
        security == "CRYPTO"
        and contract.get("symbol") in {"BTC", "ETH"}
        and contract.get("currency") == "USD"
        and contract.get("routing_exchange", contract.get("exchange")) == "PAXOS"
    )
    equity = (
        security == "STK"
        and contract.get("currency") == "USD"
        and contract.get("primary_exchange", contract.get("exchange")) in US_EXCHANGES
    )
    return {
        "executions": ["long_bracket", "oca_breakout"]
        if equity
        else ["crypto_breakout"]
        if crypto
        else [],
        "unsupported_reason": None
        if equity or crypto
        else "Market data only: this contract has no qualified paper execution adapter.",
        "session_policy": "xnys" if equity else "utc_24x7",
        "protection_type": "broker_held" if equity else "locally_monitored" if crypto else None,
        "candle_source": "AGGTRADES"
        if security == "CRYPTO"
        else "MIDPOINT"
        if security == "CASH"
        else "TRADES",
    }


def execution_kind(document):
    if document.get("schema_version") == 9:
        return "fx_breakout"
    if document.get("schema_version") in (7, 8):
        from .stock_strategies import requirements

        return requirements(document)["kind"]
    kinds = {n["kind"] for n in document["nodes"]}
    return (
        "crypto_breakout"
        if "long_breakout" in kinds
        else "oca_breakout"
        if "paired_stop" in kinds
        else "long_bracket"
    )


def execution_reason(contract, document):
    if document.get("schema_version") == 9:
        from .fx_policy import compatibility as fx_compatibility

        return " ".join(fx_compatibility(contract, document)["blockers"]) or None
    if document.get("schema_version") in (7, 8):
        from .stock_policy import compatibility

        blockers = compatibility(contract, document)["blockers"]
        return " ".join(blockers) or None
    kind = execution_kind(document)
    if kind in capabilities(contract)["executions"]:
        return None
    if kind == "oca_breakout" and contract.get("sec_type") == "CRYPTO":
        return (
            "PAXOS cannot execute native opposing stop entries or shorts. Select the separate"
            " long-only breakout template."
        )
    return (
        capabilities(contract)["unsupported_reason"]
        or "This template is incompatible with the selected contract."
    )


def reviewed_sizing(document, sizing=None):
    sizing = dict(sizing or {})
    if set(sizing) - {"shares", "notional", "risk", "sizing"}:
        raise ValueError("Unsupported run sizing field.")
    result = {
        "shares": 1,
        "notional": document["settings"]["notional"],
        "risk": document["settings"]["risk"],
        "sizing": document["settings"]["sizing"],
        **sizing,
    }
    if type(result["shares"]) is not int or not 1 <= result["shares"] <= 10:
        raise ValueError("Use one to ten whole shares for equity runs.")
    if result["sizing"] not in {"fixed", "risk"}:
        raise ValueError("Choose fixed or risk sizing.")
    for key, cap in (("notional", 1000), ("risk", 10)):
        if not 0 < number(result[key]) <= min(number(document["settings"][key]), cap):
            raise ValueError("Run sizing cannot exceed the published strategy ceilings.")
        result[key] = str(number(result[key]))
    return result
