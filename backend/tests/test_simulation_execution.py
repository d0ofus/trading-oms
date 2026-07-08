from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from trading_oms_backend.bar_builder import Bar
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


def test_approved_simulation_order_fills_through_oms_and_fake_broker(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = _orchestrator_with_pending_ticket(journal)

    result = orchestrator.execute_approved_order(execution_request())

    assert result.approval_decision.new_status == "approved"
    assert result.approved_transition.new_state == "APPROVED"
    assert result.submitted_transition.new_state == "SUBMITTED"
    assert result.acknowledged_transition is not None
    assert result.acknowledged_transition.new_state == "ACKNOWLEDGED"
    assert result.final_order_transition is not None
    assert result.final_order_transition.new_state == "FILLED"
    assert [transition.state for transition in result.broker_transitions] == [
        "acknowledged",
        "filled",
    ]

    event_types = [record.event_type for record in journal.read_all()]
    assert event_types.count("approval.ticket.decided") == 1
    assert event_types.count("fake_broker.order.transitioned") == 2
    assert event_types[-1] == "oms.order.transitioned"
    assert journal.read_all()[-1].payload["new_state"] == "FILLED"


def test_approved_simulation_order_reject_path_journals_fake_reject_and_oms_reject(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = _orchestrator_with_pending_ticket(journal)

    result = orchestrator.execute_approved_order(
        execution_request(execution_id="execution-reject-001", broker_outcome="reject"),
    )

    assert result.acknowledged_transition is None
    assert result.final_order_transition is not None
    assert result.final_order_transition.new_state == "REJECTED"
    assert [transition.state for transition in result.broker_transitions] == ["rejected"]
    assert "fake_broker.order.transitioned" in [record.event_type for record in journal.read_all()]


def test_approved_simulation_order_cancel_path_requests_cancel_before_oms_cancelled(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = _orchestrator_with_pending_ticket(journal)

    result = orchestrator.execute_approved_order(
        execution_request(execution_id="execution-cancel-001", broker_outcome="cancel"),
    )

    assert result.acknowledged_transition is not None
    assert result.cancel_requested_transition is not None
    assert result.cancel_requested_transition.new_state == "CANCEL_REQUESTED"
    assert result.final_order_transition is not None
    assert result.final_order_transition.new_state == "CANCELLED"
    assert [transition.state for transition in result.broker_transitions] == [
        "acknowledged",
        "cancelled",
    ]


def test_approved_simulation_order_execution_id_is_idempotent(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = _orchestrator_with_pending_ticket(journal)
    request = execution_request()

    first = orchestrator.execute_approved_order(request)
    event_count = len(journal.read_all())
    second = orchestrator.execute_approved_order(request)

    assert second == first
    assert len(journal.read_all()) == event_count


def test_approved_simulation_order_cannot_execute_after_terminal_order_state(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    orchestrator = _orchestrator_with_pending_ticket(journal)
    orchestrator.execute_approved_order(execution_request())

    with pytest.raises(SimulationOrchestrationError, match="PENDING_APPROVAL"):
        orchestrator.execute_approved_order(
            execution_request(
                execution_id="execution-second-001",
                decision_id="approval-decision-second-001",
                decision_reference="manual-simulation-approval-second-001",
            ),
        )


def test_simulation_execution_module_does_not_define_transport_or_http_behavior() -> None:
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


def _orchestrator_with_pending_ticket(
    journal: JsonlEventJournal,
) -> ReplayToApprovalOrchestrator:
    orchestrator = ReplayToApprovalOrchestrator(journal)
    result = orchestrator.run(
        replay_events=replay_events(),
        historical_sessions=historical_sessions(),
        risk_policy=risk_policy(),
        config=orchestration_config(),
    )
    assert result.approval_ticket is not None
    assert result.approval_ticket.status == "pending"
    return orchestrator


def execution_request(**overrides: Any) -> ApprovedOrderExecutionRequest:
    values = {
        "execution_id": "execution-fill-001",
        "order_id": "order-001",
        "ticket_id": "approval-ticket-001",
        "decision_id": "approval-decision-fill-001",
        "decided_at": "2026-07-08T13:46:00Z",
        "actor": "human-operator-001",
        "decision_reference": "manual-simulation-approval-fill-001",
        "reason": "operator_approved_simulation_order",
        "broker_outcome": "fill",
    }
    values.update(overrides)
    return ApprovedOrderExecutionRequest(**values)


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


def risk_policy() -> RiskPolicy:
    return RiskPolicy(
        max_order_quantity=100,
        max_order_notional=10_000.0,
        max_market_data_age_seconds=30,
        allowed_symbols=("AAPL",),
    )


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
