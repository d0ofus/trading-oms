from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


class GraphError(ValueError):
    def __init__(self, message: str, node: str | None = None):
        super().__init__(message)
        self.node = node


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def number(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise GraphError("Use a number, not a Boolean.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise GraphError("Enter a finite number.") from exc
    if not result.is_finite() or abs(result) > Decimal("1e12"):
        raise GraphError("Number is outside the supported range.")
    return result


CATALOG = [
    {
        "kind": "field",
        "label": "Market value",
        "group": "Market",
        "inputs": {},
        "output": "number",
        "defaults": {"field": "close", "period": 20, "source": "current"},
        "fields": [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "last",
            "sma",
            "ema",
            "rolling_high",
            "rolling_low",
            "prior_close",
            "session_volume",
            "relative_volume",
            "opening_high",
            "opening_low",
            "session_low",
        ],
    },
    {
        "kind": "constant",
        "label": "Number",
        "group": "Market",
        "inputs": {},
        "output": "number",
        "defaults": {"value": "1.5"},
    },
    {
        "kind": "math",
        "label": "Calculation",
        "group": "Calculations",
        "inputs": {"a": "number", "b": "number"},
        "output": "number",
        "defaults": {"op": "subtract"},
        "choices": ["add", "subtract", "multiply", "divide"],
    },
    {
        "kind": "compare",
        "label": "Compare",
        "group": "Conditions",
        "inputs": {"a": "number", "b": "number"},
        "output": "boolean",
        "defaults": {"op": "gt"},
        "choices": ["gt", "gte", "lt", "lte", "eq"],
    },
    {
        "kind": "cross",
        "label": "Crosses",
        "group": "Conditions",
        "inputs": {"a": "number", "b": "number"},
        "output": "boolean",
        "defaults": {"direction": "above"},
        "choices": ["above", "below"],
    },
    {
        "kind": "all",
        "label": "Both conditions (AND)",
        "group": "Conditions",
        "inputs": {"a": "boolean", "b": "boolean"},
        "output": "boolean",
        "defaults": {},
    },
    {
        "kind": "any",
        "label": "Either condition (OR)",
        "group": "Conditions",
        "inputs": {"a": "boolean", "b": "boolean"},
        "output": "boolean",
        "defaults": {},
    },
    {
        "kind": "not",
        "label": "Not",
        "group": "Conditions",
        "inputs": {"a": "boolean"},
        "output": "boolean",
        "defaults": {},
    },
    {
        "kind": "session",
        "label": "Entry window",
        "group": "Session",
        "inputs": {},
        "output": "boolean",
        "defaults": {"after_minutes": 5, "before_close_minutes": 15},
    },
    {
        "kind": "cooldown",
        "label": "Time since last entry",
        "group": "Session",
        "inputs": {},
        "output": "boolean",
        "defaults": {"seconds": 60},
    },
    {
        "kind": "entry",
        "label": "Long entry",
        "group": "Trade plan",
        "inputs": {"a": "boolean"},
        "output": "boolean",
        "defaults": {},
    },
    {
        "kind": "prior",
        "label": "Previous value",
        "group": "Calculations",
        "inputs": {"a": "number"},
        "output": "number",
        "defaults": {},
    },
    {
        "kind": "time_exit",
        "label": "Session exit window",
        "group": "Session",
        "inputs": {},
        "output": "boolean",
        "defaults": {"minutes_before_close": 5},
    },
    {
        "kind": "exit",
        "label": "Conditional exit",
        "group": "Trade plan",
        "inputs": {"a": "boolean"},
        "output": "boolean",
        "defaults": {},
    },
    {
        "kind": "stop",
        "label": "Protective stop price",
        "group": "Trade plan",
        "inputs": {"a": "number"},
        "output": "number",
        "defaults": {},
    },
    {
        "kind": "target",
        "label": "Profit target price",
        "group": "Trade plan",
        "inputs": {"a": "number"},
        "output": "number",
        "defaults": {},
    },
]
SPECS = {spec["kind"]: spec for spec in CATALOG}
DEFAULT_SETTINGS = {
    "symbol": "AAPL",
    "timeframe": 60,
    "evaluation": "intrabar",
    "sizing": "risk",
    "shares": 1,
    "risk": "10",
    "notional": "1000",
    "entry_timeout": 30,
    "exit_before_close": 5,
    "max_entries": 5,
}


@dataclass
class Compiled:
    document: dict
    ordered: list[dict]
    inputs: dict[str, dict[str, str]]
    digest: str

    def evaluate(self, market: dict, previous: dict) -> dict:
        values: dict[str, Any] = {}
        outputs: dict[str, Any] = {"entry": False, "exit": False, "stop": None, "target": None}
        for node in self.ordered:
            kind, params, key = node["kind"], node["params"], node["id"]
            refs = self.inputs[key]
            args = {port: values.get(source) for port, source in refs.items()}
            a, b = args.get("a"), args.get("b")
            value: Any = None
            if kind == "field":
                value = market.get(key, market.get(params["field"]))
            elif kind == "constant":
                value = number(params["value"])
            elif kind == "session":
                value = (
                    market.get("minutes_from_open", -1) >= params["after_minutes"]
                    and market.get("minutes_to_close", -1) > params["before_close_minutes"]
                )
            elif kind == "cooldown":
                value = market.get("since_entry", 1e12) >= params["seconds"]
            elif kind == "time_exit":
                remaining = market.get("minutes_to_close")
                value = remaining is not None and 0 <= remaining <= params["minutes_before_close"]
            elif kind == "prior":
                value = previous.get(refs["a"])
            elif any(v is None for v in args.values()):
                value = None
            elif kind == "math":
                op = params["op"]
                value = (
                    a + b
                    if op == "add"
                    else a - b
                    if op == "subtract"
                    else a * b
                    if op == "multiply"
                    else a / b
                    if b
                    else None
                )
            elif kind == "compare":
                value = {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b, "eq": a == b}[
                    params["op"]
                ]
            elif kind == "cross":
                pa, pb = previous.get(refs["a"]), previous.get(refs["b"])
                value = (
                    False
                    if pa is None or pb is None
                    else (
                        pa <= pb and a > b if params["direction"] == "above" else pa >= pb and a < b
                    )
                )
            elif kind == "all":
                value = a is True and b is True
            elif kind == "any":
                value = a is True or b is True
            elif kind == "not":
                value = not a
            else:
                value = a
            if isinstance(value, Decimal) and (
                not value.is_finite() or abs(value) > Decimal("1e12")
            ):
                value = None
            values[key] = value
            if kind in outputs:
                outputs[kind] = value
        return {**outputs, "values": values}

    def explain(self) -> list[dict]:
        text: dict[str, str] = {}
        explanations = []
        for node in self.ordered:
            kind, params, key = node["kind"], node["params"], node["id"]
            args = {port: text[source] for port, source in self.inputs[key].items()}
            a, b = args.get("a", ""), args.get("b", "")
            if kind == "field":
                label = params["field"].replace("_", " ")
                period = (
                    f" ({params['period']} bars)"
                    if params["field"] in {"sma", "ema", "rolling_high", "rolling_low"}
                    else ""
                )
                expression = f"{params['source']} {label}{period}"
                if params["field"] in {"opening_high", "opening_low"}:
                    side = "high" if params["field"] == "opening_high" else "low"
                    expression = f"{side} of the first {params['period']} regular-session minutes"
                elif params["field"] == "relative_volume":
                    expression = (
                        "cumulative relative volume versus 10 matching completed-minute boundaries"
                    )
                elif params["field"] in {"last", "session_volume", "session_low"}:
                    expression = {
                        "last": "last eligible trade",
                        "session_volume": "volume since the regular-session open",
                        "session_low": "low since the regular-session open",
                    }[params["field"]]
                elif self.document["settings"]["evaluation"] == "bar_close":
                    expression = f"completed-candle {label}{period}"
            elif kind == "constant":
                expression = str(params["value"])
            elif kind == "math":
                operator = {"add": "+", "subtract": "−", "multiply": "×", "divide": "÷"}[
                    params["op"]
                ]
                expression = f"({a} {operator} {b})"
            elif kind == "compare":
                operator = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "eq": "="}[params["op"]]
                expression = f"{a} {operator} {b}"
            elif kind == "cross":
                expression = f"{a} crosses {params['direction']} {b}"
            elif kind in {"all", "any"}:
                expression = f"({a}) {'AND' if kind == 'all' else 'OR'} ({b})"
            elif kind == "not":
                expression = f"NOT ({a})"
            elif kind == "session":
                expression = (
                    f"from {params['after_minutes']} minutes after open "
                    f"until {params['before_close_minutes']} minutes before close"
                )
            elif kind == "cooldown":
                expression = f"at least {params['seconds']} seconds since the last entry"
            elif kind == "prior":
                cadence = (
                    "intrabar"
                    if self.document["settings"]["evaluation"] == "intrabar"
                    else "completed-candle"
                )
                expression = f"previous {cadence} evaluation of ({a})"
            elif kind == "time_exit":
                expression = (
                    f"within {params['minutes_before_close']} minutes of the exchange close"
                )
            else:
                expression = a
            text[key] = expression
            if kind in {"entry", "exit", "stop", "target"}:
                explanations.append({"node": key, "kind": kind, "text": expression})
        settings = self.document["settings"]
        explanations.append(
            {
                "node": "settings",
                "kind": "session",
                "text": (
                    "Entries end 15 minutes before the exchange close. "
                    f"Start the session exit {settings['exit_before_close']} minutes before close."
                ),
            }
        )
        size = (
            f"up to {settings['shares']} fixed shares"
            if settings["sizing"] == "fixed"
            else "whole shares sized from the planned stop risk"
        )
        explanations.append(
            {
                "node": "settings",
                "kind": "sizing",
                "text": (
                    f"Use {size}, within ${settings['risk']} planned stop risk "
                    f"and ${settings['notional']} notional. "
                    "Session qualification can impose tighter limits."
                    " Entry requires a false-to-true transition after warm-up, "
                    "at most once per candle."
                ),
            }
        )
        return explanations


def compile_graph(raw: dict) -> Compiled:
    if not isinstance(raw, dict) or set(raw) - {"nodes", "edges", "settings", "schema_version"}:
        raise GraphError("Unsupported strategy document.")
    if raw.get("schema_version") != 3:
        raise GraphError("Strategy schema version must be 3.")
    nodes, edges = raw.get("nodes"), raw.get("edges")
    if (
        not isinstance(nodes, list)
        or not 1 <= len(nodes) <= 100
        or not isinstance(edges, list)
        or len(edges) > 200
    ):
        raise GraphError("Use between 1 and 100 blocks and at most 200 connections.")
    if not isinstance(raw.get("settings", {}), dict):
        raise GraphError("Strategy settings must be named fields.")
    settings = {**DEFAULT_SETTINGS, **raw.get("settings", {})}
    if set(settings) != set(DEFAULT_SETTINGS):
        raise GraphError("Unsupported strategy setting.")
    if not re.fullmatch(r"[A-Z][A-Z0-9. -]{0,14}", str(settings["symbol"])):
        raise GraphError("Choose a supported US equity symbol.")
    if (
        settings["timeframe"] not in (5, 60, 300)
        or settings["evaluation"] not in ("intrabar", "bar_close")
        or settings["sizing"] not in ("risk", "fixed")
    ):
        raise GraphError("Unsupported candle, evaluation or sizing mode.")
    for key, low, high in [
        ("shares", 1, 10),
        ("entry_timeout", 1, 30),
        ("exit_before_close", 5, 60),
        ("max_entries", 1, 5),
    ]:
        if type(settings[key]) is not int or not low <= settings[key] <= high:
            raise GraphError(f"{key.replace('_', ' ')} must be {low}–{high}.")
    for key, cap in [("risk", 10), ("notional", 1000)]:
        if not 0 < number(settings[key]) <= cap:
            raise GraphError(f"{key} must be positive and no more than {cap} for paper testing.")
        settings[key] = str(number(settings[key]))
    lookup: dict[str, dict] = {}
    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            raise GraphError("Each block must have a supported type and parameters.")
        node = dict(raw_node)
        key, kind = node.get("id"), node.get("kind")
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", key)
            or key in lookup
            or not isinstance(kind, str)
            or kind not in SPECS
        ):
            raise GraphError("Block identifiers must be unique and block types supported.")
        if set(node) - {"id", "kind", "label", "position", "params"}:
            raise GraphError("Unsupported block property.", key)
        spec = SPECS[kind]
        if not isinstance(node.get("params", {}), dict):
            raise GraphError("Block parameters must be named fields.", key)
        params = {**spec["defaults"], **node.get("params", {})}
        if set(params) != set(spec["defaults"]):
            raise GraphError("Unsupported block parameter.", key)
        if kind == "field":
            if (
                params["field"] not in spec["fields"]
                or params["source"] not in ("current", "closed")
                or type(params["period"]) is not int
                or not 1 <= params["period"] <= 500
            ):
                raise GraphError(
                    "Select a supported field, candle source and 1–500 bar period.", key
                )
        if "op" in params and params["op"] not in spec.get("choices", []):
            raise GraphError("Select a supported operation.", key)
        if kind == "cross" and params["direction"] not in spec["choices"]:
            raise GraphError("Choose crosses above or below.", key)
        if kind == "constant":
            params["value"] = str(number(params["value"]))
        for field in ("after_minutes", "before_close_minutes", "seconds", "minutes_before_close"):
            if field in params and (
                type(params[field]) is not int or not 0 <= params[field] <= 23400
            ):
                raise GraphError("Use a non-negative whole time interval.", key)
        if not isinstance(node.get("label", ""), str) or len(node.get("label", "")) > 100:
            raise GraphError("Block labels are limited to 100 characters.", key)
        if "position" in node:
            position = node["position"]
            if not isinstance(position, dict) or set(position) != {"x", "y"}:
                raise GraphError("Canvas positions require x and y coordinates.", key)
            for coordinate in position.values():
                number(coordinate)
        node["params"] = params
        lookup[key] = node
    inputs: dict[str, dict[str, str]] = {key: {} for key in lookup}
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"source", "target", "input"}:
            raise GraphError("Invalid connection.")
        source, target, port = edge["source"], edge["target"], edge["input"]
        if not all(isinstance(value, str) for value in (source, target, port)):
            raise GraphError("Connections must identify a source, target and typed input.")
        if source not in lookup or target not in lookup:
            raise GraphError("A connection references a missing block.")
        expected = SPECS[lookup[target]["kind"]]["inputs"].get(port)
        if expected != SPECS[lookup[source]["kind"]]["output"] or port in inputs[target]:
            raise GraphError("Connect one compatible value to each input.", target)
        inputs[target][port] = source
    for key, node in lookup.items():
        if set(inputs[key]) != set(SPECS[node["kind"]]["inputs"]):
            raise GraphError("Connect each required input.", key)
    for kind in ("entry", "stop", "exit", "target"):
        count = sum(n["kind"] == kind for n in lookup.values())
        if count > 1 or (kind in ("entry", "stop") and count != 1):
            raise GraphError(
                "Use exactly one entry and one stop output, and at most one exit and target."
            )
    ordered: list[dict] = []
    remaining = dict(lookup)
    while remaining:
        available = sorted(
            key for key in remaining if all(s not in remaining for s in inputs[key].values())
        )
        if not available:
            raise GraphError("Circular connections cannot execute.")
        ordered.extend(remaining.pop(key) for key in available)
    document = {
        "schema_version": 3,
        "settings": settings,
        "nodes": list(lookup.values()),
        "edges": edges,
    }
    semantic = {
        **document,
        "nodes": [
            {k: n[k] for k in ("id", "kind", "params")}
            for n in sorted(lookup.values(), key=lambda n: n["id"])
        ],
        "edges": sorted(edges, key=canonical),
    }
    return Compiled(document, ordered, inputs, digest(semantic))


def templates() -> list[dict]:
    labels = {
        "price": "Forming candle price",
        "distance": "Stop distance · dollars",
        "stop_calc": "Initial stop calculation",
        "range": "Opening range high",
        "rvol": "Relative session volume",
        "threshold": "Minimum relative volume",
        "volume_rule": "Volume confirmation",
        "both": "Price AND volume",
        "sma_fast": "Fast moving average",
        "sma_slow": "Slow moving average",
        "entry_rule": "Entry crossing",
        "exit_rule": "Exit comparison",
    }

    def node(key, kind, x, y, **params):
        return {
            "id": key,
            "kind": kind,
            "label": labels.get(key, SPECS[kind]["label"]),
            "params": {**SPECS[kind]["defaults"], **params},
            "position": {"x": x, "y": y},
        }

    def edge(source, target, port="a"):
        return {"source": source, "target": target, "input": port}

    common = [
        node("price", "field", 0, 0, field="close"),
        node("distance", "constant", 0, 520, value="1"),
        node("stop_calc", "math", 270, 460, op="subtract"),
        node("stop", "stop", 540, 460),
        node("entry", "entry", 810, 60),
    ]
    connections = [
        edge("price", "stop_calc"),
        edge("distance", "stop_calc", "b"),
        edge("stop_calc", "stop"),
    ]
    breakout = common + [
        node("range", "field", 0, 130, field="opening_high", period=5),
        node("entry_rule", "cross", 260, 0),
        node("rvol", "field", 0, 270, field="relative_volume"),
        node("threshold", "constant", 0, 390, value="1.5"),
        node("volume_rule", "compare", 270, 250, op="gte"),
        node("both", "all", 540, 60),
    ]
    breakout_edges = connections + [
        edge("price", "entry_rule"),
        edge("range", "entry_rule", "b"),
        edge("rvol", "volume_rule"),
        edge("threshold", "volume_rule", "b"),
        edge("entry_rule", "both"),
        edge("volume_rule", "both", "b"),
        edge("both", "entry"),
    ]
    moving = common + [
        node("sma_fast", "field", 0, 140, field="sma", period=5),
        node("sma_slow", "field", 0, 280, field="sma", period=20),
        node("entry_rule", "cross", 280, 100),
        node("exit_rule", "compare", 280, 280, op="lt"),
        node("exit", "exit", 540, 280),
    ]
    moving_edges = connections + [
        edge("sma_fast", "entry_rule"),
        edge("sma_slow", "entry_rule", "b"),
        edge("entry_rule", "entry"),
        edge("sma_fast", "exit_rule"),
        edge("sma_slow", "exit_rule", "b"),
        edge("exit_rule", "exit"),
    ]
    return [
        {
            "id": key,
            "name": name,
            "description": description,
            "document": {
                "schema_version": 3,
                "settings": dict(DEFAULT_SETTINGS),
                "nodes": nodes,
                "edges": edges,
            },
        }
        for key, name, description, nodes, edges in [
            (
                "opening-range",
                "Opening range breakout",
                "A five-minute range break confirmed by relative volume.",
                breakout,
                breakout_edges,
            ),
            (
                "moving-average",
                "Moving average crossover",
                "Fast and slow averages with a separate exit condition.",
                moving,
                moving_edges,
            ),
        ]
    ]
