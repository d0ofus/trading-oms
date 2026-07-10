from __future__ import annotations

import inspect
import re
from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend import app as app_module
from trading_oms_backend.app import (
    app,
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
