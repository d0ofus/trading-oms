"""Schema 6 shares rules; only an immutable run binding selects an instrument."""

import copy

from .contracts import execution_kind, reviewed_sizing
from .graph import Compiled, GraphError, canonical, compile_graph, digest, templates

BOUND_FIELDS = {"symbol", "shares", "quantity", "instrument_profile"}


def reusable_copy(document):
    result = copy.deepcopy(compile_graph(document).document)
    result["schema_version"] = 6
    result["settings"] = {k: v for k, v in result["settings"].items() if k not in BOUND_FIELDS}
    return compile_reusable(result).document


def _project(document, contract, sizing):
    result = copy.deepcopy(document)
    kind = execution_kind(document)
    paired = kind in {"oca_breakout", "crypto_breakout"}
    result["schema_version"] = 5 if paired else 3
    result["settings"].update(symbol=contract["symbol"], shares=sizing.get("shares", 1))
    result["settings"].update({k: v for k, v in sizing.items() if k != "shares"})
    if paired:
        result["settings"]["instrument_profile"] = "us_equity"
    if kind == "crypto_breakout":
        result["nodes"][0]["kind"] = "paired_stop"
        result["settings"].pop("shares")
        result["settings"].update(instrument_profile="paxos_crypto", quantity="0.001")
    return result


def compile_reusable(raw):
    if set(raw) != {"nodes", "edges", "settings", "schema_version"} or not isinstance(
        raw["settings"], dict
    ):
        raise GraphError("Reusable strategies require rules and settings.")
    if BOUND_FIELDS & set(raw["settings"]):
        raise GraphError("Choose the contract and quantity when preparing a run.")
    long = any(n.get("kind") == "long_breakout" for n in raw["nodes"] if isinstance(n, dict))
    projected = _project(raw, {"symbol": "BTC" if long else "SPY"}, {})
    validated = compile_graph(projected)
    document = copy.deepcopy(validated.document)
    document["schema_version"] = 6
    document["settings"] = {k: v for k, v in document["settings"].items() if k not in BOUND_FIELDS}
    if long:
        document["nodes"][0]["kind"] = "long_breakout"
    semantic = {
        **document,
        "nodes": [
            {k: n[k] for k in ("id", "kind", "params")}
            for n in sorted(document["nodes"], key=lambda n: n["id"])
        ],
        "edges": sorted(document["edges"], key=canonical),
    }
    return Compiled(
        document,
        document["nodes"] if long else validated.ordered,
        validated.inputs,
        digest(semantic),
    )


def bind_graph(document, binding):
    if document["schema_version"] in (7, 8, 9):
        graph = compile_graph(document)
        if binding:
            graph.document["settings"].update(binding["sizing"])
            graph.document["settings"]["symbol"] = binding["contract"]["symbol"]
        return graph
    if document["schema_version"] != 6:
        return compile_graph(document)
    generic = compile_graph(document)
    graph = compile_graph(
        _project(
            generic.document, binding["contract"], reviewed_sizing(document, binding.get("sizing"))
        )
    )
    graph.digest = generic.digest
    return graph


def shared_templates():
    items = [{**item, "document": reusable_copy(item["document"])} for item in templates()]
    long = copy.deepcopy(items[-1])
    long.update(
        id="previous-minute-long",
        name="Previous-minute long-only breakout",
        description=(
            "PAXOS BTC/ETH paper cash-budget entry with a locally monitored 1% stop. No short"
            " branch."
        ),
    )
    long["document"]["nodes"][0].update(
        kind="long_breakout", label="Previous-minute long-only breakout"
    )
    long["document"]["settings"]["notional"] = "25"
    items.append(long)
    return items
