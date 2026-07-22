from __future__ import annotations

from dataclasses import replace

from trading_oms_backend.read_models import (
    AlertReadModel,
    AuditEventReadModel,
    OperationsReadModel,
    OrderReadModel,
    PositionReadModel,
    ReadModelProvenance,
    SimulationExecutionAttributionReadModel,
)
from trading_oms_backend.workflow_simulation_runs import (
    WorkflowSimulationProjectionSource,
)


class SimulationExecutionProjectionError(ValueError):
    """Raised when durable execution evidence cannot form one safe read snapshot."""


_PROJECTED_RESOURCES = {"audit_events", "orders", "positions", "alerts"}
_PROJECTED_CLASSIFICATIONS = (
    "simulated",
    "local_only",
    "fake_broker_derived",
    "externally_unverified",
)


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

    executed_sources = tuple(
        sorted(
            (item for item in sources if item.run.execution is not None),
            key=lambda item: (
                item.run.updated_at,
                item.run.workflow_id,
                item.run.run_id,
            ),
        )
    )
    if not executed_sources:
        return base

    orders: list[OrderReadModel] = []
    positions: list[PositionReadModel] = []
    alerts: list[AlertReadModel] = []
    audit_events: list[AuditEventReadModel] = []
    seen_execution_ids: set[str] = set()
    seen_order_ids: set[str] = set()
    seen_position_ids: set[str] = set()
    seen_alert_ids: set[str] = set()
    seen_audit_sequences: set[int] = set()

    for source in executed_sources:
        run = source.run
        execution = run.execution
        decision = run.approval_decision
        if execution is None or decision is None or run.approval_ticket_id is None:
            raise SimulationExecutionProjectionError("executed run evidence is incomplete")
        if len(execution.alert_intents) != 1 or len(execution.alert_dispatches) != 1:
            raise SimulationExecutionProjectionError("execution alert evidence is incomplete")
        alert = execution.alert_intents[0]
        dispatch = execution.alert_dispatches[0]
        filled = execution.broker_transitions[-1]
        final_order = execution.oms_transitions[-1].snapshot
        attribution = SimulationExecutionAttributionReadModel(
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
            journal_references=tuple(
                f"journal_sequence:{record.sequence}" for record in source.journal_manifest
            ),
            execution_journal_references=execution.journal_references,
        )
        _claim_unique(seen_execution_ids, attribution.execution_id, "execution")
        _claim_unique(seen_order_ids, attribution.order_id, "order")
        _claim_unique(seen_position_ids, attribution.position_id, "position")
        _claim_unique(seen_alert_ids, attribution.alert_id, "alert")

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
                execution_attribution=attribution,
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
                execution_attribution=attribution,
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
                execution_attribution=attribution,
            )
        )
        for record in source.journal_manifest:
            if record.sequence in seen_audit_sequences:
                raise SimulationExecutionProjectionError("duplicate audit sequence")
            seen_audit_sequences.add(record.sequence)
            severity = record.payload.get("severity")
            if severity not in {"informational", "warning", "critical", "emergency"}:
                severity = None
            audit_events.append(
                AuditEventReadModel(
                    sequence=record.sequence,
                    event_type=record.event_type,
                    timestamp=record.timestamp,
                    summary=_event_summary(record.event_type),
                    run_id=run.run_id,
                    symbol=execution.position.symbol,
                    order_id=execution.order_id,
                    ticket_id=run.approval_ticket_id,
                    severity=severity,
                    execution_attribution=attribution,
                )
            )

    return replace(
        base,
        audit_events=tuple(sorted(audit_events, key=lambda item: item.sequence)),
        orders=tuple(orders),
        positions=tuple(positions),
        alerts=tuple(alerts),
        provenance=tuple(_projected_provenance(item) for item in base.provenance),
    )


def _claim_unique(seen: set[str], value: str, identity_name: str) -> None:
    if value in seen:
        raise SimulationExecutionProjectionError(f"duplicate {identity_name} identity")
    seen.add(value)


def _projected_provenance(provenance: ReadModelProvenance) -> ReadModelProvenance:
    if provenance.resource not in _PROJECTED_RESOURCES:
        return provenance
    return ReadModelProvenance(
        resource=provenance.resource,
        source="durable_saved_workflow_simulation_execution",
        classifications=_PROJECTED_CLASSIFICATIONS,
        broker_derived=False,
        externally_verified=False,
        summary=(
            "Validated local saved-workflow simulation execution evidence; "
            "fake-broker-derived and not externally verified"
        ),
    )


def _event_summary(event_type: str) -> str:
    summaries = {
        "risk.decision.evaluated": "Risk decision recorded for durable simulation execution",
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
