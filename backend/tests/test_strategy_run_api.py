from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from test_workflow_dsl_v2 import valid_v2_workflow

from trading_oms_backend import typed_strategy_api
from trading_oms_backend.app import (
    app,
    reset_emergency_stop_service,
    reset_workflow_definition_service,
)


def test_v2_catalog_validation_dataset_and_run_lifecycle(monkeypatch: MonkeyPatch) -> None:
    _reset(monkeypatch)
    client = TestClient(app)
    author = _headers("strategy-author-001", "strategy_author")
    operator = _headers("strategy-operator-001", "strategy_operator")
    viewer = _headers("viewer-operator-001", "viewer")

    catalog = client.get("/api/typed-workflows/catalog", headers=viewer)
    validation = client.post(
        "/api/typed-workflows/first-five-minute-breakout/validate",
        headers=author,
        json={"document": valid_v2_workflow()},
    )
    workflow = client.post("/api/typed-workflows", headers=author, json=_workflow_body())
    dataset = client.post(
        "/api/strategy-datasets",
        headers=operator,
        json=_dataset_body(),
    )
    unsafe_dataset_body = _dataset_body()
    unsafe_dataset_body["transmit"] = True
    unsafe_dataset = client.post(
        "/api/strategy-datasets",
        headers=operator,
        json=unsafe_dataset_body,
    )
    draft = client.post(
        "/api/typed-workflows/first-five-minute-breakout/runs",
        headers=operator,
        json=_draft_body(),
    )
    viewer_arm = client.post(
        "/api/strategy-runs/strategy-run-001/arm",
        headers=viewer,
        json={
            "authorized_at": "2026-07-08T13:00:00Z",
            "expires_at": "2026-07-08T20:00:00Z",
        },
    )
    armed = client.post(
        "/api/strategy-runs/strategy-run-001/arm",
        headers=operator,
        json={
            "authorized_at": "2026-07-08T13:00:00Z",
            "expires_at": "2026-07-08T20:00:00Z",
        },
    )
    simulated = client.post(
        "/api/strategy-runs/strategy-run-001/simulate",
        headers=operator,
        json={
            "buying_power": "50000.00",
            "reconciled": True,
            "concurrent_positions": 0,
            "current_symbol_exposure": "0.00",
            "daily_realized_loss": "0.00",
        },
    )
    loaded = client.get("/api/strategy-runs/strategy-run-001", headers=viewer)
    events = client.get("/api/strategy-runs/strategy-run-001/events", headers=viewer)
    policy = client.get("/api/strategy-risk-policy", headers=viewer)

    assert catalog.status_code == 200
    assert "opening_range_high" in [node["type"] for node in catalog.json()["nodes"]]
    assert validation.status_code == 200
    assert validation.json()["status"] == "valid"
    assert len(validation.json()["checksum"]) == 64
    assert workflow.status_code == 200
    assert workflow.json()["schema_version"] == 2
    assert workflow.json()["version"] == 1
    assert dataset.status_code == 200
    assert unsafe_dataset.status_code == 422
    assert dataset.json()["resolution"] == "trade_ticks"
    assert draft.status_code == 200
    assert draft.json()["state"] == "draft"
    assert draft.json()["envelope"]["maximum_dollar_loss"] == "100.00"
    assert viewer_arm.status_code == 403
    assert "operate_strategy" in viewer_arm.json()["detail"]
    assert armed.status_code == 200
    assert armed.json()["state"] == "armed"
    assert simulated.status_code == 200
    assert simulated.json()["state"] == "completed"
    assert simulated.json()["result"]["shares"] == "64"
    assert simulated.json()["result"]["simulated"] is True
    assert loaded.json() == simulated.json()
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "workflow.risk.passed" in events.text
    assert "workflow.order.filled" in events.text
    assert policy.status_code == 200
    assert policy.json()["mutable_through_run_request"] is False
    assert client.post("/api/strategy-risk-policy", headers=operator, json={}).status_code == 405


def test_workflow_edit_disarms_armed_run_and_author_cannot_arm(
    monkeypatch: MonkeyPatch,
) -> None:
    _reset(monkeypatch)
    client = TestClient(app)
    author = _headers("strategy-author-001", "strategy_author")
    operator = _headers("strategy-operator-001", "strategy_operator")
    client.post("/api/typed-workflows", headers=author, json=_workflow_body())
    client.post("/api/strategy-datasets", headers=operator, json=_dataset_body())
    client.post(
        "/api/typed-workflows/first-five-minute-breakout/runs",
        headers=operator,
        json=_draft_body(),
    )
    client.post(
        "/api/strategy-runs/strategy-run-001/arm",
        headers=operator,
        json={
            "authorized_at": "2026-07-08T13:00:00Z",
            "expires_at": "2026-07-08T20:00:00Z",
        },
    )

    author_arm = client.post(
        "/api/strategy-runs/strategy-run-001/arm",
        headers=author,
        json={
            "authorized_at": "2026-07-08T13:00:01Z",
            "expires_at": "2026-07-08T20:00:00Z",
        },
    )
    edited_document = valid_v2_workflow()
    edited_document["nodes"][4]["config"] = {"minutes": 1}
    edited = client.put(
        "/api/typed-workflows/first-five-minute-breakout",
        headers=author,
        json=_workflow_body(
            document=edited_document,
            requested_at="2026-07-08T13:01:00Z",
            expected_version=1,
        ),
    )
    loaded = client.get(
        "/api/strategy-runs/strategy-run-001",
        headers=_headers("viewer-operator-001", "viewer"),
    )
    versions = client.get(
        "/api/typed-workflows/first-five-minute-breakout/versions",
        headers=_headers("viewer-operator-001", "viewer"),
    )

    assert author_arm.status_code == 403
    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert loaded.json()["state"] == "disarmed"
    assert loaded.json()["disarm_reason"] == "workflow_version_changed"
    assert [item["version"] for item in versions.json()] == [1, 2]


def test_emergency_stop_activation_disarms_an_armed_strategy_run(
    monkeypatch: MonkeyPatch,
) -> None:
    _reset(monkeypatch)
    client = TestClient(app)
    client.post(
        "/api/typed-workflows",
        headers=_headers("strategy-author-001", "strategy_author"),
        json=_workflow_body(),
    )
    client.post(
        "/api/strategy-datasets",
        headers=_headers("strategy-operator-001", "strategy_operator"),
        json=_dataset_body(),
    )
    client.post(
        "/api/typed-workflows/first-five-minute-breakout/runs",
        headers=_headers("strategy-operator-001", "strategy_operator"),
        json=_draft_body(),
    )
    client.post(
        "/api/strategy-runs/strategy-run-001/arm",
        headers=_headers("strategy-operator-001", "strategy_operator"),
        json={
            "authorized_at": "2026-07-08T13:00:00Z",
            "expires_at": "2026-07-08T20:00:00Z",
        },
    )

    activated = client.post(
        "/api/emergency-stop/activate",
        headers=_headers("admin-operator-001", "admin"),
        json={
            "schema_version": 1,
            "event_id": "strategy-emergency-stop-001",
            "requested_at": "2026-07-08T13:01:00Z",
            "actor": "admin-operator-001",
            "reason": "strategy_runtime_review",
        },
    )
    loaded = client.get(
        "/api/strategy-runs/strategy-run-001",
        headers=_headers("viewer-operator-001", "viewer"),
    )

    assert activated.status_code == 200
    assert loaded.json()["state"] == "disarmed"
    assert loaded.json()["disarm_reason"] == "emergency_stop_activated"


def _workflow_body(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "schema_version": 2,
        "workflow_id": "first-five-minute-breakout",
        "display_name": "First five minute breakout",
        "description": "Typed deterministic simulation workflow",
        "requested_at": "2026-07-08T12:00:00Z",
        "document": valid_v2_workflow(),
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("reason", ["expired", "unknown_reconciliation"])
def test_api_uses_server_time_and_requires_reconciliation(
    monkeypatch: MonkeyPatch, reason: str
) -> None:
    client, operator = _armed_client(monkeypatch)
    if reason == "expired":
        monkeypatch.setattr(typed_strategy_api, "_utc_now", lambda: "2026-07-08T20:00:00Z")
    body = {
        "buying_power": "50000.00",
        "concurrent_positions": 0,
        "current_symbol_exposure": "0.00",
        "daily_realized_loss": "0.00",
        "evaluated_at": "2026-07-08T13:00:00Z",
    }
    if reason == "expired":
        body["reconciled"] = True
    response = client.post(
        "/api/strategy-runs/strategy-run-001/simulate", headers=operator, json=body
    )
    assert response.status_code == 400
    assert not any(
        event.event_type == "workflow.order.filled"
        for event in typed_strategy_api.get_strategy_run_service().journal_records()
    )


def test_admin_cannot_arm_and_unavailable_evidence_is_generic(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    client, _ = _armed_client(monkeypatch)
    response = client.post(
        "/api/strategy-runs/strategy-run-001/arm",
        headers=_headers("admin-operator-001", "admin"),
        json={"authorized_at": "2026-07-08T13:00:00Z", "expires_at": "2026-07-08T20:00:00Z"},
    )
    assert response.status_code == 403
    (tmp_path / "strategy-run-journal.jsonl").write_text("", encoding="utf-8")
    response = client.get(
        "/api/strategy-runs/strategy-run-001", headers=_headers("viewer-operator-001", "viewer")
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "strategy run evidence unavailable"}


def test_reconciliation_requires_an_explicit_boolean(monkeypatch: MonkeyPatch) -> None:
    client, operator = _armed_client(monkeypatch)
    response = client.post(
        "/api/strategy-runs/strategy-run-001/simulate",
        headers=operator,
        json={
            "buying_power": "50000.00",
            "concurrent_positions": 0,
            "current_symbol_exposure": "0.00",
            "daily_realized_loss": "0.00",
            "reconciled": "true",
        },
    )
    assert response.status_code == 422
    assert (
        typed_strategy_api.get_strategy_run_service().get_run("strategy-run-001").state == "armed"
    )


def _armed_client(monkeypatch: MonkeyPatch) -> tuple[TestClient, dict[str, str]]:
    _reset(monkeypatch)
    client = TestClient(app)
    operator = _headers("strategy-operator-001", "strategy_operator")
    assert (
        client.post(
            "/api/typed-workflows",
            headers=_headers("strategy-author-001", "strategy_author"),
            json=_workflow_body(),
        ).status_code
        == 200
    )
    assert (
        client.post("/api/strategy-datasets", headers=operator, json=_dataset_body()).status_code
        == 200
    )
    assert (
        client.post(
            "/api/typed-workflows/first-five-minute-breakout/runs",
            headers=operator,
            json=_draft_body(),
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/strategy-runs/strategy-run-001/arm",
            headers=operator,
            json={"authorized_at": "2026-07-08T13:00:00Z", "expires_at": "2026-07-08T20:00:00Z"},
        ).status_code
        == 200
    )
    return client, operator


def _dataset_body() -> dict[str, Any]:
    return {
        "dataset_id": "dataset-aapl-2026-07-08",
        "symbol": "AAPL",
        "contract_id": "fixture-contract-aapl",
        "primary_exchange": "NASDAQ",
        "currency": "USD",
        "routing": "SMART",
        "min_tick": "0.01",
        "session_date": "2026-07-08",
        "session_timezone": "America/New_York",
        "rth_open": "09:30:00",
        "rth_close": "16:00:00",
        "source": "local_fixture",
        "resolution": "trade_ticks",
        "complete": True,
        "quality": "complete",
        "registered_at": "2026-07-08T12:30:00Z",
        "trades": [
            {"timestamp": "2026-07-08T13:30:00Z", "price": "99.50", "sequence": 1},
            {"timestamp": "2026-07-08T13:34:59Z", "price": "101.00", "sequence": 2},
            {"timestamp": "2026-07-08T13:35:01Z", "price": "101.01", "sequence": 3},
            {"timestamp": "2026-07-08T13:35:02Z", "price": "101.03", "sequence": 4},
            {"timestamp": "2026-07-08T13:35:03Z", "price": "101.04", "sequence": 5},
        ],
    }


def _draft_body() -> dict[str, Any]:
    return {
        "run_id": "strategy-run-001",
        "workflow_version": 1,
        "symbol": "AAPL",
        "maximum_dollar_loss": "100.00",
        "runtime_mode": "historical_simulation",
        "dataset_id": "dataset-aapl-2026-07-08",
        "expires_at": "2026-07-08T20:00:00Z",
        "requested_at": "2026-07-08T12:45:00Z",
    }


def _headers(operator_id: str, role: str) -> dict[str, str]:
    return {"x-operator-id": operator_id, "x-operator-roles": role}


def _reset(monkeypatch: MonkeyPatch) -> None:
    for key in (
        "APP_ENV",
        "APP_MODE",
        "LIVE_TRADING_ENABLED",
        "IBKR_ACCOUNT_MODE",
        "IBKR_HOST",
        "IBKR_PORT",
        "TRADING_OMS_STATE_DIRECTORY",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_workflow_definition_service()
    reset_emergency_stop_service()


@pytest.fixture(autouse=True)
def isolated_typed_state(tmp_path: Path, monkeypatch: MonkeyPatch):
    monkeypatch.setenv("TRADING_OMS_TYPED_STATE_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(typed_strategy_api, "_utc_now", lambda: "2026-07-08T13:00:00Z")
