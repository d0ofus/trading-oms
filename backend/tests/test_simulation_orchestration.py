from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.emergency_stop import (
    EMERGENCY_STOP_BLOCKED_EVENT_TYPE,
    EmergencyStopChangeRequest,
    EmergencyStopService,
)
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.market_data_replay import MarketDataReplayEvent
from trading_oms_backend.product_strategy import HistoricalVolumeSession
from trading_oms_backend.risk_engine import RiskPolicy
from trading_oms_backend.simulation_orchestration import (
    ApprovedOrderExecutionRequest,
    ReplayToApprovalConfig,
    ReplayToApprovalOrchestrator,
    SimulationOrchestrationError,
)


def test_replay_to_approval_orchestration_creates_pending_ticket_after_risk_pass(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = ReplayToApprovalOrchestrator(journal)

    result = orchestrator.run(
        replay_events=replay_events(),
        historical_sessions=historical_sessions(),
        risk_policy=risk_policy(),
        config=orchestration_config(),
    )

    assert result.run.status == "completed"
    assert len(result.bars) == 3
    assert len(result.signals) == 1
    assert result.proposal is not None
    assert result.proposal.status == "proposed_non_routable"
    assert result.risk_decision is not None
    assert result.risk_decision.result == "passed"
    assert result.created_order_transition is not None
    assert result.created_order_transition.new_state == "CREATED"
    assert result.pending_approval_transition is not None
    assert result.pending_approval_transition.new_state == "PENDING_APPROVAL"
    assert result.approval_ticket is not None
    assert result.approval_ticket.status == "pending"
    assert result.approval_ticket.risk_decision_id == "risk-001"

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        "simulation_run.created",
        "simulation_run.status_changed",
        "strategy.signal.generated",
        "order_intent.proposed",
        "risk.decision.evaluated",
        "oms.order.transitioned",
        "oms.order.transitioned",
        "approval.ticket.created",
        "simulation_run.status_changed",
    ]
    assert "fake_broker.order.transitioned" not in [record.event_type for record in records]


@pytest.mark.parametrize(
    ("config_kwargs", "failed_check"),
    [
        ({"evaluated_at": "2026-07-08T13:46:00Z"}, "market_data_freshness"),
        ({"broker_state_known": False}, "broker_state_known"),
        ({"existing_risk_request_ids": frozenset({"risk-001"})}, "duplicate_request"),
    ],
)
def test_replay_to_approval_orchestration_blocks_before_ticket_when_risk_fails(
    config_kwargs: dict[str, Any],
    failed_check: str,
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = ReplayToApprovalOrchestrator(journal)

    result = orchestrator.run(
        replay_events=replay_events(),
        historical_sessions=historical_sessions(),
        risk_policy=risk_policy(max_market_data_age_seconds=30),
        config=orchestration_config(**config_kwargs),
    )

    assert result.risk_decision is not None
    assert result.risk_decision.result == "blocked"
    assert failed_check in [check.name for check in result.risk_decision.failed_checks()]
    assert result.created_order_transition is None
    assert result.pending_approval_transition is None
    assert result.approval_ticket is None
    assert result.run.status == "completed"

    event_types = [record.event_type for record in journal.read_all()]
    assert "risk.decision.evaluated" in event_types
    assert "approval.ticket.created" not in event_types
    assert "fake_broker.order.transitioned" not in event_types


def test_replay_to_approval_orchestration_returns_no_proposal_without_signal(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = ReplayToApprovalOrchestrator(journal)

    result = orchestrator.run(
        replay_events=no_breakout_replay_events(),
        historical_sessions=historical_sessions(),
        risk_policy=risk_policy(),
        config=orchestration_config(),
    )

    assert result.signals == ()
    assert result.proposal is None
    assert result.risk_decision is None
    assert result.approval_ticket is None
    assert result.run.status == "completed"
    assert [record.event_type for record in journal.read_all()] == [
        "simulation_run.created",
        "simulation_run.status_changed",
        "simulation_run.status_changed",
    ]


def test_replay_to_approval_orchestration_blocks_duplicate_order_intent_ids(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = ReplayToApprovalOrchestrator(journal)
    orchestrator.run(
        replay_events=replay_events(),
        historical_sessions=historical_sessions(),
        risk_policy=risk_policy(),
        config=orchestration_config(),
    )

    with pytest.raises(SimulationOrchestrationError, match="order intent"):
        orchestrator.run(
            replay_events=replay_events(),
            historical_sessions=historical_sessions(),
            risk_policy=risk_policy(),
            config=orchestration_config(
                run_id="sim-run-002",
                proposal_id="intent-001",
                risk_request_id="risk-002",
                order_id="order-002",
                client_order_id="client-002",
                ticket_id="approval-ticket-002",
            ),
        )

    event_types = [record.event_type for record in journal.read_all()]
    assert event_types.count("order_intent.proposed") == 1
    assert event_types[-1] == "simulation_run.status_changed"
    assert journal.read_all()[-1].payload["status"] == "failed"


def test_active_emergency_stop_blocks_approved_execution_before_oms_and_fake_broker(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    emergency_stop = EmergencyStopService(journal)
    orchestrator = ReplayToApprovalOrchestrator(
        journal,
        emergency_stop_service=emergency_stop,
    )
    result = orchestrator.run(
        replay_events=replay_events(),
        historical_sessions=historical_sessions(),
        risk_policy=risk_policy(),
        config=orchestration_config(),
    )
    assert result.pending_approval_transition is not None
    emergency_stop.activate(
        EmergencyStopChangeRequest(
            event_id="emergency-stop-activate-001",
            requested_at="2026-07-08T13:45:30Z",
            actor="admin-operator-001",
            reason="operator_review",
        ),
    )

    with pytest.raises(SimulationOrchestrationError, match="emergency stop is active"):
        orchestrator.execute_approved_order(
            ApprovedOrderExecutionRequest(
                execution_id="execution-001",
                order_id="order-001",
                ticket_id="approval-ticket-001",
                decision_id="approval-decision-001",
                decided_at="2026-07-08T13:46:00Z",
                actor="approver-operator-001",
                decision_reference="manual-simulation-approval-001",
                reason="operator_reviewed_simulation_ticket",
            ),
        )

    event_types = [record.event_type for record in journal.read_all()]
    assert EMERGENCY_STOP_BLOCKED_EVENT_TYPE in event_types
    assert "approval.ticket.decided" not in event_types
    assert event_types.count("oms.order.transitioned") == 2
    assert "fake_broker.order.transitioned" not in event_types


def test_replay_to_approval_config_rejects_invalid_values() -> None:
    with pytest.raises(SimulationOrchestrationError, match="quantity"):
        orchestration_config(quantity=0)

    with pytest.raises(SimulationOrchestrationError, match="broker_state_known"):
        orchestration_config(broker_state_known="yes")

    with pytest.raises(SimulationOrchestrationError, match="existing_risk_request_ids"):
        orchestration_config(existing_risk_request_ids={"risk-001"})


def test_simulation_orchestration_module_does_not_define_transport_or_http_behavior() -> None:
    import trading_oms_backend.simulation_orchestration as simulation_orchestration

    source = inspect.getsource(simulation_orchestration).lower()
    forbidden_source_tokens = [
        "@app.post",
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
    ]
    for token in forbidden_source_tokens:
        assert token not in source


def orchestration_config(**overrides: Any) -> ReplayToApprovalConfig:
    values = {
        "run_id": "sim-run-001",
        "requested_at": "2026-07-08T13:29:55Z",
        "replay_input_reference": "fixtures/replay/aapl-session.jsonl",
        "strategy_id": "first-bar-breakout-demo",
        "proposal_id": "intent-001",
        "risk_request_id": "risk-001",
        "order_id": "order-001",
        "client_order_id": "client-001",
        "ticket_id": "approval-ticket-001",
        "symbol": "AAPL",
        "quantity": 10,
        "evaluated_at": "2026-07-08T13:45:10Z",
        "approval_expires_at": "2026-07-08T13:50:10Z",
        "broker_state_known": True,
        "existing_risk_request_ids": frozenset(),
    }
    values.update(overrides)
    return ReplayToApprovalConfig(**values)


def risk_policy(**overrides: Any) -> RiskPolicy:
    values = {
        "max_order_quantity": 100,
        "max_order_notional": 10_000.0,
        "max_market_data_age_seconds": 30,
        "allowed_symbols": ("AAPL",),
    }
    values.update(overrides)
    return RiskPolicy(**values)


def historical_sessions() -> tuple[HistoricalVolumeSession, ...]:
    return tuple(
        HistoricalVolumeSession(
            session_id=f"historical-session-{index:02d}",
            bars=(
                historical_bar(0, high=101.00, close=100.50, volume=50.0),
                historical_bar(1, high=101.25, close=100.75, volume=70.0),
                historical_bar(2, high=101.40, close=101.00, volume=80.0),
            ),
        )
        for index in range(10)
    )


def historical_bar(index: int, *, high: float, close: float, volume: float) -> Bar:
    start_minutes = 30 + (index * 5)
    end_minutes = start_minutes + 5
    return Bar(
        symbol="AAPL",
        timeframe_seconds=300,
        start_timestamp=f"2026-07-01T13:{start_minutes:02d}:00Z",
        end_timestamp=f"2026-07-01T13:{end_minutes:02d}:00Z",
        open=close,
        high=high,
        low=close - 0.5,
        close=close,
        volume=volume,
        event_count=1,
    )


def replay_events() -> tuple[MarketDataReplayEvent, ...]:
    return (
        replay_event(1, "2026-07-08T13:30:00Z", price=100.50, volume=50.0),
        replay_event(2, "2026-07-08T13:31:00Z", price=101.50, volume=50.0),
        replay_event(3, "2026-07-08T13:35:00Z", price=101.40, volume=80.0),
        replay_event(4, "2026-07-08T13:40:00Z", price=102.20, volume=200.0),
    )


def no_breakout_replay_events() -> tuple[MarketDataReplayEvent, ...]:
    return (
        replay_event(1, "2026-07-08T13:30:00Z", price=100.50, volume=50.0),
        replay_event(2, "2026-07-08T13:31:00Z", price=101.50, volume=50.0),
        replay_event(3, "2026-07-08T13:35:00Z", price=101.40, volume=200.0),
        replay_event(4, "2026-07-08T13:40:00Z", price=101.45, volume=200.0),
    )


def replay_event(
    sequence: int,
    timestamp: str,
    *,
    price: float,
    volume: float,
) -> MarketDataReplayEvent:
    return MarketDataReplayEvent(
        sequence=sequence,
        timestamp=timestamp,
        symbol="AAPL",
        event_type="trade",
        payload={"price": price, "volume": volume},
    )
