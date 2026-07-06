from __future__ import annotations

import json

import pytest

from trading_oms_backend.event_journal import (
    JournalRecord,
    JournalValidationError,
    JsonlEventJournal,
)

FIXED_TIMESTAMP = "2026-07-06T00:00:00Z"


def test_append_creates_ordered_jsonl_records(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    first = journal.append(
        event_type="system.started",
        payload={"app_mode": "paper"},
        timestamp=FIXED_TIMESTAMP,
    )
    second = journal.append(
        event_type="risk.checked",
        payload={"result": "blocked"},
        timestamp="2026-07-06T00:00:01Z",
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert [record.event_type for record in journal.read_all()] == [
        "system.started",
        "risk.checked",
    ]


def test_append_preserves_existing_file_bytes(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    journal = JsonlEventJournal(path)
    journal.append("system.started", {"app_mode": "paper"}, timestamp=FIXED_TIMESTAMP)
    original_bytes = path.read_bytes()

    journal.append("system.stopped", {"reason": "test"}, timestamp="2026-07-06T00:00:01Z")

    updated_bytes = path.read_bytes()
    assert updated_bytes.startswith(original_bytes)
    assert updated_bytes.count(b"\n") == 2


def test_record_round_trip_uses_stable_json_shape() -> None:
    record = JournalRecord(
        sequence=1,
        event_type="system.started",
        timestamp=FIXED_TIMESTAMP,
        payload={"app_mode": "paper"},
    )

    assert record.to_json_dict() == {
        "schema_version": 1,
        "sequence": 1,
        "type": "system.started",
        "timestamp": FIXED_TIMESTAMP,
        "payload": {"app_mode": "paper"},
    }
    assert JournalRecord.from_json_dict(record.to_json_dict()) == record


@pytest.mark.parametrize(
    "raw_record",
    [
        {},
        {"schema_version": 1, "sequence": 1, "timestamp": FIXED_TIMESTAMP, "payload": {}},
        {
            "schema_version": 1,
            "sequence": 1,
            "type": "",
            "timestamp": FIXED_TIMESTAMP,
            "payload": {},
        },
        {
            "schema_version": 1,
            "sequence": 0,
            "type": "x",
            "timestamp": FIXED_TIMESTAMP,
            "payload": {},
        },
        {"schema_version": 1, "sequence": 1, "type": "x", "timestamp": "not-a-date", "payload": {}},
        {
            "schema_version": 1,
            "sequence": 1,
            "type": "x",
            "timestamp": FIXED_TIMESTAMP,
            "payload": [],
        },
    ],
)
def test_record_validation_rejects_invalid_records(raw_record) -> None:
    with pytest.raises(JournalValidationError):
        JournalRecord.from_json_dict(raw_record)


def test_append_rejects_non_json_serializable_payload(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    with pytest.raises(JournalValidationError, match="JSON-serializable"):
        journal.append("system.started", {"bad": {object()}}, timestamp=FIXED_TIMESTAMP)


def test_append_rejects_non_standard_json_payload(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    with pytest.raises(JournalValidationError, match="JSON-serializable"):
        journal.append("system.started", {"bad": float("nan")}, timestamp=FIXED_TIMESTAMP)


def test_reader_rejects_invalid_json_line(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(JournalValidationError, match="Invalid JSON"):
        JsonlEventJournal(path).read_all()


def test_reader_rejects_blank_lines(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("\n", encoding="utf-8")

    with pytest.raises(JournalValidationError, match="blank"):
        JsonlEventJournal(path).read_all()


def test_reader_rejects_out_of_order_sequences(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    records = [
        JournalRecord(1, "system.started", FIXED_TIMESTAMP, {}).to_json_dict(),
        JournalRecord(1, "system.started", "2026-07-06T00:00:01Z", {}).to_json_dict(),
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    with pytest.raises(JournalValidationError, match="sequence"):
        JsonlEventJournal(path).read_all()
