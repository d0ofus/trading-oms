from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class ReplayError(ValueError):
    """Base error for market-data replay failures."""


class ReplayValidationError(ReplayError):
    """Raised when replay data violates the deterministic replay contract."""


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayValidationError("timestamp must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReplayValidationError("timestamp must include a timezone")
    return parsed


@dataclass(frozen=True)
class MarketDataReplayEvent:
    sequence: int
    timestamp: str
    symbol: str
    event_type: str
    payload: dict[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> MarketDataReplayEvent:
        if not isinstance(raw_record, Mapping):
            raise ReplayValidationError("replay record must be a JSON object")

        try:
            sequence = raw_record["sequence"]
            timestamp = raw_record["timestamp"]
            symbol = raw_record["symbol"]
            event_type = raw_record["event_type"]
            payload = raw_record["payload"]
        except KeyError as exc:
            raise ReplayValidationError(f"replay record is missing {exc.args[0]}") from exc

        return cls(
            schema_version=raw_record.get("schema_version", 1),
            sequence=sequence,
            timestamp=timestamp,
            symbol=symbol,
            event_type=event_type,
            payload=payload,
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "event_type": self.event_type,
            "payload": self.payload,
        }

    def to_json_line(self) -> str:
        return (
            json.dumps(
                self.to_json_dict(),
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

    def parsed_timestamp(self) -> datetime:
        return _parse_timestamp(self.timestamp)

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ReplayValidationError("schema_version must be 1")
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise ReplayValidationError("sequence must be a positive integer")
        if not isinstance(self.timestamp, str) or not self.timestamp.strip():
            raise ReplayValidationError("timestamp must be a non-empty string")
        _parse_timestamp(self.timestamp)
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ReplayValidationError("symbol must be a non-empty string")
        if self.symbol != self.symbol.upper():
            raise ReplayValidationError("symbol must be uppercase")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ReplayValidationError("event_type must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise ReplayValidationError("payload must be a JSON object")
        try:
            json.dumps(self.payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ReplayValidationError("payload must be JSON-serializable") from exc


class JsonlMarketDataReplay:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read_all(self) -> list[MarketDataReplayEvent]:
        if not self.path.exists():
            raise ReplayValidationError(f"replay file does not exist: {self.path}")

        events: list[MarketDataReplayEvent] = []
        with self.path.open("r", encoding="utf-8") as replay_file:
            for line_number, line in enumerate(replay_file, start=1):
                if not line.strip():
                    raise ReplayValidationError(f"replay line {line_number} must not be blank")
                events.append(self._read_line(line, line_number))

        self._validate_order(events)
        return events

    def iter_events(self) -> list[MarketDataReplayEvent]:
        return self.read_all()

    def _read_line(self, line: str, line_number: int) -> MarketDataReplayEvent:
        try:
            raw_record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayValidationError(f"Invalid JSON on replay line {line_number}") from exc

        try:
            return MarketDataReplayEvent.from_json_dict(raw_record)
        except ReplayValidationError as exc:
            raise ReplayValidationError(
                f"Invalid replay record on line {line_number}: {exc}"
            ) from exc

    def _validate_order(self, events: list[MarketDataReplayEvent]) -> None:
        previous_timestamp: datetime | None = None
        for expected_sequence, event in enumerate(events, start=1):
            if event.sequence != expected_sequence:
                raise ReplayValidationError(
                    f"replay sequence must be contiguous; expected {expected_sequence}, "
                    f"got {event.sequence}",
                )

            event_timestamp = event.parsed_timestamp()
            if previous_timestamp is not None and event_timestamp < previous_timestamp:
                raise ReplayValidationError("replay timestamps must be nondecreasing")
            previous_timestamp = event_timestamp
