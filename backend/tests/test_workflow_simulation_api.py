from __future__ import annotations

import inspect
import re
import sqlite3
from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend import app as app_module
from trading_oms_backend.app import (
    app,
    reconstruct_workflow_services,
    reset_emergency_stop_service,
    reset_workflow_definition_service,
    reset_workflow_simulation_runner_service,
)


def test_workflow_simulation_api_runs_saved_workflow_to_approval_wait(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)

    created = client.post("/api/workflows", json=_workflow_body())
    response = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(),
    )

    assert created.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_id"] == "workflow-001"
    assert payload["run_id"] == "workflow-run-001"
    assert payload["status"] == "waiting_for_approval"
    assert payload["approval_ticket_id"] == "workflow-run-001-approval-ticket"
    assert [node["status"] for node in payload["node_statuses"]] == [
        "completed",
        "completed",
        "completed",
        "passed",
        "waiting_for_approval",
        "blocked_waiting_for_approval",
        "blocked_waiting_for_approval",
        "blocked_waiting_for_approval",
        "completed",
    ]


def test_workflow_simulation_api_approves_persisted_run_and_recovers_after_restart(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())
    client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())

    approved = client.post(
        "/api/workflows/workflow-001/simulation-runs/workflow-run-001/approve",
        headers=_approver_headers(),
        json=_decision_body("approve"),
    )
    journal_count = len(app_module.get_workflow_simulation_runner().journal_records())
    reconstruct_workflow_services()
    recovered = client.get("/api/workflows/workflow-001/simulation-runs/workflow-run-001")
    retried = client.post(
        "/api/workflows/workflow-001/simulation-runs/workflow-run-001/approve",
        headers=_approver_headers(),
        json=_decision_body("approve"),
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved_not_executed"
    assert approved.json()["approval_decision"]["new_status"] == "approved"
    assert recovered.json() == approved.json()
    assert retried.json() == approved.json()
    assert len(app_module.get_workflow_simulation_runner().journal_records()) == journal_count


def test_workflow_simulation_api_executes_committed_approval_and_recovers_exact_retry(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())
    client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())
    approved = client.post(
        "/api/workflows/workflow-001/simulation-runs/workflow-run-001/approve",
        headers=_approver_headers(),
        json=_decision_body("approve"),
    )

    path = "/api/workflows/workflow-001/simulation-runs/workflow-run-001/execute"
    executed = client.post(path, json=_execution_body())
    journal_count = len(app_module.get_workflow_simulation_runner().journal_records())
    reconstruct_workflow_services()
    recovered = client.get("/api/workflows/workflow-001/simulation-runs/workflow-run-001")
    retried = client.post(path, json=_execution_body())

    assert approved.status_code == 200
    assert executed.status_code == 200
    payload = executed.json()
    assert payload["status"] == "executed"
    assert payload["execution"]["approval_decision_id"] == ("workflow-run-001-approve-decision")
    assert payload["execution"]["order_intent_id"] == "workflow-run-001-intent"
    assert payload["execution"]["risk_decision_id"] == "workflow-run-001-risk"
    assert payload["execution"]["order_id"] == "workflow-run-001-order"
    assert [item["new_state"] for item in payload["execution"]["oms_transitions"]] == [
        "APPROVED",
        "SUBMITTED",
        "ACKNOWLEDGED",
        "FILLED",
    ]
    assert [item["state"] for item in payload["execution"]["broker_transitions"]] == [
        "acknowledged",
        "filled",
    ]
    assert payload["execution"]["position"]["quantity"] == 10
    assert payload["execution"]["protection_status"] == "expected_protection_present"
    assert payload["execution"]["alert_dispatches"] == [
        {
            **payload["execution"]["alert_dispatches"][0],
            "channel": "local",
            "status": "recorded",
            "dispatcher": "noop",
        }
    ]
    assert recovered.json() == payload
    assert retried.json() == payload
    assert len(app_module.get_workflow_simulation_runner().journal_records()) == journal_count


def test_workflow_simulation_execution_requires_admin_committed_approval_and_matching_actor(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())
    client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())
    path = "/api/workflows/workflow-001/simulation-runs/workflow-run-001/execute"

    before_approval = client.post(path, json=_execution_body())
    client.post(
        "/api/workflows/workflow-001/simulation-runs/workflow-run-001/approve",
        headers=_approver_headers(),
        json=_decision_body("approve"),
    )
    approver = client.post(path, headers=_approver_headers(), json=_execution_body())
    actor_mismatch = client.post(path, json=_execution_body(actor="other-admin"))

    assert before_approval.status_code == 409
    assert approver.status_code == 403
    assert "administer_system" in approver.json()["detail"]
    assert actor_mismatch.status_code == 400
    loaded = client.get("/api/workflows/workflow-001/simulation-runs/workflow-run-001")
    assert loaded.json()["status"] == "approved_not_executed"
    assert loaded.json()["execution"] is None
    assert any(
        record.event_type == "workflow_simulation.execution_blocked"
        and record.payload["reason"] == "actor_mismatch"
        for record in app_module.get_workflow_simulation_runner().journal_records()
    )


def test_workflow_simulation_execution_maps_emergency_and_unknown_state_fail_closed(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())
    client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())
    client.post(
        "/api/workflows/workflow-001/simulation-runs/workflow-run-001/approve",
        headers=_approver_headers(),
        json=_decision_body("approve"),
    )
    path = "/api/workflows/workflow-001/simulation-runs/workflow-run-001/execute"

    unknown_state = client.post(path, json=_execution_body(broker_state_known=False))
    activated = client.post(
        "/api/emergency-stop/activate",
        json={
            "event_id": "execution-stop-001",
            "requested_at": "2026-07-08T13:46:30Z",
            "actor": "human-operator-001",
            "reason": "operator_safety_hold",
        },
    )
    stopped = client.post(path, json=_execution_body())

    assert unknown_state.status_code == 400
    assert "unknown simulated broker state" in unknown_state.json()["detail"]
    assert activated.status_code == 200
    assert stopped.status_code == 423
    loaded = client.get("/api/workflows/workflow-001/simulation-runs/workflow-run-001")
    assert loaded.json()["status"] == "approved_not_executed"
    assert loaded.json()["execution"] is None


def test_workflow_simulation_api_requires_separate_approver_and_matching_actor(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())
    client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())
    path = "/api/workflows/workflow-001/simulation-runs/workflow-run-001/approve"

    admin = client.post(path, json=_decision_body("approve"))
    mismatched_actor = client.post(
        path,
        headers=_approver_headers(),
        json=_decision_body("approve", actor="other-operator"),
    )

    assert admin.status_code == 403
    assert mismatched_actor.status_code == 400
    loaded = client.get("/api/workflows/workflow-001/simulation-runs/workflow-run-001")
    assert loaded.json()["status"] == "waiting_for_approval"


def test_workflow_simulation_decision_api_rejects_unknown_run(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)

    response = client.post(
        "/api/workflows/workflow-001/simulation-runs/missing-run/approve",
        headers=_approver_headers(),
        json=_decision_body(
            "approve",
            approval_ticket_id="missing-run-approval-ticket",
            decision_id="missing-run-approve-decision",
            decision_reference="missing-run-approve-manual-review",
        ),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "unknown workflow simulation run"}


def test_workflow_simulation_api_is_idempotent_for_same_run_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())

    first = client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())
    second = client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()


def test_workflow_simulation_api_rejects_stale_workflow_version_with_conflict(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())
    updated = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(
            display_name="Opening breakout simulation version two",
            requested_at="2026-07-08T00:01:00Z",
            expected_version=1,
        ),
    )

    response = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(expected_workflow_version=1),
    )
    listed = client.get("/api/workflows/workflow-001/simulation-runs")

    assert updated.status_code == 200
    assert response.status_code == 409
    assert listed.status_code == 200
    assert listed.json() == []


def test_workflow_simulation_api_requires_strict_expected_workflow_version(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())

    missing = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json={
            key: value for key, value in _run_body().items() if key != "expected_workflow_version"
        },
    )
    loose = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(expected_workflow_version="1"),
    )
    extra = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json={**_run_body(), "unexpected": "field"},
    )
    unapproved_replay = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(replay_input_reference="fixtures/replay/other.jsonl"),
    )

    assert missing.status_code == 422
    assert loose.status_code == 422
    assert extra.status_code == 422
    assert unapproved_replay.status_code == 400


def test_workflow_simulation_api_lists_and_loads_run_inspection_records(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())

    created = client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())
    listed = client.get("/api/workflows/workflow-001/simulation-runs")
    loaded = client.get("/api/workflows/workflow-001/simulation-runs/workflow-run-001")
    missing = client.get("/api/workflows/workflow-001/simulation-runs/missing-run")

    assert created.status_code == 200
    assert listed.status_code == 200
    assert listed.json() == [created.json()]
    assert loaded.status_code == 200
    assert loaded.json() == created.json()
    assert missing.status_code == 404


def test_workflow_simulation_api_recovers_list_get_and_exact_retry_after_reconstruction(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())
    created = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(),
    )
    journal_count = len(app_module.get_workflow_simulation_runner().journal_records())

    reconstruct_workflow_services()

    listed = client.get("/api/workflows/workflow-001/simulation-runs")
    loaded = client.get("/api/workflows/workflow-001/simulation-runs/workflow-run-001")
    retried = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(),
    )

    assert created.status_code == 200
    assert listed.status_code == 200
    assert listed.json() == [created.json()]
    assert loaded.status_code == 200
    assert loaded.json() == created.json()
    assert retried.status_code == 200
    assert retried.json() == created.json()
    assert len(app_module.get_workflow_simulation_runner().journal_records()) == journal_count


def test_workflow_simulation_api_hides_corrupt_persistence_details(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())
    created = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(),
    )
    connection = sqlite3.connect(app_module._workflow_simulation_database_path())
    try:
        connection.execute("UPDATE workflow_simulation_run_evidence SET record_json = 'not-json'")
        connection.commit()
    finally:
        connection.close()

    reconstruct_workflow_services()
    listed = client.get("/api/workflows/workflow-001/simulation-runs")
    loaded = client.get("/api/workflows/workflow-001/simulation-runs/workflow-run-001")
    retried = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(),
    )

    assert created.status_code == 200
    for response in (listed, loaded, retried):
        assert response.status_code == 503
        assert response.json() == {"detail": "workflow simulation evidence is unavailable"}
        response_text = response.text.lower()
        assert "sqlite" not in response_text
        assert "record_json" not in response_text
        assert str(app_module._workflow_simulation_database_path()).lower() not in response_text


def test_workflow_simulation_api_rejects_unknown_or_conflicting_runs(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())

    unknown = client.post("/api/workflows/missing-workflow/simulation-runs", json=_run_body())
    first = client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())
    conflicting = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        json=_run_body(evaluated_at="2026-07-08T13:46:00Z"),
    )

    assert unknown.status_code == 404
    assert first.status_code == 200
    assert conflicting.status_code == 400
    assert "conflicting run_id" in conflicting.json()["detail"]


def test_workflow_simulation_api_requires_admin_permission_for_run_start(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())

    response = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        headers={
            "x-operator-id": "viewer-operator-001",
            "x-operator-roles": "viewer",
        },
        json=_run_body(),
    )

    assert response.status_code == 403
    assert "administer_system" in response.json()["detail"]


def test_workflow_simulation_api_rejects_approver_for_run_start(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())

    response = client.post(
        "/api/workflows/workflow-001/simulation-runs",
        headers={
            "x-operator-id": "approver-operator-001",
            "x-operator-roles": "approver",
        },
        json=_run_body(),
    )

    assert response.status_code == 403
    assert "administer_system" in response.json()["detail"]


def test_workflow_simulation_api_response_excludes_broker_secret_and_execution_affordances(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    client.post("/api/workflows", json=_workflow_body())

    response = client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())

    assert response.status_code == 200
    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker_host",
        "broker_port",
        "credential",
        "host",
        "password",
        "port",
        "private_key",
        "route",
        "secret",
        "socket",
        "submit",
        "token",
        "transmit",
    }
    assert forbidden_keys.isdisjoint(_all_payload_keys(response.json()))


def test_app_module_allows_only_known_simulation_mutation_routes() -> None:
    source = inspect.getsource(app_module).lower()

    post_routes = set(re.findall(r'@app\.post\("([^"]+)"', source))
    put_routes = set(re.findall(r'@app\.put\("([^"]+)"', source))
    assert post_routes == {
        "/api/approval-tickets/{ticket_id}/approve",
        "/api/approval-tickets/{ticket_id}/reject",
        "/api/emergency-stop/activate",
        "/api/emergency-stop/deactivate",
        "/api/workflows",
        "/api/workflows/{workflow_id}/simulation-runs",
        "/api/workflows/{workflow_id}/simulation-runs/{run_id}/approve",
        "/api/workflows/{workflow_id}/simulation-runs/{run_id}/execute",
        "/api/workflows/{workflow_id}/simulation-runs/{run_id}/reject",
    }
    assert put_routes == {"/api/workflows/{workflow_id}"}

    forbidden_source_tokens = [
        "@app.patch",
        "@app.delete",
        "import socket",
        "from socket",
        "httpx",
        "requests",
        "ibapi",
        "ib_insync",
        "open_connection",
        "create_connection",
        "place_order",
        "submit_order",
        "transmit_order",
    ]
    for token in forbidden_source_tokens:
        assert token not in source


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
        "expected_workflow_version": 1,
        "run_id": "workflow-run-001",
        "requested_at": "2026-07-08T13:29:55Z",
        "evaluated_at": "2026-07-08T13:45:10Z",
        "approval_expires_at": "2026-07-08T13:50:10Z",
        "replay_input_reference": "fixtures/replay/aapl-session.jsonl",
    }
    values.update(overrides)
    return values


def _decision_body(action: str, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "schema_version": 1,
        "expected_workflow_version": 1,
        "approval_ticket_id": "workflow-run-001-approval-ticket",
        "decision_id": f"workflow-run-001-{action}-decision",
        "decided_at": "2026-07-08T13:46:00Z",
        "actor": "approver-operator-001",
        "decision_reference": f"workflow-run-001-{action}-manual-review",
        "reason": "operator_reviewed_simulation_evidence",
    }
    values.update(overrides)
    return values


def _execution_body(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "schema_version": 1,
        "expected_workflow_version": 1,
        "approval_ticket_id": "workflow-run-001-approval-ticket",
        "approval_decision_id": "workflow-run-001-approve-decision",
        "order_intent_id": "workflow-run-001-intent",
        "risk_decision_id": "workflow-run-001-risk",
        "order_id": "workflow-run-001-order",
        "execution_id": "workflow-run-001-execution",
        "executed_at": "2026-07-08T13:47:00Z",
        "actor": "human-operator-001",
        "execution_reference": "workflow-run-001-admin-execution-review",
        "reason": "operator_confirmed_simulation_execution",
        "broker_state_known": True,
        "expected_protection_present": True,
    }
    values.update(overrides)
    return values


def _approver_headers() -> dict[str, str]:
    return {
        "x-operator-id": "approver-operator-001",
        "x-operator-roles": "approver",
    }


def _valid_workflow_dsl() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "visual-simulation-workflow",
        "mode": "simulation",
        "runtime": "preview_only",
        "broker": "fake_broker_only",
        "nodes": [
            {
                "id": "replay-source",
                "type": "replay_source",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "bar-builder",
                "type": "bar_builder",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "strategy-trigger",
                "type": "strategy_trigger",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "risk-check",
                "type": "risk_check",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "approval-ticket",
                "type": "approval_ticket",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "fake-broker",
                "type": "fake_broker",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "position-update",
                "type": "position_update",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "alert",
                "type": "alert",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "audit-sink",
                "type": "audit_sink",
                "required_for_risk_increasing_path": True,
            },
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
