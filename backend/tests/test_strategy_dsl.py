from __future__ import annotations

import json
from typing import Any

import pytest

from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.replay_strategy import ReplayStrategyConfig, ReplayStrategySignal
from trading_oms_backend.strategy_dsl import (
    StrategyDslDocument,
    StrategyDslError,
    StrategyDslParameters,
    compile_strategy_dsl,
    parse_strategy_dsl,
    parse_strategy_dsl_json,
    run_strategy_dsl,
)


def dsl_document(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "schema_version": 1,
        "strategy_id": "dsl-close-above-sma-demo",
        "strategy_type": "close_above_sma",
        "mode": "replay",
        "symbol": "AAPL",
        "bar_timeframe_seconds": 60,
        "parameters": {
            "lookback_bars": 3,
            "price_source": "close",
        },
    }
    values.update(overrides)
    return values


def bar(
    close: float,
    *,
    start_timestamp: str,
    end_timestamp: str,
    symbol: str = "AAPL",
    timeframe_seconds: int = 60,
) -> Bar:
    return Bar(
        symbol=symbol,
        timeframe_seconds=timeframe_seconds,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        event_count=1,
    )


def strategy_bars() -> list[Bar]:
    return [
        bar(
            100.0,
            start_timestamp="2026-07-06T00:00:00Z",
            end_timestamp="2026-07-06T00:01:00Z",
        ),
        bar(
            101.0,
            start_timestamp="2026-07-06T00:01:00Z",
            end_timestamp="2026-07-06T00:02:00Z",
        ),
        bar(
            103.0,
            start_timestamp="2026-07-06T00:02:00Z",
            end_timestamp="2026-07-06T00:03:00Z",
        ),
        bar(
            99.0,
            start_timestamp="2026-07-06T00:03:00Z",
            end_timestamp="2026-07-06T00:04:00Z",
        ),
    ]


def test_parse_strategy_dsl_returns_typed_document_and_stable_json_shape() -> None:
    document = parse_strategy_dsl(dsl_document())

    assert document == StrategyDslDocument(
        strategy_id="dsl-close-above-sma-demo",
        strategy_type="close_above_sma",
        mode="replay",
        symbol="AAPL",
        bar_timeframe_seconds=60,
        parameters=StrategyDslParameters(lookback_bars=3, price_source="close"),
    )
    assert document.to_json_dict() == dsl_document()


def test_parse_strategy_dsl_json_is_deterministic() -> None:
    raw_json = json.dumps(dsl_document(), sort_keys=True)

    first = parse_strategy_dsl_json(raw_json)
    second = parse_strategy_dsl_json(raw_json)

    assert first == second
    assert first.to_json_dict() == dsl_document()


def test_compile_strategy_dsl_returns_existing_replay_strategy_config() -> None:
    document = parse_strategy_dsl(dsl_document())

    config = compile_strategy_dsl(document)

    assert config == ReplayStrategyConfig(
        strategy_id="dsl-close-above-sma-demo",
        symbol="AAPL",
        lookback_bars=3,
    )


def test_run_strategy_dsl_executes_replay_only_and_journals_signals(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    document = parse_strategy_dsl(dsl_document())

    signals = run_strategy_dsl(strategy_bars(), document, journal)

    assert signals == [
        ReplayStrategySignal(
            strategy_id="dsl-close-above-sma-demo",
            symbol="AAPL",
            bar_start_timestamp="2026-07-06T00:02:00Z",
            bar_end_timestamp="2026-07-06T00:03:00Z",
            signal="long_bias",
            close=103.0,
            moving_average=(100.0 + 101.0 + 103.0) / 3,
            lookback_bars=3,
            reason="close_above_sma",
        ),
        ReplayStrategySignal(
            strategy_id="dsl-close-above-sma-demo",
            symbol="AAPL",
            bar_start_timestamp="2026-07-06T00:03:00Z",
            bar_end_timestamp="2026-07-06T00:04:00Z",
            signal="risk_off_bias",
            close=99.0,
            moving_average=(101.0 + 103.0 + 99.0) / 3,
            lookback_bars=3,
            reason="close_at_or_below_sma",
        ),
    ]

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        "strategy.signal.generated",
        "strategy.signal.generated",
    ]
    assert [record.payload for record in records] == [signal.to_json_dict() for signal in signals]


def test_strategy_dsl_payloads_do_not_contain_order_broker_or_secret_fields(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    document = parse_strategy_dsl(dsl_document())

    signals = run_strategy_dsl(strategy_bars(), document, journal)

    forbidden_keys = {
        "account",
        "action",
        "api_key",
        "authorization",
        "broker",
        "broker_host",
        "broker_port",
        "chat_id",
        "client_order_id",
        "credential",
        "host",
        "order_id",
        "order_type",
        "password",
        "private_key",
        "quantity",
        "route",
        "secret",
        "side",
        "socket",
        "submit",
        "token",
        "transmit",
    }
    payloads = [document.to_json_dict(), *(signal.to_json_dict() for signal in signals)]
    for payload in payloads:
        assert forbidden_keys.isdisjoint(_all_payload_keys(payload))


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ([], "JSON object"),
        ({"strategy_id": "missing-required-fields"}, "missing schema_version"),
        (dsl_document(schema_version=2), "schema_version"),
        (dsl_document(strategy_id=""), "strategy_id"),
        (dsl_document(strategy_id=" token=redacted"), "forbidden"),
        (dsl_document(strategy_type="first_bar_breakout"), "strategy_type"),
        (dsl_document(mode="live"), "mode"),
        (dsl_document(symbol="aapl"), "symbol"),
        (dsl_document(bar_timeframe_seconds=0), "bar_timeframe_seconds"),
        (dsl_document(bar_timeframe_seconds=True), "bar_timeframe_seconds"),
        (dsl_document(parameters="not-a-dict"), "parameters"),
        (dsl_document(parameters={"lookback_bars": 1, "price_source": "close"}), "lookback_bars"),
        (dsl_document(parameters={"lookback_bars": 3, "price_source": "bid"}), "price_source"),
        (dsl_document(extra_field="not-allowed"), "unknown field"),
        (dsl_document(actions=[{"side": "buy", "quantity": 1}]), "forbidden"),
        (dsl_document(broker={"host": "127.0.0.1"}), "forbidden"),
        (
            dsl_document(parameters={"lookback_bars": 3, "price_source": "close", "quantity": 1}),
            "forbidden",
        ),
        (
            dsl_document(
                parameters={
                    "lookback_bars": 3,
                    "price_source": "close",
                    "expression": "close > sma",
                }
            ),
            "forbidden",
        ),
        (
            dsl_document(
                parameters={
                    "lookback_bars": 3,
                    "price_source": "close",
                    "api_token": "redacted-sample",
                }
            ),
            "forbidden",
        ),
    ],
)
def test_strategy_dsl_rejects_invalid_or_unsafe_documents(
    raw: Any,
    match: str,
) -> None:
    with pytest.raises(StrategyDslError, match=match):
        parse_strategy_dsl(raw)


@pytest.mark.parametrize(
    ("raw_json", "match"),
    [
        ("not-json", "valid JSON"),
        ("[]", "JSON object"),
    ],
)
def test_strategy_dsl_json_rejects_invalid_values(raw_json: str, match: str) -> None:
    with pytest.raises(StrategyDslError, match=match):
        parse_strategy_dsl_json(raw_json)


def test_compile_strategy_dsl_requires_document_instance() -> None:
    with pytest.raises(StrategyDslError, match="StrategyDslDocument"):
        compile_strategy_dsl(dsl_document())  # type: ignore[arg-type]


def _all_payload_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested_value in value.values():
            keys.update(_all_payload_keys(nested_value))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_all_payload_keys(item))
        return keys
    return set()
