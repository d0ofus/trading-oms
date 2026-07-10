from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import (
    app,
    emergency_stop_journal_records,
    reset_emergency_stop_service,
    reset_operator_auth_service,
    reset_simulation_approval_service,
    reset_workflow_definition_service,
    reset_workflow_simulation_runner_service,
)


def test_emergency_stop_read_endpoint_returns_local_state(monkeypatch: MonkeyPatch) -> None:
    _set_safe_env(monkeypatch)
    reset_emergency_stop_service()
    client = TestClient(app)

    response = client.get("/api/emergency-stop")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": 1,
        "active": False,
        "status": "inactive",
        "updated_at": "2026-07-08T00:00:00Z",
        "activated_at": None,
        "activated_by": None,
        "activation_reason": None,
        "deactivated_at": None,
        "deactivated_by": None,
        "deactivation_reason": None,
        "blocking_risk_increasing_actions": False,
    }


def test_emergency_stop_activation_and_deactivation_require_admin_and_journal(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_operator_auth_service()
    reset_emergency_stop_service()
    client = TestClient(app)

    denied = client.post(
        "/api/emergency-stop/activate",
        headers={"x-operator-id": "approver-operator-001", "x-operator-roles": "approver"},
        json=_change_body(actor="approver-operator-001"),
    )
    activated = client.post(
        "/api/emergency-stop/activate",
        json=_change_body(event_id="emergency-stop-activate-001"),
    )
    idempotent = client.post(
        "/api/emergency-stop/activate",
        json=_change_body(event_id="emergency-stop-activate-001"),
    )
    deactivated = client.post(
        "/api/emergency-stop/deactivate",
        json=_change_body(
            event_id="emergency-stop-deactivate-001",
            reason="review_resolved",
        ),
    )

    assert denied.status_code == 403
    assert "administer_system" in denied.json()["detail"]
    assert activated.status_code == 200
    assert activated.json()["state"]["active"] is True
    assert activated.json()["state"]["activated_by"] == "human-operator-001"
    assert idempotent.status_code == 200
    assert idempotent.json() == activated.json()
    assert deactivated.status_code == 200
    assert deactivated.json()["state"]["active"] is False

    records = emergency_stop_journal_records()
    assert [record.event_type for record in records] == [
        "emergency_stop.activated",
        "emergency_stop.deactivated",
    ]
    assert records[0].payload["state"]["blocking_risk_increasing_actions"] is True


def test_emergency_stop_mutation_binds_actor_to_authenticated_operator(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_emergency_stop_service()
    client = TestClient(app)

    response = client.post(
        "/api/emergency-stop/activate",
        json=_change_body(actor="different-operator-001"),
    )

    assert response.status_code == 400
    assert "actor must match authenticated operator" in response.json()["detail"]


def test_active_emergency_stop_blocks_approval_but_allows_rejection(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_operator_auth_service()
    reset_emergency_stop_service()
    reset_simulation_approval_service()
    client = TestClient(app)
    activated = client.post(
        "/api/emergency-stop/activate",
        json=_change_body(event_id="emergency-stop-activate-001"),
    )

    approval = client.post(
        "/api/approval-tickets/approval-ticket-001/approve",
        headers=_approver_headers(),
        json=_decision_body(
            actor="approver-operator-001",
            decision_id="approval-decision-blocked-001",
        ),
    )
    rejection = client.post(
        "/api/approval-tickets/approval-ticket-001/reject",
        headers=_approver_headers(),
        json=_decision_body(
            actor="approver-operator-001",
            decision_id="approval-decision-reject-001",
        ),
    )

    assert activated.status_code == 200
    assert approval.status_code == 423
    assert "emergency stop is active" in approval.json()["detail"]
    assert rejection.status_code == 200
    assert rejection.json()["new_status"] == "rejected"

    records = emergency_stop_journal_records()
    assert [record.event_type for record in records] == [
        "emergency_stop.activated",
        "emergency_stop.risk_increasing_action_blocked",
    ]
    assert records[1].payload["resource"] == "approval_ticket.approval-ticket-001"
    assert records[1].payload["action"] == "approve"
    assert records[1].payload["actor"] == "approver-operator-001"


def test_active_emergency_stop_blocks_workflow_simulation_run_start(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_operator_auth_service()
    reset_emergency_stop_service()
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    created = client.post("/api/workflows", json=_workflow_body())
    activated = client.post(
        "/api/emergency-stop/activate",
        json=_change_body(event_id="emergency-stop-activate-001"),
    )

    response = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(),
    )

    assert created.status_code == 200
    assert activated.status_code == 200
    assert response.status_code == 423
    assert "emergency stop is active" in response.json()["detail"]

    records = emergency_stop_journal_records()
    assert records[-1].event_type == "emergency_stop.risk_increasing_action_blocked"
    assert records[-1].payload["resource"] == "workflow_simulation_run.workflow-001"
    assert records[-1].payload["action"] == "start"
    assert records[-1].payload["actor"] == "human-operator-001"


def test_emergency_stop_api_payloads_exclude_broker_secret_and_live_affordances(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_emergency_stop_service()
    client = TestClient(app)
    activated = client.post(
        "/api/emergency-stop/activate",
        json=_change_body(event_id="emergency-stop-activate-001"),
    )
    state = client.get("/api/emergency-stop")

    assert activated.status_code == 200
    assert state.status_code == 200
    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "approve_action",
        "approve_url",
        "authorization",
        "broker_host",
        "broker_port",
        "cancel_action",
        "cancel_url",
        "certificate",
        "connect_action",
        "connect_url",
        "credential",
        "host",
        "password",
        "place_order_url",
        "port",
        "private_key",
        "reject_action",
        "reject_url",
        "route",
        "secret",
        "socket",
        "submit_action",
        "submit_url",
        "token",
        "transmit",
        "transmit_url",
    }
    assert forbidden_keys.isdisjoint(
        _all_payload_keys(
            {
                "activated": activated.json(),
                "state": state.json(),
                "records": [record.to_json_dict() for record in emergency_stop_journal_records()],
            },
        ),
    )


def _change_body(**overrides: str) -> dict[str, str]:
    values = {
        "event_id": "emergency-stop-event-001",
        "requested_at": "2026-07-08T13:45:00Z",
        "actor": "human-operator-001",
        "reason": "operator_review",
    }
    values.update(overrides)
    return values


def _decision_body(**overrides: str) -> dict[str, str]:
    values = {
        "decision_id": "approval-decision-001",
        "decided_at": "2026-07-08T13:46:00Z",
        "actor": "human-operator-001",
        "decision_reference": "manual-simulation-approval-001",
        "reason": "operator_reviewed_simulation_ticket",
    }
    values.update(overrides)
    return values


def _approver_headers() -> dict[str, str]:
    return {
        "x-operator-id": "approver-operator-001",
        "x-operator-roles": "approver",
    }


def _workflow_body(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "workflow_id": "workflow-001",
        "display_name": "Opening breakout simulation",
        "description": "Validated visual simulation workflow",
        "requested_at": "2026-07-08T00:00:00Z",
        "document": _valid_workflow_dsl(),
    }
    values.update(overrides)
    return values


def _run_body(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "run_id": "workflow-run-001",
        "requested_at": "2026-07-08T13:29:55Z",
        "evaluated_at": "2026-07-08T13:45:10Z",
        "approval_expires_at": "2026-07-08T13:50:10Z",
        "replay_input_reference": "fixtures/replay/aapl-session.jsonl",
    }
    values.update(overrides)
    return values


def _valid_workflow_dsl() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "visual-simulation-workflow",
        "mode": "simulation",
        "runtime": "preview_only",
        "broker": "fake_broker_only",
        "nodes": [
            _workflow_node("replay-source", "replay_source"),
            _workflow_node("bar-builder", "bar_builder"),
            _workflow_node("strategy-trigger", "strategy_trigger"),
            _workflow_node("risk-check", "risk_check"),
            _workflow_node("approval-ticket", "approval_ticket"),
            _workflow_node("fake-broker", "fake_broker"),
            _workflow_node("position-update", "position_update"),
            _workflow_node("alert", "alert"),
            _workflow_node("audit-sink", "audit_sink"),
        ],
        "edges": [
            {"source": "replay-source", "target": "bar-builder"},
            {"source": "bar-builder", "target": "strategy-trigger"},
            {"source": "strategy-trigger", "target": "risk-check"},
            {"source": "risk-check", "target": "approval-ticket"},
            {"source": "approval-ticket", "target": "fake-broker"},
            {"source": "fake-broker", "target": "position-update"},
            {"source": "position-update", "target": "alert"},
            {"source": "alert", "target": "audit-sink"},
        ],
        "safety_gates": {
            "risk_check_required": True,
            "manual_approval_required": True,
            "audit_sink_required": True,
            "broker_transport_allowed": False,
            "live_trading_enabled": False,
            "arbitrary_code_allowed": False,
        },
    }


def _workflow_node(node_id: str, node_type: str) -> dict[str, object]:
    return {
        "id": node_id,
        "type": node_type,
        "required_for_risk_increasing_path": True,
    }


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
