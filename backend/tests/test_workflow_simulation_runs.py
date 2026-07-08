from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.workflow_definitions import (
    WorkflowDefinitionSaveRequest,
    WorkflowDefinitionStore,
)
from trading_oms_backend.workflow_simulation_runs import (
    WorkflowSimulationRunError,
    WorkflowSimulationRunner,
    WorkflowSimulationRunRequest,
)


@pytest.fixture
def workflow_paths() -> Iterator[tuple[Path, Path]]:
    root = Path(__file__).resolve().parents[1] / ".test-tmp"
    root.mkdir(exist_ok=True)
    try:
        with TemporaryDirectory(dir=root) as temp_dir:
            temp_path = Path(temp_dir)
            yield temp_path / "workflows.json", temp_path / "journal.jsonl"
    finally:
        try:
            root.rmdir()
        except OSError:
            pass


def test_workflow_simulation_runner_runs_saved_workflow_to_approval_wait(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    store = _store_with_workflow(store_path)
    journal = JsonlEventJournal(journal_path)
    runner = WorkflowSimulationRunner(store, journal)

    record = runner.start_run("workflow-001", _run_request())

    assert record.workflow_id == "workflow-001"
    assert record.run_id == "workflow-run-001"
    assert record.status == "waiting_for_approval"
    assert record.approval_ticket_id == "workflow-run-001-approval-ticket"
    assert record.simulation_run.status == "completed"
    assert [(node.node_type, node.status) for node in record.node_statuses] == [
        ("replay_source", "completed"),
        ("bar_builder", "completed"),
        ("strategy_trigger", "completed"),
        ("risk_check", "passed"),
        ("approval_ticket", "waiting_for_approval"),
        ("fake_broker", "blocked_waiting_for_approval"),
        ("position_update", "blocked_waiting_for_approval"),
        ("alert", "blocked_waiting_for_approval"),
        ("audit_sink", "completed"),
    ]

    event_types = [event.event_type for event in journal.read_all()]
    assert "workflow_simulation.node_status" in event_types
    assert "approval.ticket.created" in event_types
    assert "fake_broker.order.transitioned" not in event_types
    assert "position.updated" not in event_types
    assert "alert.intent.created" not in event_types


def test_workflow_simulation_runner_is_idempotent_for_identical_run_payload(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path), JsonlEventJournal(journal_path)
    )
    request = _run_request()

    first = runner.start_run("workflow-001", request)
    event_count = len(runner.journal_records())
    second = runner.start_run("workflow-001", request)

    assert second == first
    assert len(runner.journal_records()) == event_count


def test_workflow_simulation_runner_lists_and_loads_run_inspection_records(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path), JsonlEventJournal(journal_path)
    )

    record = runner.start_run("workflow-001", _run_request())

    assert runner.list_runs("workflow-001") == (record,)
    assert runner.get_run("workflow-001", "workflow-run-001") == record
    with pytest.raises(WorkflowSimulationRunError, match="unknown workflow simulation run"):
        runner.get_run("workflow-001", "missing-run")


def test_workflow_simulation_runner_rejects_unknown_or_conflicting_runs(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path), JsonlEventJournal(journal_path)
    )

    with pytest.raises(WorkflowSimulationRunError, match="unknown workflow_id"):
        runner.start_run("missing-workflow", _run_request())

    runner.start_run("workflow-001", _run_request())
    with pytest.raises(WorkflowSimulationRunError, match="conflicting run_id"):
        runner.start_run(
            "workflow-001",
            _run_request(evaluated_at="2026-07-08T13:46:00Z"),
        )


def test_workflow_simulation_runner_revalidates_saved_workflow_before_running(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    store = _store_with_workflow(store_path)
    payload = store_path.read_text(encoding="utf-8")
    unsafe_payload = payload.replace(
        '"live_trading_enabled": false', '"live_trading_enabled": true'
    )
    store_path.write_text(unsafe_payload, encoding="utf-8")
    runner = WorkflowSimulationRunner(store, JsonlEventJournal(journal_path))

    with pytest.raises(WorkflowSimulationRunError, match="live_trading_enabled"):
        runner.start_run("workflow-001", _run_request())


def test_workflow_simulation_run_payloads_exclude_broker_network_and_secret_affordances(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path), JsonlEventJournal(journal_path)
    )

    record = runner.start_run("workflow-001", _run_request())

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
    assert forbidden_keys.isdisjoint(_all_payload_keys(record.to_json_dict()))


def test_workflow_simulation_runs_module_does_not_define_transport_or_live_execution() -> None:
    import trading_oms_backend.workflow_simulation_runs as workflow_simulation_runs

    source = inspect.getsource(workflow_simulation_runs).lower()
    forbidden_source_tokens = [
        "@app.put",
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
        "live_trading_enabled = true",
    ]
    for token in forbidden_source_tokens:
        assert token not in source


def _store_with_workflow(store_path: Path) -> WorkflowDefinitionStore:
    store = WorkflowDefinitionStore(store_path)
    store.create_workflow(
        WorkflowDefinitionSaveRequest(
            workflow_id="workflow-001",
            display_name="Opening breakout simulation",
            description="Validated visual simulation workflow",
            document=_valid_workflow_dsl(),
            requested_at="2026-07-08T00:00:00Z",
        ),
    )
    return store


def _run_request(**overrides: Any) -> WorkflowSimulationRunRequest:
    values = {
        "run_id": "workflow-run-001",
        "requested_at": "2026-07-08T13:29:55Z",
        "evaluated_at": "2026-07-08T13:45:10Z",
        "approval_expires_at": "2026-07-08T13:50:10Z",
        "replay_input_reference": "fixtures/replay/aapl-session.jsonl",
    }
    values.update(overrides)
    return WorkflowSimulationRunRequest(**values)


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
