from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend import app as app_module
from trading_oms_backend.app import app
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.local_persistence import LocalSqlitePersistenceStore
from trading_oms_backend.simulation_run_comparison import (
    AuditExportSelectionConflictError,
    SimulationRunComparisonError,
    SimulationRunNotFoundError,
    SimulationRunSelector,
    build_simulation_run_comparison,
    select_simulation_run_audit_evidence,
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
)


def test_comparison_is_deterministic_and_covers_every_required_evidence_section(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-pending", minute=1)
    _execute(
        runner,
        "workflow-b",
        "run-executed",
        minute=1,
        expected_protection_present=True,
    )
    sources = runner.list_projection_sources()

    first = build_simulation_run_comparison(
        sources,
        left=SimulationRunSelector("workflow-a", "run-pending"),
        right=SimulationRunSelector("workflow-b", "run-executed"),
    )
    second = build_simulation_run_comparison(
        sources,
        left=SimulationRunSelector("workflow-a", "run-pending"),
        right=SimulationRunSelector("workflow-b", "run-executed"),
    )

    payload = first.to_json_dict()
    assert payload == second.to_json_dict()
    assert first.to_stable_json() == second.to_stable_json()
    assert payload["comparison_sha256"] == second.comparison_sha256
    assert payload["selection_state"] == "different_runs"
    assert [section["name"] for section in payload["sections"]] == [
        "workflow",
        "run",
        "signal",
        "order_intent",
        "risk_decision",
        "approval_ticket",
        "approval_decision",
        "execution",
        "protection",
        "alerts",
        "journal_provenance",
    ]
    section_by_name = {section["name"]: section for section in payload["sections"]}
    assert section_by_name["approval_decision"]["status"] == "added"
    assert section_by_name["execution"]["status"] == "added"
    assert section_by_name["protection"]["status"] == "added"
    assert section_by_name["alerts"]["status"] == "added"
    assert section_by_name["signal"]["status"] == "changed"
    assert set(payload["summary"]) == {"added", "removed", "changed", "unchanged"}
    assert sum(payload["summary"].values()) == 11

    right = payload["right"]
    assert right["workflow"] == {
        "workflow_id": "workflow-b",
        "expected_workflow_version": 1,
    }
    assert right["run"]["status"] == "executed"
    assert right["order_intent"]["proposal_id"] == "run-executed-intent"
    assert right["risk_decision"]["request_id"] == "run-executed-risk"
    assert right["approval_ticket"]["ticket_id"] == "run-executed-approval-ticket"
    assert right["approval_decision"]["new_status"] == "approved"
    assert right["execution"]["execution_id"] == "run-executed-execution"
    assert right["protection"]["status"] == "expected_protection_present"
    assert right["alerts"][0]["channel"] == "local"
    assert right["alerts"][0]["dispatch_status"] == "recorded"
    assert right["journal_provenance"]["journal_references"]
    assert len(right["journal_provenance"]["manifest_sha256"]) == 64
    assert all(
        len(record["record_sha256"]) == 64 for record in right["journal_provenance"]["records"]
    )
    assert right["provenance"] == {
        "classifications": [
            "simulated",
            "local_only",
            "fake_broker_derived",
            "externally_unverified",
        ],
        "broker_derived": False,
        "externally_verified": False,
    }


def test_same_run_comparison_is_explicitly_identical(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a")
    selector = SimulationRunSelector("workflow-a", "run-a")

    comparison = build_simulation_run_comparison(
        runner.list_projection_sources(),
        left=selector,
        right=selector,
    ).to_json_dict()

    assert comparison["selection_state"] == "same_run"
    assert comparison["summary"] == {
        "added": 0,
        "removed": 0,
        "changed": 0,
        "unchanged": 11,
    }
    assert all(section["status"] == "unchanged" for section in comparison["sections"])
    assert all(section["differences"] == [] for section in comparison["sections"])


def test_comparison_classification_direction_is_stable(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-pending", minute=1)
    _decide(runner, "workflow-b", "run-approved", decision="approved", minute=2, start=True)
    sources = runner.list_projection_sources()
    pending = SimulationRunSelector("workflow-a", "run-pending")
    approved = SimulationRunSelector("workflow-b", "run-approved")

    forward = build_simulation_run_comparison(sources, left=pending, right=approved)
    reverse = build_simulation_run_comparison(sources, left=approved, right=pending)
    forward_sections = {item.name: item for item in forward.sections}
    reverse_sections = {item.name: item for item in reverse.sections}

    assert forward_sections["approval_decision"].status == "added"
    assert reverse_sections["approval_decision"].status == "removed"
    assert forward.comparison_sha256 != reverse.comparison_sha256
    assert [item.path for item in forward_sections["approval_decision"].differences] == sorted(
        item.path for item in forward_sections["approval_decision"].differences
    )


@pytest.mark.parametrize(
    ("decision", "execute", "protection", "expected_status"),
    (
        (None, False, True, "waiting_for_approval"),
        ("rejected", False, True, "rejected"),
        ("approved", False, True, "approved_not_executed"),
        ("approved", True, True, "executed"),
        ("approved", True, False, "executed_protection_missing"),
    ),
)
def test_comparison_supports_every_committed_run_lifecycle(
    tmp_path: Path,
    decision: str | None,
    execute: bool,
    protection: bool,
    expected_status: str,
) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a")
    if decision is not None:
        _decide(runner, "workflow-a", "run-a", decision=decision)
    if execute:
        _execute_started(
            runner,
            "workflow-a",
            "run-a",
            expected_protection_present=protection,
        )
    selector = SimulationRunSelector("workflow-a", "run-a")

    payload = build_simulation_run_comparison(
        runner.list_projection_sources(),
        left=selector,
        right=selector,
    ).to_json_dict()

    assert payload["left"]["run"]["status"] == expected_status
    assert payload["right"]["run"]["status"] == expected_status


def test_comparison_rejects_missing_duplicate_and_cross_run_evidence(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a", minute=1)
    _start(runner, "workflow-b", "run-b", minute=2)
    sources = runner.list_projection_sources()

    with pytest.raises(SimulationRunNotFoundError):
        build_simulation_run_comparison(
            sources,
            left=SimulationRunSelector("workflow-a", "missing"),
            right=SimulationRunSelector("workflow-b", "run-b"),
        )

    duplicated = (
        sources[0],
        replace(
            sources[1],
            journal_manifest=(
                *sources[1].journal_manifest,
                sources[0].journal_manifest[0],
            ),
        ),
    )
    with pytest.raises(SimulationRunComparisonError):
        build_simulation_run_comparison(
            duplicated,
            left=SimulationRunSelector("workflow-a", "run-a"),
            right=SimulationRunSelector("workflow-b", "run-b"),
        )

    wrong_source = replace(
        sources[1],
        run=replace(sources[1].run, workflow_id="workflow-a"),
    )
    with pytest.raises(SimulationRunComparisonError):
        build_simulation_run_comparison(
            (sources[0], wrong_source),
            left=SimulationRunSelector("workflow-a", "run-a"),
            right=SimulationRunSelector("workflow-a", "run-b"),
        )


def test_comparison_recovers_identically_after_restart_and_never_writes(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a", minute=1)
    _execute(
        runner,
        "workflow-b",
        "run-b",
        minute=2,
        expected_protection_present=False,
    )
    selectors = {
        "left": SimulationRunSelector("workflow-a", "run-a"),
        "right": SimulationRunSelector("workflow-b", "run-b"),
    }
    journal_path = tmp_path / "journal.jsonl"
    database_path = tmp_path / "state.sqlite3"
    journal_before = journal_path.read_bytes()
    database_before = database_path.read_bytes()
    first = build_simulation_run_comparison(runner.list_projection_sources(), **selectors)

    restarted = _runner(tmp_path, create_workflows=False)
    second = build_simulation_run_comparison(restarted.list_projection_sources(), **selectors)
    third = build_simulation_run_comparison(restarted.list_projection_sources(), **selectors)

    assert first.to_stable_json() == second.to_stable_json() == third.to_stable_json()
    assert journal_path.read_bytes() == journal_before
    assert database_path.read_bytes() == database_before


def test_selected_audit_evidence_supports_complete_and_single_event_scope(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    _execute(
        runner,
        "workflow-a",
        "run-a",
        expected_protection_present=True,
    )
    source = runner.list_projection_sources()[0]
    selector = SimulationRunSelector("workflow-a", "run-a")
    comparison = build_simulation_run_comparison((source,), left=selector, right=selector)
    digest = comparison.left.journal_provenance.manifest_sha256

    complete = select_simulation_run_audit_evidence(
        (source,),
        selector=selector,
        expected_manifest_sha256=digest,
        journal_scope="complete_run_manifest",
    )
    sequence = source.journal_manifest[2].sequence
    single = select_simulation_run_audit_evidence(
        (source,),
        selector=selector,
        expected_manifest_sha256=digest,
        journal_scope="single_journal_event",
        journal_sequence=sequence,
    )

    assert complete.selection.selected_journal_references == (
        comparison.left.journal_provenance.journal_references
    )
    assert complete.journal_records == source.journal_manifest
    assert len(complete.selection.selected_record_sha256) == len(source.journal_manifest)
    assert len(single.journal_records) == 1
    assert single.journal_records[0].sequence == sequence
    assert single.selection.selected_journal_references == (f"journal_sequence:{sequence}",)
    assert single.selection.source_manifest_sha256 == digest
    assert single.selection.selection_sha256 != complete.selection.selection_sha256
    assert single.selection.broker_derived is False
    assert single.selection.externally_verified is False


def test_selected_audit_evidence_rejects_stale_or_out_of_manifest_selection(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a")
    source = runner.list_projection_sources()[0]
    selector = SimulationRunSelector("workflow-a", "run-a")

    with pytest.raises(AuditExportSelectionConflictError):
        select_simulation_run_audit_evidence(
            (source,),
            selector=selector,
            expected_manifest_sha256="0" * 64,
            journal_scope="complete_run_manifest",
        )
    with pytest.raises(SimulationRunComparisonError):
        select_simulation_run_audit_evidence(
            (source,),
            selector=selector,
            expected_manifest_sha256=build_simulation_run_comparison(
                (source,),
                left=selector,
                right=selector,
            ).left.journal_provenance.manifest_sha256,
            journal_scope="single_journal_event",
            journal_sequence=999999,
        )


def test_comparison_and_selected_audit_apis_are_read_only_and_exactly_bound(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a", minute=1)
    _execute(
        runner,
        "workflow-b",
        "run-b",
        minute=2,
        expected_protection_present=True,
    )
    monkeypatch.setattr(app_module, "get_workflow_simulation_runner", lambda: runner)
    client = TestClient(app)
    comparison_path = "/api/simulation-run-comparison?" + urlencode(
        {
            "left_workflow_id": "workflow-a",
            "left_run_id": "run-a",
            "right_workflow_id": "workflow-b",
            "right_run_id": "run-b",
        }
    )
    journal_before = tuple(record.to_json_dict() for record in runner.journal_records())

    comparison = client.get(comparison_path)
    digest = comparison.json()["right"]["journal_provenance"]["manifest_sha256"]
    complete_path = "/api/audit-export-bundle?" + urlencode(
        {
            "workflow_id": "workflow-b",
            "run_id": "run-b",
            "expected_manifest_sha256": digest,
            "journal_scope": "complete_run_manifest",
        }
    )
    complete = client.get(complete_path)
    selected_sequence = comparison.json()["right"]["journal_provenance"]["records"][0]["sequence"]
    single = client.get(
        "/api/audit-export-bundle?"
        + urlencode(
            {
                "workflow_id": "workflow-b",
                "run_id": "run-b",
                "expected_manifest_sha256": digest,
                "journal_scope": "single_journal_event",
                "journal_sequence": selected_sequence,
            }
        )
    )

    assert comparison.status_code == 200
    assert complete.status_code == 200
    assert single.status_code == 200
    assert complete.json()["manifest"]["selection"]["run_id"] == "run-b"
    assert complete.json()["manifest"]["selection"]["source_manifest_sha256"] == digest
    assert complete.json()["manifest"]["counts"]["workflow_simulation_runs"] == 1
    assert single.json()["manifest"]["counts"]["journal_records"] == 1
    assert single.json()["manifest"]["counts"]["audit_events"] == 1
    assert single.json()["journal_records"][0]["sequence"] == selected_sequence
    assert tuple(record.to_json_dict() for record in runner.journal_records()) == journal_before
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, comparison_path).status_code == 405
        assert client.request(method, complete_path).status_code == 405


def test_comparison_and_selected_audit_apis_fail_closed_without_details(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = _runner(tmp_path)
    _start(runner, "workflow-a", "run-a")
    monkeypatch.setattr(app_module, "get_workflow_simulation_runner", lambda: runner)
    client = TestClient(app)

    missing = client.get(
        "/api/simulation-run-comparison?"
        + urlencode(
            {
                "left_workflow_id": "workflow-a",
                "left_run_id": "missing",
                "right_workflow_id": "workflow-a",
                "right_run_id": "run-a",
            }
        )
    )
    malformed_export = client.get(
        "/api/audit-export-bundle?" + urlencode({"workflow_id": "workflow-a", "run_id": "run-a"})
    )
    stale = client.get(
        "/api/audit-export-bundle?"
        + urlencode(
            {
                "workflow_id": "workflow-a",
                "run_id": "run-a",
                "expected_manifest_sha256": "0" * 64,
                "journal_scope": "complete_run_manifest",
            }
        )
    )
    malformed_digest = client.get(
        "/api/audit-export-bundle?"
        + urlencode(
            {
                "workflow_id": "workflow-a",
                "run_id": "run-a",
                "expected_manifest_sha256": "z" * 64,
                "journal_scope": "complete_run_manifest",
            }
        )
    )

    assert missing.status_code == 404
    assert missing.json() == {"detail": "simulation run comparison evidence is unavailable"}
    assert malformed_export.status_code == 400
    assert malformed_export.json() == {"detail": "audit export selection is invalid"}
    assert stale.status_code == 409
    assert stale.json() == {"detail": "audit export selection is stale"}
    assert malformed_digest.status_code == 400
    assert malformed_digest.json() == {"detail": "audit export selection is invalid"}
    for response in (missing, malformed_export, stale, malformed_digest):
        assert "sqlite" not in response.text.lower()
        assert str(tmp_path).lower() not in response.text.lower()

    monkeypatch.setattr(
        runner,
        "list_projection_sources",
        lambda: (_ for _ in ()).throw(RuntimeError("private sqlite path")),
    )
    unavailable = client.get(
        "/api/simulation-run-comparison?"
        + urlencode(
            {
                "left_workflow_id": "workflow-a",
                "left_run_id": "run-a",
                "right_workflow_id": "workflow-a",
                "right_run_id": "run-a",
            }
        )
    )
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "simulation run comparison evidence is unavailable"}
    assert "sqlite" not in unavailable.text.lower()


def test_comparison_payload_exposes_no_unsafe_affordance_keys(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _execute(
        runner,
        "workflow-a",
        "run-a",
        expected_protection_present=False,
    )
    selector = SimulationRunSelector("workflow-a", "run-a")
    payload = build_simulation_run_comparison(
        runner.list_projection_sources(),
        left=selector,
        right=selector,
    ).to_json_dict()
    text = json.dumps(payload).lower()

    for forbidden in (
        '"account_id"',
        '"credential"',
        '"password"',
        '"token"',
        '"broker_host"',
        '"route_url"',
        '"submit_url"',
        '"transmit_url"',
        '"live_trading_enabled": true',
        '"broker_derived": true',
        '"externally_verified": true',
    ):
        assert forbidden not in text


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
    start: bool = False,
) -> None:
    if start:
        _start(runner, workflow_id, run_id, minute=minute)
    prefix = f"2026-07-08T13:{minute:02d}"
    suffix = "approved" if decision == "approved" else "rejected"
    runner.apply_decision(
        workflow_id,
        run_id,
        WorkflowSimulationDecisionRequest(
            expected_workflow_version=1,
            approval_ticket_id=f"{run_id}-approval-ticket",
            decision_id=f"{run_id}-{suffix}-decision",
            decision=decision,
            decided_at=f"{prefix}:20Z",
            actor="approver-operator-001",
            decision_reference=f"{run_id}-{suffix}-manual-review",
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


def _valid_workflow_dsl() -> dict[str, object]:
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
            {"source": nodes[index]["id"], "target": nodes[index + 1]["id"]}
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
