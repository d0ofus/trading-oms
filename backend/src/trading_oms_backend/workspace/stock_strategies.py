"""Instrument-independent stock graphs. Legacy validators and hashes stay unchanged."""

import copy

from .graph import Compiled, GraphError, canonical, compile_graph, digest

BOUND = {"symbol", "shares", "quantity", "instrument_profile"}


def stock_copy(document, schema_version=7):
    source = copy.deepcopy(compile_graph(document).document)
    source["schema_version"] = schema_version
    source["settings"] = {k: v for k, v in source["settings"].items() if k not in BOUND}
    return compile_stock(source).document


def compile_stock(raw):
    if set(raw) != {"schema_version", "settings", "nodes", "edges"} or not isinstance(
        raw["settings"], dict
    ):
        raise GraphError("Stock strategies require rules and settings.")
    if not isinstance(raw["nodes"], list) or not all(isinstance(n, dict) for n in raw["nodes"]):
        raise GraphError("Stock strategy blocks must be a list of named blocks.")
    if BOUND & raw["settings"].keys():
        raise GraphError("Select the stock and quantity when preparing a run.")
    # Reuse structural validation only. No real instrument is bound or classified here.
    source = copy.deepcopy(raw)
    version = source["schema_version"]
    optional = {}
    if version == 8:
        from .paper_risk import ceiling

        for key in ("risk", "notional"):
            value = ceiling(source["settings"].get(key))
            optional[key] = str(value) if value is not None else None
        if source["settings"].get("sizing", "fixed") == "risk" and optional["risk"] is None:
            raise GraphError("Risk sizing requires a positive stop-risk budget.")
        source["settings"].setdefault("sizing", "fixed")
        # Legacy validation validates node structure without changing its old limits.
        source["settings"].update(risk="10", notional="1000")
    special = any(
        n.get("kind") in {"long_breakout", "paired_stop"}
        for n in source["nodes"]
        if isinstance(n, dict)
    )
    long = any(n.get("kind") == "long_breakout" for n in source["nodes"] if isinstance(n, dict))
    source["schema_version"] = 5 if special else 3
    source["settings"].update(symbol="SPY", shares=1)
    if special:
        source["settings"]["instrument_profile"] = "us_equity"
    for node in source["nodes"]:
        if node.get("kind") == "long_breakout":
            node["kind"] = "paired_stop"
    checked = compile_graph(source)
    document = copy.deepcopy(checked.document)
    document["schema_version"] = version
    document["settings"] = {k: v for k, v in document["settings"].items() if k not in BOUND}
    document["settings"].update(optional)
    if long:
        document["nodes"][0]["kind"] = "long_breakout"
    nodes = {n["id"]: n for n in document["nodes"]}
    semantic = {
        **document,
        "nodes": [
            {k: n[k] for k in ("id", "kind", "params")}
            for n in sorted(nodes.values(), key=lambda n: n["id"])
        ],
        "edges": sorted(document["edges"], key=canonical),
    }
    return Compiled(
        document, [nodes[n["id"]] for n in checked.ordered], checked.inputs, digest(semantic)
    )


def requirements(document):
    graph = compile_graph(document)
    fields = {n["params"]["field"] for n in graph.ordered if n["kind"] == "field"}
    kinds = {n["kind"] for n in graph.ordered}
    return {
        "trade_ticks": True,
        "quotes": True,
        "history": True,
        "volume": bool(fields & {"volume", "session_volume", "relative_volume"}),
        "reference_sessions": 10 if "relative_volume" in fields else 0,
        "lookback_bars": max((n["params"].get("period", 1) for n in graph.ordered), default=1),
        "timeframe": graph.document["settings"]["timeframe"],
        "short": "paired_stop" in kinds,
        "native_oca": "paired_stop" in kinds,
        "kind": "oca_breakout"
        if "paired_stop" in kinds
        else "stock_breakout"
        if "long_breakout" in kinds
        else "stock_bracket",
    }


def stock_templates(schema_version=7):
    from .reusable import shared_templates

    result = [
        {
            **t,
            "document": stock_copy(t["document"]),
            "description": (
                "Reusable stock rules; contract, quantity and protection "
                "are reviewed when preparing a run."
            ),
        }
        for t in shared_templates()
    ]
    if schema_version == 8:
        for item in result:
            item["document"]["schema_version"] = 8
            item["document"]["settings"].update(notional=None, risk=None, sizing="fixed")
            item["document"] = compile_stock(item["document"]).document
    return result
