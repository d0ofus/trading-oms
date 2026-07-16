from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import (
    app,
    reset_emergency_stop_service,
    reset_workflow_definition_service,
    reset_workflow_simulation_runner_service,
)
from trading_oms_backend.audit_export import (
    AuditExportError,
    build_audit_export_bundle,
    scan_for_unsafe_export_content,
    write_audit_export_bundle,
)
from trading_oms_backend.config import Settings
from trading_oms_backend.event_journal import JournalRecord
from trading_oms_backend.read_models import build_demo_operations_read_model
from trading_oms_backend.simulation_runs import SimulationRunRecord
from trading_oms_backend.workflow_definitions import WorkflowDefinitionRecord
from trading_oms_backend.workflow_simulation_runs import (
    WorkflowNodeRunStatus,
    WorkflowSimulationRunRecord,
)


@pytest.fixture
def audit_export_path() -> Iterator[Path]:
    root = Path(__file__).resolve().parents[1] / ".test-tmp"
    root.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=root) as temp_dir:
        yield Path(temp_dir) / "audit-export.json"


def test_audit_export_bundle_is_deterministic_and_references_review_records() -> None:
    operations = build_demo_operations_read_model(
        Settings(app_env="development", app_mode="simulation", live_trading_enabled=False)
    )
    bundle = build_audit_export_bundle(
        export_id="audit-export-001",
        generated_at="2026-07-08T13:46:00Z",
        review_reference="human-review-001",
        operations_read_model=operations,
        workflow_definitions=(_workflow_definition_record(),),
        workflow_simulation_runs=(_workflow_simulation_run_record(),),
        journal_records=(
            JournalRecord(
                sequence=10,
                event_type="alert.intent.created",
                timestamp="2026-07-08T13:45:10Z",
                payload={
                    "schema_version": 1,
                    "run_id": "workflow-run-001",
                    "symbol": "AAPL",
                    "order_id": "order-001",
                    "ticket_id": "ticket-001",
                    "severity": "critical",
                    "summary": "Protection review required",
                },
            ),
        ),
    )

    payload = bundle.to_json_dict()

    assert payload["schema_version"] == 1
    assert payload["bundle_type"] == "audit_review_bundle"
    assert payload["manifest"]["workflow_ids"] == ["workflow-001"]
    assert payload["manifest"]["run_ids"] == ["workflow-run-001"]
    assert payload["manifest"]["journal_references"] == ["journal_sequence:10"]
    assert payload["manifest"]["safety_scan"] == {"result": "passed", "finding_count": 0}
    assert payload["workflow_definitions"][0]["workflow_id"] == "workflow-001"
    assert payload["workflow_simulation_runs"][0]["run_id"] == "workflow-run-001"
    assert payload["journal_records"][0]["sequence"] == 10
    assert json.loads(bundle.to_stable_json()) == payload
    assert (
        bundle.to_stable_json()
        == build_audit_export_bundle(
            export_id="audit-export-001",
            generated_at="2026-07-08T13:46:00Z",
            review_reference="human-review-001",
            operations_read_model=operations,
            workflow_definitions=(_workflow_definition_record(),),
            workflow_simulation_runs=(_workflow_simulation_run_record(),),
            journal_records=(
                JournalRecord(
                    sequence=10,
                    event_type="alert.intent.created",
                    timestamp="2026-07-08T13:45:10Z",
                    payload={
                        "schema_version": 1,
                        "run_id": "workflow-run-001",
                        "symbol": "AAPL",
                        "order_id": "order-001",
                        "ticket_id": "ticket-001",
                        "severity": "critical",
                        "summary": "Protection review required",
                    },
                ),
            ),
        ).to_stable_json()
    )


def test_audit_export_bundle_rejects_secret_shapes_and_live_controls() -> None:
    unsafe_payloads = (
        {"api_key": "redacted"},
        {"summary": "token: redacted"},
        {"live_trading_enabled": True},
        {"broker_host": "127.0.0.1"},
        {"action": "transmit_order"},
    )

    for payload in unsafe_payloads:
        findings = scan_for_unsafe_export_content(payload)
        assert findings
        with pytest.raises(AuditExportError):
            build_audit_export_bundle(
                export_id="audit-export-001",
                generated_at="2026-07-08T13:46:00Z",
                review_reference="human-review-001",
                operations_read_model=build_demo_operations_read_model(),
                workflow_definitions=(),
                workflow_simulation_runs=(),
                journal_records=(
                    JournalRecord(
                        sequence=1,
                        event_type="unsafe.export",
                        timestamp="2026-07-08T13:45:10Z",
                        payload=payload,
                    ),
                ),
            )


def test_write_audit_export_bundle_writes_stable_json(audit_export_path: Path) -> None:
    bundle = build_audit_export_bundle(
        export_id="audit-export-001",
        generated_at="2026-07-08T13:46:00Z",
        review_reference="human-review-001",
        operations_read_model=build_demo_operations_read_model(),
        workflow_definitions=(),
        workflow_simulation_runs=(),
        journal_records=(),
    )
    write_audit_export_bundle(bundle, audit_export_path)

    assert audit_export_path.read_text(encoding="utf-8") == bundle.to_stable_json() + "\n"


def test_audit_export_api_returns_read_only_bundle_with_workflow_references(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_emergency_stop_service()
    reset_workflow_definition_service()
    reset_workflow_simulation_runner_service()
    client = TestClient(app)
    created = client.post("/api/workflows", json=_workflow_body())
    run = client.post("/api/workflows/workflow-001/simulation-runs", json=_run_body())

    response = client.get("/api/audit-export-bundle")

    assert created.status_code == 200
    assert run.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["bundle_type"] == "audit_review_bundle"
    assert payload["manifest"]["workflow_ids"] == ["workflow-001"]
    assert payload["manifest"]["run_ids"] == ["workflow-run-001"]
    assert payload["manifest"]["journal_references"]
    assert payload["manifest"]["safety_scan"]["result"] == "passed"
    assert "upload" not in json.dumps(payload).lower()
    assert 'live_trading_enabled": true' not in json.dumps(payload).lower()


def _workflow_definition_record() -> WorkflowDefinitionRecord:
    return WorkflowDefinitionRecord(
        workflow_id="workflow-001",
        display_name="Opening breakout simulation",
        description="Validated visual simulation workflow",
        version=1,
        created_at="2026-07-08T13:30:00Z",
        updated_at="2026-07-08T13:30:00Z",
        document=_valid_workflow_dsl(),
    )


def _workflow_simulation_run_record() -> WorkflowSimulationRunRecord:
    return WorkflowSimulationRunRecord(
        workflow_id="workflow-001",
        run_id="workflow-run-001",
        status="waiting_for_approval",
        created_at="2026-07-08T13:30:00Z",
        updated_at="2026-07-08T13:45:10Z",
        approval_ticket_id="ticket-001",
        simulation_run=SimulationRunRecord(
            run_id="workflow-run-001",
            status="completed",
            created_at="2026-07-08T13:30:00Z",
            updated_at="2026-07-08T13:45:10Z",
            replay_input_reference="fixtures/replay/aapl-session.jsonl",
            journal_references=("journal_sequence:1",),
        ),
        node_statuses=(
            WorkflowNodeRunStatus(
                node_id="approval-ticket",
                node_type="approval_ticket",
                status="waiting_for_approval",
                detail="Manual approval is required",
                journal_reference="journal_sequence:10",
            ),
        ),
        journal_references=("journal_sequence:10",),
    )


def _workflow_body() -> dict[str, object]:
    return {
        "workflow_id": "workflow-001",
        "display_name": "Opening breakout simulation",
        "description": "Validated visual simulation workflow",
        "requested_at": "2026-07-08T00:00:00Z",
        "document": _valid_workflow_dsl(),
    }


def _run_body() -> dict[str, object]:
    return {
        "expected_workflow_version": 1,
        "run_id": "workflow-run-001",
        "requested_at": "2026-07-08T13:29:55Z",
        "evaluated_at": "2026-07-08T13:45:10Z",
        "approval_expires_at": "2026-07-08T13:50:10Z",
        "replay_input_reference": "fixtures/replay/aapl-session.jsonl",
    }


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
    monkeypatch.setenv("APP_MODE", "simulation")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
