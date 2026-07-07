from __future__ import annotations

import math

import pytest

from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.replay_strategy import (
    ReplayStrategyConfig,
    ReplayStrategyError,
    ReplayStrategySignal,
    run_close_above_sma_strategy,
)


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


def strategy_config(**overrides) -> ReplayStrategyConfig:
    values = {
        "strategy_id": "close-above-sma-demo",
        "symbol": "AAPL",
        "lookback_bars": 3,
    }
    values.update(overrides)
    return ReplayStrategyConfig(**values)


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


def test_replay_strategy_emits_deterministic_signals_and_journals_each_one(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    signals = run_close_above_sma_strategy(
        strategy_bars(),
        strategy_config(),
        journal,
    )

    assert signals == [
        ReplayStrategySignal(
            strategy_id="close-above-sma-demo",
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
            strategy_id="close-above-sma-demo",
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

    journal_records = journal.read_all()
    assert [record.sequence for record in journal_records] == [1, 2]
    assert [record.event_type for record in journal_records] == [
        "strategy.signal.generated",
        "strategy.signal.generated",
    ]
    assert [record.timestamp for record in journal_records] == [
        "2026-07-06T00:03:00Z",
        "2026-07-06T00:04:00Z",
    ]
    assert [record.payload for record in journal_records] == [
        signal.to_json_dict() for signal in signals
    ]


def test_signal_round_trip_uses_stable_json_shape() -> None:
    signal = ReplayStrategySignal(
        strategy_id="close-above-sma-demo",
        symbol="AAPL",
        bar_start_timestamp="2026-07-06T00:02:00Z",
        bar_end_timestamp="2026-07-06T00:03:00Z",
        signal="long_bias",
        close=103.0,
        moving_average=101.33333333333333,
        lookback_bars=3,
        reason="close_above_sma",
    )

    assert signal.to_json_dict() == {
        "schema_version": 1,
        "strategy_id": "close-above-sma-demo",
        "strategy_type": "close_above_sma",
        "symbol": "AAPL",
        "bar_start_timestamp": "2026-07-06T00:02:00Z",
        "bar_end_timestamp": "2026-07-06T00:03:00Z",
        "signal": "long_bias",
        "close": 103.0,
        "moving_average": 101.33333333333333,
        "lookback_bars": 3,
        "reason": "close_above_sma",
    }


def test_replay_strategy_does_not_emit_order_shaped_payload(tmp_path) -> None:
    signals = run_close_above_sma_strategy(
        strategy_bars(),
        strategy_config(),
        JsonlEventJournal(tmp_path / "events.jsonl"),
    )

    forbidden_order_keys = {
        "account",
        "broker",
        "client_order_id",
        "order_id",
        "order_type",
        "quantity",
        "qty",
        "side",
        "submit",
        "transmit",
    }
    for signal in signals:
        assert forbidden_order_keys.isdisjoint(signal.to_json_dict())


def test_replay_strategy_returns_no_signals_without_enough_bars(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    signals = run_close_above_sma_strategy(
        strategy_bars()[:2],
        strategy_config(),
        journal,
    )

    assert signals == []
    assert journal.read_all() == []


@pytest.mark.parametrize(
    ("config_kwargs", "match"),
    [
        ({"strategy_id": ""}, "strategy_id"),
        ({"strategy_id": " demo"}, "strategy_id"),
        ({"symbol": "aapl"}, "symbol"),
        ({"symbol": "AAPL "}, "symbol"),
        ({"lookback_bars": 1}, "lookback_bars"),
        ({"lookback_bars": 2.5}, "lookback_bars"),
    ],
)
def test_replay_strategy_config_rejects_invalid_values(config_kwargs: dict, match: str) -> None:
    with pytest.raises(ReplayStrategyError, match=match):
        strategy_config(**config_kwargs)


@pytest.mark.parametrize(
    ("bars", "match"),
    [
        (
            [
                bar(
                    100.0,
                    start_timestamp="2026-07-06T00:00:00Z",
                    end_timestamp="2026-07-06T00:01:00Z",
                ),
                bar(
                    101.0,
                    symbol="MSFT",
                    start_timestamp="2026-07-06T00:01:00Z",
                    end_timestamp="2026-07-06T00:02:00Z",
                ),
            ],
            "symbol",
        ),
        (
            [
                bar(
                    100.0,
                    start_timestamp="2026-07-06T00:00:00Z",
                    end_timestamp="2026-07-06T00:01:00Z",
                ),
                bar(
                    101.0,
                    timeframe_seconds=300,
                    start_timestamp="2026-07-06T00:01:00Z",
                    end_timestamp="2026-07-06T00:02:00Z",
                ),
            ],
            "timeframe",
        ),
        (
            [
                bar(
                    100.0,
                    start_timestamp="2026-07-06T00:01:00Z",
                    end_timestamp="2026-07-06T00:02:00Z",
                ),
                bar(
                    101.0,
                    start_timestamp="2026-07-06T00:00:00Z",
                    end_timestamp="2026-07-06T00:01:00Z",
                ),
            ],
            "timestamps",
        ),
        (
            [
                bar(
                    math.nan,
                    start_timestamp="2026-07-06T00:00:00Z",
                    end_timestamp="2026-07-06T00:01:00Z",
                ),
            ],
            "close",
        ),
    ],
)
def test_replay_strategy_rejects_invalid_bars(
    bars: list[Bar],
    match: str,
    tmp_path,
) -> None:
    with pytest.raises(ReplayStrategyError, match=match):
        run_close_above_sma_strategy(
            bars,
            strategy_config(lookback_bars=2),
            JsonlEventJournal(tmp_path / "events.jsonl"),
        )


@pytest.mark.parametrize(
    ("signal_kwargs", "match"),
    [
        ({"signal": "buy"}, "signal"),
        ({"close": math.inf}, "close"),
        ({"moving_average": math.nan}, "moving_average"),
        ({"reason": ""}, "reason"),
    ],
)
def test_signal_rejects_invalid_payload_values(signal_kwargs: dict, match: str) -> None:
    values = {
        "strategy_id": "close-above-sma-demo",
        "symbol": "AAPL",
        "bar_start_timestamp": "2026-07-06T00:02:00Z",
        "bar_end_timestamp": "2026-07-06T00:03:00Z",
        "signal": "long_bias",
        "close": 103.0,
        "moving_average": 101.33333333333333,
        "lookback_bars": 3,
        "reason": "close_above_sma",
    }
    values.update(signal_kwargs)

    with pytest.raises(ReplayStrategyError, match=match):
        ReplayStrategySignal(**values)
