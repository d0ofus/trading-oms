from __future__ import annotations

import inspect
import math
from pathlib import Path
from typing import Any

import pytest

from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.product_strategy import (
    HistoricalVolumeSession,
    ProductBreakoutSignal,
    ProductBreakoutStrategyConfig,
    ProductBreakoutStrategyError,
    run_first_bar_breakout_volume_strategy,
)


def strategy_config(**overrides: Any) -> ProductBreakoutStrategyConfig:
    values = {
        "strategy_id": "first-bar-breakout-demo",
        "symbol": "AAPL",
    }
    values.update(overrides)
    return ProductBreakoutStrategyConfig(**values)


def historical_sessions() -> tuple[HistoricalVolumeSession, ...]:
    return tuple(
        HistoricalVolumeSession(
            session_id=f"historical-session-{index:02d}",
            bars=(
                bar(0, high=101.00, close=100.50, volume=50.0),
                bar(1, high=101.25, close=100.75, volume=70.0),
                bar(2, high=101.40, close=101.00, volume=80.0),
            ),
        )
        for index in range(10)
    )


def bar(
    index: int,
    *,
    high: float,
    close: float,
    volume: float,
    symbol: str = "AAPL",
    timeframe_seconds: int = 300,
) -> Bar:
    start_minutes = 30 + (index * 5)
    end_minutes = start_minutes + 5
    return Bar(
        symbol=symbol,
        timeframe_seconds=timeframe_seconds,
        start_timestamp=f"2026-07-08T13:{start_minutes:02d}:00Z",
        end_timestamp=f"2026-07-08T13:{end_minutes:02d}:00Z",
        open=close,
        high=high,
        low=close - 0.5,
        close=close,
        volume=volume,
        event_count=1,
    )


def test_product_strategy_emits_first_breakout_signal_and_journals_it(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")

    signals = run_first_bar_breakout_volume_strategy(
        current_session_bars=[
            bar(0, high=101.50, close=101.00, volume=100.0),
            bar(1, high=101.40, close=101.10, volume=80.0),
            bar(2, high=102.20, close=102.00, volume=200.0),
        ],
        historical_sessions=historical_sessions(),
        config=strategy_config(),
        journal=journal,
    )

    assert signals == [
        ProductBreakoutSignal(
            strategy_id="first-bar-breakout-demo",
            symbol="AAPL",
            trigger_bar_start_timestamp="2026-07-08T13:40:00Z",
            trigger_bar_end_timestamp="2026-07-08T13:45:00Z",
            signal="long_entry_candidate",
            first_bar_high=101.5,
            breakout_bar_high=102.2,
            cumulative_volume=380.0,
            average_cumulative_volume=200.0,
            volume_threshold=300.0,
            volume_multiplier=1.5,
            historical_session_count=10,
            reason="first_5_minute_high_breakout_with_volume_filter",
        ),
    ]

    journal_records = journal.read_all()
    assert [record.sequence for record in journal_records] == [1]
    assert [record.event_type for record in journal_records] == ["strategy.signal.generated"]
    assert [record.timestamp for record in journal_records] == ["2026-07-08T13:45:00Z"]
    assert [record.payload for record in journal_records] == [
        signal.to_json_dict() for signal in signals
    ]


def test_product_strategy_blocks_breakout_when_cumulative_volume_filter_fails(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")

    signals = run_first_bar_breakout_volume_strategy(
        current_session_bars=[
            bar(0, high=101.50, close=101.00, volume=60.0),
            bar(1, high=101.40, close=101.10, volume=50.0),
            bar(2, high=102.20, close=102.00, volume=140.0),
        ],
        historical_sessions=historical_sessions(),
        config=strategy_config(),
        journal=journal,
    )

    assert signals == []
    assert journal.read_all() == []


def test_product_strategy_returns_no_signal_without_breakout(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")

    signals = run_first_bar_breakout_volume_strategy(
        current_session_bars=[
            bar(0, high=101.50, close=101.00, volume=100.0),
            bar(1, high=101.45, close=101.10, volume=250.0),
            bar(2, high=101.50, close=101.20, volume=250.0),
        ],
        historical_sessions=historical_sessions(),
        config=strategy_config(),
        journal=journal,
    )

    assert signals == []
    assert journal.read_all() == []


def test_product_strategy_returns_no_signal_before_first_bar_can_be_broken(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")

    signals = run_first_bar_breakout_volume_strategy(
        current_session_bars=[bar(0, high=101.50, close=101.00, volume=500.0)],
        historical_sessions=historical_sessions(),
        config=strategy_config(),
        journal=journal,
    )

    assert signals == []
    assert journal.read_all() == []


def test_product_signal_round_trip_uses_stable_json_shape() -> None:
    signal = ProductBreakoutSignal(
        strategy_id="first-bar-breakout-demo",
        symbol="AAPL",
        trigger_bar_start_timestamp="2026-07-08T13:40:00Z",
        trigger_bar_end_timestamp="2026-07-08T13:45:00Z",
        signal="long_entry_candidate",
        first_bar_high=101.5,
        breakout_bar_high=102.2,
        cumulative_volume=380.0,
        average_cumulative_volume=200.0,
        volume_threshold=300.0,
        volume_multiplier=1.5,
        historical_session_count=10,
        reason="first_5_minute_high_breakout_with_volume_filter",
    )

    assert signal.to_json_dict() == {
        "schema_version": 1,
        "strategy_id": "first-bar-breakout-demo",
        "strategy_type": "first_5_minute_breakout_volume_filter",
        "symbol": "AAPL",
        "trigger_bar_start_timestamp": "2026-07-08T13:40:00Z",
        "trigger_bar_end_timestamp": "2026-07-08T13:45:00Z",
        "signal": "long_entry_candidate",
        "first_bar_high": 101.5,
        "breakout_bar_high": 102.2,
        "cumulative_volume": 380.0,
        "average_cumulative_volume": 200.0,
        "volume_threshold": 300.0,
        "volume_multiplier": 1.5,
        "historical_session_count": 10,
        "reason": "first_5_minute_high_breakout_with_volume_filter",
    }


def test_product_strategy_payloads_exclude_order_broker_network_and_secret_fields(
    tmp_path: Path,
) -> None:
    signals = run_first_bar_breakout_volume_strategy(
        current_session_bars=[
            bar(0, high=101.50, close=101.00, volume=100.0),
            bar(1, high=101.40, close=101.10, volume=80.0),
            bar(2, high=102.20, close=102.00, volume=200.0),
        ],
        historical_sessions=historical_sessions(),
        config=strategy_config(),
        journal=JsonlEventJournal(tmp_path / "journal.jsonl"),
    )

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker",
        "client_order_id",
        "credential",
        "host",
        "order_id",
        "order_type",
        "password",
        "port",
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
    for signal in signals:
        assert forbidden_keys.isdisjoint(_all_payload_keys(signal.to_json_dict()))


@pytest.mark.parametrize(
    ("config_kwargs", "match"),
    [
        ({"strategy_id": ""}, "strategy_id"),
        ({"strategy_id": " demo"}, "strategy_id"),
        ({"symbol": "aapl"}, "symbol"),
        ({"opening_range_seconds": 60}, "opening_range_seconds"),
        ({"volume_multiplier": 1.0}, "volume_multiplier"),
        ({"historical_session_count": 9}, "historical_session_count"),
    ],
)
def test_product_strategy_config_rejects_invalid_values(
    config_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ProductBreakoutStrategyError, match=match):
        strategy_config(**config_kwargs)


def test_product_strategy_requires_exact_10_session_volume_baseline(tmp_path: Path) -> None:
    with pytest.raises(ProductBreakoutStrategyError, match="historical sessions"):
        run_first_bar_breakout_volume_strategy(
            current_session_bars=[
                bar(0, high=101.50, close=101.00, volume=100.0),
                bar(1, high=102.20, close=102.00, volume=250.0),
            ],
            historical_sessions=historical_sessions()[:9],
            config=strategy_config(),
            journal=JsonlEventJournal(tmp_path / "journal.jsonl"),
        )


@pytest.mark.parametrize(
    ("current_bars", "match"),
    [
        (
            [
                bar(0, high=101.50, close=101.00, volume=100.0),
                bar(1, high=102.20, close=102.00, volume=200.0, symbol="MSFT"),
            ],
            "symbol",
        ),
        (
            [
                bar(0, high=101.50, close=101.00, volume=100.0),
                bar(1, high=102.20, close=102.00, volume=200.0, timeframe_seconds=60),
            ],
            "timeframe",
        ),
        (
            [
                bar(1, high=101.50, close=101.00, volume=100.0),
                bar(0, high=102.20, close=102.00, volume=200.0),
            ],
            "timestamps",
        ),
        (
            [bar(0, high=math.nan, close=101.00, volume=100.0)],
            "high",
        ),
        (
            [bar(0, high=101.50, close=101.00, volume=-1.0)],
            "volume",
        ),
    ],
)
def test_product_strategy_rejects_invalid_current_bars(
    current_bars: list[Bar],
    match: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(ProductBreakoutStrategyError, match=match):
        run_first_bar_breakout_volume_strategy(
            current_session_bars=current_bars,
            historical_sessions=historical_sessions(),
            config=strategy_config(),
            journal=JsonlEventJournal(tmp_path / "journal.jsonl"),
        )


def test_product_strategy_rejects_historical_sessions_without_matching_bar_index(
    tmp_path: Path,
) -> None:
    sessions = list(historical_sessions())
    sessions[0] = HistoricalVolumeSession(
        session_id="historical-session-00",
        bars=(bar(0, high=101.00, close=100.50, volume=50.0),),
    )

    with pytest.raises(ProductBreakoutStrategyError, match="same session time"):
        run_first_bar_breakout_volume_strategy(
            current_session_bars=[
                bar(0, high=101.50, close=101.00, volume=100.0),
                bar(1, high=101.40, close=101.10, volume=80.0),
                bar(2, high=102.20, close=102.00, volume=200.0),
            ],
            historical_sessions=tuple(sessions),
            config=strategy_config(),
            journal=JsonlEventJournal(tmp_path / "journal.jsonl"),
        )


def test_product_strategy_module_does_not_define_transport_or_http_behavior() -> None:
    import trading_oms_backend.product_strategy as product_strategy

    source = inspect.getsource(product_strategy).lower()
    forbidden_source_tokens = [
        "@app.post",
        "@app.put",
        "@app.patch",
        "@app.delete",
        "import socket",
        "from socket",
        "httpx",
        "requests",
        "ibapi",
        "ib_insync",
        "open_connection",
        "create_connection",
        "place_order",
        "submit_order",
        "transmit_order",
    ]
    for token in forbidden_source_tokens:
        assert token not in source


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
