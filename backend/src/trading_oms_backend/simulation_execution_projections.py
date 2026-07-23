from __future__ import annotations

from dataclasses import dataclass, replace

from trading_oms_backend.approval_tickets import ApprovalDecisionRecord, ApprovalTicket
from trading_oms_backend.event_journal import JournalRecord
from trading_oms_backend.order_intents import OrderIntentProposal
from trading_oms_backend.product_strategy import ProductBreakoutSignal
from trading_oms_backend.read_models import (
    AlertReadModel,
    ApprovalTicketReadModel,
    AuditEventReadModel,
    OperationsReadModel,
    OrderReadModel,
    PositionReadModel,
    ReadModelProvenance,
    RiskDecisionReadModel,
    SignalReadModel,
    SimulationDecisionAttributionReadModel,
    SimulationExecutionAttributionReadModel,
)
from trading_oms_backend.risk_engine import RiskDecision
from trading_oms_backend.workflow_simulation_runs import (
    WorkflowSimulationProjectionSource,
)


class SimulationExecutionProjectionError(ValueError):
    """Raised when durable simulation evidence cannot form one safe read snapshot."""


_LIFECYCLE_RESOURCES = {
    "audit_events",
    "signals",
    "risk_decisions",
    "approval_tickets",
    "orders",
    "positions",
    "alerts",
}
_DOWNSTREAM_RESOURCES = {"orders", "positions", "alerts"}
_LIFECYCLE_CLASSIFICATIONS = (
    "simulated",
    "local_only",
    "externally_unverified",
)
_EXECUTION_CLASSIFICATIONS = (
    "simulated",
    "local_only",
    "fake_broker_derived",
    "externally_unverified",
)


@dataclass(frozen=True)
class SimulationLifecycleEvidence:
    source: WorkflowSimulationProjectionSource
    signal_record: JournalRecord
    signal: ProductBreakoutSignal
    proposal_record: JournalRecord
    proposal: OrderIntentProposal
    risk_record: JournalRecord
    risk_decision: RiskDecision
    ticket_record: JournalRecord
    created_ticket: ApprovalTicket
    decision_record: JournalRecord | None
    approval_decision: ApprovalDecisionRecord | None
    current_ticket: ApprovalTicket
    attribution: SimulationDecisionAttributionReadModel


def project_simulation_executions(
    base: OperationsReadModel,
    sources: tuple[WorkflowSimulationProjectionSource, ...],
) -> OperationsReadModel:
    if not isinstance(base, OperationsReadModel):
        raise SimulationExecutionProjectionError("base read model is invalid")
    if not isinstance(sources, tuple) or any(
        not isinstance(item, WorkflowSimulationProjectionSource) for item in sources
    ):
        raise SimulationExecutionProjectionError("projection sources are invalid")
    if not sources:
        return base

    ordered_sources = tuple(
        sorted(
            sources,
            key=lambda item: (
                item.run.updated_at,
                item.run.workflow_id,
                item.run.run_id,
            ),
        )
    )
    lifecycles: list[SimulationLifecycleEvidence] = []
    seen_run_ids: set[str] = set()
    seen_signal_ids: set[str] = set()
    seen_order_intent_ids: set[str] = set()
    seen_risk_decision_ids: set[str] = set()
    seen_approval_ticket_ids: set[str] = set()
    seen_approval_decision_ids: set[str] = set()
    seen_journal_sequences: set[int] = set()

    for source in ordered_sources:
        lifecycle = validated_simulation_lifecycle(source)
        _claim_unique(seen_run_ids, source.run.run_id, "run")
        _claim_unique(seen_signal_ids, lifecycle.attribution.signal_id, "signal")
        _claim_unique(
            seen_order_intent_ids,
            lifecycle.attribution.order_intent_id,
            "order intent",
        )
        _claim_unique(
            seen_risk_decision_ids,
            lifecycle.attribution.risk_decision_id,
            "risk decision",
        )
        _claim_unique(
            seen_approval_ticket_ids,
            lifecycle.attribution.approval_ticket_id,
            "approval ticket",
        )
        if lifecycle.attribution.approval_decision_id is not None:
            _claim_unique(
                seen_approval_decision_ids,
                lifecycle.attribution.approval_decision_id,
                "approval decision",
            )
        for record in source.journal_manifest:
            if record.sequence in seen_journal_sequences:
                raise SimulationExecutionProjectionError("duplicate audit sequence")
            seen_journal_sequences.add(record.sequence)
        lifecycles.append(lifecycle)

    signals: list[SignalReadModel] = []
    risk_decisions: list[RiskDecisionReadModel] = []
    approval_tickets: list[ApprovalTicketReadModel] = []
    orders: list[OrderReadModel] = []
    positions: list[PositionReadModel] = []
    alerts: list[AlertReadModel] = []
    audit_events: list[AuditEventReadModel] = []
    seen_execution_ids: set[str] = set()
    seen_order_ids: set[str] = set()
    seen_position_ids: set[str] = set()
    seen_alert_ids: set[str] = set()

    for lifecycle in lifecycles:
        signal = lifecycle.signal
        risk = lifecycle.risk_decision
        ticket = lifecycle.current_ticket
        decision_attribution = lifecycle.attribution
        signals.append(
            SignalReadModel(
                signal_id=decision_attribution.signal_id,
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                signal=signal.signal,
                reason=signal.reason,
                bar_start_timestamp=signal.trigger_bar_start_timestamp,
                bar_end_timestamp=signal.trigger_bar_end_timestamp,
                decision_attribution=decision_attribution,
            )
        )
        risk_decisions.append(
            RiskDecisionReadModel(
                request_id=risk.request_id,
                evaluated_at=risk.evaluated_at,
                symbol=risk.symbol,
                risk_intent=risk.risk_intent,
                result=risk.result,
                failed_check_names=tuple(
                    check.name for check in risk.checks if check.status == "failed"
                ),
                decision_attribution=decision_attribution,
            )
        )
        approval_tickets.append(
            ApprovalTicketReadModel(
                ticket_id=ticket.ticket_id,
                order_id=ticket.order_id,
                symbol=ticket.symbol,
                side=ticket.side,
                quantity=ticket.quantity,
                status=ticket.status,
                risk_decision_id=ticket.risk_decision_id,
                created_at=ticket.created_at,
                expires_at=ticket.expires_at,
                decision_attribution=decision_attribution,
            )
        )

        execution_attribution = _execution_attribution(lifecycle)
        if execution_attribution is not None:
            execution = lifecycle.source.run.execution
            if execution is None:
                raise SimulationExecutionProjectionError("executed run evidence is incomplete")
            alert = execution.alert_intents[0]
            dispatch = execution.alert_dispatches[0]
            final_order = execution.oms_transitions[-1].snapshot
            _claim_unique(seen_execution_ids, execution_attribution.execution_id, "execution")
            _claim_unique(seen_order_ids, execution_attribution.order_id, "order")
            _claim_unique(seen_position_ids, execution_attribution.position_id, "position")
            _claim_unique(seen_alert_ids, execution_attribution.alert_id, "alert")
            orders.append(
                OrderReadModel(
                    order_id=final_order.order_id,
                    client_order_id=final_order.client_order_id,
                    symbol=final_order.symbol,
                    side=final_order.side,
                    quantity=final_order.quantity,
                    state=final_order.state,
                    updated_at=final_order.updated_at,
                    risk_decision_id=final_order.risk_decision_id,
                    approval_reference=final_order.approval_reference,
                    requires_reconciliation=final_order.requires_reconciliation,
                    cumulative_filled_quantity=final_order.cumulative_filled_quantity,
                    leaves_quantity=final_order.leaves_quantity,
                    execution_attribution=execution_attribution,
                )
            )
            positions.append(
                PositionReadModel(
                    position_id=execution.position.position_id,
                    symbol=execution.position.symbol,
                    quantity=execution.position.quantity,
                    average_price=execution.position.average_price,
                    protection_status=execution.position.protection_status,
                    updated_at=execution.position.updated_at,
                    source="durable_saved_workflow_simulation",
                    execution_attribution=execution_attribution,
                )
            )
            alerts.append(
                AlertReadModel(
                    alert_id=alert.alert_id,
                    severity=alert.severity,
                    channel=alert.channel,
                    status=dispatch.status,
                    title=alert.title,
                    created_at=alert.created_at,
                    source_event_reference=alert.source_event_reference,
                    execution_attribution=execution_attribution,
                )
            )

        for record in lifecycle.source.journal_manifest:
            severity = record.payload.get("severity")
            if severity not in {"informational", "warning", "critical", "emergency"}:
                severity = None
            audit_events.append(
                AuditEventReadModel(
                    sequence=record.sequence,
                    event_type=record.event_type,
                    timestamp=record.timestamp,
                    summary=_event_summary(record.event_type),
                    run_id=lifecycle.source.run.run_id,
                    symbol=signal.symbol,
                    order_id=ticket.order_id,
                    ticket_id=ticket.ticket_id,
                    severity=severity,
                    decision_attribution=decision_attribution,
                    execution_attribution=execution_attribution,
                )
            )

    has_execution = bool(orders)
    return replace(
        base,
        audit_events=tuple(sorted(audit_events, key=lambda item: item.sequence)),
        signals=tuple(signals),
        risk_decisions=tuple(risk_decisions),
        approval_tickets=tuple(approval_tickets),
        orders=tuple(orders),
        positions=tuple(positions),
        alerts=tuple(alerts),
        provenance=tuple(
            _projected_provenance(item, has_execution=has_execution) for item in base.provenance
        ),
    )


def validated_simulation_lifecycle(
    source: WorkflowSimulationProjectionSource,
) -> SimulationLifecycleEvidence:
    run = source.run
    signal_record = _one_record(source, "strategy.signal.generated")
    proposal_record = _one_record(source, "order_intent.proposed")
    risk_record = _one_record(source, "risk.decision.evaluated")
    ticket_record = _one_record(source, "approval.ticket.created")
    decision_records = tuple(
        record
        for record in source.journal_manifest
        if record.event_type == "approval.ticket.decided"
    )
    if run.approval_decision is None:
        if decision_records:
            raise SimulationExecutionProjectionError("pending run has approval decision evidence")
        decision_record = None
    else:
        if len(decision_records) != 1:
            raise SimulationExecutionProjectionError("terminal run approval decision is incomplete")
        decision_record = decision_records[0]

    try:
        signal = ProductBreakoutSignal.from_json_dict(signal_record.payload)
        proposal = OrderIntentProposal.from_json_dict(proposal_record.payload)
        risk_decision = RiskDecision.from_json_dict(risk_record.payload)
        created_ticket = ApprovalTicket.from_json_dict(ticket_record.payload)
        approval_decision = (
            None
            if decision_record is None
            else ApprovalDecisionRecord.from_json_dict(decision_record.payload)
        )
    except Exception as exc:
        raise SimulationExecutionProjectionError("upstream simulation evidence is invalid") from exc

    signal_reference = _journal_reference(signal_record.sequence)
    if (
        signal_record.timestamp != signal.trigger_bar_end_timestamp
        or proposal_record.timestamp != proposal.proposed_at
        or risk_record.timestamp != risk_decision.evaluated_at
        or ticket_record.timestamp != created_ticket.created_at
        or proposal.source_signal_reference != signal_reference
        or proposal.symbol != signal.symbol
        or risk_decision.symbol != proposal.symbol
        or risk_decision.risk_intent != proposal.risk_intent
        or created_ticket.ticket_id != run.approval_ticket_id
        or created_ticket.symbol != proposal.symbol
        or created_ticket.side != proposal.side
        or created_ticket.quantity != proposal.quantity
        or created_ticket.risk_intent != proposal.risk_intent
        or created_ticket.risk_decision_id != risk_decision.request_id
    ):
        raise SimulationExecutionProjectionError(
            "upstream simulation identity chain is inconsistent"
        )
    risk_request = risk_decision.request
    if (
        risk_request.get("quantity") != proposal.quantity
        or risk_request.get("side") != proposal.side
        or risk_request.get("symbol") != proposal.symbol
        or risk_request.get("risk_intent") != proposal.risk_intent
    ):
        raise SimulationExecutionProjectionError("order intent and risk evidence are inconsistent")

    current_ticket = created_ticket
    if approval_decision is not None:
        if (
            decision_record is None
            or decision_record.timestamp != approval_decision.decided_at
            or approval_decision != run.approval_decision
            or approval_decision.ticket_id != created_ticket.ticket_id
            or approval_decision.previous_status != "pending"
            or approval_decision.ticket.create_request != created_ticket.create_request
        ):
            raise SimulationExecutionProjectionError("approval decision evidence is inconsistent")
        current_ticket = approval_decision.ticket
    expected_ticket_status = (
        "pending"
        if run.status == "waiting_for_approval"
        else "rejected"
        if run.status == "rejected"
        else "approved"
    )
    if current_ticket.status != expected_ticket_status:
        raise SimulationExecutionProjectionError("approval ticket status is inconsistent")
    if run.execution is not None and (
        run.execution.order_intent_id != proposal.proposal_id
        or run.execution.risk_decision_id != risk_decision.request_id
        or run.execution.approval_ticket_id != current_ticket.ticket_id
        or run.execution.approval_decision_id
        != (None if approval_decision is None else approval_decision.decision_id)
    ):
        raise SimulationExecutionProjectionError("execution and upstream evidence are inconsistent")

    journal_references = tuple(
        _journal_reference(record.sequence) for record in source.journal_manifest
    )
    decision_reference = (
        None if decision_record is None else _journal_reference(decision_record.sequence)
    )
    attribution = SimulationDecisionAttributionReadModel(
        workflow_id=run.workflow_id,
        workflow_version=run.expected_workflow_version,
        run_id=run.run_id,
        run_status=run.status,
        signal_id=signal_reference,
        order_intent_id=proposal.proposal_id,
        risk_decision_id=risk_decision.request_id,
        approval_ticket_id=created_ticket.ticket_id,
        approval_decision_id=(None if approval_decision is None else approval_decision.decision_id),
        approval_decision=(None if approval_decision is None else approval_decision.new_status),
        approval_actor=None if approval_decision is None else approval_decision.actor,
        approval_reason=None if approval_decision is None else approval_decision.reason,
        approval_decided_at=(None if approval_decision is None else approval_decision.decided_at),
        signal_journal_reference=signal_reference,
        order_intent_journal_reference=_journal_reference(proposal_record.sequence),
        risk_journal_reference=_journal_reference(risk_record.sequence),
        approval_ticket_journal_reference=_journal_reference(ticket_record.sequence),
        approval_decision_journal_reference=decision_reference,
        journal_references=journal_references,
    )
    return SimulationLifecycleEvidence(
        source=source,
        signal_record=signal_record,
        signal=signal,
        proposal_record=proposal_record,
        proposal=proposal,
        risk_record=risk_record,
        risk_decision=risk_decision,
        ticket_record=ticket_record,
        created_ticket=created_ticket,
        decision_record=decision_record,
        approval_decision=approval_decision,
        current_ticket=current_ticket,
        attribution=attribution,
    )


def _execution_attribution(
    lifecycle: SimulationLifecycleEvidence,
) -> SimulationExecutionAttributionReadModel | None:
    run = lifecycle.source.run
    execution = run.execution
    decision = run.approval_decision
    if execution is None:
        return None
    if decision is None or run.approval_ticket_id is None:
        raise SimulationExecutionProjectionError("executed run evidence is incomplete")
    if len(execution.alert_intents) != 1 or len(execution.alert_dispatches) != 1:
        raise SimulationExecutionProjectionError("execution alert evidence is incomplete")
    alert = execution.alert_intents[0]
    filled = execution.broker_transitions[-1]
    return SimulationExecutionAttributionReadModel(
        workflow_id=run.workflow_id,
        workflow_version=run.expected_workflow_version,
        run_id=run.run_id,
        execution_id=execution.execution_id,
        order_intent_id=execution.order_intent_id,
        risk_decision_id=execution.risk_decision_id,
        approval_ticket_id=run.approval_ticket_id,
        approval_decision_id=decision.decision_id,
        order_id=execution.order_id,
        fill_reference=filled.fake_broker_order_id,
        position_id=execution.position.position_id,
        protection_status=execution.protection_status,
        expected_protection_kind=execution.position.expected_protection_kind,
        risk_increasing_actions_blocked=execution.risk_increasing_actions_blocked,
        alert_id=alert.alert_id,
        journal_references=lifecycle.attribution.journal_references,
        execution_journal_references=execution.journal_references,
    )


def _one_record(
    source: WorkflowSimulationProjectionSource,
    event_type: str,
) -> JournalRecord:
    matches = tuple(record for record in source.journal_manifest if record.event_type == event_type)
    if len(matches) != 1:
        label = event_type.replace(".", " ")
        raise SimulationExecutionProjectionError(f"{label} evidence is incomplete")
    return matches[0]


def _claim_unique(seen: set[str], identity: str, identity_name: str) -> None:
    if identity in seen:
        raise SimulationExecutionProjectionError(f"duplicate {identity_name} identity")
    seen.add(identity)


def _projected_provenance(
    provenance: ReadModelProvenance,
    *,
    has_execution: bool,
) -> ReadModelProvenance:
    if provenance.resource not in _LIFECYCLE_RESOURCES:
        return provenance
    if provenance.resource in _DOWNSTREAM_RESOURCES and has_execution:
        return ReadModelProvenance(
            resource=provenance.resource,
            source="durable_saved_workflow_simulation_execution",
            classifications=_EXECUTION_CLASSIFICATIONS,
            broker_derived=False,
            externally_verified=False,
            summary=(
                "Validated local saved-workflow simulation execution evidence; "
                "fake-broker-derived and not externally verified"
            ),
        )
    return ReadModelProvenance(
        resource=provenance.resource,
        source="durable_saved_workflow_simulation",
        classifications=_LIFECYCLE_CLASSIFICATIONS,
        broker_derived=False,
        externally_verified=False,
        summary=(
            "Validated local saved-workflow simulation lifecycle evidence; "
            "not broker-derived and not externally verified"
        ),
    )


def _event_summary(event_type: str) -> str:
    summaries = {
        "strategy.signal.generated": "Product strategy signal recorded for durable simulation run",
        "order_intent.proposed": "Non-routable order intent recorded for durable simulation run",
        "risk.decision.evaluated": "Risk decision recorded for durable simulation run",
        "approval.ticket.created": "Manual approval ticket recorded for durable simulation run",
        "approval.ticket.decided": "Manual approval decision recorded for durable simulation run",
        "oms.order.transitioned": "Local OMS transition recorded for durable simulation execution",
        "fake_broker.order.transitioned": (
            "Local fake-broker transition recorded for durable simulation execution"
        ),
        "position.updated": "Simulated position and protection observation recorded",
        "alert.intent.created": "Local simulation alert intent recorded",
        "alert.dispatch.recorded": "Local no-op alert dispatch recorded",
        "workflow_simulation.execution_completed": (
            "Durable saved-workflow simulation execution completed"
        ),
    }
    return summaries.get(event_type, "Durable saved-workflow simulation evidence recorded")


def _journal_reference(sequence: int) -> str:
    return f"journal_sequence:{sequence}"
