from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JournalError(ValueError):
    """Base error for event journal failures."""


class JournalValidationError(JournalError):
    """Raised when a journal record or journal file violates the append-only contract."""


def _parse_timestamp(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JournalValidationError("timestamp must be an ISO-8601 datetime") from exc


def _utc_timestamp() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class JournalRecord:
    sequence: int
    event_type: str
    timestamp: str
    payload: dict[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> JournalRecord:
        if not isinstance(raw_record, Mapping):
            raise JournalValidationError("journal record must be a JSON object")

        try:
            sequence = raw_record["sequence"]
            event_type = raw_record["type"]
            timestamp = raw_record["timestamp"]
            payload = raw_record["payload"]
        except KeyError as exc:
            raise JournalValidationError(f"journal record is missing {exc.args[0]}") from exc

        schema_version = raw_record.get("schema_version", 1)
        return cls(
            schema_version=schema_version,
            sequence=sequence,
            event_type=event_type,
            timestamp=timestamp,
            payload=payload,
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "type": self.event_type,
            "timestamp": self.timestamp,
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

    def validate(self) -> None:
        if self.schema_version != 1:
            raise JournalValidationError("schema_version must be 1")
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise JournalValidationError("sequence must be a positive integer")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise JournalValidationError("type must be a non-empty string")
        if not isinstance(self.timestamp, str) or not self.timestamp.strip():
            raise JournalValidationError("timestamp must be a non-empty string")
        _parse_timestamp(self.timestamp)
        if not isinstance(self.payload, dict):
            raise JournalValidationError("payload must be a JSON object")
        try:
            json.dumps(self.payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise JournalValidationError("payload must be JSON-serializable") from exc


class JsonlEventJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        timestamp: str | None = None,
    ) -> JournalRecord:
        existing_records = self.read_all()
        sequence = existing_records[-1].sequence + 1 if existing_records else 1
        record = JournalRecord(
            sequence=sequence,
            event_type=event_type,
            timestamp=timestamp or _utc_timestamp(),
            payload=payload,
        )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as journal_file:
            journal_file.write(record.to_json_line())

        return record

    def read_all(self) -> list[JournalRecord]:
        if not self.path.exists():
            return []

        records: list[JournalRecord] = []
        with self.path.open("r", encoding="utf-8") as journal_file:
            for line_number, line in enumerate(journal_file, start=1):
                if not line.strip():
                    raise JournalValidationError(f"journal line {line_number} must not be blank")
                records.append(self._read_line(line, line_number))

        self._validate_sequence_order(records)
        return records

    def _read_line(self, line: str, line_number: int) -> JournalRecord:
        try:
            raw_record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalValidationError(f"Invalid JSON on journal line {line_number}") from exc

        try:
            return JournalRecord.from_json_dict(raw_record)
        except JournalValidationError as exc:
            raise JournalValidationError(
                f"Invalid journal record on line {line_number}: {exc}"
            ) from exc

    def _validate_sequence_order(self, records: list[JournalRecord]) -> None:
        for expected_sequence, record in enumerate(records, start=1):
            if record.sequence != expected_sequence:
                raise JournalValidationError(
                    f"journal sequence must be contiguous; expected {expected_sequence}, "
                    f"got {record.sequence}",
                )
