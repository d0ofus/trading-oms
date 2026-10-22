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
        "kind": "paired_stop",
        "label": "Previous minute OCA entries",
        "group": "Trade plan",
        "inputs": {},
        "output": "boolean",
        "defaults": {},
    },
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
CATALOG.append(
    {
        **next(spec for spec in CATALOG if spec["kind"] == "paired_stop"),
        "kind": "long_breakout",
        "label": "Previous-minute long-only breakout",
    }
)
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
        def money_limit(key):
            value = self.document["settings"].get(key)
            return "no monetary ceiling" if value is None else f"USD {value}"

        if self.document["schema_version"] == 9:
            source = self.document["settings"]["signal_source"]
            return [
                {
                    "node": "long",
                    "kind": "entry",
                    "text": f"Use {source} for live signals and matching history. "
                    "Wait for a complete live minute beginning after authorization; "
                    "a fresh price strictly above its unrounded high during the next minute "
                    "submits one paper base-quantity BUY MKT/IOC. Equality does not trigger.",
                },
                {
                    "node": "long",
                    "kind": "stop",
                    "text": "Protect actual fill VWAP at 99%, rounded toward entry. "
                    "Broker-held bid/ask stops or explicitly approved local bid-triggered "
                    "limit exits are pinned in the run. The trigger distance is not a "
                    "guaranteed loss limit.",
                },
                {
                    "node": "long",
                    "kind": "sizing",
                    "text": "Explicit funded base-currency quantity; published notional: "
                    f"{money_limit('notional')}; planned stop risk: {money_limit('risk')}. "
                    "Partial fills become the trade; no top-ups. Pause after completion "
                    "or a terminal zero-fill entry.",
                },
                {
                    "node": "long",
                    "kind": "session",
                    "text": "Use current qualified FX broker intervals. Request the session exit "
                    f"{self.document['settings']['exit_before_close']} minutes before close; "
                    "carry an unresolved exit intent across closure without claiming a fill.",
                },
            ]

        if self.document["schema_version"] in (7, 8) and any(
            n["kind"] == "long_breakout" for n in self.ordered
        ):
            return [
                {
                    "node": "long",
                    "kind": "entry",
                    "text": (
                        "After arming, wait for a new complete eligible live minute. "
                        "A subsequent fresh Last crossing its high submits one paper "
                        "share-based market buy."
                    ),
                },
                {
                    "node": "long",
                    "kind": "stop",
                    "text": (
                        "Protect confirmed fills at 99% of actual average entry, "
                        "rounded toward entry. "
                        "Broker-held or explicitly acknowledged local protection "
                        "is pinned when preparing the run."
                    ),
                },
                {
                    "node": "long",
                    "kind": "sizing",
                    "text": (
                        f"Published notional: {money_limit('notional')}; "
                        + (
                            "approved legal share quantity. "
                            if self.document["schema_version"] == 8
                            else "smallest legal quantity for qualification. "
                        )
                        + "Partial fills count as the trade. "
                        "Pause after closing or a terminal zero-fill entry."
                    ),
                },
            ]
        if any(n["kind"] == "long_breakout" for n in self.ordered):
            return [
                {
                    "node": "long",
                    "kind": "entry",
                    "text": (
                        "Monitor the previous complete live minute high. A subsequent fresh "
                        "Last crossing submits one paper USD cash-budget market buy, IOC. No "
                        "short branch."
                    ),
                },
                {
                    "node": "long",
                    "kind": "stop",
                    "text": (
                        "Locally monitor 99% of actual entry VWAP. A fresh stop breach "
                        "requests a market sell, IOC. Protection cannot execute while the "
                        "application or connection is unavailable."
                    ),
                },
                {
                    "node": "long",
                    "kind": "sizing",
                    "text": (
                        "Initially supervised with a $25 ceiling. Partial fills count as the "
                        "trade. Pause after closing; fresh manual arming is required."
                    ),
                },
            ]
        if any(n["kind"] == "paired_stop" for n in self.ordered):
            return [
                {
                    "node": "pair",
                    "kind": "entry",
                    "text": "Buy stop-market at the previous completed live minute high; "
                    "short sell "
                    "stop-market at its low. First fill cancels the opposite entry. Refresh "
                    "each minute only after confirmed cancellation and reconciliation.",
                },
                {
                    "node": "pair",
                    "kind": "stop",
                    "text": "Fixed 1% protection from actual average entry: 99% for longs, "
                    "101% for "
                    "shorts, rounded toward entry. Stop-market slippage can exceed 1%.",
                },
                {
                    "node": "pair",
                    "kind": "sizing",
                    "text": "Reserve both pending branches under the combined risk and "
                    "notional limits. "
                    "Pause after one completed trade; re-arm manually. Existing "
                    "session exits apply.",
                },
            ]
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
                operator = {
                    "add": "plus",
                    "subtract": "minus",
                    "multiply": "multiplied by",
                    "divide": "divided by",
                }[params["op"]]
                expression = f"({a} {operator} {b})"
            elif kind == "compare":
                operator = {
                    "gt": "greater than",
                    "gte": "greater than or equal to",
                    "lt": "less than",
                    "lte": "less than or equal to",
                    "eq": "equal to",
                }[params["op"]]
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
                    "Entries end 15 minutes before the selected execution session ends. "
                    f"Start the session exit {settings['exit_before_close']} "
                    "minutes before that end. "
                    + (
                        "Regular + pre/post-market; broker-held stop-limit protection may "
                        "trigger without filling."
                        if settings.get("trading_hours") == "extended"
                        else "Regular hours only."
                    )
                ),
            }
        )
        size = (
            (
                "the fixed stock quantity selected when preparing the run"
                if self.document["schema_version"] in (7, 8)
                else f"up to {settings.get('quantity', settings.get('shares'))} fixed units"
            )
            if settings["sizing"] == "fixed"
            else "units sized from the planned stop risk"
        )
        explanations.append(
            {
                "node": "settings",
                "kind": "sizing",
                "text": (
                    f"Use {size}; planned stop risk: {money_limit('risk')}; "
                    f"notional: {money_limit('notional')}. "
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
    version = raw.get("schema_version")
    if type(version) is int and version == 9:
        from .fx_strategies import compile_fx

        return compile_fx(raw)
    if type(version) is int and version in (7, 8):
        from .stock_strategies import compile_stock

        return compile_stock(raw)
    if type(version) is int and version == 6:
        from .reusable import compile_reusable

        return compile_reusable(raw)
    if type(version) is not int or version not in (3, 4, 5):
        raise GraphError("Strategy schema version must be 3, 4 or 5.")
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
    defaults = dict(DEFAULT_SETTINGS)
    stock_session = version == 4 and bool(
        {"trading_hours", "stop_limit_offset"} & raw.get("settings", {}).keys()
    )
    if stock_session and {"instrument_profile", "quantity"} & raw.get("settings", {}).keys():
        raise GraphError("Schema 4 cannot mix stock and crypto settings.")
    crypto = (version == 4 and not stock_session) or (
        version == 5 and raw.get("settings", {}).get("instrument_profile") == "paxos_crypto"
    )
    if version == 5:
        defaults.update(
            instrument_profile="us_equity", entry_timeout=60, max_entries=1, evaluation="bar_close"
        )
    if crypto:
        defaults.pop("shares")
        defaults.update(instrument_profile="paxos_crypto", quantity="0.001", symbol="BTC")
    if stock_session:
        defaults.update(trading_hours="regular", stop_limit_offset="0.10")
    settings = {**defaults, **raw.get("settings", {})}
    if set(settings) != set(defaults):
        raise GraphError("Unsupported strategy setting.")
    if stock_session:
        if settings["trading_hours"] not in {"regular", "extended"}:
            raise GraphError("Select regular or regular + pre/post-market execution.")
        if not 0 < number(settings["stop_limit_offset"]) <= 10:
            raise GraphError("Stop-limit offset must be positive and at most $10.")
        settings["stop_limit_offset"] = str(number(settings["stop_limit_offset"]))
    if crypto:
        if settings["instrument_profile"] != "paxos_crypto" or settings["symbol"] not in {
            "BTC",
            "ETH",
        }:
            raise GraphError("Crypto simulation supports BTC or ETH on PAXOS in USD.")
        if not isinstance(settings["quantity"], str) or not 0 < number(settings["quantity"]) <= 10:
            raise GraphError(
                "Use a positive decimal quantity up to 10; notional and risk caps also apply."
            )
        settings["quantity"] = str(number(settings["quantity"]))
    if version == 5 and (
        settings["instrument_profile"] not in {"us_equity", "paxos_crypto"}
        or settings["timeframe"] != 60
        or settings["evaluation"] != "bar_close"
        or settings["entry_timeout"] != 60
        or settings["max_entries"] != 1
    ):
        raise GraphError(
            "Paired stops require 1-minute closed candles, a 60-second lifetime "
            "and one trade per authorization."
        )
    if not re.fullmatch(r"[A-Z][A-Z0-9. -]{0,14}", str(settings["symbol"])):
        raise GraphError("Choose a supported US equity symbol.")
    if (
        settings["timeframe"] not in (5, 60, 300)
        or settings["evaluation"] not in ("intrabar", "bar_close")
        or settings["sizing"] not in ("risk", "fixed")
    ):
        raise GraphError("Unsupported candle, evaluation or sizing mode.")
    for key, low, high in [
        *(([("shares", 1, 10)]) if not crypto else []),
        ("entry_timeout", 1, 60 if version == 5 else 30),
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
        if kind == "paired_stop" and version != 5:
            raise GraphError("Paired stop entries require schema version 5.", key)
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
    if version == 5 and (
        len(lookup) != 1 or next(iter(lookup.values()))["kind"] != "paired_stop" or edges
    ):
        raise GraphError("Use one paired-stop block; its entry and 1% protection plan is fixed.")
    for kind in () if version == 5 else ("entry", "stop", "exit", "target"):
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
        "schema_version": version,
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


def crypto_copy(document, symbol="BTC"):
    """Explicit conversion; the source document and its published hash are untouched."""
    import copy

    result = copy.deepcopy(document)
    result["schema_version"] = 5 if document.get("schema_version") == 5 else 4
    result["settings"].pop("trading_hours", None)
    result["settings"].pop("stop_limit_offset", None)
    result["settings"].pop("shares", None)
    result["settings"].update(instrument_profile="paxos_crypto", quantity="0.001", symbol=symbol)
    return compile_graph(result).document


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
    ] + [
        {
            "id": "previous-minute-oca",
            "name": "Previous 1-minute candle — OCA breakout",
            "description": "Opposing stop-market entries, fixed 1% protection, "
            "one trade then pause.",
            "document": {
                "schema_version": 5,
                "settings": {
                    **DEFAULT_SETTINGS,
                    "instrument_profile": "us_equity",
                    "evaluation": "bar_close",
                    "entry_timeout": 60,
                    "max_entries": 1,
                },
                "nodes": [node("pair", "paired_stop", 160, 100)],
                "edges": [],
            },
        }
    ]
