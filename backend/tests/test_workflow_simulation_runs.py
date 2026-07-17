from __future__ import annotations

import inspect
import json
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from trading_oms_backend.emergency_stop import (
    EMERGENCY_STOP_BLOCKED_EVENT_TYPE,
    EmergencyStopChangeRequest,
    EmergencyStopService,
)
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.local_persistence import LocalSqlitePersistenceStore
from trading_oms_backend.workflow_definitions import (
    WorkflowDefinitionSaveRequest,
    WorkflowDefinitionStore,
)
from trading_oms_backend.workflow_simulation_runs import (
    WorkflowSimulationRunConflictError,
    WorkflowSimulationRunError,
    WorkflowSimulationRunner,
    WorkflowSimulationRunRequest,
    WorkflowSimulationRunUnavailableError,
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
    runner = WorkflowSimulationRunner(
        store,
        journal,
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
    )

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


def test_workflow_simulation_runner_uses_replay_clock_for_market_data_freshness(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
    )

    record = runner.start_run(
        "workflow-001",
        _run_request(
            requested_at="2026-07-16T10:01:00Z",
            evaluated_at="2026-07-16T10:01:00Z",
            approval_expires_at="2026-07-16T10:06:00Z",
        ),
    )

    assert record.status == "waiting_for_approval"
    assert record.approval_ticket_id == "workflow-run-001-approval-ticket"
    risk_events = [
        event for event in runner.journal_records() if event.event_type == "risk.decision.evaluated"
    ]
    assert len(risk_events) == 1
    assert risk_events[0].payload["evaluated_at"] == "2026-07-08T13:45:10Z"


@pytest.mark.parametrize(
    "replay_input_reference",
    ["fixtures/replay/other.jsonl", "https://example.invalid/replay.jsonl"],
)
def test_workflow_simulation_run_request_rejects_unapproved_replay_reference(
    replay_input_reference: str,
) -> None:
    with pytest.raises(WorkflowSimulationRunError, match="replay_input_reference"):
        _run_request(replay_input_reference=replay_input_reference)


def test_workflow_simulation_runner_is_idempotent_for_identical_run_payload(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
    )
    request = _run_request()

    first = runner.start_run("workflow-001", request)
    event_count = len(runner.journal_records())
    second = runner.start_run("workflow-001", request)

    assert second == first
    assert len(runner.journal_records()) == event_count


def test_workflow_simulation_runner_rejects_stale_workflow_version_before_journaling(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    store = _store_with_workflow(store_path)
    store.update_workflow(
        "workflow-001",
        WorkflowDefinitionSaveRequest(
            workflow_id="workflow-001",
            display_name="Opening breakout simulation version two",
            description="Validated visual simulation workflow",
            document=_valid_workflow_dsl(),
            requested_at="2026-07-08T00:01:00Z",
            expected_version=1,
        ),
    )
    runner = WorkflowSimulationRunner(
        store,
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
    )

    with pytest.raises(
        WorkflowSimulationRunConflictError,
        match="expected_workflow_version does not match current workflow version",
    ):
        runner.start_run(
            "workflow-001",
            _run_request(expected_workflow_version=1),
        )

    assert runner.journal_records() == ()
    assert runner.list_runs("workflow-001") == ()


@pytest.mark.parametrize("expected_workflow_version", [0, -1, True, "1"])
def test_workflow_simulation_run_request_requires_positive_integer_workflow_version(
    expected_workflow_version: object,
) -> None:
    with pytest.raises(WorkflowSimulationRunError, match="expected_workflow_version"):
        _run_request(expected_workflow_version=expected_workflow_version)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"evaluated_at": "2026-07-08T13:29:54Z"},
            "evaluated_at must not be before requested_at",
        ),
        (
            {"approval_expires_at": "2026-07-08T13:45:10Z"},
            "approval_expires_at must be after evaluated_at",
        ),
    ],
)
def test_workflow_simulation_run_request_requires_ordered_timestamps(
    overrides: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(WorkflowSimulationRunError, match=message):
        _run_request(**overrides)


def test_workflow_simulation_runner_lists_and_loads_run_inspection_records(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
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
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
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
    runner = WorkflowSimulationRunner(
        store,
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
    )

    with pytest.raises(WorkflowSimulationRunError, match="live_trading_enabled"):
        runner.start_run("workflow-001", _run_request())


def test_workflow_simulation_runner_recovers_list_get_and_exact_retry_after_restart(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    persistence_path = journal_path.with_suffix(".sqlite3")
    request = _run_request()
    first_runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )

    first = first_runner.start_run("workflow-001", request)
    journal_count = len(first_runner.journal_records())
    restarted_runner = WorkflowSimulationRunner(
        WorkflowDefinitionStore(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )

    assert restarted_runner.list_runs("workflow-001") == (first,)
    assert restarted_runner.get_run("workflow-001", request.run_id) == first
    assert restarted_runner.start_run("workflow-001", request) == first
    assert len(restarted_runner.journal_records()) == journal_count


def test_workflow_simulation_runner_rejects_conflicting_retry_after_restart(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    persistence_path = journal_path.with_suffix(".sqlite3")
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    runner.start_run("workflow-001", _run_request())
    restarted_runner = WorkflowSimulationRunner(
        WorkflowDefinitionStore(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )

    with pytest.raises(WorkflowSimulationRunError, match="conflicting run_id"):
        restarted_runner.start_run(
            "workflow-001",
            _run_request(evaluated_at="2026-07-08T13:46:00Z"),
        )


def test_workflow_simulation_runner_lists_recovered_runs_in_deterministic_order(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    persistence_path = journal_path.with_suffix(".sqlite3")
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    runner.start_run("workflow-001", _run_request(run_id="workflow-run-002"))
    runner.start_run("workflow-001", _run_request(run_id="workflow-run-001"))

    restarted_runner = WorkflowSimulationRunner(
        WorkflowDefinitionStore(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )

    assert [record.run_id for record in restarted_runner.list_runs("workflow-001")] == [
        "workflow-run-001",
        "workflow-run-002",
    ]


def test_workflow_simulation_runner_serializes_concurrent_exact_duplicates(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
    )
    request = _run_request()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(runner.start_run, "workflow-001", request) for _ in range(2)]
    records = [future.result() for future in futures]

    assert records[0] == records[1]
    assert len(runner.list_runs("workflow-001")) == 1
    assert (
        sum(record.event_type == "simulation_run.created" for record in runner.journal_records())
        == 1
    )


def test_workflow_simulation_runner_fails_closed_for_pending_evidence(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    persistence = LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3"))
    request = _run_request()
    persistence.reserve_workflow_simulation_run(
        {"workflow_id": "workflow-001", **request.to_payload()}
    )
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=persistence,
    )

    with pytest.raises(WorkflowSimulationRunUnavailableError, match="evidence is unavailable"):
        runner.list_runs("workflow-001")
    with pytest.raises(WorkflowSimulationRunUnavailableError, match="evidence is unavailable"):
        runner.start_run("workflow-001", request)


def test_workflow_simulation_runner_prevents_cross_instance_duplicate_orchestration(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    _store_with_workflow(store_path)
    persistence_path = journal_path.with_suffix(".sqlite3")
    runners = tuple(
        WorkflowSimulationRunner(
            WorkflowDefinitionStore(store_path),
            JsonlEventJournal(journal_path),
            persistence_store=LocalSqlitePersistenceStore(persistence_path),
        )
        for _ in range(2)
    )
    request = _run_request()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(runner.start_run, "workflow-001", request) for runner in runners]
    records = []
    unavailable = []
    for future in futures:
        try:
            records.append(future.result())
        except WorkflowSimulationRunUnavailableError as exc:
            unavailable.append(exc)

    assert records
    assert all(record == records[0] for record in records)
    assert all(str(error) == "workflow simulation evidence is unavailable" for error in unavailable)
    journal_records = JsonlEventJournal(journal_path).read_all()
    assert sum(record.event_type == "simulation_run.created" for record in journal_records) == 1


def test_workflow_simulation_runner_fails_closed_for_corrupt_persisted_record(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    persistence_path = journal_path.with_suffix(".sqlite3")
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    runner.start_run("workflow-001", _run_request())
    connection = sqlite3.connect(persistence_path)
    try:
        connection.execute("UPDATE workflow_simulation_run_evidence SET record_json = '{'")
        connection.commit()
    finally:
        connection.close()

    restarted_runner = WorkflowSimulationRunner(
        WorkflowDefinitionStore(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    with pytest.raises(WorkflowSimulationRunUnavailableError, match="evidence is unavailable"):
        restarted_runner.get_run("workflow-001", "workflow-run-001")


def test_workflow_simulation_runner_fails_closed_for_missing_journal_reference(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    persistence_path = journal_path.with_suffix(".sqlite3")
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    runner.start_run("workflow-001", _run_request())
    journal_lines = journal_path.read_text(encoding="utf-8").splitlines()
    journal_path.write_text("\n".join(journal_lines[:-1]) + "\n", encoding="utf-8")

    restarted_runner = WorkflowSimulationRunner(
        WorkflowDefinitionStore(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    with pytest.raises(WorkflowSimulationRunUnavailableError, match="evidence is unavailable"):
        restarted_runner.list_runs("workflow-001")


@pytest.mark.parametrize(
    "corruption_sql",
    [
        "journal_manifest_json = NULL",
        "journal_manifest_sha256 = 'invalid-digest'",
        "journal_manifest_json = replace(journal_manifest_json, "
        "'\"schema_version\":1', "
        '\'"unexpected":"field","schema_version":1\')',
    ],
)
def test_workflow_simulation_runner_fails_closed_for_partial_or_corrupt_manifest(
    workflow_paths: tuple[Path, Path],
    corruption_sql: str,
) -> None:
    store_path, journal_path = workflow_paths
    persistence_path = journal_path.with_suffix(".sqlite3")
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    runner.start_run("workflow-001", _run_request())
    connection = sqlite3.connect(persistence_path)
    try:
        connection.execute(f"UPDATE workflow_simulation_run_evidence SET {corruption_sql}")
        connection.commit()
    finally:
        connection.close()

    restarted_runner = WorkflowSimulationRunner(
        WorkflowDefinitionStore(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    with pytest.raises(WorkflowSimulationRunUnavailableError, match="evidence is unavailable"):
        restarted_runner.list_runs("workflow-001")


def test_workflow_simulation_runner_fails_closed_for_contradictory_journal_record(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    persistence_path = journal_path.with_suffix(".sqlite3")
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    runner.start_run("workflow-001", _run_request())
    journal_lines = journal_path.read_text(encoding="utf-8").splitlines()
    altered = json.loads(journal_lines[0])
    altered["payload"]["run_id"] = "contradictory-run"
    journal_lines[0] = json.dumps(altered, sort_keys=True, separators=(",", ":"))
    journal_path.write_text("\n".join(journal_lines) + "\n", encoding="utf-8")

    restarted_runner = WorkflowSimulationRunner(
        WorkflowDefinitionStore(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    with pytest.raises(WorkflowSimulationRunUnavailableError, match="evidence is unavailable"):
        restarted_runner.list_runs("workflow-001")


def test_workflow_simulation_runner_fails_closed_for_corrupt_journal_json(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    persistence_path = journal_path.with_suffix(".sqlite3")
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    runner.start_run("workflow-001", _run_request())
    journal_lines = journal_path.read_text(encoding="utf-8").splitlines()
    journal_lines[0] = "{"
    journal_path.write_text("\n".join(journal_lines) + "\n", encoding="utf-8")

    restarted_runner = WorkflowSimulationRunner(
        WorkflowDefinitionStore(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(persistence_path),
    )
    with pytest.raises(WorkflowSimulationRunUnavailableError, match="evidence is unavailable"):
        restarted_runner.get_run("workflow-001", "workflow-run-001")


def test_workflow_simulation_runner_blocks_start_when_emergency_stop_is_active(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    journal = JsonlEventJournal(journal_path)
    emergency_stop = EmergencyStopService(journal)
    emergency_stop.activate(
        EmergencyStopChangeRequest(
            event_id="emergency-stop-activate-001",
            requested_at="2026-07-08T13:45:00Z",
            actor="admin-operator-001",
            reason="operator_review",
        ),
    )
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        journal,
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
        emergency_stop_service=emergency_stop,
    )

    with pytest.raises(WorkflowSimulationRunError, match="emergency stop is active"):
        runner.start_run(
            "workflow-001",
            _run_request(),
            requested_by="admin-operator-001",
        )

    event_types = [event.event_type for event in journal.read_all()]
    assert event_types == [
        "emergency_stop.activated",
        EMERGENCY_STOP_BLOCKED_EVENT_TYPE,
    ]


def test_workflow_simulation_run_payloads_exclude_broker_network_and_secret_affordances(
    workflow_paths: tuple[Path, Path],
) -> None:
    store_path, journal_path = workflow_paths
    runner = WorkflowSimulationRunner(
        _store_with_workflow(store_path),
        JsonlEventJournal(journal_path),
        persistence_store=LocalSqlitePersistenceStore(journal_path.with_suffix(".sqlite3")),
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
        "expected_workflow_version": 1,
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
