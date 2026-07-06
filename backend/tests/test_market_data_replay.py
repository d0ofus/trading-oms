from __future__ import annotations

import json

import pytest

from trading_oms_backend.market_data_replay import (
    JsonlMarketDataReplay,
    MarketDataReplayEvent,
    ReplayValidationError,
)

FIXED_TIMESTAMP = "2026-07-06T00:00:00Z"


def replay_record(
    sequence: int,
    timestamp: str = FIXED_TIMESTAMP,
    symbol: str = "AAPL",
    event_type: str = "trade",
    payload: dict | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "timestamp": timestamp,
        "symbol": symbol,
        "event_type": event_type,
        "payload": {"price": 100.25, "size": 10} if payload is None else payload,
    }


def write_replay(path, *records: dict) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_replay_reader_returns_events_in_file_order(tmp_path) -> None:
    path = tmp_path / "market-data.jsonl"
    write_replay(
        path,
        replay_record(1, payload={"bid": 100.0, "ask": 100.1}, event_type="quote"),
        replay_record(2, timestamp="2026-07-06T00:00:01Z"),
    )

    events = JsonlMarketDataReplay(path).read_all()

    assert [event.sequence for event in events] == [1, 2]
    assert [event.event_type for event in events] == ["quote", "trade"]
    assert events[0].payload == {"bid": 100.0, "ask": 100.1}


def test_event_round_trip_uses_stable_json_shape() -> None:
    event = MarketDataReplayEvent(
        sequence=1,
        timestamp=FIXED_TIMESTAMP,
        symbol="AAPL",
        event_type="trade",
        payload={"price": 100.25, "size": 10},
    )

    assert event.to_json_dict() == replay_record(1)
    assert MarketDataReplayEvent.from_json_dict(event.to_json_dict()) == event


@pytest.mark.parametrize(
    "raw_record",
    [
        {},
        {
            "schema_version": 1,
            "sequence": 1,
            "timestamp": FIXED_TIMESTAMP,
            "symbol": "AAPL",
            "payload": {},
        },
        replay_record(0),
        replay_record(1, timestamp="not-a-date"),
        replay_record(1, timestamp="2026-07-06T00:00:00"),
        replay_record(1, symbol=""),
        replay_record(1, symbol="aapl"),
        replay_record(1, event_type=""),
        replay_record(1, payload=[]),
    ],
)
def test_event_validation_rejects_invalid_records(raw_record) -> None:
    with pytest.raises(ReplayValidationError):
        MarketDataReplayEvent.from_json_dict(raw_record)


def test_reader_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(ReplayValidationError, match="does not exist"):
        JsonlMarketDataReplay(tmp_path / "missing.jsonl").read_all()


def test_reader_rejects_invalid_json_line(tmp_path) -> None:
    path = tmp_path / "market-data.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ReplayValidationError, match="Invalid JSON"):
        JsonlMarketDataReplay(path).read_all()


def test_reader_rejects_blank_lines(tmp_path) -> None:
    path = tmp_path / "market-data.jsonl"
    path.write_text("\n", encoding="utf-8")

    with pytest.raises(ReplayValidationError, match="blank"):
        JsonlMarketDataReplay(path).read_all()


def test_reader_rejects_duplicate_or_out_of_order_sequences(tmp_path) -> None:
    path = tmp_path / "market-data.jsonl"
    write_replay(path, replay_record(1), replay_record(1, timestamp="2026-07-06T00:00:01Z"))

    with pytest.raises(ReplayValidationError, match="sequence"):
        JsonlMarketDataReplay(path).read_all()


def test_reader_rejects_decreasing_timestamps(tmp_path) -> None:
    path = tmp_path / "market-data.jsonl"
    write_replay(
        path,
        replay_record(1, timestamp="2026-07-06T00:00:01Z"),
        replay_record(2, timestamp=FIXED_TIMESTAMP),
    )

    with pytest.raises(ReplayValidationError, match="timestamp"):
        JsonlMarketDataReplay(path).read_all()


def test_event_rejects_non_standard_json_payload() -> None:
    with pytest.raises(ReplayValidationError, match="JSON-serializable"):
        MarketDataReplayEvent(
            sequence=1,
            timestamp=FIXED_TIMESTAMP,
            symbol="AAPL",
            event_type="trade",
            payload={"price": float("nan")},
        )
