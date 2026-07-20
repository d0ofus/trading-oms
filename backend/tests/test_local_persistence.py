from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from trading_oms_backend.config import Settings
from trading_oms_backend.event_journal import JournalRecord
from trading_oms_backend.local_persistence import (
    LocalPersistenceError,
    LocalSqlitePersistenceStore,
)
from trading_oms_backend.local_persistence import (
    main as persistence_main,
)
from trading_oms_backend.read_models import build_demo_operations_read_model
from trading_oms_backend.simulation_runs import SimulationRunRecord
from trading_oms_backend.workflow_definitions import WorkflowDefinitionRecord
from trading_oms_backend.workflow_simulation_runs import (
    WorkflowNodeRunStatus,
    WorkflowSimulationRunRecord,
)


@pytest.fixture
def local_database_path() -> Iterator[Path]:
    root = Path(__file__).resolve().parents[1] / ".test-tmp"
    root.mkdir(exist_ok=True)
    try:
        with TemporaryDirectory(dir=root) as temp_dir:
            yield Path(temp_dir) / "local.sqlite3"
    finally:
        try:
            root.rmdir()
        except OSError:
            pass


def test_local_persistence_initializes_schema_idempotently(
    local_database_path: Path,
) -> None:
    store = LocalSqlitePersistenceStore(local_database_path)

    store.initialize()
    store.initialize()

    assert store.schema_version() == 3
    assert _table_names(local_database_path) == {
        "journal_index",
        "read_model_snapshots",
        "schema_migrations",
        "workflow_definitions",
        "workflow_simulation_run_evidence",
        "workflow_simulation_runs",
    }


def test_local_persistence_migrates_schema_one_without_discarding_legacy_data(
    local_database_path: Path,
) -> None:
    connection = sqlite3.connect(local_database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations (version, applied_at)
            VALUES (1, '1970-01-01T00:00:00Z');
            CREATE TABLE workflow_simulation_runs (
              run_id TEXT PRIMARY KEY,
              workflow_id TEXT NOT NULL,
              status TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              approval_ticket_id TEXT,
              payload_json TEXT NOT NULL
            );
            INSERT INTO workflow_simulation_runs (
              run_id, workflow_id, status, updated_at, approval_ticket_id, payload_json
            ) VALUES (
              'legacy-run-001', 'workflow-001', 'completed',
              '2026-07-08T13:45:10Z', NULL, '{"schema_version":1}'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    store = LocalSqlitePersistenceStore(local_database_path)
    store.initialize()

    assert store.schema_version() == 3
    assert "workflow_simulation_run_evidence" in _table_names(local_database_path)
    connection = sqlite3.connect(local_database_path)
    try:
        legacy_count = connection.execute(
            "SELECT count(*) FROM workflow_simulation_runs WHERE run_id = 'legacy-run-001'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert legacy_count == 1


def test_local_persistence_reserves_and_atomically_finalizes_exact_run_evidence(
    local_database_path: Path,
) -> None:
    store = LocalSqlitePersistenceStore(local_database_path)
    request_payload = _workflow_simulation_request_payload()
    run = _workflow_simulation_run_record()
    journal_records = tuple(
        JournalRecord(
            sequence=sequence,
            event_type="workflow_simulation.evidence",
            timestamp="2026-07-08T13:45:10Z",
            payload={
                "schema_version": 1,
                "run_id": "workflow-run-001",
                "sequence_marker": sequence,
            },
        )
        for sequence in range(1, 11)
    )

    pending, pending_created = store.reserve_workflow_simulation_run(request_payload)
    exact_pending, exact_pending_created = store.reserve_workflow_simulation_run(request_payload)

    assert exact_pending == pending
    assert pending_created is True
    assert exact_pending_created is False
    assert pending["evidence_state"] == "pending"
    assert pending["request"] == request_payload
    assert pending["record"] is None
    assert pending["journal_manifest"] is None
    with pytest.raises(LocalPersistenceError, match="conflicting workflow simulation run_id"):
        store.reserve_workflow_simulation_run(
            {**request_payload, "evaluated_at": "2026-07-08T13:46:00Z"}
        )

    committed = store.finalize_workflow_simulation_run(
        "workflow-run-001",
        run,
        journal_records,
    )

    assert committed["evidence_state"] == "committed"
    assert committed["record"] == run.to_json_dict()
    assert committed["journal_manifest"] == [record.to_json_dict() for record in journal_records]
    assert isinstance(committed["request_sha256"], str)
    assert len(committed["request_sha256"]) == 64
    assert isinstance(committed["journal_manifest_sha256"], str)
    assert len(committed["journal_manifest_sha256"]) == 64
    assert store.get_workflow_simulation_run_evidence("workflow-run-001") == committed
    assert store.list_workflow_simulation_run_evidence("workflow-001") == (committed,)


def test_local_persistence_stores_safe_domain_snapshots(local_database_path: Path) -> None:
    store = LocalSqlitePersistenceStore(local_database_path)
    workflow = _workflow_definition_record()
    run = _workflow_simulation_run_record()
    read_model = build_demo_operations_read_model(
        Settings(app_env="development", app_mode="simulation", live_trading_enabled=False)
    )
    journal_record = JournalRecord(
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
    )

    store.initialize()
    store.put_workflow_definition(workflow)
    store.put_workflow_simulation_run(run)
    store.put_operations_read_model(
        "snapshot-001",
        read_model,
        recorded_at="2026-07-08T13:45:11Z",
    )
    store.index_journal_records((journal_record,))

    assert store.list_workflow_definitions() == (workflow.to_json_dict(),)
    assert store.list_workflow_simulation_runs("workflow-001") == (run.to_json_dict(),)
    assert store.get_operations_read_model("snapshot-001") == read_model.to_json_dict()
    assert [
        entry.to_json_dict() for entry in store.query_journal_index(run_id="workflow-run-001")
    ] == [
        {
            "schema_version": 1,
            "sequence": 10,
            "event_type": "alert.intent.created",
            "timestamp": "2026-07-08T13:45:10Z",
            "run_id": "workflow-run-001",
            "symbol": "AAPL",
            "order_id": "order-001",
            "ticket_id": "ticket-001",
            "severity": "critical",
            "payload": journal_record.payload,
        }
    ]
    assert store.query_journal_index(symbol="MSFT") == ()


def test_local_persistence_rejects_secret_live_and_broker_action_payloads(
    local_database_path: Path,
) -> None:
    store = LocalSqlitePersistenceStore(local_database_path)
    store.initialize()

    unsafe_records = (
        JournalRecord(
            sequence=1,
            event_type="unsafe.secret",
            timestamp="2026-07-08T13:45:10Z",
            payload={"api_key": "redacted"},
        ),
        JournalRecord(
            sequence=2,
            event_type="unsafe.live",
            timestamp="2026-07-08T13:45:11Z",
            payload={"live_trading_enabled": True},
        ),
        JournalRecord(
            sequence=3,
            event_type="unsafe.transmit",
            timestamp="2026-07-08T13:45:12Z",
            payload={"action": "transmit_order"},
        ),
    )

    for record in unsafe_records:
        with pytest.raises(LocalPersistenceError):
            store.index_journal_records((record,))


def test_local_persistence_init_command_creates_database(local_database_path: Path) -> None:
    database_path = local_database_path.with_name("from-cli.sqlite3")

    assert persistence_main(["init", "--database", str(database_path)]) == 0

    store = LocalSqlitePersistenceStore(database_path)
    assert store.schema_version() == 3


def _table_names(database_path: Path) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


def _workflow_definition_record() -> WorkflowDefinitionRecord:
    return WorkflowDefinitionRecord(
        workflow_id="workflow-001",
        display_name="Opening breakout simulation",
        description="Validated visual simulation workflow",
        version=1,
        created_at="2026-07-08T13:30:00Z",
        updated_at="2026-07-08T13:30:00Z",
        document=_workflow_dsl(),
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


def _workflow_simulation_request_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "workflow-001",
        "expected_workflow_version": 1,
        "run_id": "workflow-run-001",
        "requested_at": "2026-07-08T13:29:55Z",
        "evaluated_at": "2026-07-08T13:45:10Z",
        "approval_expires_at": "2026-07-08T13:50:10Z",
        "replay_input_reference": "fixtures/replay/aapl-session.jsonl",
    }


def _workflow_dsl() -> dict[str, object]:
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
            {"id": "e1", "source": "replay-source", "target": "bar-builder"},
            {"id": "e2", "source": "bar-builder", "target": "strategy-trigger"},
            {"id": "e3", "source": "strategy-trigger", "target": "risk-check"},
            {"id": "e4", "source": "risk-check", "target": "approval-ticket"},
            {"id": "e5", "source": "approval-ticket", "target": "fake-broker"},
            {"id": "e6", "source": "fake-broker", "target": "position-update"},
            {"id": "e7", "source": "position-update", "target": "alert"},
            {"id": "e8", "source": "alert", "target": "audit-sink"},
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
