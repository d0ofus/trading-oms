from __future__ import annotations

from typing import Any

import pytest

from trading_oms_backend.approval_tickets import (
    APPROVAL_DECISION_EVENT_TYPE,
    APPROVAL_TICKET_CREATED_EVENT_TYPE,
    ApprovalDecisionRecord,
    ApprovalDecisionRequest,
    ApprovalTicket,
    ApprovalTicketBook,
    ApprovalTicketCreateRequest,
    ApprovalTicketError,
)
from trading_oms_backend.event_journal import JsonlEventJournal

CREATED_AT = "2026-07-06T00:04:00Z"
EXPIRES_AT = "2026-07-06T00:09:00Z"
APPROVED_AT = "2026-07-06T00:05:00Z"
REJECTED_AT = "2026-07-06T00:05:30Z"
EXPIRED_AT = "2026-07-06T00:09:01Z"
CANCELLED_AT = "2026-07-06T00:06:00Z"


def create_request(**overrides: Any) -> ApprovalTicketCreateRequest:
    values = {
        "ticket_id": "approval-ticket-001",
        "order_id": "order-001",
        "client_order_id": "client-001",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "risk_intent": "increase",
        "risk_decision_id": "risk-001",
        "risk_decision_result": "passed",
        "oms_transition_reference": "oms-transition-002",
        "oms_state": "PENDING_APPROVAL",
        "created_at": CREATED_AT,
        "expires_at": EXPIRES_AT,
        "reason": "risk_passed_requires_human_approval",
    }
    values.update(overrides)
    return ApprovalTicketCreateRequest(**values)


def decision_request(**overrides: Any) -> ApprovalDecisionRequest:
    values = {
        "decision_id": "approval-decision-001",
        "ticket_id": "approval-ticket-001",
        "decision": "approved",
        "decided_at": APPROVED_AT,
        "actor": "human-operator-001",
        "decision_reference": "manual-approval-001",
        "reason": "operator_approved_order",
    }
    values.update(overrides)
    return ApprovalDecisionRequest(**values)


def test_approval_ticket_book_creates_pending_ticket_and_journals_creation(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = ApprovalTicketBook(journal)

    ticket = book.create_ticket(create_request())

    assert ticket == ApprovalTicket(
        ticket_id="approval-ticket-001",
        order_id="order-001",
        client_order_id="client-001",
        symbol="AAPL",
        side="buy",
        quantity=10,
        risk_intent="increase",
        risk_decision_id="risk-001",
        oms_transition_reference="oms-transition-002",
        status="pending",
        created_at=CREATED_AT,
        expires_at=EXPIRES_AT,
        decision_id=None,
        decided_at=None,
        actor=None,
        decision_reference=None,
        reason=None,
        create_request=create_request().to_json_dict(),
    )
    assert book.current_ticket("approval-ticket-001") == ticket

    records = journal.read_all()
    assert len(records) == 1
    assert records[0].event_type == APPROVAL_TICKET_CREATED_EVENT_TYPE
    assert records[0].timestamp == CREATED_AT
    assert records[0].payload == ticket.to_json_dict()


@pytest.mark.parametrize(
    ("decision", "decided_at", "reason"),
    [
        ("approved", APPROVED_AT, "operator_approved_order"),
        ("rejected", REJECTED_AT, "operator_rejected_order"),
        ("expired", EXPIRED_AT, "ticket_expired"),
        ("cancelled", CANCELLED_AT, "operator_cancelled_ticket"),
    ],
)
def test_approval_ticket_book_applies_decisions_and_journals_each_one(
    decision: str,
    decided_at: str,
    reason: str,
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = ApprovalTicketBook(journal)
    book.create_ticket(create_request())

    record = book.apply_decision(
        decision_request(
            decision_id=f"approval-decision-{decision}",
            decision=decision,
            decided_at=decided_at,
            reason=reason,
            actor=("system-expiry-check" if decision == "expired" else "human-operator-001"),
            decision_reference=(
                "expiry-check-001" if decision == "expired" else f"manual-{decision}-001"
            ),
        ),
    )

    assert record == ApprovalDecisionRecord(
        decision_id=f"approval-decision-{decision}",
        ticket_id="approval-ticket-001",
        previous_status="pending",
        new_status=decision,
        decided_at=decided_at,
        actor="system-expiry-check" if decision == "expired" else "human-operator-001",
        decision_reference=(
            "expiry-check-001" if decision == "expired" else f"manual-{decision}-001"
        ),
        reason=reason,
        request=decision_request(
            decision_id=f"approval-decision-{decision}",
            decision=decision,
            decided_at=decided_at,
            reason=reason,
            actor=("system-expiry-check" if decision == "expired" else "human-operator-001"),
            decision_reference=(
                "expiry-check-001" if decision == "expired" else f"manual-{decision}-001"
            ),
        ).to_json_dict(),
        ticket=book.current_ticket("approval-ticket-001"),
    )
    assert record.ticket.status == decision
    assert record.ticket.decision_id == f"approval-decision-{decision}"
    assert record.ticket.actor is not None
    assert record.ticket.decision_reference is not None

    records = journal.read_all()
    assert [journal_record.event_type for journal_record in records] == [
        APPROVAL_TICKET_CREATED_EVENT_TYPE,
        APPROVAL_DECISION_EVENT_TYPE,
    ]
    assert records[1].timestamp == decided_at
    assert records[1].payload == record.to_json_dict()


def test_approved_ticket_does_not_emit_submission_or_broker_payload_fields(tmp_path) -> None:
    book = ApprovalTicketBook(JsonlEventJournal(tmp_path / "events.jsonl"))
    book.create_ticket(create_request())

    record = book.apply_decision(decision_request())

    forbidden_keys = {
        "account",
        "broker",
        "broker_host",
        "broker_order_id",
        "broker_port",
        "credential",
        "destination",
        "host",
        "route",
        "secret",
        "socket",
        "submit",
        "submitted",
        "transmit",
    }
    assert forbidden_keys.isdisjoint(_all_payload_keys(record.to_json_dict()))


def test_ticket_create_is_idempotent_for_same_payload_without_new_journal_record(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = ApprovalTicketBook(journal)
    request = create_request()

    first = book.create_ticket(request)
    replayed = book.create_ticket(request)

    assert replayed == first
    assert len(journal.read_all()) == 1


def test_ticket_create_rejects_conflicting_duplicate_ticket_id(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = ApprovalTicketBook(journal)
    book.create_ticket(create_request())

    with pytest.raises(ApprovalTicketError, match="conflicting ticket_id"):
        book.create_ticket(create_request(reason="different_reason"))

    assert len(journal.read_all()) == 1


def test_decision_id_is_idempotent_for_same_payload_without_new_journal_record(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = ApprovalTicketBook(journal)
    book.create_ticket(create_request())
    request = decision_request()

    first = book.apply_decision(request)
    replayed = book.apply_decision(request)

    assert replayed == first
    assert len(journal.read_all()) == 2


def test_decision_id_rejects_conflicting_duplicate_payload(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = ApprovalTicketBook(journal)
    book.create_ticket(create_request())
    book.apply_decision(decision_request())

    with pytest.raises(ApprovalTicketError, match="conflicting decision_id"):
        book.apply_decision(decision_request(reason="different_reason"))

    assert len(journal.read_all()) == 2


def test_ticket_cannot_be_decided_twice_with_different_decision_ids(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = ApprovalTicketBook(journal)
    book.create_ticket(create_request())
    book.apply_decision(decision_request())

    with pytest.raises(ApprovalTicketError, match="ticket is not pending"):
        book.apply_decision(
            decision_request(
                decision_id="approval-decision-002",
                decision="rejected",
                decided_at=REJECTED_AT,
                decision_reference="manual-rejection-001",
                reason="operator_changed_mind",
            ),
        )

    assert book.current_ticket("approval-ticket-001").status == "approved"
    assert len(journal.read_all()) == 2


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"ticket_id": ""}, "ticket_id"),
        ({"ticket_id": " approval-ticket-001"}, "ticket_id"),
        ({"order_id": ""}, "order_id"),
        ({"client_order_id": ""}, "client_order_id"),
        ({"symbol": "aapl"}, "symbol"),
        ({"side": "hold"}, "side"),
        ({"quantity": 0}, "quantity"),
        ({"quantity": True}, "quantity"),
        ({"risk_intent": "neutral"}, "risk_intent"),
        ({"risk_decision_id": ""}, "risk_decision_id"),
        ({"risk_decision_result": "blocked"}, "risk_decision_result"),
        ({"oms_transition_reference": ""}, "oms_transition_reference"),
        ({"oms_state": "CREATED"}, "oms_state"),
        ({"created_at": "not-a-date"}, "created_at"),
        ({"created_at": "2026-07-06T00:04:00"}, "created_at"),
        ({"expires_at": "not-a-date"}, "expires_at"),
        ({"expires_at": CREATED_AT}, "expires_at"),
        ({"reason": ""}, "reason"),
    ],
)
def test_ticket_create_request_rejects_invalid_values(
    request_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ApprovalTicketError, match=match):
        create_request(**request_kwargs)


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"decision_id": ""}, "decision_id"),
        ({"decision_id": " approval-decision-001"}, "decision_id"),
        ({"ticket_id": ""}, "ticket_id"),
        ({"decision": "submitted"}, "decision"),
        ({"decided_at": "not-a-date"}, "decided_at"),
        ({"decided_at": "2026-07-06T00:05:00"}, "decided_at"),
        ({"actor": ""}, "actor"),
        ({"actor": " human-operator-001"}, "actor"),
        ({"decision_reference": ""}, "decision_reference"),
        ({"decision_reference": " manual-approval-001"}, "decision_reference"),
        ({"reason": ""}, "reason"),
    ],
)
def test_decision_request_rejects_invalid_values(
    request_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ApprovalTicketError, match=match):
        decision_request(**request_kwargs)


@pytest.mark.parametrize(
    ("decision", "decided_at", "match"),
    [
        ("approved", EXPIRED_AT, "expired"),
        ("rejected", EXPIRED_AT, "expired"),
        ("cancelled", EXPIRED_AT, "expired"),
        ("expired", APPROVED_AT, "expires_at"),
    ],
)
def test_decisions_enforce_ticket_expiry_timing(
    decision: str,
    decided_at: str,
    match: str,
    tmp_path,
) -> None:
    book = ApprovalTicketBook(JsonlEventJournal(tmp_path / "events.jsonl"))
    book.create_ticket(create_request())

    with pytest.raises(ApprovalTicketError, match=match):
        book.apply_decision(
            decision_request(
                decision=decision,
                decided_at=decided_at,
                actor="system-expiry-check" if decision == "expired" else "human-operator-001",
                decision_reference=(
                    "expiry-check-001" if decision == "expired" else f"manual-{decision}-001"
                ),
                reason=f"{decision}_timing_invalid",
            ),
        )


def test_decision_for_unknown_ticket_fails_without_journaling(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    book = ApprovalTicketBook(journal)

    with pytest.raises(ApprovalTicketError, match="unknown ticket_id"):
        book.apply_decision(decision_request())

    assert journal.read_all() == []


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
