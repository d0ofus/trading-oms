from __future__ import annotations

from typing import Any

import pytest

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.oms_state_machine import (
    OMS_TRANSITION_EVENT_TYPE,
    OMSStateMachineError,
    OrderStateMachine,
    OrderTransitionRequest,
)

CREATED_AT = "2026-07-06T00:03:00Z"
PENDING_AT = "2026-07-06T00:03:01Z"
APPROVED_AT = "2026-07-06T00:03:02Z"
SUBMITTED_AT = "2026-07-06T00:03:03Z"
ACKED_AT = "2026-07-06T00:03:04Z"
FILLED_AT = "2026-07-06T00:03:05Z"
CANCEL_REQUESTED_AT = "2026-07-06T00:03:06Z"
CANCELLED_AT = "2026-07-06T00:03:07Z"
UNKNOWN_AT = "2026-07-06T00:03:08Z"


def transition_request(**overrides: Any) -> OrderTransitionRequest:
    values = {
        "transition_id": "oms-transition-001",
        "order_id": "order-001",
        "client_order_id": "client-001",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "risk_intent": "increase",
        "target_state": "CREATED",
        "occurred_at": CREATED_AT,
        "reason": "order_intent_created",
        "risk_decision_id": "risk-001",
    }
    values.update(overrides)
    return OrderTransitionRequest(**values)


def apply_happy_path_until_submitted(machine: OrderStateMachine) -> None:
    machine.apply_transition(transition_request())
    machine.apply_transition(
        transition_request(
            transition_id="oms-transition-002",
            target_state="PENDING_APPROVAL",
            occurred_at=PENDING_AT,
            reason="risk_passed_pending_approval",
        ),
    )
    machine.apply_transition(
        transition_request(
            transition_id="oms-transition-003",
            target_state="APPROVED",
            occurred_at=APPROVED_AT,
            reason="manual_approval_recorded",
            approval_reference="approval-001",
        ),
    )
    machine.apply_transition(
        transition_request(
            transition_id="oms-transition-004",
            target_state="SUBMITTED",
            occurred_at=SUBMITTED_AT,
            reason="submitted_to_simulation_adapter",
            approval_reference="approval-001",
        ),
    )


def test_oms_state_machine_applies_full_lifecycle_and_journals_each_transition(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    machine = OrderStateMachine(journal)

    apply_happy_path_until_submitted(machine)
    acknowledged = machine.apply_transition(
        transition_request(
            transition_id="oms-transition-005",
            target_state="ACKNOWLEDGED",
            occurred_at=ACKED_AT,
            reason="fake_broker_acknowledged",
            approval_reference="approval-001",
            broker_transition_reference="fake-transition-ack",
        ),
    )
    filled = machine.apply_transition(
        transition_request(
            transition_id="oms-transition-006",
            target_state="FILLED",
            occurred_at=FILLED_AT,
            reason="fake_broker_filled",
            approval_reference="approval-001",
            broker_transition_reference="fake-transition-fill",
            cumulative_filled_quantity=10,
        ),
    )

    assert acknowledged.previous_state == "SUBMITTED"
    assert acknowledged.new_state == "ACKNOWLEDGED"
    assert filled.previous_state == "ACKNOWLEDGED"
    assert filled.new_state == "FILLED"
    assert filled.snapshot.state == "FILLED"
    assert filled.snapshot.cumulative_filled_quantity == 10
    assert filled.snapshot.leaves_quantity == 0
    assert machine.current_snapshot("order-001") == filled.snapshot

    records = journal.read_all()
    assert len(records) == 6
    assert [record.sequence for record in records] == [1, 2, 3, 4, 5, 6]
    assert [record.event_type for record in records] == [OMS_TRANSITION_EVENT_TYPE] * 6
    assert [record.payload["new_state"] for record in records] == [
        "CREATED",
        "PENDING_APPROVAL",
        "APPROVED",
        "SUBMITTED",
        "ACKNOWLEDGED",
        "FILLED",
    ]
    assert records[-1].payload == filled.to_json_dict()


def test_oms_state_machine_applies_cancel_path(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    machine = OrderStateMachine(journal)
    apply_happy_path_until_submitted(machine)
    machine.apply_transition(
        transition_request(
            transition_id="oms-transition-005",
            target_state="ACKNOWLEDGED",
            occurred_at=ACKED_AT,
            reason="fake_broker_acknowledged",
            approval_reference="approval-001",
            broker_transition_reference="fake-transition-ack",
        ),
    )

    cancel_requested = machine.apply_transition(
        transition_request(
            transition_id="oms-transition-006",
            target_state="CANCEL_REQUESTED",
            occurred_at=CANCEL_REQUESTED_AT,
            reason="operator_cancel_requested",
            approval_reference="approval-001",
        ),
    )
    cancelled = machine.apply_transition(
        transition_request(
            transition_id="oms-transition-007",
            target_state="CANCELLED",
            occurred_at=CANCELLED_AT,
            reason="fake_broker_cancelled",
            approval_reference="approval-001",
            broker_transition_reference="fake-transition-cancel",
        ),
    )

    assert cancel_requested.previous_state == "ACKNOWLEDGED"
    assert cancelled.previous_state == "CANCEL_REQUESTED"
    assert cancelled.snapshot.state == "CANCELLED"
    assert cancelled.snapshot.leaves_quantity == 0
    assert [record.payload["new_state"] for record in journal.read_all()] == [
        "CREATED",
        "PENDING_APPROVAL",
        "APPROVED",
        "SUBMITTED",
        "ACKNOWLEDGED",
        "CANCEL_REQUESTED",
        "CANCELLED",
    ]


@pytest.mark.parametrize(
    ("target_state", "reason"),
    [
        ("RISK_REJECTED", "risk_blocked"),
        ("APPROVAL_REJECTED", "manual_approval_rejected"),
    ],
)
def test_oms_state_machine_applies_rejection_terminal_paths(
    target_state: str,
    reason: str,
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    machine = OrderStateMachine(journal)
    machine.apply_transition(transition_request())
    if target_state == "APPROVAL_REJECTED":
        machine.apply_transition(
            transition_request(
                transition_id="oms-transition-002",
                target_state="PENDING_APPROVAL",
                occurred_at=PENDING_AT,
                reason="risk_passed_pending_approval",
            ),
        )

    record = machine.apply_transition(
        transition_request(
            transition_id="oms-transition-003",
            target_state=target_state,
            occurred_at=APPROVED_AT,
            reason=reason,
        ),
    )

    assert record.new_state == target_state
    assert machine.current_snapshot("order-001").state == target_state
    assert journal.read_all()[-1].payload["new_state"] == target_state


def test_oms_state_machine_blocks_invalid_transition_without_journaling(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    machine = OrderStateMachine(journal)
    machine.apply_transition(transition_request())

    with pytest.raises(OMSStateMachineError, match="invalid transition"):
        machine.apply_transition(
            transition_request(
                transition_id="oms-transition-002",
                target_state="SUBMITTED",
                occurred_at=SUBMITTED_AT,
                reason="skip_required_states",
                approval_reference="approval-001",
            ),
        )

    assert machine.current_snapshot("order-001").state == "CREATED"
    assert len(journal.read_all()) == 1


def test_oms_state_machine_replays_duplicate_transition_id_idempotently(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    machine = OrderStateMachine(journal)
    request = transition_request()

    first = machine.apply_transition(request)
    replayed = machine.apply_transition(request)

    assert replayed == first
    assert len(journal.read_all()) == 1


def test_oms_state_machine_rejects_conflicting_duplicate_transition_id(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    machine = OrderStateMachine(journal)
    machine.apply_transition(transition_request())

    with pytest.raises(OMSStateMachineError, match="conflicting transition_id"):
        machine.apply_transition(
            transition_request(
                transition_id="oms-transition-001",
                reason="different_payload",
            ),
        )

    assert len(journal.read_all()) == 1


def test_unknown_broker_state_requires_reconciliation_and_blocks_risk_increase(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    machine = OrderStateMachine(journal)
    apply_happy_path_until_submitted(machine)

    unknown = machine.apply_transition(
        transition_request(
            transition_id="oms-transition-005",
            target_state="UNKNOWN_REQUIRES_RECONCILIATION",
            occurred_at=UNKNOWN_AT,
            reason="broker_state_unknown",
            approval_reference="approval-001",
            broker_transition_reference="reconciliation-required-001",
        ),
    )

    assert unknown.new_state == "UNKNOWN_REQUIRES_RECONCILIATION"
    assert unknown.snapshot.requires_reconciliation is True
    assert machine.risk_increasing_decisions_blocked("order-001") is True
    assert journal.read_all()[-1].payload["snapshot"]["requires_reconciliation"] is True


def test_oms_transition_payload_has_no_live_routing_or_secret_fields(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    machine = OrderStateMachine(journal)

    record = machine.apply_transition(transition_request())

    forbidden_keys = {
        "account",
        "broker_host",
        "broker_port",
        "certificate",
        "credential",
        "destination",
        "host",
        "password",
        "private_key",
        "route",
        "secret",
        "socket",
        "token",
        "transmit",
    }
    assert forbidden_keys.isdisjoint(_all_payload_keys(record.to_json_dict()))


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"transition_id": ""}, "transition_id"),
        ({"transition_id": " oms-transition-001"}, "transition_id"),
        ({"order_id": ""}, "order_id"),
        ({"client_order_id": ""}, "client_order_id"),
        ({"symbol": "aapl"}, "symbol"),
        ({"side": "hold"}, "side"),
        ({"quantity": 0}, "quantity"),
        ({"quantity": True}, "quantity"),
        ({"risk_intent": "neutral"}, "risk_intent"),
        ({"target_state": "BROKER_SENT"}, "target_state"),
        ({"occurred_at": "not-a-date"}, "occurred_at"),
        ({"occurred_at": "2026-07-06T00:03:00"}, "occurred_at"),
        ({"reason": ""}, "reason"),
        ({"risk_decision_id": ""}, "risk_decision_id"),
        ({"approval_reference": " approval-001"}, "approval_reference"),
        ({"broker_transition_reference": " fake-transition"}, "broker_transition_reference"),
        ({"cumulative_filled_quantity": -1}, "cumulative_filled_quantity"),
        ({"cumulative_filled_quantity": True}, "cumulative_filled_quantity"),
    ],
)
def test_oms_transition_request_rejects_invalid_values(
    request_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(OMSStateMachineError, match=match):
        transition_request(**request_kwargs)


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        (
            {
                "transition_id": "oms-transition-003",
                "target_state": "APPROVED",
                "occurred_at": APPROVED_AT,
                "reason": "manual_approval_recorded",
            },
            "approval_reference",
        ),
        (
            {
                "transition_id": "oms-transition-005",
                "target_state": "ACKNOWLEDGED",
                "occurred_at": ACKED_AT,
                "reason": "fake_broker_acknowledged",
                "approval_reference": "approval-001",
            },
            "broker_transition_reference",
        ),
        (
            {
                "transition_id": "oms-transition-006",
                "target_state": "FILLED",
                "occurred_at": FILLED_AT,
                "reason": "fake_broker_filled",
                "approval_reference": "approval-001",
                "broker_transition_reference": "fake-transition-fill",
                "cumulative_filled_quantity": 9,
            },
            "FILLED",
        ),
    ],
)
def test_oms_state_machine_rejects_missing_state_required_context(
    request_kwargs: dict[str, Any],
    match: str,
    tmp_path,
) -> None:
    machine = OrderStateMachine(JsonlEventJournal(tmp_path / "events.jsonl"))
    if request_kwargs["target_state"] == "APPROVED":
        machine.apply_transition(transition_request())
        machine.apply_transition(
            transition_request(
                transition_id="oms-transition-002",
                target_state="PENDING_APPROVAL",
                occurred_at=PENDING_AT,
                reason="risk_passed_pending_approval",
            ),
        )
    else:
        apply_happy_path_until_submitted(machine)
        if request_kwargs["target_state"] == "FILLED":
            machine.apply_transition(
                transition_request(
                    transition_id="oms-transition-005",
                    target_state="ACKNOWLEDGED",
                    occurred_at=ACKED_AT,
                    reason="fake_broker_acknowledged",
                    approval_reference="approval-001",
                    broker_transition_reference="fake-transition-ack",
                ),
            )

    with pytest.raises(OMSStateMachineError, match=match):
        machine.apply_transition(transition_request(**request_kwargs))


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
