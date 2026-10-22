"""Explicit quote-based FX graphs; published stock and crypto graphs are unchanged."""

import copy

from .graph import Compiled, GraphError, canonical, compile_graph, digest
from .stock_strategies import compile_stock, stock_copy

SOURCES = {"MIDPOINT", "BID", "ASK"}


def fx_copy(document):
    source = copy.deepcopy(compile_graph(document).document)
    if len(source["nodes"]) != 1 or source["nodes"][0]["kind"] != "long_breakout":
        raise GraphError("FX currently supports the Previous-minute long-only breakout only.")
    if source["schema_version"] != 9:
        source = stock_copy(source, 8)
    source["schema_version"] = 9
    source["settings"].update(signal_source="MIDPOINT", breakout_comparison="gt", sizing="fixed")
    return compile_fx(source).document


def compile_fx(raw):
    source = copy.deepcopy(raw)
    settings = source.get("settings")
    if not isinstance(settings, dict) or settings.get("signal_source") not in SOURCES:
        raise GraphError("FX signal source must be Midpoint, Bid or Ask.")
    if settings.get("breakout_comparison") != "gt":
        raise GraphError("The FX breakout must strictly exceed the previous-minute high.")
    if settings.get("sizing") != "fixed":
        raise GraphError("The initial FX strategy uses explicit base-currency quantity.")
    nodes = source.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 1 or nodes[0].get("kind") != "long_breakout":
        raise GraphError("FX currently supports the Previous-minute long-only breakout only.")
    basis = settings.pop("signal_source")
    settings.pop("breakout_comparison")
    source["schema_version"] = 8
    checked = compile_stock(source)
    document = checked.document
    document["schema_version"] = 9
    document["settings"].update(signal_source=basis, breakout_comparison="gt")
    semantic = {
        **document,
        "nodes": [{k: n[k] for k in ("id", "kind", "params")} for n in document["nodes"]],
        "edges": sorted(document["edges"], key=canonical),
    }
    return Compiled(document, document["nodes"], checked.inputs, digest(semantic))


def requirements(document):
    checked = compile_fx(document).document
    return {
        "kind": "fx_breakout",
        "trade_ticks": False,
        "quotes": True,
        "history": True,
        "volume": False,
        "reference_sessions": 0,
        "lookback_bars": 1,
        "timeframe": 60,
        "short": False,
        "native_oca": False,
        "signal_source": checked["settings"]["signal_source"],
    }
