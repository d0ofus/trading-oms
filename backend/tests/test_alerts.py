from __future__ import annotations

import math
from typing import Any

import pytest

from trading_oms_backend.alerts import (
    ALERT_DISPATCH_RECORDED_EVENT_TYPE,
    ALERT_INTENT_CREATED_EVENT_TYPE,
    AlertBook,
    AlertDispatchOutcome,
    AlertDispatchRequest,
    AlertError,
    AlertIntent,
    AlertIntentRequest,
    NoopAlertDispatcher,
    TelegramAlertPayload,
    format_telegram_alert,
)
from trading_oms_backend.event_journal import JsonlEventJournal

CREATED_AT = "2026-07-06T00:10:00Z"
DISPATCHED_AT = "2026-07-06T00:10:02Z"


def intent_request(**overrides: Any) -> AlertIntentRequest:
    values = {
        "alert_id": "alert-001",
        "source_event_type": "oms.position.protection_missing",
        "source_event_reference": "event-001",
        "severity": "critical",
        "channel": "telegram",
        "created_at": CREATED_AT,
        "title": "Position protection missing",
        "message": "A risk-increasing position is missing expected protection.",
        "metadata": {
            "symbol": "AAPL",
            "position_id": "position-001",
            "expected_protection": "stop_loss",
        },
    }
    values.update(overrides)
    return AlertIntentRequest(**values)


def dispatch_request(**overrides: Any) -> AlertDispatchRequest:
    values = {
        "dispatch_id": "dispatch-001",
        "alert_id": "alert-001",
        "dispatched_at": DISPATCHED_AT,
        "reason": "record_local_noop_dispatch",
    }
    values.update(overrides)
    return AlertDispatchRequest(**values)


def test_alert_book_creates_intent_and_journals_it(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = AlertBook(journal)

    intent = book.create_intent(intent_request())

    assert intent == AlertIntent(
        alert_id="alert-001",
        source_event_type="oms.position.protection_missing",
        source_event_reference="event-001",
        severity="critical",
        channel="telegram",
        created_at=CREATED_AT,
        title="Position protection missing",
        message="A risk-increasing position is missing expected protection.",
        metadata={
            "symbol": "AAPL",
            "position_id": "position-001",
            "expected_protection": "stop_loss",
        },
    )

    records = journal.read_all()
    assert len(records) == 1
    assert records[0].event_type == ALERT_INTENT_CREATED_EVENT_TYPE
    assert records[0].timestamp == CREATED_AT
    assert records[0].payload == intent.to_json_dict()


@pytest.mark.parametrize("severity", ["informational", "warning", "critical", "emergency"])
def test_alert_intents_support_explicit_severities(severity: str, tmp_path) -> None:
    book = AlertBook(JsonlEventJournal(tmp_path / "events.jsonl"))

    intent = book.create_intent(
        intent_request(
            alert_id=f"alert-{severity}",
            severity=severity,
        ),
    )

    assert intent.severity == severity


def test_noop_dispatcher_records_dispatch_outcome_and_journals_it(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = AlertBook(journal)
    intent = book.create_intent(intent_request())

    outcome = book.dispatch_alert(dispatch_request(), NoopAlertDispatcher())

    assert outcome == AlertDispatchOutcome(
        dispatch_id="dispatch-001",
        alert_id="alert-001",
        severity="critical",
        channel="telegram",
        status="recorded",
        dispatcher="noop",
        dispatched_at=DISPATCHED_AT,
        reason="record_local_noop_dispatch",
        formatted_payload=format_telegram_alert(intent).to_json_dict(),
        alert=intent.to_json_dict(),
    )

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        ALERT_INTENT_CREATED_EVENT_TYPE,
        ALERT_DISPATCH_RECORDED_EVENT_TYPE,
    ]
    assert records[1].timestamp == DISPATCHED_AT
    assert records[1].payload == outcome.to_json_dict()


def test_telegram_formatter_returns_payload_without_token_chat_id_or_network_fields(
    tmp_path,
) -> None:
    book = AlertBook(JsonlEventJournal(tmp_path / "events.jsonl"))
    intent = book.create_intent(intent_request())

    payload = format_telegram_alert(intent)

    assert payload == TelegramAlertPayload(
        api_method="sendMessage",
        text=payload.text,
        disable_web_page_preview=True,
    )
    assert "CRITICAL" in payload.text
    assert "Position protection missing" in payload.text
    assert "source_event_reference: event-001" in payload.text
    assert "symbol: AAPL" in payload.text

    payload_dict = payload.to_json_dict()
    assert "chat_id" not in payload_dict
    assert "token" not in payload_dict
    assert "url" not in payload_dict


def test_alert_payload_has_no_broker_order_network_or_secret_fields(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = AlertBook(journal)
    book.create_intent(intent_request())

    outcome = book.dispatch_alert(dispatch_request(), NoopAlertDispatcher())

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker",
        "broker_host",
        "broker_port",
        "certificate",
        "chat_id",
        "credential",
        "destination",
        "host",
        "password",
        "private_key",
        "route",
        "secret",
        "socket",
        "submit",
        "token",
        "transmit",
        "url",
    }
    assert forbidden_keys.isdisjoint(_all_payload_keys(outcome.to_json_dict()))


def test_alert_intent_id_is_idempotent_for_same_payload_without_new_journal_record(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = AlertBook(journal)
    request = intent_request()

    first = book.create_intent(request)
    replayed = book.create_intent(request)

    assert replayed == first
    assert len(journal.read_all()) == 1


def test_dispatch_id_is_idempotent_for_same_payload_without_new_journal_record(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = AlertBook(journal)
    book.create_intent(intent_request())
    request = dispatch_request()

    first = book.dispatch_alert(request, NoopAlertDispatcher())
    replayed = book.dispatch_alert(request, NoopAlertDispatcher())

    assert replayed == first
    assert len(journal.read_all()) == 2


def test_alert_book_rejects_conflicting_duplicate_alert_id(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = AlertBook(journal)
    book.create_intent(intent_request())

    with pytest.raises(AlertError, match="conflicting alert_id"):
        book.create_intent(intent_request(title="Different title"))

    assert len(journal.read_all()) == 1


def test_alert_book_rejects_conflicting_duplicate_dispatch_id(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = AlertBook(journal)
    book.create_intent(intent_request())
    book.dispatch_alert(dispatch_request(), NoopAlertDispatcher())

    with pytest.raises(AlertError, match="conflicting dispatch_id"):
        book.dispatch_alert(dispatch_request(reason="different_reason"), NoopAlertDispatcher())

    assert len(journal.read_all()) == 2


def test_dispatch_for_unknown_alert_fails_without_journaling(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = AlertBook(journal)

    with pytest.raises(AlertError, match="unknown alert_id"):
        book.dispatch_alert(dispatch_request(), NoopAlertDispatcher())

    assert journal.read_all() == []


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"alert_id": ""}, "alert_id"),
        ({"alert_id": " alert-001"}, "alert_id"),
        ({"source_event_type": ""}, "source_event_type"),
        ({"source_event_reference": ""}, "source_event_reference"),
        ({"severity": "info"}, "severity"),
        ({"channel": "email"}, "channel"),
        ({"created_at": "not-a-date"}, "created_at"),
        ({"created_at": "2026-07-06T00:10:00"}, "created_at"),
        ({"title": ""}, "title"),
        ({"title": " token=redacted"}, "title"),
        ({"message": ""}, "message"),
        ({"message": "password: redacted"}, "message"),
        ({"metadata": "not-a-dict"}, "metadata"),
        ({"metadata": {"api_token": "redacted-sample"}}, "metadata"),
        ({"metadata": {"nested": {"password": "redacted-sample"}}}, "metadata"),
        ({"metadata": {"note": "token=redacted-sample"}}, "metadata"),
        ({"metadata": {"value": math.nan}}, "metadata"),
    ],
)
def test_alert_intent_request_rejects_invalid_or_secret_shaped_values(
    request_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(AlertError, match=match):
        intent_request(**request_kwargs)


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"dispatch_id": ""}, "dispatch_id"),
        ({"dispatch_id": " dispatch-001"}, "dispatch_id"),
        ({"alert_id": ""}, "alert_id"),
        ({"dispatched_at": "not-a-date"}, "dispatched_at"),
        ({"dispatched_at": "2026-07-06T00:10:02"}, "dispatched_at"),
        ({"reason": ""}, "reason"),
        ({"reason": "secret: redacted"}, "reason"),
    ],
)
def test_alert_dispatch_request_rejects_invalid_values(
    request_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(AlertError, match=match):
        dispatch_request(**request_kwargs)


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
