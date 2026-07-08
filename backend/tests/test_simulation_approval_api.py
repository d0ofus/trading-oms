from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import app, reset_simulation_approval_service


def test_simulation_approval_endpoint_approves_pending_ticket(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
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

    first = client.post("/api/approval-tickets/approval-ticket-001/approve", json=body)
    second = client.post("/api/approval-tickets/approval-ticket-001/approve", json=body)

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
        json=decision_body(decision_id="approval-decision-approve-001"),
    )
    rejected = client.post(
        "/api/approval-tickets/approval-ticket-001/reject",
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
        json=decision_body(decision_id="approval-decision-unknown-001"),
    )

    assert response.status_code == 400
    assert "unknown ticket_id" in response.json()["detail"]


def test_simulation_approval_endpoint_response_excludes_broker_and_secret_affordances(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_simulation_approval_service()
    client = TestClient(app)

    response = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
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


def _set_safe_env(monkeypatch: MonkeyPatch) -> None:
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
