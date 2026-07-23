from __future__ import annotations

import sqlite3
from dataclasses import replace
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

    assert len(projected.signals) == 1
    assert len(projected.risk_decisions) == 1
    assert len(projected.approval_tickets) == 1
    assert len(projected.orders) == len(projected.positions) == len(projected.alerts) == 1
    decision_attribution = projected.signals[0].decision_attribution
    assert decision_attribution is not None
    assert decision_attribution == projected.risk_decisions[0].decision_attribution
    assert decision_attribution == projected.approval_tickets[0].decision_attribution
    assert decision_attribution.workflow_id == "workflow-a"
    assert decision_attribution.workflow_version == 1
    assert decision_attribution.run_id == "run-a"
    assert decision_attribution.run_status == "executed"
    assert decision_attribution.signal_id == projected.signals[0].signal_id
    assert decision_attribution.signal_id.startswith("journal_sequence:")
    assert decision_attribution.order_intent_id == "run-a-intent"
    assert decision_attribution.risk_decision_id == "run-a-risk"
    assert decision_attribution.approval_ticket_id == "run-a-approval-ticket"
    assert decision_attribution.approval_decision_id == "run-a-approved-decision"
    assert decision_attribution.approval_decision == "approved"
    assert decision_attribution.approval_actor == "approver-operator-001"
    assert decision_attribution.approval_reason == "operator_reviewed_simulation_evidence"
    assert decision_attribution.approval_decided_at == "2026-07-08T13:01:20Z"
    assert decision_attribution.classifications == (
        "simulated",
        "local_only",
        "externally_unverified",
    )
    assert decision_attribution.broker_derived is False
    assert decision_attribution.externally_verified is False
    assert projected.signals[0].signal == "long_entry_candidate"
    assert projected.risk_decisions[0].request_id == "run-a-risk"
    assert projected.risk_decisions[0].result == "passed"
    assert projected.approval_tickets[0].status == "approved"
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
            "strategy.signal.generated",
            "order_intent.proposed",
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
    assert all(
        event.decision_attribution == decision_attribution for event in projected.audit_events
    )
    for resource in ("orders", "positions", "alerts", "audit_events"):
        provenance = projected.provenance_for(resource)
        expected_source = (
            "durable_saved_workflow_simulation"
            if resource == "audit_events"
            else "durable_saved_workflow_simulation_execution"
        )
        expected_classifications = (
            decision_attribution.classifications
            if resource == "audit_events"
            else attribution.classifications
        )
        assert provenance.source == expected_source
        assert provenance.classifications == expected_classifications
        assert provenance.broker_derived is False
        assert provenance.externally_verified is False
    for resource in ("signals", "risk_decisions", "approval_tickets"):
        provenance = projected.provenance_for(resource)
        assert provenance.source == "durable_saved_workflow_simulation"
        assert provenance.classifications == decision_attribution.classifications


def test_projects_pending_run_and_leaves_unreached_stages_durably_empty(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a")

    projected = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        runner.list_projection_sources(),
    )

    assert len(projected.signals) == 1
    assert len(projected.risk_decisions) == 1
    assert len(projected.approval_tickets) == 1
    assert projected.orders == projected.positions == projected.alerts == ()
    assert projected.approval_tickets[0].status == "pending"
    attribution = projected.approval_tickets[0].decision_attribution
    assert attribution is not None
    assert attribution.run_status == "waiting_for_approval"
    assert attribution.approval_decision_id is None
    assert attribution.approval_decision is None
    assert attribution.approval_actor is None
    assert attribution.approval_reason is None
    assert attribution.approval_decided_at is None
    assert attribution.approval_decision_journal_reference is None
    assert {event.event_type for event in projected.audit_events}.issuperset(
        {
            "strategy.signal.generated",
            "order_intent.proposed",
            "risk.decision.evaluated",
            "approval.ticket.created",
        }
    )
    assert "approval.ticket.decided" not in {event.event_type for event in projected.audit_events}
    for resource in (
        "audit_events",
        "signals",
        "risk_decisions",
        "approval_tickets",
        "orders",
        "positions",
        "alerts",
    ):
        provenance = projected.provenance_for(resource)
        assert provenance.source == "durable_saved_workflow_simulation"
        assert "representative" not in provenance.classifications
        assert "fake_broker_derived" not in provenance.classifications


@pytest.mark.parametrize(
    ("decision", "expected_status", "decision_id", "actor", "reason"),
    (
        (
            "approved",
            "approved_not_executed",
            "run-a-approved-decision",
            "approver-operator-001",
            "operator_reviewed_simulation_evidence",
        ),
        (
            "rejected",
            "rejected",
            "run-a-rejected-decision",
            "approver-operator-001",
            "operator_rejected_simulation_evidence",
        ),
    ),
)
def test_projects_terminal_decision_exactly_without_downstream_execution(
    tmp_path: Path,
    decision: str,
    expected_status: str,
    decision_id: str,
    actor: str,
    reason: str,
) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a")
    _decide(runner, "workflow-a", "run-a", decision=decision)

    projected = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        runner.list_projection_sources(),
    )

    ticket = projected.approval_tickets[0]
    attribution = ticket.decision_attribution
    assert attribution is not None
    assert ticket.status == decision
    assert attribution.run_status == expected_status
    assert attribution.approval_decision_id == decision_id
    assert attribution.approval_decision == decision
    assert attribution.approval_actor == actor
    assert attribution.approval_reason == reason
    assert attribution.approval_decided_at == "2026-07-08T13:01:20Z"
    assert attribution.approval_decision_journal_reference in attribution.journal_references
    assert projected.orders == projected.positions == projected.alerts == ()
    assert any(event.event_type == "approval.ticket.decided" for event in projected.audit_events)


def test_mixed_lifecycle_projection_is_deterministic_and_never_mixes_representative_data(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-b", "run-b", minute=3)
    _start(runner, "workflow-a", "run-a", minute=1)
    _decide(runner, "workflow-a", "run-a", decision="approved", minute=1)
    _execute_started(runner, "workflow-a", "run-a", expected_protection_present=True, minute=1)

    first = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        runner.list_projection_sources(),
    )
    second = project_simulation_executions(
        build_demo_operations_read_model(Settings()),
        runner.list_projection_sources(),
    )

    assert first.to_json_dict() == second.to_json_dict()
    assert [item.decision_attribution.run_id for item in first.signals] == ["run-a", "run-b"]
    assert [item.decision_attribution.run_id for item in first.risk_decisions] == [
        "run-a",
        "run-b",
    ]
    assert [item.decision_attribution.run_id for item in first.approval_tickets] == [
        "run-a",
        "run-b",
    ]
    assert len(first.orders) == len(first.positions) == len(first.alerts) == 1
    for resource in (
        "audit_events",
        "signals",
        "risk_decisions",
        "approval_tickets",
        "orders",
        "positions",
        "alerts",
    ):
        assert "representative" not in first.provenance_for(resource).classifications


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


def test_missing_or_source_mismatched_upstream_evidence_is_rejected(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a")
    source = runner.list_projection_sources()[0]
    signal_record = next(
        record
        for record in source.journal_manifest
        if record.event_type == "strategy.signal.generated"
    )
    without_signal = replace(
        source,
        journal_manifest=tuple(
            record for record in source.journal_manifest if record != signal_record
        ),
    )
    with pytest.raises(SimulationExecutionProjectionError, match="identity|signal"):
        project_simulation_executions(
            build_demo_operations_read_model(Settings()),
            (without_signal,),
        )

    proposal_record = next(
        record for record in source.journal_manifest if record.event_type == "order_intent.proposed"
    )
    bad_proposal = replace(
        proposal_record,
        payload={**proposal_record.payload, "source_signal_reference": "journal_sequence:999999"},
    )
    mismatched = replace(
        source,
        journal_manifest=tuple(
            bad_proposal if record == proposal_record else record
            for record in source.journal_manifest
        ),
    )
    with pytest.raises(SimulationExecutionProjectionError, match="identity|signal"):
        project_simulation_executions(
            build_demo_operations_read_model(Settings()),
            (mismatched,),
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
            "signals": "/api/signals",
            "risk_decisions": "/api/risk-decisions",
            "approval_tickets": "/api/approval-tickets",
            "orders": "/api/orders",
            "positions": "/api/positions",
            "alerts": "/api/alerts",
        }.items()
    }

    assert all(response.status_code == 200 for response in responses.values())
    for resource, response in responses.items():
        payload = response.json()
        assert payload["resource"] == resource
        expected_classifications = ["simulated", "local_only", "externally_unverified"]
        if resource in {"orders", "positions", "alerts"}:
            expected_classifications.insert(2, "fake_broker_derived")
        assert payload["provenance"]["classifications"] == expected_classifications
        assert payload["data"]
        attribution_field = (
            "execution_attribution"
            if resource in {"orders", "positions", "alerts"}
            else "decision_attribution"
        )
        assert all(item[attribution_field]["run_id"] == "run-a" for item in payload["data"])
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

    for path in (
        "/api/audit-events",
        "/api/signals",
        "/api/risk-decisions",
        "/api/approval-tickets",
        "/api/orders",
        "/api/positions",
        "/api/alerts",
    ):
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
    _start(runner, workflow_id, run_id, minute=minute)
    _decide(runner, workflow_id, run_id, decision="approved", minute=minute)
    _execute_started(
        runner,
        workflow_id,
        run_id,
        expected_protection_present=expected_protection_present,
        minute=minute,
    )


def _start(
    runner: WorkflowSimulationRunner,
    workflow_id: str,
    run_id: str,
    *,
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


def _decide(
    runner: WorkflowSimulationRunner,
    workflow_id: str,
    run_id: str,
    *,
    decision: str,
    minute: int = 1,
) -> None:
    prefix = f"2026-07-08T13:{minute:02d}"
    decision_suffix = "approved" if decision == "approved" else "rejected"
    runner.apply_decision(
        workflow_id,
        run_id,
        WorkflowSimulationDecisionRequest(
            expected_workflow_version=1,
            approval_ticket_id=f"{run_id}-approval-ticket",
            decision_id=f"{run_id}-{decision_suffix}-decision",
            decision=decision,
            decided_at=f"{prefix}:20Z",
            actor="approver-operator-001",
            decision_reference=f"{run_id}-{decision_suffix}-manual-review",
            reason=(
                "operator_reviewed_simulation_evidence"
                if decision == "approved"
                else "operator_rejected_simulation_evidence"
            ),
        ),
        decided_by="approver-operator-001",
    )


def _execute_started(
    runner: WorkflowSimulationRunner,
    workflow_id: str,
    run_id: str,
    *,
    expected_protection_present: bool,
    minute: int = 1,
) -> None:
    prefix = f"2026-07-08T13:{minute:02d}"
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
