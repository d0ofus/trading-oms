from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.replay_strategy import (
    ReplayStrategyConfig,
    ReplayStrategySignal,
    run_close_above_sma_strategy,
)

STRATEGY_DSL_SCHEMA_VERSION = 1
SUPPORTED_STRATEGY_TYPE = "close_above_sma"
SUPPORTED_MODE = "replay"
SUPPORTED_PRICE_SOURCE = "close"

_DOCUMENT_FIELDS = {
    "schema_version",
    "strategy_id",
    "strategy_type",
    "mode",
    "symbol",
    "bar_timeframe_seconds",
    "parameters",
}
_PARAMETER_FIELDS = {"lookback_bars", "price_source"}

_FORBIDDEN_KEY_FRAGMENTS = {
    "account",
    "action",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "broker",
    "certificate",
    "chat_id",
    "client_order",
    "code",
    "credential",
    "destination",
    "eval",
    "execution",
    "expression",
    "function",
    "gateway",
    "host",
    "ibkr",
    "import",
    "order",
    "password",
    "private_key",
    "quantity",
    "route",
    "script",
    "secret",
    "side",
    "socket",
    "submit",
    "telegram",
    "token",
    "transmit",
    "tws",
    "url",
}

_FORBIDDEN_TEXT_MARKERS = (
    "api_key=",
    "api_key:",
    "authorization=",
    "authorization:",
    "broker_host=",
    "broker_host:",
    "chat_id=",
    "chat_id:",
    "password=",
    "password:",
    "private_key=",
    "private_key:",
    "secret=",
    "secret:",
    "submit order",
    "token=",
    "token:",
    "transmit order",
)


class StrategyDslError(ValueError):
    """Raised when Strategy DSL documents are invalid or unsafe."""


@dataclass(frozen=True)
class StrategyDslParameters:
    lookback_bars: int
    price_source: str = SUPPORTED_PRICE_SOURCE

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_json_dict(cls, raw_parameters: Mapping[str, Any]) -> StrategyDslParameters:
        if not isinstance(raw_parameters, Mapping):
            raise StrategyDslError("parameters must be a JSON object")
        _reject_forbidden_content(raw_parameters)
        _reject_unknown_fields(raw_parameters, _PARAMETER_FIELDS, "parameters")

        try:
            lookback_bars = raw_parameters["lookback_bars"]
            price_source = raw_parameters["price_source"]
        except KeyError as exc:
            raise StrategyDslError(f"parameters is missing {exc.args[0]}") from exc

        return cls(
            lookback_bars=lookback_bars,
            price_source=price_source,
        )

    def validate(self) -> None:
        if (
            isinstance(self.lookback_bars, bool)
            or not isinstance(self.lookback_bars, int)
            or self.lookback_bars < 2
        ):
            raise StrategyDslError("lookback_bars must be an integer greater than or equal to 2")
        if self.price_source != SUPPORTED_PRICE_SOURCE:
            raise StrategyDslError("price_source must be close")
        _assert_json_serializable(self.to_json_dict(), "strategy DSL parameters")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "lookback_bars": self.lookback_bars,
            "price_source": self.price_source,
        }


@dataclass(frozen=True)
class StrategyDslDocument:
    strategy_id: str
    strategy_type: str
    mode: str
    symbol: str
    bar_timeframe_seconds: int
    parameters: StrategyDslParameters
    schema_version: int = STRATEGY_DSL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_json_dict(cls, raw_document: Mapping[str, Any]) -> StrategyDslDocument:
        if not isinstance(raw_document, Mapping):
            raise StrategyDslError("strategy DSL document must be a JSON object")
        _reject_forbidden_content(raw_document)
        _reject_unknown_fields(raw_document, _DOCUMENT_FIELDS, "strategy DSL document")

        try:
            schema_version = raw_document["schema_version"]
            strategy_id = raw_document["strategy_id"]
            strategy_type = raw_document["strategy_type"]
            mode = raw_document["mode"]
            symbol = raw_document["symbol"]
            bar_timeframe_seconds = raw_document["bar_timeframe_seconds"]
            parameters = raw_document["parameters"]
        except KeyError as exc:
            raise StrategyDslError(f"strategy DSL document is missing {exc.args[0]}") from exc

        return cls(
            schema_version=schema_version,
            strategy_id=strategy_id,
            strategy_type=strategy_type,
            mode=mode,
            symbol=symbol,
            bar_timeframe_seconds=bar_timeframe_seconds,
            parameters=StrategyDslParameters.from_json_dict(parameters),
        )

    def validate(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != STRATEGY_DSL_SCHEMA_VERSION
        ):
            raise StrategyDslError("schema_version must be 1")
        _validated_identifier(self.strategy_id, "strategy_id")
        if self.strategy_type != SUPPORTED_STRATEGY_TYPE:
            raise StrategyDslError("strategy_type must be close_above_sma")
        if self.mode != SUPPORTED_MODE:
            raise StrategyDslError("mode must be replay")
        _validated_symbol(self.symbol)
        if (
            isinstance(self.bar_timeframe_seconds, bool)
            or not isinstance(self.bar_timeframe_seconds, int)
            or self.bar_timeframe_seconds < 1
        ):
            raise StrategyDslError("bar_timeframe_seconds must be a positive integer")
        if not isinstance(self.parameters, StrategyDslParameters):
            raise StrategyDslError("parameters must be StrategyDslParameters")
        _assert_json_serializable(self.to_json_dict(), "strategy DSL document")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "strategy_type": self.strategy_type,
            "mode": self.mode,
            "symbol": self.symbol,
            "bar_timeframe_seconds": self.bar_timeframe_seconds,
            "parameters": self.parameters.to_json_dict(),
        }

    def to_replay_strategy_config(self) -> ReplayStrategyConfig:
        return ReplayStrategyConfig(
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            lookback_bars=self.parameters.lookback_bars,
        )


def parse_strategy_dsl(raw_document: Mapping[str, Any]) -> StrategyDslDocument:
    return StrategyDslDocument.from_json_dict(raw_document)


def parse_strategy_dsl_json(raw_json: str) -> StrategyDslDocument:
    if not isinstance(raw_json, str) or not raw_json.strip():
        raise StrategyDslError("strategy DSL JSON must be a non-empty string")
    try:
        raw_document = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise StrategyDslError("strategy DSL must be valid JSON") from exc
    return parse_strategy_dsl(raw_document)


def compile_strategy_dsl(document: StrategyDslDocument) -> ReplayStrategyConfig:
    if not isinstance(document, StrategyDslDocument):
        raise StrategyDslError("document must be a StrategyDslDocument")
    return document.to_replay_strategy_config()


def run_strategy_dsl(
    bars: Iterable[Bar],
    document: StrategyDslDocument,
    journal: JsonlEventJournal,
) -> list[ReplayStrategySignal]:
    if not isinstance(document, StrategyDslDocument):
        raise StrategyDslError("document must be a StrategyDslDocument")
    if document.strategy_type != SUPPORTED_STRATEGY_TYPE or document.mode != SUPPORTED_MODE:
        raise StrategyDslError("only replay close_above_sma strategy DSL is supported")
    return run_close_above_sma_strategy(
        bars=bars,
        config=compile_strategy_dsl(document),
        journal=journal,
    )


def _reject_unknown_fields(
    raw_mapping: Mapping[str, Any],
    allowed_fields: set[str],
    object_name: str,
) -> None:
    unknown_fields = sorted(set(raw_mapping) - allowed_fields)
    if unknown_fields:
        raise StrategyDslError(f"{object_name} contains unknown field {unknown_fields[0]}")


def _reject_forbidden_content(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise StrategyDslError("strategy DSL keys must be strings")
            if _is_forbidden_key(key):
                raise StrategyDslError(f"strategy DSL contains forbidden field {key}")
            _reject_forbidden_content(nested_value)
        return
    if isinstance(value, list):
        for item in value:
            _reject_forbidden_content(item)
        return
    if isinstance(value, str):
        _reject_forbidden_text(value)


def _is_forbidden_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS)


def _reject_forbidden_text(value: str) -> None:
    normalized = value.lower()
    if any(marker in normalized for marker in _FORBIDDEN_TEXT_MARKERS):
        raise StrategyDslError("strategy DSL contains forbidden credential or order text")


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategyDslError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise StrategyDslError(f"{field_name} must not contain leading or trailing whitespace")
    _reject_forbidden_text(value)
    return value


def _validated_symbol(symbol: str) -> str:
    _validated_identifier(symbol, "symbol")
    if symbol != symbol.upper():
        raise StrategyDslError("symbol must be uppercase")
    return symbol


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StrategyDslError(f"{payload_name} must be JSON-serializable") from exc
