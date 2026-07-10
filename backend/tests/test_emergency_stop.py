from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from trading_oms_backend.emergency_stop import (
    EMERGENCY_STOP_ACTIVATED_EVENT_TYPE,
    EMERGENCY_STOP_BLOCKED_EVENT_TYPE,
    EMERGENCY_STOP_DEACTIVATED_EVENT_TYPE,
    EmergencyStopChangeRequest,
    EmergencyStopError,
    EmergencyStopService,
)
from trading_oms_backend.event_journal import JsonlEventJournal

ROOT = Path(__file__).resolve().parents[2]


def test_emergency_stop_activates_deactivates_and_journals_state_changes() -> None:
    journal = JsonlEventJournal(_journal_path())
    service = EmergencyStopService(journal)

    initial = service.current_state()
    activated = service.activate(_change_request("activate-001", reason="operator_review"))
    deactivated = service.deactivate(_change_request("deactivate-001", reason="resolved"))

    assert initial.active is False
    assert initial.status == "inactive"
    assert activated.state.active is True
    assert activated.state.status == "active"
    assert activated.state.activated_by == "admin-operator-001"
    assert activated.state.blocking_risk_increasing_actions is True
    assert deactivated.state.active is False
    assert deactivated.state.status == "inactive"
    assert deactivated.state.deactivated_by == "admin-operator-001"

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        EMERGENCY_STOP_ACTIVATED_EVENT_TYPE,
        EMERGENCY_STOP_DEACTIVATED_EVENT_TYPE,
    ]
    assert records[0].payload["state"]["active"] is True
    assert records[1].payload["state"]["active"] is False


def test_emergency_stop_change_requests_are_idempotent_and_reject_conflicts() -> None:
    service = EmergencyStopService(JsonlEventJournal(_journal_path()))
    request = _change_request("activate-001", reason="operator_review")

    first = service.activate(request)
    second = service.activate(request)

    assert second == first

    with pytest.raises(EmergencyStopError, match="conflicting event_id"):
        service.activate(_change_request("activate-001", reason="different_reason"))


def test_emergency_stop_blocks_risk_increasing_actions_and_journals_block_event() -> None:
    journal = JsonlEventJournal(_journal_path())
    service = EmergencyStopService(journal)
    service.activate(_change_request("activate-001", reason="operator_review"))

    with pytest.raises(EmergencyStopError, match="emergency stop is active"):
        service.ensure_risk_increasing_allowed(
            resource="approval_ticket.approval-ticket-001",
            action="approve",
            checked_at="2026-07-08T13:46:00Z",
            actor="approver-operator-001",
        )

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        EMERGENCY_STOP_ACTIVATED_EVENT_TYPE,
        EMERGENCY_STOP_BLOCKED_EVENT_TYPE,
    ]
    assert records[1].payload == {
        "schema_version": 1,
        "resource": "approval_ticket.approval-ticket-001",
        "action": "approve",
        "checked_at": "2026-07-08T13:46:00Z",
        "actor": "approver-operator-001",
        "emergency_stop_active": True,
        "reason": "emergency_stop_active_blocks_risk_increase",
    }


def test_emergency_stop_payloads_exclude_live_broker_and_secret_affordances() -> None:
    journal = JsonlEventJournal(_journal_path())
    service = EmergencyStopService(journal)
    change = service.activate(_change_request("activate-001", reason="operator_review"))

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "broker_host",
        "broker_port",
        "cancel_live",
        "credential",
        "flatten",
        "host",
        "liquidate",
        "password",
        "place_order_url",
        "port",
        "private_key",
        "route",
        "secret",
        "socket",
        "submit_url",
        "token",
        "transmit",
        "transmit_url",
    }
    assert forbidden_keys.isdisjoint(
        _all_payload_keys(
            {
                "change": change.to_json_dict(),
                "state": service.current_state().to_json_dict(),
                "records": [record.to_json_dict() for record in journal.read_all()],
            },
        ),
    )

    with pytest.raises(EmergencyStopError, match="secret-shaped"):
        service.activate(_change_request("secret-activate", reason="operator_review"))


def _change_request(event_id: str, *, reason: str) -> EmergencyStopChangeRequest:
    return EmergencyStopChangeRequest(
        event_id=event_id,
        requested_at="2026-07-08T13:45:00Z",
        actor="admin-operator-001",
        reason=reason,
    )


def _journal_path() -> Path:
    path = ROOT / ".tmp" / f"emergency-stop-{uuid4()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


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
