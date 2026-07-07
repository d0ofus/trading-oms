from __future__ import annotations

from datetime import timedelta

import pytest

from trading_oms_backend.bar_builder import (
    Bar,
    BarBuilderConfig,
    BarBuildError,
    build_time_bars,
)
from trading_oms_backend.market_data_replay import JsonlMarketDataReplay, MarketDataReplayEvent

FIXED_TIMESTAMP = "2026-07-06T00:00:00Z"


def replay_event(
    sequence: int,
    timestamp: str = FIXED_TIMESTAMP,
    symbol: str = "AAPL",
    event_type: str = "trade",
    payload: dict | None = None,
) -> MarketDataReplayEvent:
    return MarketDataReplayEvent(
        sequence=sequence,
        timestamp=timestamp,
        symbol=symbol,
        event_type=event_type,
        payload={"price": 100.0, "size": 1} if payload is None else payload,
    )


def one_minute_config(**overrides) -> BarBuilderConfig:
    values = {"symbol": "AAPL", "timeframe": timedelta(minutes=1)}
    values.update(overrides)
    return BarBuilderConfig(**values)


def test_build_time_bars_from_trades_returns_deterministic_ohlcv() -> None:
    bars = build_time_bars(
        [
            replay_event(1, payload={"price": 100.0, "size": 2}),
            replay_event(2, timestamp="2026-07-06T00:00:10Z", payload={"price": 101.0, "size": 3}),
            replay_event(3, timestamp="2026-07-06T00:00:20Z", payload={"price": 99.0, "size": 4}),
            replay_event(
                4,
                timestamp="2026-07-06T00:00:59Z",
                payload={"price": 100.5, "volume": 5},
            ),
        ],
        one_minute_config(),
    )

    assert bars == [
        Bar(
            symbol="AAPL",
            timeframe_seconds=60,
            start_timestamp="2026-07-06T00:00:00Z",
            end_timestamp="2026-07-06T00:01:00Z",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=14.0,
            event_count=4,
        )
    ]
    assert bars[0].to_json_dict() == {
        "schema_version": 1,
        "symbol": "AAPL",
        "timeframe_seconds": 60,
        "start_timestamp": "2026-07-06T00:00:00Z",
        "end_timestamp": "2026-07-06T00:01:00Z",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 14.0,
        "event_count": 4,
    }


def test_build_time_bars_from_replay_reader_output(tmp_path) -> None:
    replay_path = tmp_path / "market-data.jsonl"
    replay_path.write_text(
        replay_event(1, payload={"price": 100.0, "size": 2}).to_json_line()
        + replay_event(
            2,
            timestamp="2026-07-06T00:00:10Z",
            payload={"price": 101.0, "size": 3},
        ).to_json_line(),
        encoding="utf-8",
    )

    bars = build_time_bars(JsonlMarketDataReplay(replay_path).read_all(), one_minute_config())

    assert bars[0].open == 100.0
    assert bars[0].close == 101.0
    assert bars[0].volume == 5.0


def test_build_time_bars_groups_events_by_timeframe_boundary() -> None:
    bars = build_time_bars(
        [
            replay_event(1, timestamp="2026-07-06T00:00:59Z", payload={"price": 100.0}),
            replay_event(2, timestamp="2026-07-06T00:01:00Z", payload={"price": 101.0}),
        ],
        one_minute_config(),
    )

    assert [bar.start_timestamp for bar in bars] == [
        "2026-07-06T00:00:00Z",
        "2026-07-06T00:01:00Z",
    ]
    assert [bar.close for bar in bars] == [100.0, 101.0]
    assert [bar.volume for bar in bars] == [0.0, 0.0]


def test_build_time_bars_supports_explicit_quote_mid_price_source() -> None:
    bars = build_time_bars(
        [
            replay_event(
                1,
                event_type="quote",
                payload={"bid": 100.0, "ask": 100.5},
            ),
            replay_event(
                2,
                timestamp="2026-07-06T00:00:10Z",
                event_type="quote",
                payload={"bid": 100.5, "ask": 101.0},
            ),
        ],
        one_minute_config(quote_price_source="mid"),
    )

    assert bars == [
        Bar(
            symbol="AAPL",
            timeframe_seconds=60,
            start_timestamp="2026-07-06T00:00:00Z",
            end_timestamp="2026-07-06T00:01:00Z",
            open=100.25,
            high=100.75,
            low=100.25,
            close=100.75,
            volume=0.0,
            event_count=2,
        )
    ]


def test_build_time_bars_returns_empty_list_for_empty_input() -> None:
    assert build_time_bars([], one_minute_config()) == []


@pytest.mark.parametrize(
    ("events", "config", "match"),
    [
        ([replay_event(1, event_type="depth")], one_minute_config(), "unsupported"),
        ([replay_event(1, event_type="quote")], one_minute_config(), "quote"),
        ([replay_event(1, payload={})], one_minute_config(), "price"),
        ([replay_event(1, payload={"price": True})], one_minute_config(), "price"),
        ([replay_event(1, payload={"price": 100.0, "size": -1})], one_minute_config(), "size"),
        ([replay_event(1)], one_minute_config(symbol=" AAPL"), "symbol"),
        ([replay_event(1)], one_minute_config(symbol="aapl"), "symbol"),
        ([replay_event(1, symbol="MSFT")], one_minute_config(), "symbol"),
        (
            [
                replay_event(1, timestamp="2026-07-06T00:00:01Z"),
                replay_event(2, timestamp=FIXED_TIMESTAMP),
            ],
            one_minute_config(),
            "timestamps",
        ),
        ([replay_event(1)], one_minute_config(timeframe=timedelta(seconds=0)), "timeframe"),
        (
            [replay_event(1, event_type="quote", payload={"bid": 100.0, "ask": 100.2})],
            one_minute_config(quote_price_source="last"),
            "quote_price_source",
        ),
    ],
)
def test_build_time_bars_rejects_invalid_inputs(
    events: list[MarketDataReplayEvent],
    config: BarBuilderConfig,
    match: str,
) -> None:
    with pytest.raises(BarBuildError, match=match):
        build_time_bars(events, config)
