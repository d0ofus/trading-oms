from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from trading_oms_backend.approval_tickets import (
    ApprovalTicket,
    ApprovalTicketBook,
    ApprovalTicketCreateRequest,
)
from trading_oms_backend.bar_builder import Bar, BarBuilderConfig, build_time_bars
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.market_data_replay import MarketDataReplayEvent
from trading_oms_backend.oms_state_machine import (
    OrderStateMachine,
    OrderTransitionRecord,
    OrderTransitionRequest,
)
from trading_oms_backend.order_intents import (
    OrderIntentError,
    OrderIntentProposal,
    OrderIntentProposalBook,
    OrderIntentProposalRequest,
    OrderIntentProtectivePlan,
)
from trading_oms_backend.product_strategy import (
    HistoricalVolumeSession,
    ProductBreakoutSignal,
    ProductBreakoutStrategyConfig,
    run_first_bar_breakout_volume_strategy,
)
from trading_oms_backend.risk_engine import (
    ProtectiveOrderPlan,
    RiskDecision,
    RiskEvaluationRequest,
    RiskPolicy,
    evaluate_risk,
)
from trading_oms_backend.simulation_runs import (
    SimulationRunBook,
    SimulationRunCreateRequest,
    SimulationRunRecord,
    SimulationRunTransitionRequest,
)


class SimulationOrchestrationError(ValueError):
    """Raised when deterministic simulation orchestration cannot proceed safely."""


@dataclass(frozen=True)
class ReplayToApprovalConfig:
    run_id: str
    requested_at: str
    replay_input_reference: str
    strategy_id: str
    proposal_id: str
    risk_request_id: str
    order_id: str
    client_order_id: str
    ticket_id: str
    symbol: str
    quantity: int
    evaluated_at: str
    approval_expires_at: str
    broker_state_known: bool
    existing_risk_request_ids: frozenset[str]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise SimulationOrchestrationError("schema_version must be 1")
        SimulationRunCreateRequest(
            run_id=self.run_id,
            requested_at=self.requested_at,
            replay_input_reference=self.replay_input_reference,
        )
        ProductBreakoutStrategyConfig(strategy_id=self.strategy_id, symbol=self.symbol)
        _validated_identifier(self.proposal_id, "proposal_id")
        _validated_identifier(self.risk_request_id, "risk_request_id")
        _validated_identifier(self.order_id, "order_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_identifier(self.ticket_id, "ticket_id")
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise SimulationOrchestrationError("quantity must be a positive integer")
        _validated_timestamp(self.evaluated_at, "evaluated_at")
        _validated_timestamp(self.approval_expires_at, "approval_expires_at")
        if not isinstance(self.broker_state_known, bool):
            raise SimulationOrchestrationError("broker_state_known must be a boolean")
        if not isinstance(self.existing_risk_request_ids, frozenset):
            raise SimulationOrchestrationError("existing_risk_request_ids must be a frozenset")
        for request_id in self.existing_risk_request_ids:
            _validated_identifier(request_id, "existing_risk_request_ids")


@dataclass(frozen=True)
class ReplayToApprovalResult:
    run: SimulationRunRecord
    bars: tuple[Bar, ...]
    signals: tuple[ProductBreakoutSignal, ...]
    proposal: OrderIntentProposal | None
    risk_decision: RiskDecision | None
    created_order_transition: OrderTransitionRecord | None
    pending_approval_transition: OrderTransitionRecord | None
    approval_ticket: ApprovalTicket | None


class ReplayToApprovalOrchestrator:
    def __init__(self, journal: JsonlEventJournal) -> None:
        if not isinstance(journal, JsonlEventJournal):
            raise SimulationOrchestrationError("journal must be JsonlEventJournal")
        self._journal = journal
        self._runs = SimulationRunBook(journal)
        self._proposals = OrderIntentProposalBook(journal)
        self._orders = OrderStateMachine(journal)
        self._approval_tickets = ApprovalTicketBook(journal)

    def run(
        self,
        *,
        replay_events: Iterable[MarketDataReplayEvent],
        historical_sessions: Iterable[HistoricalVolumeSession],
        risk_policy: RiskPolicy,
        config: ReplayToApprovalConfig,
    ) -> ReplayToApprovalResult:
        if not isinstance(config, ReplayToApprovalConfig):
            raise SimulationOrchestrationError("config must be ReplayToApprovalConfig")
        if not isinstance(risk_policy, RiskPolicy):
            raise SimulationOrchestrationError("risk_policy must be RiskPolicy")

        self._runs.create_run(
            SimulationRunCreateRequest(
                run_id=config.run_id,
                requested_at=config.requested_at,
                replay_input_reference=config.replay_input_reference,
            ),
        )
        self._runs.transition_run(
            SimulationRunTransitionRequest(
                transition_id=f"{config.run_id}-running",
                run_id=config.run_id,
                status="running",
                occurred_at=config.requested_at,
                reason="replay_to_approval_started",
            ),
        )

        try:
            result = self._run_after_start(
                replay_events=replay_events,
                historical_sessions=historical_sessions,
                risk_policy=risk_policy,
                config=config,
            )
            completed_run = self._runs.transition_run(
                SimulationRunTransitionRequest(
                    transition_id=f"{config.run_id}-completed",
                    run_id=config.run_id,
                    status="completed",
                    occurred_at=config.evaluated_at,
                    reason="replay_to_approval_finished",
                ),
            )
            return ReplayToApprovalResult(
                run=completed_run,
                bars=result.bars,
                signals=result.signals,
                proposal=result.proposal,
                risk_decision=result.risk_decision,
                created_order_transition=result.created_order_transition,
                pending_approval_transition=result.pending_approval_transition,
                approval_ticket=result.approval_ticket,
            )
        except Exception as exc:
            self._runs.transition_run(
                SimulationRunTransitionRequest(
                    transition_id=f"{config.run_id}-failed",
                    run_id=config.run_id,
                    status="failed",
                    occurred_at=config.evaluated_at,
                    reason="replay_to_approval_failed",
                ),
            )
            raise SimulationOrchestrationError(f"order intent orchestration failed: {exc}") from exc

    def _run_after_start(
        self,
        *,
        replay_events: Iterable[MarketDataReplayEvent],
        historical_sessions: Iterable[HistoricalVolumeSession],
        risk_policy: RiskPolicy,
        config: ReplayToApprovalConfig,
    ) -> ReplayToApprovalResult:
        bars = tuple(
            build_time_bars(
                replay_events,
                BarBuilderConfig(symbol=config.symbol, timeframe=timedelta(minutes=5)),
            ),
        )
        signals = tuple(
            run_first_bar_breakout_volume_strategy(
                current_session_bars=bars,
                historical_sessions=historical_sessions,
                config=ProductBreakoutStrategyConfig(
                    strategy_id=config.strategy_id,
                    symbol=config.symbol,
                ),
                journal=self._journal,
            ),
        )
        if not signals:
            return ReplayToApprovalResult(
                run=self._runs.get_run(config.run_id),
                bars=bars,
                signals=signals,
                proposal=None,
                risk_decision=None,
                created_order_transition=None,
                pending_approval_transition=None,
                approval_ticket=None,
            )

        signal = signals[0]
        proposal = self._create_proposal(config, signal)
        risk_decision = self._evaluate_risk(config, proposal, risk_policy, signal)
        if risk_decision.result != "passed":
            return ReplayToApprovalResult(
                run=self._runs.get_run(config.run_id),
                bars=bars,
                signals=signals,
                proposal=proposal,
                risk_decision=risk_decision,
                created_order_transition=None,
                pending_approval_transition=None,
                approval_ticket=None,
            )

        created_transition, pending_transition = self._create_pending_approval_order(
            config,
            proposal,
            risk_decision,
        )
        ticket = self._approval_tickets.create_ticket(
            ApprovalTicketCreateRequest(
                ticket_id=config.ticket_id,
                order_id=config.order_id,
                client_order_id=config.client_order_id,
                symbol=proposal.symbol,
                side=proposal.side,
                quantity=proposal.quantity,
                risk_intent=proposal.risk_intent,
                risk_decision_id=risk_decision.request_id,
                risk_decision_result=risk_decision.result,
                oms_transition_reference=pending_transition.transition_id,
                oms_state=pending_transition.new_state,
                created_at=config.evaluated_at,
                expires_at=config.approval_expires_at,
                reason="risk_passed_requires_human_approval",
            ),
        )
        return ReplayToApprovalResult(
            run=self._runs.get_run(config.run_id),
            bars=bars,
            signals=signals,
            proposal=proposal,
            risk_decision=risk_decision,
            created_order_transition=created_transition,
            pending_approval_transition=pending_transition,
            approval_ticket=ticket,
        )

    def _create_proposal(
        self,
        config: ReplayToApprovalConfig,
        signal: ProductBreakoutSignal,
    ) -> OrderIntentProposal:
        try:
            return self._proposals.propose(
                OrderIntentProposalRequest(
                    proposal_id=config.proposal_id,
                    source_signal_reference=_latest_journal_reference(
                        self._journal,
                        "strategy.signal.generated",
                    ),
                    symbol=signal.symbol,
                    side="buy",
                    risk_intent="increase",
                    quantity=config.quantity,
                    order_type="market",
                    reference_price=signal.breakout_bar_high,
                    proposed_at=config.evaluated_at,
                    protective_order_plan=OrderIntentProtectivePlan(
                        kind="stop_loss",
                        stop_price=signal.first_bar_high,
                    ),
                ),
            )
        except OrderIntentError as exc:
            raise SimulationOrchestrationError(f"order intent proposal failed: {exc}") from exc

    def _evaluate_risk(
        self,
        config: ReplayToApprovalConfig,
        proposal: OrderIntentProposal,
        risk_policy: RiskPolicy,
        signal: ProductBreakoutSignal,
    ) -> RiskDecision:
        protective_order = (
            None
            if proposal.protective_order_plan is None
            else ProtectiveOrderPlan(
                kind=proposal.protective_order_plan.kind,
                stop_price=proposal.protective_order_plan.stop_price,
            )
        )
        return evaluate_risk(
            RiskEvaluationRequest(
                request_id=config.risk_request_id,
                symbol=proposal.symbol,
                side=proposal.side,
                risk_intent=proposal.risk_intent,
                quantity=proposal.quantity,
                reference_price=proposal.reference_price,
                market_data_timestamp=signal.trigger_bar_end_timestamp,
                evaluated_at=config.evaluated_at,
                broker_state_known=config.broker_state_known,
                protective_order=protective_order,
                protective_exception_approved=proposal.protective_exception_reference is not None,
                existing_request_ids=config.existing_risk_request_ids,
            ),
            risk_policy,
            self._journal,
        )

    def _create_pending_approval_order(
        self,
        config: ReplayToApprovalConfig,
        proposal: OrderIntentProposal,
        risk_decision: RiskDecision,
    ) -> tuple[OrderTransitionRecord, OrderTransitionRecord]:
        created = self._orders.apply_transition(
            OrderTransitionRequest(
                transition_id=f"{config.order_id}-created",
                order_id=config.order_id,
                client_order_id=config.client_order_id,
                symbol=proposal.symbol,
                side=proposal.side,
                quantity=proposal.quantity,
                risk_intent=proposal.risk_intent,
                target_state="CREATED",
                occurred_at=config.evaluated_at,
                reason="risk_passed_order_created",
                risk_decision_id=risk_decision.request_id,
            ),
        )
        pending_approval = self._orders.apply_transition(
            OrderTransitionRequest(
                transition_id=f"{config.order_id}-pending-approval",
                order_id=config.order_id,
                client_order_id=config.client_order_id,
                symbol=proposal.symbol,
                side=proposal.side,
                quantity=proposal.quantity,
                risk_intent=proposal.risk_intent,
                target_state="PENDING_APPROVAL",
                occurred_at=config.evaluated_at,
                reason="risk_passed_requires_human_approval",
                risk_decision_id=risk_decision.request_id,
            ),
        )
        return created, pending_approval


def _latest_journal_reference(journal: JsonlEventJournal, event_type: str) -> str:
    for record in reversed(journal.read_all()):
        if record.event_type == event_type:
            return f"journal_sequence:{record.sequence}"
    raise SimulationOrchestrationError(f"journal event does not exist: {event_type}")


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SimulationOrchestrationError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise SimulationOrchestrationError(f"{field_name} must not contain whitespace padding")
    return value


def _validated_timestamp(value: str, field_name: str) -> None:
    SimulationRunTransitionRequest(
        transition_id=f"{field_name}-validation",
        run_id="timestamp-validation-run",
        status="running",
        occurred_at=value,
        reason="timestamp_validation",
    )
