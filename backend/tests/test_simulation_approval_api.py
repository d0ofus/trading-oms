from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import (
    app,
    operator_auth_journal_records,
    reset_emergency_stop_service,
    reset_operator_auth_service,
    reset_simulation_approval_service,
)


def test_simulation_approval_endpoint_approves_pending_ticket(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        headers=approver_headers(),
        json=decision_body(decision_id="approval-decision-approve-001"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["new_status"] == "approved"
    assert payload["actor"] == "human-operator-001"
    assert payload["reason"] == "operator_reviewed_simulation_ticket"
    assert payload["ticket"]["status"] == "approved"
    assert payload["ticket"]["ticket_id"] == "approval-ticket-001"


def test_simulation_approval_endpoint_rejects_pending_ticket(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/approval-ticket-001/reject",
        headers=approver_headers(),
        json=decision_body(decision_id="approval-decision-reject-001"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["new_status"] == "rejected"
    assert payload["ticket"]["status"] == "rejected"


def test_simulation_approval_endpoint_is_idempotent_for_same_decision_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_simulation_approval_service()
    client = TestClient(app)
    body = decision_body(decision_id="approval-decision-idempotent-001")

    first = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        headers=approver_headers(),
        json=body,
    )
    second = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        headers=approver_headers(),
        json=body,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()


def test_simulation_approval_endpoint_rejects_second_different_decision(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_simulation_approval_service()
    client = TestClient(app)

    approved = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        headers=approver_headers(),
        json=decision_body(decision_id="approval-decision-approve-001"),
    )
    rejected = client.post(
        "/api/approval-tickets/approval-ticket-001/reject",
        headers=approver_headers(),
        json=decision_body(decision_id="approval-decision-reject-001"),
    )

    assert approved.status_code == 200
    assert rejected.status_code == 400
    assert "ticket is not pending" in rejected.json()["detail"]


def test_simulation_approval_endpoint_rejects_unknown_ticket(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/unknown-ticket/approve",
        headers=approver_headers(),
        json=decision_body(decision_id="approval-decision-unknown-001"),
    )

    assert response.status_code == 400
    assert "unknown ticket_id" in response.json()["detail"]


def test_simulation_approval_endpoint_requires_approver_role_and_journals_admin_denial(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_operator_auth_service()
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        json=decision_body(actor="human-operator-001"),
    )

    assert response.status_code == 403
    assert "approve_simulation" in response.json()["detail"]

    records = operator_auth_journal_records()
    assert len(records) == 1
    assert records[0].event_type == "authz.decision.evaluated"
    assert records[0].payload["operator_id"] == "human-operator-001"
    assert records[0].payload["operator_roles"] == ["admin"]
    assert records[0].payload["permission"] == "approve_simulation"
    assert records[0].payload["required_role"] == "approver"
    assert records[0].payload["role_separation"] == "admin_approver_separated"
    assert records[0].payload["resource"] == "approval_ticket.approval-ticket-001"
    assert records[0].payload["result"] == "denied"


def test_simulation_approval_endpoint_requires_approve_permission_and_journals_viewer_denial(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_operator_auth_service()
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        headers={
            "x-operator-id": "viewer-operator-001",
            "x-operator-roles": "viewer",
        },
        json=decision_body(actor="viewer-operator-001"),
    )

    assert response.status_code == 403
    assert "approve_simulation" in response.json()["detail"]

    records = operator_auth_journal_records()
    assert len(records) == 1
    assert records[0].event_type == "authz.decision.evaluated"
    assert records[0].payload["operator_id"] == "viewer-operator-001"
    assert records[0].payload["operator_roles"] == ["viewer"]
    assert records[0].payload["permission"] == "approve_simulation"
    assert records[0].payload["required_role"] == "approver"
    assert records[0].payload["resource"] == "approval_ticket.approval-ticket-001"
    assert records[0].payload["result"] == "denied"


def test_simulation_approval_endpoint_requires_body_actor_to_match_authenticated_operator(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_operator_auth_service()
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        headers={
            "x-operator-id": "approver-operator-001",
            "x-operator-roles": "approver",
        },
        json=decision_body(actor="different-operator-001"),
    )

    assert response.status_code == 400
    assert "actor must match authenticated operator" in response.json()["detail"]


def test_simulation_approval_endpoint_response_excludes_broker_and_secret_affordances(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        headers=approver_headers(),
        json=decision_body(decision_id="approval-decision-safety-001"),
    )

    assert response.status_code == 200
    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "broker_host",
        "broker_order_id",
        "broker_port",
        "credential",
        "host",
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
    assert forbidden_keys.isdisjoint(_all_payload_keys(response.json()))


def decision_body(**overrides: Any) -> dict[str, str]:
    values = {
        "decision_id": "approval-decision-001",
        "decided_at": "2026-07-08T13:46:00Z",
        "actor": "human-operator-001",
        "decision_reference": "manual-simulation-approval-001",
        "reason": "operator_reviewed_simulation_ticket",
    }
    values.update(overrides)
    return values


def approver_headers() -> dict[str, str]:
    return {
        "x-operator-id": "human-operator-001",
        "x-operator-roles": "approver",
    }


def _set_safe_env(monkeypatch: MonkeyPatch) -> None:
    reset_emergency_stop_service()
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_ACCOUNT_MODE", raising=False)
    monkeypatch.delenv("IBKR_HOST", raising=False)
    monkeypatch.delenv("IBKR_PORT", raising=False)


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
