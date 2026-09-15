from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from test_workflow_dsl_v2 import valid_v2_workflow

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.strategy_run_service import (
    DatasetRegistration,
    StrategyRunDraftRequest,
    StrategyRunError,
    StrategyRunService,
)
from trading_oms_backend.typed_strategy_simulation import NormalizedTrade, RiskContext
from trading_oms_backend.typed_workflow_definitions import (
    SqliteWorkflowDefinitionStore,
    WorkflowDefinitionSaveRequest,
)


def test_dataset_draft_arm_and_simulate_are_persisted_and_audited() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        service, workflow_store = _service(root)
        workflow = workflow_store.create_workflow(_workflow_request())
        dataset = service.register_dataset(_dataset_registration(), _trades())
        draft = service.create_draft(
            workflow.workflow_id,
            _draft_request(),
            requested_by="strategy-operator-001",
        )
        armed = service.arm_run(
            draft.run_id,
            authorized_by="strategy-operator-001",
            authorized_at="2026-07-08T13:00:00Z",
            expires_at="2026-07-08T20:00:00Z",
        )
        completed = service.simulate_run(
            draft.run_id,
            risk_context=_risk_context(),
        )

        assert dataset.checksum is not None
        assert len(dataset.manifest_checksum) == 64
        assert dataset.manifest_checksum != dataset.checksum
        assert dataset.trade_count == 5
        assert draft.state == "draft"
        assert draft.envelope.maximum_dollar_loss == "100.00"
        assert draft.envelope.opening_range_minutes == 5
        assert draft.envelope.entry_lifetime == "DAY"
        assert draft.envelope.position_lifetime == {"kind": "hold_with_protective_stop"}
        assert armed.state == "armed"
        assert armed.authorization is not None
        assert armed.authorization.fingerprint == draft.fingerprint
        assert completed.state == "completed"
        assert completed.result is not None
        assert completed.result.status == "position_open_protected"
        assert service.get_run(draft.run_id) == completed
        assert service.simulate_run(draft.run_id, risk_context=_risk_context()) == completed

        restored_service = StrategyRunService(
            workflow_store,
            database_path=root / "strategy.sqlite3",
            dataset_directory=root / "datasets",
            journal=JsonlEventJournal(root / "strategy-journal.jsonl"),
            clock=lambda: "2026-07-08T13:00:00Z",
        )
        assert restored_service.get_dataset(dataset.dataset_id) == dataset
        assert restored_service.get_run(draft.run_id) == completed
        with closing(sqlite3.connect(root / "strategy.sqlite3")) as connection:
            assert connection.execute(
                "SELECT version, description FROM strategy_schema_migrations"
            ).fetchall() == [(1, "workflow-dsl-v2-foundation")]
        event_types = [record.event_type for record in restored_service.journal_records()]
        assert event_types[:3] == [
            "market_data.dataset.registered",
            "workflow.run.drafted",
            "workflow.run.armed",
        ]
        assert "workflow.risk.passed" in event_types
        assert "workflow.order.filled" in event_types
        assert event_types[-1] == "workflow.run.completed"


def test_disarm_blocks_simulation_and_workflow_edit_disarms_prior_version() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        service, workflow_store = _service(root)
        workflow = workflow_store.create_workflow(_workflow_request())
        service.register_dataset(_dataset_registration(), _trades())
        draft = service.create_draft(
            workflow.workflow_id,
            _draft_request(),
            requested_by="strategy-operator-001",
        )
        service.arm_run(
            draft.run_id,
            authorized_by="strategy-operator-001",
            authorized_at="2026-07-08T13:00:00Z",
            expires_at="2026-07-08T20:00:00Z",
        )

        edited_document = valid_v2_workflow()
        edited_document["workflow_id"] = "strategy-workflow-001"
        edited_document["nodes"][4]["config"] = {"minutes": 1}
        workflow_store.update_workflow(
            workflow.workflow_id,
            _workflow_request(
                document=edited_document,
                requested_at="2026-07-08T13:01:00Z",
                expected_version=1,
            ),
        )
        disarmed_count = service.disarm_runs_for_workflow_edit(
            workflow.workflow_id,
            current_version=2,
            disarmed_at="2026-07-08T13:01:00Z",
            actor="strategy-author-001",
        )

        assert disarmed_count == 1
        assert service.get_run(draft.run_id).state == "disarmed"
        with pytest.raises(StrategyRunError, match="armed"):
            service.simulate_run(draft.run_id, risk_context=_risk_context())


def test_dataset_is_immutable_and_incomplete_data_cannot_create_a_draft() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        service, workflow_store = _service(root)
        workflow_store.create_workflow(_workflow_request())
        dataset = service.register_dataset(_dataset_registration(), _trades())

        assert service.register_dataset(_dataset_registration(), _trades()) == dataset
        changed = _trades()
        changed[-1] = NormalizedTrade("2026-07-08T13:35:03Z", "102.00", 5)
        with pytest.raises(StrategyRunError, match="immutable"):
            service.register_dataset(_dataset_registration(), changed)

        service.register_dataset(
            _dataset_registration(
                dataset_id="dataset-incomplete",
                complete=False,
                quality="gap_detected",
            ),
            _trades(),
        )
        with pytest.raises(StrategyRunError, match="complete"):
            service.create_draft(
                "strategy-workflow-001",
                _draft_request(dataset_id="dataset-incomplete", run_id="strategy-run-002"),
                requested_by="strategy-operator-001",
            )


def test_emergency_disarm_covers_every_active_run_and_is_idempotent() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        service, workflow_store = _service(root)
        workflow_store.create_workflow(_workflow_request())
        service.register_dataset(_dataset_registration(), _trades())
        service.create_draft(
            "strategy-workflow-001",
            _draft_request(),
            requested_by="strategy-operator-001",
        )
        service.arm_run(
            "strategy-run-001",
            authorized_by="strategy-operator-001",
            authorized_at="2026-07-08T13:00:00Z",
            expires_at="2026-07-08T20:00:00Z",
        )

        assert (
            service.disarm_all_active(
                disarmed_at="2026-07-08T13:01:00Z",
                actor="admin-operator-001",
                reason="emergency_stop_activated",
            )
            == 1
        )
        assert (
            service.disarm_all_active(
                disarmed_at="2026-07-08T13:01:01Z",
                actor="admin-operator-001",
                reason="emergency_stop_activated",
            )
            == 0
        )
        assert service.get_run("strategy-run-001").state == "disarmed"


def test_degraded_five_second_dataset_is_retained_but_fails_closed_for_now() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        service, workflow_store = _service(root)
        workflow_store.create_workflow(_workflow_request())
        service.register_dataset(
            _dataset_registration(
                dataset_id="dataset-five-second",
                resolution="five_second_bars",
                quality="degraded",
            ),
            _trades(),
        )

        with pytest.raises(StrategyRunError, match="pessimistic bar-ordering"):
            service.create_draft(
                "strategy-workflow-001",
                _draft_request(
                    dataset_id="dataset-five-second",
                    run_id="strategy-run-five-second",
                ),
                requested_by="strategy-operator-001",
            )

        service.register_dataset(
            _dataset_registration(
                dataset_id="dataset-degraded-ticks",
                quality="degraded",
            ),
            _trades(),
        )
        with pytest.raises(StrategyRunError, match="degraded datasets"):
            service.create_draft(
                "strategy-workflow-001",
                _draft_request(
                    dataset_id="dataset-degraded-ticks",
                    run_id="strategy-run-degraded-ticks",
                ),
                requested_by="strategy-operator-001",
            )


def test_typed_condition_position_lifetime_fails_closed_until_runtime_exists() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        service, workflow_store = _service(root)
        document = valid_v2_workflow()
        document["workflow_id"] = "strategy-workflow-001"
        position_lifetime = next(
            node for node in document["nodes"] if node["type"] == "position_lifetime"
        )
        position_lifetime["config"] = {"kind": "exit_on_typed_condition"}
        workflow_store.create_workflow(_workflow_request(document=document))
        service.register_dataset(_dataset_registration(), _trades())

        with pytest.raises(StrategyRunError, match="typed-exit runtime"):
            service.create_draft(
                "strategy-workflow-001",
                _draft_request(),
                requested_by="strategy-operator-001",
            )


def test_failed_risk_decision_is_journaled_before_the_run_block() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        service, workflow_store = _service(root)
        workflow_store.create_workflow(_workflow_request())
        service.register_dataset(_dataset_registration(), _trades())
        service.create_draft(
            "strategy-workflow-001",
            _draft_request(),
            requested_by="strategy-operator-001",
        )
        service.arm_run(
            "strategy-run-001",
            authorized_by="strategy-operator-001",
            authorized_at="2026-07-08T13:00:00Z",
            expires_at="2026-07-08T20:00:00Z",
        )

        with pytest.raises(StrategyRunError, match="buying power"):
            service.simulate_run(
                "strategy-run-001",
                risk_context=RiskContext(
                    buying_power="10.00",
                    concurrent_positions=0,
                    current_symbol_exposure="0.00",
                    daily_realized_loss="0.00",
                ),
            )

        assert [record.event_type for record in service.journal_records()][-2:] == [
            "workflow.risk.blocked",
            "workflow.run.blocked",
        ]


def test_expired_chase_persists_an_order_plan_but_no_position() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        service, workflow_store = _service(root)
        workflow_store.create_workflow(_workflow_request())
        trades = _trades()
        trades[3] = NormalizedTrade("2026-07-08T13:35:02Z", "101.80", 4)
        service.register_dataset(_dataset_registration(), trades)
        service.create_draft(
            "strategy-workflow-001",
            _draft_request(),
            requested_by="strategy-operator-001",
        )
        service.arm_run(
            "strategy-run-001",
            authorized_by="strategy-operator-001",
            authorized_at="2026-07-08T13:00:00Z",
            expires_at="2026-07-08T20:00:00Z",
        )

        completed = service.simulate_run(
            "strategy-run-001",
            risk_context=_risk_context(),
        )

        assert completed.result is not None
        assert completed.result.status == "expired_chase"
        with closing(sqlite3.connect(root / "strategy.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM strategy_orders").fetchone() == (1,)
            assert connection.execute("SELECT COUNT(*) FROM strategy_positions").fetchone() == (0,)


def _service(
    root: Path,
) -> tuple[StrategyRunService, SqliteWorkflowDefinitionStore]:
    database_path = root / "strategy.sqlite3"
    workflow_store = SqliteWorkflowDefinitionStore(database_path)
    return (
        StrategyRunService(
            workflow_store,
            database_path=database_path,
            dataset_directory=root / "datasets",
            journal=JsonlEventJournal(root / "strategy-journal.jsonl"),
            clock=lambda: "2026-07-08T13:00:00Z",
        ),
        workflow_store,
    )


def _workflow_request(**overrides: object) -> WorkflowDefinitionSaveRequest:
    document = valid_v2_workflow()
    document["workflow_id"] = "strategy-workflow-001"
    values: dict[str, object] = {
        "schema_version": 2,
        "workflow_id": "strategy-workflow-001",
        "display_name": "First five minute breakout",
        "description": "Typed deterministic simulation workflow",
        "document": document,
        "requested_at": "2026-07-08T12:00:00Z",
    }
    values.update(overrides)
    return WorkflowDefinitionSaveRequest(**values)


def _dataset_registration(**overrides: object) -> DatasetRegistration:
    values: dict[str, object] = {
        "dataset_id": "dataset-aapl-2026-07-08",
        "symbol": "AAPL",
        "contract_id": "fixture-contract-aapl",
        "primary_exchange": "NASDAQ",
        "currency": "USD",
        "routing": "SMART",
        "session_date": "2026-07-08",
        "session_timezone": "America/New_York",
        "rth_open": "09:30:00",
        "rth_close": "16:00:00",
        "source": "local_fixture",
        "resolution": "trade_ticks",
        "complete": True,
        "quality": "complete",
        "registered_at": "2026-07-08T12:30:00Z",
    }
    values.update(overrides)
    return DatasetRegistration(**values)


def _draft_request(**overrides: object) -> StrategyRunDraftRequest:
    values: dict[str, object] = {
        "run_id": "strategy-run-001",
        "workflow_version": 1,
        "symbol": "AAPL",
        "maximum_dollar_loss": "100.00",
        "runtime_mode": "historical_simulation",
        "dataset_id": "dataset-aapl-2026-07-08",
        "expires_at": "2026-07-08T20:00:00Z",
        "requested_at": "2026-07-08T12:45:00Z",
    }
    values.update(overrides)
    return StrategyRunDraftRequest(**values)


def _risk_context() -> RiskContext:
    return RiskContext(
        buying_power="50000.00",
        concurrent_positions=0,
        current_symbol_exposure="0.00",
        daily_realized_loss="0.00",
    )


def _trades() -> list[NormalizedTrade]:
    return [
        NormalizedTrade("2026-07-08T13:30:00Z", "99.50", 1),
        NormalizedTrade("2026-07-08T13:34:59Z", "101.00", 2),
        NormalizedTrade("2026-07-08T13:35:01Z", "101.01", 3),
        NormalizedTrade("2026-07-08T13:35:02Z", "101.03", 4),
        NormalizedTrade("2026-07-08T13:35:03Z", "101.04", 5),
    ]
