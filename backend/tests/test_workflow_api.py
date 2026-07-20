from __future__ import annotations

import inspect
import re
from typing import Any, cast

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend import app as app_module
from trading_oms_backend.app import app, reset_workflow_definition_service

FORBIDDEN_API_AFFORDANCE_KEYS = {
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


def test_workflow_api_creates_lists_loads_and_updates_safe_workflows(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    client = TestClient(app)

    created = client.post("/api/workflows", json=_workflow_body())
    listed = client.get("/api/workflows")
    loaded = client.get("/api/workflows/workflow-001")
    updated = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(
            description="Updated local visual workflow definition",
            requested_at="2026-07-08T00:05:00Z",
            expected_version=1,
        ),
    )

    assert created.status_code == 200
    assert listed.status_code == 200
    assert loaded.status_code == 200
    assert updated.status_code == 200
    assert created.json()["version"] == 1
    assert listed.json() == [created.json()]
    assert loaded.json() == created.json()
    assert updated.json()["version"] == 2
    assert updated.json()["description"] == "Updated local visual workflow definition"


def test_workflow_api_create_and_update_are_idempotent_for_identical_payloads(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    client = TestClient(app)

    first_create = client.post("/api/workflows", json=_workflow_body())
    second_create = client.post("/api/workflows", json=_workflow_body())
    first_update = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(
            description="Updated local visual workflow definition",
            requested_at="2026-07-08T00:05:00Z",
            expected_version=1,
        ),
    )
    second_update = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(
            description="Updated local visual workflow definition",
            requested_at="2026-07-08T00:05:00Z",
            expected_version=1,
        ),
    )

    assert first_create.status_code == 200
    assert second_create.status_code == 200
    assert second_create.json() == first_create.json()
    assert first_update.status_code == 200
    assert second_update.status_code == 200
    assert second_update.json() == first_update.json()


def test_workflow_api_enforces_update_versions_and_preserves_record_on_conflict(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    client = TestClient(app)

    create_with_version = client.post(
        "/api/workflows",
        json=_workflow_body(expected_version=1),
    )
    created = client.post("/api/workflows", json=_workflow_body())
    missing_version = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(description="Missing version"),
    )
    updated = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(
            description="Version two definition",
            requested_at="2026-07-08T00:05:00Z",
            expected_version=1,
        ),
    )
    repeated = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(
            description="Version two definition",
            requested_at="2026-07-08T00:05:00Z",
            expected_version=1,
        ),
    )
    stale = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(
            description="Stale conflicting edit",
            requested_at="2026-07-08T00:10:00Z",
            expected_version=1,
        ),
    )
    loaded = client.get("/api/workflows/workflow-001")

    assert create_with_version.status_code == 400
    assert "only valid for updates" in create_with_version.json()["detail"]
    assert created.status_code == 200
    assert missing_version.status_code == 400
    assert "expected_version is required" in missing_version.json()["detail"]
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert repeated.status_code == 200
    assert repeated.json() == updated.json()
    assert stale.status_code == 409
    assert "expected_version does not match" in stale.json()["detail"]
    assert loaded.json() == updated.json()


def test_workflow_api_rejects_unsafe_documents_and_unknown_workflows(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    client = TestClient(app)
    unsafe = _workflow_body()
    safety_gates = cast(dict[str, object], unsafe["document"]["safety_gates"])
    safety_gates["live_trading_enabled"] = True

    unsafe_response = client.post("/api/workflows", json=unsafe)
    unknown_response = client.get("/api/workflows/missing-workflow")
    mismatch_response = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(workflow_id="workflow-002"),
    )

    assert unsafe_response.status_code == 400
    assert "live_trading_enabled" in unsafe_response.json()["detail"]
    assert unknown_response.status_code == 404
    assert mismatch_response.status_code == 400
    assert "path workflow_id must match body" in mismatch_response.json()["detail"]


def test_workflow_api_rejects_extra_fields_and_non_integer_update_versions(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    client = TestClient(app)
    extra_field = _workflow_body()
    extra_field["token"] = "must-be-rejected"

    extra_response = client.post("/api/workflows", json=extra_field)
    client.post("/api/workflows", json=_workflow_body())
    bool_version = client.put(
        "/api/workflows/workflow-001",
        json=_workflow_body(expected_version=True),
    )

    assert extra_response.status_code == 422
    assert bool_version.status_code == 422


def test_workflow_api_requires_admin_permission_for_definition_mutations(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    client = TestClient(app)
    headers = {
        "x-operator-id": "viewer-operator-001",
        "x-operator-roles": "viewer",
    }

    created = client.post("/api/workflows", headers=headers, json=_workflow_body())
    updated = client.put(
        "/api/workflows/workflow-001",
        headers=headers,
        json=_workflow_body(
            description="Updated local visual workflow definition",
            requested_at="2026-07-08T00:05:00Z",
        ),
    )

    assert created.status_code == 403
    assert "administer_system" in created.json()["detail"]
    assert updated.status_code == 403
    assert "administer_system" in updated.json()["detail"]


def test_workflow_api_rejects_approver_for_definition_mutations(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    client = TestClient(app)
    headers = {
        "x-operator-id": "approver-operator-001",
        "x-operator-roles": "approver",
    }

    created = client.post("/api/workflows", headers=headers, json=_workflow_body())
    updated = client.put(
        "/api/workflows/workflow-001",
        headers=headers,
        json=_workflow_body(
            description="Updated local visual workflow definition",
            requested_at="2026-07-08T00:05:00Z",
        ),
    )

    assert created.status_code == 403
    assert "administer_system" in created.json()["detail"]
    assert updated.status_code == 403
    assert "administer_system" in updated.json()["detail"]


def test_workflow_api_does_not_expose_execution_delete_or_broker_secret_affordances(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_workflow_definition_service()
    client = TestClient(app)
    created = client.post("/api/workflows", json=_workflow_body())

    assert created.status_code == 200
    assert client.delete("/api/workflows/workflow-001").status_code == 405
    assert client.patch("/api/workflows/workflow-001").status_code == 405
    assert client.post("/api/workflows/workflow-001/run").status_code == 404
    assert FORBIDDEN_API_AFFORDANCE_KEYS.isdisjoint(_all_payload_keys(created.json()))


def test_app_module_limits_workflow_mutations_to_save_and_update_routes() -> None:
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
