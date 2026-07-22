from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend import app as app_module
from trading_oms_backend.app import app
from trading_oms_backend.config import Settings
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.local_persistence import LocalSqlitePersistenceStore
from trading_oms_backend.read_models import build_demo_operations_read_model
from trading_oms_backend.simulation_execution_projections import (
    SimulationExecutionProjectionError,
    project_simulation_executions,
)
from trading_oms_backend.workflow_definitions import (
    WorkflowDefinitionSaveRequest,
    WorkflowDefinitionStore,
)
from trading_oms_backend.workflow_simulation_runs import (
    WorkflowSimulationDecisionRequest,
    WorkflowSimulationExecutionRequest,
    WorkflowSimulationRunner,
    WorkflowSimulationRunRequest,
    WorkflowSimulationRunUnavailableError,
)


def test_projects_protected_execution_with_exact_durable_attribution(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _execute(runner, "workflow-a", "run-a", expected_protection_present=True)

    projected = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        runner.list_projection_sources(),
    )

    assert len(projected.orders) == len(projected.positions) == len(projected.alerts) == 1
    order = projected.orders[0]
    position = projected.positions[0]
    alert = projected.alerts[0]
    assert order.state == "FILLED"
    assert order.cumulative_filled_quantity == order.quantity
    assert order.leaves_quantity == 0
    assert position.protection_status == "expected_protection_present"
    assert position.source == "durable_saved_workflow_simulation"
    assert alert.severity == "informational"
    assert alert.channel == "local"
    assert alert.status == "recorded"

    attribution = order.execution_attribution
    assert attribution is not None
    assert attribution == position.execution_attribution == alert.execution_attribution
    assert attribution.workflow_id == "workflow-a"
    assert attribution.workflow_version == 1
    assert attribution.run_id == "run-a"
    assert attribution.execution_id == "run-a-execution"
    assert attribution.order_intent_id == "run-a-intent"
    assert attribution.risk_decision_id == "run-a-risk"
    assert attribution.approval_ticket_id == "run-a-approval-ticket"
    assert attribution.approval_decision_id == "run-a-approved-decision"
    assert attribution.order_id == "run-a-order"
    assert attribution.fill_reference == "fake-run-a-client"
    assert attribution.position_id == position.position_id
    assert attribution.protection_status == "expected_protection_present"
    assert attribution.alert_id == alert.alert_id
    assert attribution.evidence_source == "schema_v4_sqlite_digest_bound_jsonl"
    assert attribution.classifications == (
        "simulated",
        "local_only",
        "fake_broker_derived",
        "externally_unverified",
    )
    assert attribution.broker_derived is False
    assert attribution.externally_verified is False
    assert attribution.journal_references
    assert all(item.startswith("journal_sequence:") for item in attribution.journal_references)

    assert projected.audit_events
    assert tuple(event.sequence for event in projected.audit_events) == tuple(
        sorted(event.sequence for event in projected.audit_events)
    )
    assert all(event.execution_attribution == attribution for event in projected.audit_events)
    assert {event.event_type for event in projected.audit_events}.issuperset(
        {
            "risk.decision.evaluated",
            "approval.ticket.created",
            "approval.ticket.decided",
            "oms.order.transitioned",
            "fake_broker.order.transitioned",
            "position.updated",
            "alert.intent.created",
            "alert.dispatch.recorded",
            "workflow_simulation.execution_completed",
        }
    )
    for resource in ("orders", "positions", "alerts", "audit_events"):
        provenance = projected.provenance_for(resource)
        assert provenance.source == "durable_saved_workflow_simulation_execution"
        assert provenance.classifications == attribution.classifications
        assert provenance.broker_derived is False
        assert provenance.externally_verified is False


def test_projects_missing_protection_as_critical_and_orders_runs_deterministically(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    _execute(runner, "workflow-b", "run-b", expected_protection_present=False, minute=2)
    _execute(runner, "workflow-a", "run-a", expected_protection_present=True, minute=1)

    first = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        runner.list_projection_sources(),
    )
    second = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        runner.list_projection_sources(),
    )

    assert first.to_json_dict() == second.to_json_dict()
    assert [item.execution_attribution.run_id for item in first.orders] == ["run-a", "run-b"]
    missing = next(
        item for item in first.positions if item.protection_status == "missing_expected_protection"
    )
    assert missing.execution_attribution is not None
    assert missing.execution_attribution.protection_status == "missing_expected_protection"
    critical = next(
        item for item in first.alerts if item.execution_attribution == missing.execution_attribution
    )
    assert critical.severity == "critical"


def test_restart_recovery_and_repeated_projection_are_read_only(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _execute(runner, "workflow-a", "run-a", expected_protection_present=True)
    journal_count = len(runner.journal_records())

    restarted = _runner(tmp_path, create_workflows=False)
    first = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        restarted.list_projection_sources(),
    )
    second = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        restarted.list_projection_sources(),
    )

    assert first.to_json_dict() == second.to_json_dict()
    assert len(restarted.journal_records()) == journal_count


def test_no_execution_keeps_representative_records_visibly_separate(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    base = build_demo_operations_read_model(Settings())

    projected = project_simulation_executions(base, runner.list_projection_sources())

    assert projected == base
    assert projected.orders[0].execution_attribution is None
    assert "representative" in projected.provenance_for("orders").classifications


def test_duplicate_projection_identity_is_rejected(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _execute(runner, "workflow-a", "run-a", expected_protection_present=True)
    source = runner.list_projection_sources()[0]

    with pytest.raises(SimulationExecutionProjectionError, match="duplicate"):
        project_simulation_executions(
            build_demo_operations_read_model(Settings()),
            (source, source),
        )


def test_corrupt_manifest_fails_before_any_projection_is_returned(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _execute(runner, "workflow-a", "run-a", expected_protection_present=True)
    database_path = tmp_path / "state.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE workflow_simulation_run_evidence "
            "SET journal_manifest_sha256 = ? WHERE run_id = ?",
            ("0" * 64, "run-a"),
        )

    with pytest.raises(WorkflowSimulationRunUnavailableError, match="unavailable"):
        runner.list_projection_sources()


def test_execution_read_apis_return_one_durable_projection_snapshot(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = _runner(tmp_path)
    _execute(runner, "workflow-a", "run-a", expected_protection_present=False)
    monkeypatch.setattr(app_module, "get_workflow_simulation_runner", lambda: runner)
    client = TestClient(app)

    responses = {
        resource: client.get(path)
        for resource, path in {
            "audit_events": "/api/audit-events",
            "orders": "/api/orders",
            "positions": "/api/positions",
            "alerts": "/api/alerts",
        }.items()
    }

    assert all(response.status_code == 200 for response in responses.values())
    for resource, response in responses.items():
        payload = response.json()
        assert payload["resource"] == resource
        assert payload["provenance"]["classifications"] == [
            "simulated",
            "local_only",
            "fake_broker_derived",
            "externally_unverified",
        ]
        assert payload["data"]
        assert all(item["execution_attribution"]["run_id"] == "run-a" for item in payload["data"])
    assert responses["positions"].json()["data"][0]["protection_status"] == (
        "missing_expected_protection"
    )
    assert responses["alerts"].json()["data"][0]["severity"] == "critical"


def test_corrupt_execution_read_apis_return_generic_503_without_partial_data(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = _runner(tmp_path)
    _execute(runner, "workflow-a", "run-a", expected_protection_present=True)
    with sqlite3.connect(tmp_path / "state.sqlite3") as connection:
        connection.execute(
            "UPDATE workflow_simulation_run_evidence "
            "SET execution_record_json = ? WHERE run_id = ?",
            ("{}", "run-a"),
        )
    monkeypatch.setattr(app_module, "get_workflow_simulation_runner", lambda: runner)
    client = TestClient(app)

    for path in ("/api/audit-events", "/api/orders", "/api/positions", "/api/alerts"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json() == {"detail": "simulation execution read evidence is unavailable"}
        assert "run-a" not in response.text
        assert "sqlite" not in response.text.lower()
    assert client.get("/api/safety").status_code == 200


def _runner(tmp_path: Path, *, create_workflows: bool = True) -> WorkflowSimulationRunner:
    store = WorkflowDefinitionStore(tmp_path / "workflows.json")
    if create_workflows:
        for workflow_id in ("workflow-a", "workflow-b"):
            store.create_workflow(
                WorkflowDefinitionSaveRequest(
                    workflow_id=workflow_id,
                    display_name=f"{workflow_id} simulation",
                    description="Validated local simulation workflow",
                    document=_valid_workflow_dsl(),
                    requested_at="2026-07-08T00:00:00Z",
                )
            )
    return WorkflowSimulationRunner(
        store,
        JsonlEventJournal(tmp_path / "journal.jsonl"),
        persistence_store=LocalSqlitePersistenceStore(tmp_path / "state.sqlite3"),
    )


def _execute(
    runner: WorkflowSimulationRunner,
    workflow_id: str,
    run_id: str,
    *,
    expected_protection_present: bool,
    minute: int = 1,
) -> None:
    prefix = f"2026-07-08T13:{minute:02d}"
    runner.start_run(
        workflow_id,
        WorkflowSimulationRunRequest(
            expected_workflow_version=1,
            run_id=run_id,
            requested_at=f"{prefix}:00Z",
            evaluated_at=f"{prefix}:10Z",
            approval_expires_at=f"{prefix}:50Z",
            replay_input_reference="fixtures/replay/aapl-session.jsonl",
        ),
    )
    runner.apply_decision(
        workflow_id,
        run_id,
        WorkflowSimulationDecisionRequest(
            expected_workflow_version=1,
            approval_ticket_id=f"{run_id}-approval-ticket",
            decision_id=f"{run_id}-approved-decision",
            decision="approved",
            decided_at=f"{prefix}:20Z",
            actor="approver-operator-001",
            decision_reference=f"{run_id}-approved-manual-review",
            reason="operator_reviewed_simulation_evidence",
        ),
        decided_by="approver-operator-001",
    )
    runner.execute_approved_run(
        workflow_id,
        run_id,
        WorkflowSimulationExecutionRequest(
            expected_workflow_version=1,
            approval_ticket_id=f"{run_id}-approval-ticket",
            approval_decision_id=f"{run_id}-approved-decision",
            order_intent_id=f"{run_id}-intent",
            risk_decision_id=f"{run_id}-risk",
            order_id=f"{run_id}-order",
            execution_id=f"{run_id}-execution",
            executed_at=f"{prefix}:30Z",
            actor="human-operator-001",
            execution_reference=f"{run_id}-manual-simulation-execution",
            reason="operator_confirmed_approved_simulation_execution",
            broker_state_known=True,
            expected_protection_present=expected_protection_present,
        ),
        executed_by="human-operator-001",
    )


def _valid_workflow_dsl() -> dict[str, Any]:
    node_types = (
        "replay_source",
        "bar_builder",
        "strategy_trigger",
        "risk_check",
        "approval_ticket",
        "fake_broker",
        "position_update",
        "alert",
        "audit_sink",
    )
    nodes = [
        {
            "id": node_type.replace("_", "-"),
            "type": node_type,
            "required_for_risk_increasing_path": True,
        }
        for node_type in node_types
    ]
    return {
        "schema_version": 1,
        "workflow_id": "visual-simulation-workflow",
        "mode": "simulation",
        "runtime": "preview_only",
        "broker": "fake_broker_only",
        "nodes": nodes,
        "edges": [
            {
                "source": nodes[index]["id"],
                "target": nodes[index + 1]["id"],
            }
            for index in range(len(nodes) - 1)
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
