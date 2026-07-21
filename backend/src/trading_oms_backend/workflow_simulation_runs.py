from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol

from trading_oms_backend.alerts import (
    AlertBook,
    AlertDispatchOutcome,
    AlertDispatchRequest,
    AlertIntent,
    AlertIntentRequest,
    NoopAlertDispatcher,
)
from trading_oms_backend.approval_tickets import (
    ApprovalDecisionRecord,
    ApprovalDecisionRequest,
    ApprovalTicket,
    ApprovalTicketBook,
    ApprovalTicketError,
)
from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.emergency_stop import EmergencyStopError, EmergencyStopService
from trading_oms_backend.event_journal import JournalRecord, JsonlEventJournal
from trading_oms_backend.fake_broker import (
    BrokerOrderRequest,
    BrokerOrderTransition,
    FakeBroker,
    FakeBrokerConfig,
)
from trading_oms_backend.market_data_replay import MarketDataReplayEvent
from trading_oms_backend.oms_state_machine import (
    OrderStateMachine,
    OrderTransitionRecord,
    OrderTransitionRequest,
)
from trading_oms_backend.order_intents import OrderIntentProposal
from trading_oms_backend.product_strategy import HistoricalVolumeSession
from trading_oms_backend.risk_engine import RiskDecision, RiskPolicy
from trading_oms_backend.simulated_positions import (
    PositionUpdateRequest,
    SimulatedPosition,
    SimulatedPositionBook,
)
from trading_oms_backend.simulation_orchestration import (
    ReplayToApprovalConfig,
    ReplayToApprovalOrchestrator,
    SimulationOrchestrationError,
)
from trading_oms_backend.simulation_runs import SimulationRunCreateRequest, SimulationRunRecord
from trading_oms_backend.workflow_definitions import (
    WorkflowDefinitionError,
    WorkflowDefinitionStore,
)
from trading_oms_backend.workflow_dsl import parse_workflow_dsl_document


class WorkflowSimulationRunError(ValueError):
    """Raised when a saved visual workflow cannot run safely in simulation."""


class WorkflowSimulationRunConflictError(WorkflowSimulationRunError):
    """Raised when a run start targets a stale saved workflow version."""


class WorkflowSimulationRunUnavailableError(WorkflowSimulationRunError):
    """Raised when durable run evidence cannot be validated safely."""


LOCAL_SIMULATION_REPLAY_REFERENCE = "fixtures/replay/aapl-session.jsonl"


@dataclass(frozen=True)
class WorkflowSimulationRunRequest:
    expected_workflow_version: int
    run_id: str
    requested_at: str
    evaluated_at: str
    approval_expires_at: str
    replay_input_reference: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _positive_integer(self.expected_workflow_version, "expected_workflow_version")
        _validated_identifier(self.run_id, "run_id")
        requested_at = _parse_timestamp(self.requested_at, "requested_at")
        evaluated_at = _parse_timestamp(self.evaluated_at, "evaluated_at")
        approval_expires_at = _parse_timestamp(self.approval_expires_at, "approval_expires_at")
        if evaluated_at < requested_at:
            raise WorkflowSimulationRunError("evaluated_at must not be before requested_at")
        if approval_expires_at <= evaluated_at:
            raise WorkflowSimulationRunError("approval_expires_at must be after evaluated_at")
        if self.replay_input_reference != LOCAL_SIMULATION_REPLAY_REFERENCE:
            raise WorkflowSimulationRunError(
                "replay_input_reference must be the approved local simulation replay"
            )
        SimulationRunCreateRequest(
            run_id=self.run_id,
            requested_at=self.requested_at,
            replay_input_reference=self.replay_input_reference,
        )
        _assert_json_serializable(self.to_payload(), "workflow simulation run request")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expected_workflow_version": self.expected_workflow_version,
            "run_id": self.run_id,
            "requested_at": self.requested_at,
            "evaluated_at": self.evaluated_at,
            "approval_expires_at": self.approval_expires_at,
            "replay_input_reference": self.replay_input_reference,
        }


@dataclass(frozen=True)
class WorkflowSimulationDecisionRequest:
    expected_workflow_version: int
    approval_ticket_id: str
    decision_id: str
    decision: str
    decided_at: str
    actor: str
    decision_reference: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _positive_integer(self.expected_workflow_version, "expected_workflow_version")
        _validated_identifier(self.approval_ticket_id, "approval_ticket_id")
        _validated_identifier(self.decision_id, "decision_id")
        if self.decision not in {"approved", "rejected"}:
            raise WorkflowSimulationRunError("decision must be approved or rejected")
        _parse_timestamp(self.decided_at, "decided_at")
        _validated_identifier(self.actor, "actor")
        _validated_identifier(self.decision_reference, "decision_reference")
        _validated_text(self.reason, "reason")

    def to_payload(self, workflow_id: str, run_id: str) -> dict[str, Any]:
        _validated_identifier(workflow_id, "workflow_id")
        _validated_identifier(run_id, "run_id")
        payload = {
            "schema_version": self.schema_version,
            "workflow_id": workflow_id,
            "expected_workflow_version": self.expected_workflow_version,
            "run_id": run_id,
            "approval_ticket_id": self.approval_ticket_id,
            "decision_id": self.decision_id,
            "decision": self.decision,
            "decided_at": self.decided_at,
            "actor": self.actor,
            "decision_reference": self.decision_reference,
            "reason": self.reason,
        }
        _assert_json_serializable(payload, "workflow simulation decision request")
        return payload

    def to_approval_request(self) -> ApprovalDecisionRequest:
        return ApprovalDecisionRequest(
            decision_id=self.decision_id,
            ticket_id=self.approval_ticket_id,
            decision=self.decision,
            decided_at=self.decided_at,
            actor=self.actor,
            decision_reference=self.decision_reference,
            reason=self.reason,
        )


@dataclass(frozen=True)
class WorkflowSimulationExecutionRequest:
    expected_workflow_version: int
    approval_ticket_id: str
    approval_decision_id: str
    order_intent_id: str
    risk_decision_id: str
    order_id: str
    execution_id: str
    executed_at: str
    actor: str
    execution_reference: str
    reason: str
    broker_state_known: bool
    expected_protection_present: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _positive_integer(self.expected_workflow_version, "expected_workflow_version")
        for field_name in (
            "approval_ticket_id",
            "approval_decision_id",
            "order_intent_id",
            "risk_decision_id",
            "order_id",
            "execution_id",
            "actor",
            "execution_reference",
        ):
            _validated_identifier(getattr(self, field_name), field_name)
        _parse_timestamp(self.executed_at, "executed_at")
        _validated_text(self.reason, "reason")
        if not isinstance(self.broker_state_known, bool):
            raise WorkflowSimulationRunError("broker_state_known must be a boolean")
        if not isinstance(self.expected_protection_present, bool):
            raise WorkflowSimulationRunError("expected_protection_present must be a boolean")

    def to_payload(self, workflow_id: str, run_id: str) -> dict[str, Any]:
        _validated_identifier(workflow_id, "workflow_id")
        _validated_identifier(run_id, "run_id")
        payload = {
            "schema_version": self.schema_version,
            "workflow_id": workflow_id,
            "expected_workflow_version": self.expected_workflow_version,
            "run_id": run_id,
            "approval_ticket_id": self.approval_ticket_id,
            "approval_decision_id": self.approval_decision_id,
            "order_intent_id": self.order_intent_id,
            "risk_decision_id": self.risk_decision_id,
            "order_id": self.order_id,
            "execution_id": self.execution_id,
            "executed_at": self.executed_at,
            "actor": self.actor,
            "execution_reference": self.execution_reference,
            "reason": self.reason,
            "broker_state_known": self.broker_state_known,
            "expected_protection_present": self.expected_protection_present,
        }
        _assert_json_serializable(payload, "workflow simulation execution request")
        return payload


@dataclass(frozen=True)
class WorkflowNodeRunStatus:
    node_id: str
    node_type: str
    status: str
    detail: str
    journal_reference: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.node_id, "node_id")
        _validated_identifier(self.node_type, "node_type")
        _validated_identifier(self.status, "status")
        _validated_text(self.detail, "detail")
        _validated_journal_reference(self.journal_reference)
        _assert_json_serializable(self.to_json_dict(), "workflow node run status")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status,
            "detail": self.detail,
            "journal_reference": self.journal_reference,
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> WorkflowNodeRunStatus:
        expected_keys = {
            "schema_version",
            "node_id",
            "node_type",
            "status",
            "detail",
            "journal_reference",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise WorkflowSimulationRunError("workflow node run status fields are invalid")
        return cls(
            schema_version=raw_record["schema_version"],
            node_id=raw_record["node_id"],
            node_type=raw_record["node_type"],
            status=raw_record["status"],
            detail=raw_record["detail"],
            journal_reference=raw_record["journal_reference"],
        )


@dataclass(frozen=True)
class WorkflowSimulationExecutionRecord:
    workflow_id: str
    expected_workflow_version: int
    run_id: str
    approval_ticket_id: str
    approval_decision_id: str
    order_intent_id: str
    risk_decision_id: str
    order_id: str
    execution_id: str
    executed_at: str
    actor: str
    execution_reference: str
    reason: str
    broker_state_known: bool
    expected_protection_present: bool
    protection_status: str
    risk_increasing_actions_blocked: bool
    oms_transitions: tuple[OrderTransitionRecord, ...]
    broker_transitions: tuple[BrokerOrderTransition, ...]
    position: SimulatedPosition
    alert_intents: tuple[AlertIntent, ...]
    alert_dispatches: tuple[AlertDispatchOutcome, ...]
    journal_references: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _positive_integer(self.expected_workflow_version, "expected_workflow_version")
        for field_name in (
            "workflow_id",
            "run_id",
            "approval_ticket_id",
            "approval_decision_id",
            "order_intent_id",
            "risk_decision_id",
            "order_id",
            "execution_id",
            "actor",
            "execution_reference",
        ):
            _validated_identifier(getattr(self, field_name), field_name)
        _parse_timestamp(self.executed_at, "executed_at")
        _validated_text(self.reason, "reason")
        if self.broker_state_known is not True:
            raise WorkflowSimulationRunError("executed simulation requires known broker state")
        if not isinstance(self.expected_protection_present, bool):
            raise WorkflowSimulationRunError("expected_protection_present must be a boolean")
        expected_protection_status = (
            "expected_protection_present"
            if self.expected_protection_present
            else "missing_expected_protection"
        )
        if self.protection_status != expected_protection_status:
            raise WorkflowSimulationRunError("execution protection status is inconsistent")
        expected_blocked = not self.expected_protection_present
        if self.risk_increasing_actions_blocked is not expected_blocked:
            raise WorkflowSimulationRunError("execution risk block is inconsistent")
        if not isinstance(self.oms_transitions, tuple) or tuple(
            transition.new_state for transition in self.oms_transitions
        ) != ("APPROVED", "SUBMITTED", "ACKNOWLEDGED", "FILLED"):
            raise WorkflowSimulationRunError("execution OMS transitions are incomplete")
        if any(
            transition.order_id != self.order_id
            or transition.snapshot.risk_decision_id != self.risk_decision_id
            for transition in self.oms_transitions
        ):
            raise WorkflowSimulationRunError("execution OMS attribution is inconsistent")
        if not isinstance(self.broker_transitions, tuple) or tuple(
            transition.state for transition in self.broker_transitions
        ) != ("acknowledged", "filled"):
            raise WorkflowSimulationRunError("execution broker transitions are incomplete")
        if not isinstance(self.position, SimulatedPosition):
            raise WorkflowSimulationRunError("execution position is invalid")
        if self.position.protection_status != self.protection_status:
            raise WorkflowSimulationRunError("execution position protection is inconsistent")
        if not isinstance(self.alert_intents, tuple) or len(self.alert_intents) != 1:
            raise WorkflowSimulationRunError("execution requires one local alert intent")
        if not isinstance(self.alert_dispatches, tuple) or len(self.alert_dispatches) != 1:
            raise WorkflowSimulationRunError("execution requires one local alert dispatch")
        alert = self.alert_intents[0]
        dispatch = self.alert_dispatches[0]
        expected_severity = "informational" if self.expected_protection_present else "critical"
        if (
            alert.severity != expected_severity
            or alert.channel != "local"
            or dispatch.alert_id != alert.alert_id
            or dispatch.channel != "local"
            or dispatch.status != "recorded"
            or dispatch.dispatcher != "noop"
        ):
            raise WorkflowSimulationRunError("execution local alert evidence is inconsistent")
        _validated_journal_references(self.journal_references)
        _assert_json_serializable(self.to_json_dict(), "workflow simulation execution record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "expected_workflow_version": self.expected_workflow_version,
            "run_id": self.run_id,
            "approval_ticket_id": self.approval_ticket_id,
            "approval_decision_id": self.approval_decision_id,
            "order_intent_id": self.order_intent_id,
            "risk_decision_id": self.risk_decision_id,
            "order_id": self.order_id,
            "execution_id": self.execution_id,
            "executed_at": self.executed_at,
            "actor": self.actor,
            "execution_reference": self.execution_reference,
            "reason": self.reason,
            "broker_state_known": self.broker_state_known,
            "expected_protection_present": self.expected_protection_present,
            "protection_status": self.protection_status,
            "risk_increasing_actions_blocked": self.risk_increasing_actions_blocked,
            "oms_transitions": [item.to_json_dict() for item in self.oms_transitions],
            "broker_transitions": [item.to_json_dict() for item in self.broker_transitions],
            "position": self.position.to_json_dict(),
            "alert_intents": [item.to_json_dict() for item in self.alert_intents],
            "alert_dispatches": [item.to_json_dict() for item in self.alert_dispatches],
            "journal_references": list(self.journal_references),
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> WorkflowSimulationExecutionRecord:
        expected_keys = {
            "schema_version",
            "workflow_id",
            "expected_workflow_version",
            "run_id",
            "approval_ticket_id",
            "approval_decision_id",
            "order_intent_id",
            "risk_decision_id",
            "order_id",
            "execution_id",
            "executed_at",
            "actor",
            "execution_reference",
            "reason",
            "broker_state_known",
            "expected_protection_present",
            "protection_status",
            "risk_increasing_actions_blocked",
            "oms_transitions",
            "broker_transitions",
            "position",
            "alert_intents",
            "alert_dispatches",
            "journal_references",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise WorkflowSimulationRunError("workflow execution record fields are invalid")
        list_fields = (
            "oms_transitions",
            "broker_transitions",
            "alert_intents",
            "alert_dispatches",
            "journal_references",
        )
        if any(not isinstance(raw_record[field], list) for field in list_fields):
            raise WorkflowSimulationRunError("workflow execution list fields are invalid")
        position = raw_record["position"]
        if not isinstance(position, Mapping):
            raise WorkflowSimulationRunError("workflow execution position is invalid")
        return cls(
            schema_version=raw_record["schema_version"],
            workflow_id=raw_record["workflow_id"],
            expected_workflow_version=raw_record["expected_workflow_version"],
            run_id=raw_record["run_id"],
            approval_ticket_id=raw_record["approval_ticket_id"],
            approval_decision_id=raw_record["approval_decision_id"],
            order_intent_id=raw_record["order_intent_id"],
            risk_decision_id=raw_record["risk_decision_id"],
            order_id=raw_record["order_id"],
            execution_id=raw_record["execution_id"],
            executed_at=raw_record["executed_at"],
            actor=raw_record["actor"],
            execution_reference=raw_record["execution_reference"],
            reason=raw_record["reason"],
            broker_state_known=raw_record["broker_state_known"],
            expected_protection_present=raw_record["expected_protection_present"],
            protection_status=raw_record["protection_status"],
            risk_increasing_actions_blocked=raw_record["risk_increasing_actions_blocked"],
            oms_transitions=tuple(
                OrderTransitionRecord.from_json_dict(item) for item in raw_record["oms_transitions"]
            ),
            broker_transitions=tuple(
                BrokerOrderTransition.from_json_dict(item)
                for item in raw_record["broker_transitions"]
            ),
            position=SimulatedPosition.from_json_dict(position),
            alert_intents=tuple(
                AlertIntent.from_json_dict(item) for item in raw_record["alert_intents"]
            ),
            alert_dispatches=tuple(
                AlertDispatchOutcome.from_json_dict(item) for item in raw_record["alert_dispatches"]
            ),
            journal_references=tuple(raw_record["journal_references"]),
        )


@dataclass(frozen=True)
class WorkflowSimulationRunRecord:
    workflow_id: str
    expected_workflow_version: int
    run_id: str
    status: str
    created_at: str
    updated_at: str
    simulation_run: SimulationRunRecord
    node_statuses: tuple[WorkflowNodeRunStatus, ...]
    journal_references: tuple[str, ...]
    approval_ticket_id: str | None
    approval_decision: ApprovalDecisionRecord | None = None
    execution: WorkflowSimulationExecutionRecord | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.workflow_id, "workflow_id")
        _positive_integer(self.expected_workflow_version, "expected_workflow_version")
        _validated_identifier(self.run_id, "run_id")
        _validated_identifier(self.status, "status")
        created_at = _parse_timestamp(self.created_at, "created_at")
        updated_at = _parse_timestamp(self.updated_at, "updated_at")
        if updated_at < created_at:
            raise WorkflowSimulationRunError("updated_at must not be before created_at")
        if not isinstance(self.simulation_run, SimulationRunRecord):
            raise WorkflowSimulationRunError("simulation_run must be SimulationRunRecord")
        if self.simulation_run.run_id != self.run_id:
            raise WorkflowSimulationRunError("simulation_run run_id must match run_id")
        if not isinstance(self.node_statuses, tuple) or not self.node_statuses:
            raise WorkflowSimulationRunError("node_statuses must be a non-empty tuple")
        for node_status in self.node_statuses:
            if not isinstance(node_status, WorkflowNodeRunStatus):
                raise WorkflowSimulationRunError(
                    "node_statuses must contain workflow node statuses"
                )
        _validated_journal_references(self.journal_references)
        if tuple(node.journal_reference for node in self.node_statuses) != self.journal_references:
            raise WorkflowSimulationRunError(
                "journal_references must match node status journal references"
            )
        if self.approval_ticket_id is not None:
            _validated_identifier(self.approval_ticket_id, "approval_ticket_id")
        if self.status == "waiting_for_approval" and self.approval_ticket_id is None:
            raise WorkflowSimulationRunError("waiting_for_approval requires approval_ticket_id")
        if self.status == "waiting_for_approval" and self.approval_decision is not None:
            raise WorkflowSimulationRunError(
                "waiting_for_approval must not contain an approval decision"
            )
        if self.status in {
            "approved_not_executed",
            "rejected",
            "executed",
            "executed_protection_missing",
        }:
            if not isinstance(self.approval_decision, ApprovalDecisionRecord):
                raise WorkflowSimulationRunError("decided workflow run requires approval_decision")
            expected_decision = "rejected" if self.status == "rejected" else "approved"
            if (
                self.approval_decision.new_status != expected_decision
                or self.approval_decision.ticket_id != self.approval_ticket_id
            ):
                raise WorkflowSimulationRunError("workflow run approval decision is inconsistent")
            if self.status in {"approved_not_executed", "rejected"} and (
                self.approval_decision.decided_at != self.updated_at
            ):
                raise WorkflowSimulationRunError("workflow run approval timestamp is inconsistent")
        elif self.approval_decision is not None:
            raise WorkflowSimulationRunError("workflow run status does not allow approval_decision")
        if self.status in {"executed", "executed_protection_missing"}:
            if not isinstance(self.execution, WorkflowSimulationExecutionRecord):
                raise WorkflowSimulationRunError("executed workflow run requires execution")
            expected_status = (
                "executed"
                if self.execution.protection_status == "expected_protection_present"
                else "executed_protection_missing"
            )
            if (
                self.status != expected_status
                or self.execution.workflow_id != self.workflow_id
                or self.execution.expected_workflow_version != self.expected_workflow_version
                or self.execution.run_id != self.run_id
                or self.execution.approval_ticket_id != self.approval_ticket_id
                or self.execution.approval_decision_id != self.approval_decision.decision_id
                or self.execution.executed_at != self.updated_at
            ):
                raise WorkflowSimulationRunError("workflow run execution is inconsistent")
        elif self.execution is not None:
            raise WorkflowSimulationRunError("workflow run status does not allow execution")
        _assert_json_serializable(self.to_json_dict(), "workflow simulation run record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "expected_workflow_version": self.expected_workflow_version,
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approval_ticket_id": self.approval_ticket_id,
            "approval_decision": (
                None if self.approval_decision is None else self.approval_decision.to_json_dict()
            ),
            "execution": None if self.execution is None else self.execution.to_json_dict(),
            "simulation_run": self.simulation_run.to_json_dict(),
            "node_statuses": [node.to_json_dict() for node in self.node_statuses],
            "journal_references": list(self.journal_references),
        }

    @classmethod
    def from_json_dict(
        cls,
        raw_record: Mapping[str, Any],
        *,
        fallback_expected_workflow_version: int | None = None,
    ) -> WorkflowSimulationRunRecord:
        expected_keys = {
            "schema_version",
            "workflow_id",
            "expected_workflow_version",
            "run_id",
            "status",
            "created_at",
            "updated_at",
            "approval_ticket_id",
            "approval_decision",
            "execution",
            "simulation_run",
            "node_statuses",
            "journal_references",
        }
        decision_only_keys = expected_keys - {"execution"}
        legacy_keys = decision_only_keys - {"approval_decision"}
        pre_version_keys = expected_keys - {"expected_workflow_version"}
        pre_version_decision_keys = decision_only_keys - {"expected_workflow_version"}
        pre_version_legacy_keys = legacy_keys - {"expected_workflow_version"}
        if not isinstance(raw_record, Mapping):
            raise WorkflowSimulationRunError("workflow simulation run record fields are invalid")
        raw_keys = frozenset(raw_record)
        if raw_keys not in {
            frozenset(expected_keys),
            frozenset(decision_only_keys),
            frozenset(legacy_keys),
            frozenset(pre_version_keys),
            frozenset(pre_version_decision_keys),
            frozenset(pre_version_legacy_keys),
        }:
            raise WorkflowSimulationRunError("workflow simulation run record fields are invalid")
        expected_workflow_version = raw_record.get(
            "expected_workflow_version",
            fallback_expected_workflow_version,
        )
        if expected_workflow_version is None:
            expected_workflow_version = 1
        simulation_run = raw_record["simulation_run"]
        node_statuses = raw_record["node_statuses"]
        journal_references = raw_record["journal_references"]
        if not isinstance(simulation_run, Mapping):
            raise WorkflowSimulationRunError("simulation_run must be an object")
        if not isinstance(node_statuses, list):
            raise WorkflowSimulationRunError("node_statuses must be a list")
        if not isinstance(journal_references, list):
            raise WorkflowSimulationRunError("journal_references must be a list")
        approval_decision = raw_record.get("approval_decision")
        if approval_decision is not None and not isinstance(approval_decision, Mapping):
            raise WorkflowSimulationRunError("approval_decision must be an object or null")
        execution = raw_record.get("execution")
        if execution is not None and not isinstance(execution, Mapping):
            raise WorkflowSimulationRunError("execution must be an object or null")
        return cls(
            schema_version=raw_record["schema_version"],
            workflow_id=raw_record["workflow_id"],
            expected_workflow_version=expected_workflow_version,
            run_id=raw_record["run_id"],
            status=raw_record["status"],
            created_at=raw_record["created_at"],
            updated_at=raw_record["updated_at"],
            approval_ticket_id=raw_record["approval_ticket_id"],
            approval_decision=(
                None
                if approval_decision is None
                else ApprovalDecisionRecord.from_json_dict(approval_decision)
            ),
            execution=(
                None
                if execution is None
                else WorkflowSimulationExecutionRecord.from_json_dict(execution)
            ),
            simulation_run=SimulationRunRecord.from_json_dict(simulation_run),
            node_statuses=tuple(
                WorkflowNodeRunStatus.from_json_dict(node_status) for node_status in node_statuses
            ),
            journal_references=tuple(journal_references),
        )


class WorkflowSimulationRunPersistence(Protocol):
    def reserve_workflow_simulation_run(
        self,
        request_payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]: ...

    def finalize_workflow_simulation_run(
        self,
        run_id: str,
        record: WorkflowSimulationRunRecord,
        journal_records: tuple[JournalRecord, ...],
    ) -> dict[str, Any]: ...

    def get_workflow_simulation_run_evidence(
        self,
        run_id: str,
    ) -> dict[str, Any] | None: ...

    def list_workflow_simulation_run_evidence(
        self,
        workflow_id: str,
    ) -> tuple[dict[str, Any], ...]: ...

    def reserve_workflow_simulation_decision(
        self,
        request_payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]: ...

    def finalize_workflow_simulation_decision(
        self,
        run_id: str,
        record: WorkflowSimulationRunRecord,
        decision_record: ApprovalDecisionRecord,
        journal_records: tuple[JournalRecord, ...],
    ) -> dict[str, Any]: ...

    def reserve_workflow_simulation_execution(
        self,
        request_payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]: ...

    def finalize_workflow_simulation_execution(
        self,
        run_id: str,
        record: WorkflowSimulationRunRecord,
        execution_record: WorkflowSimulationExecutionRecord,
        journal_records: tuple[JournalRecord, ...],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _ApprovedExecutionContext:
    ticket: ApprovalTicket
    decision: ApprovalDecisionRecord
    proposal: OrderIntentProposal
    risk_decision: RiskDecision
    oms_history: tuple[OrderTransitionRecord, ...]


class WorkflowSimulationRunner:
    def __init__(
        self,
        store: WorkflowDefinitionStore,
        journal: JsonlEventJournal,
        *,
        persistence_store: WorkflowSimulationRunPersistence,
        emergency_stop_service: EmergencyStopService | None = None,
    ) -> None:
        if not isinstance(store, WorkflowDefinitionStore):
            raise WorkflowSimulationRunError("store must be WorkflowDefinitionStore")
        if not isinstance(journal, JsonlEventJournal):
            raise WorkflowSimulationRunError("journal must be JsonlEventJournal")
        if emergency_stop_service is not None and not isinstance(
            emergency_stop_service,
            EmergencyStopService,
        ):
            raise WorkflowSimulationRunError("emergency_stop_service must be EmergencyStopService")
        persistence_methods = (
            "reserve_workflow_simulation_run",
            "finalize_workflow_simulation_run",
            "get_workflow_simulation_run_evidence",
            "list_workflow_simulation_run_evidence",
            "reserve_workflow_simulation_decision",
            "finalize_workflow_simulation_decision",
            "reserve_workflow_simulation_execution",
            "finalize_workflow_simulation_execution",
        )
        if not all(
            callable(getattr(persistence_store, method, None)) for method in persistence_methods
        ):
            raise WorkflowSimulationRunError("persistence_store is invalid")
        self._store = store
        self._journal = journal
        self._persistence_store = persistence_store
        self._emergency_stop_service = emergency_stop_service
        self._lock = threading.RLock()
        self._execution_lock = threading.Lock()

    def start_run(
        self,
        workflow_id: str,
        request: WorkflowSimulationRunRequest,
        *,
        requested_by: str = "system",
    ) -> WorkflowSimulationRunRecord:
        _validated_identifier(workflow_id, "workflow_id")
        if not isinstance(request, WorkflowSimulationRunRequest):
            raise WorkflowSimulationRunError("request must be WorkflowSimulationRunRequest")
        _validated_identifier(requested_by, "requested_by")
        with self._lock:
            return self._start_run_locked(
                workflow_id,
                request,
                requested_by=requested_by,
            )

    def _start_run_locked(
        self,
        workflow_id: str,
        request: WorkflowSimulationRunRequest,
        *,
        requested_by: str,
    ) -> WorkflowSimulationRunRecord:
        if self._emergency_stop_service is not None:
            try:
                self._emergency_stop_service.ensure_risk_increasing_allowed(
                    resource=f"workflow_simulation_run.{workflow_id}",
                    action="start",
                    checked_at=request.requested_at,
                    actor=requested_by,
                )
            except EmergencyStopError as exc:
                raise WorkflowSimulationRunError(str(exc)) from exc

        payload = {"workflow_id": workflow_id, **request.to_payload()}
        existing_evidence = self._load_evidence(request.run_id)
        if existing_evidence is not None:
            return self._record_for_exact_request(existing_evidence, payload)

        workflow = self._load_valid_workflow(
            workflow_id,
            expected_version=request.expected_workflow_version,
        )
        reservation, reservation_created = self._reserve_evidence(payload)
        if not reservation_created:
            return self._record_for_exact_request(reservation, payload)

        with self._journal.write_session():
            records_before = self._read_journal_for_evidence()
            orchestrator = ReplayToApprovalOrchestrator(
                self._journal,
                emergency_stop_service=self._emergency_stop_service,
            )
            try:
                result = orchestrator.run(
                    replay_events=_deterministic_replay_events(),
                    historical_sessions=_historical_sessions(),
                    risk_policy=_risk_policy(),
                    config=_orchestration_config(request),
                    requested_by=requested_by,
                )
            except SimulationOrchestrationError as exc:
                raise WorkflowSimulationRunError(str(exc)) from exc

            node_statuses = self._journal_node_statuses(
                workflow.workflow_id, workflow.document, request, result
            )
            record = WorkflowSimulationRunRecord(
                workflow_id=workflow.workflow_id,
                expected_workflow_version=request.expected_workflow_version,
                run_id=request.run_id,
                status=(
                    "waiting_for_approval" if result.approval_ticket is not None else "completed"
                ),
                created_at=request.requested_at,
                updated_at=request.evaluated_at,
                simulation_run=result.run,
                approval_ticket_id=(
                    None if result.approval_ticket is None else result.approval_ticket.ticket_id
                ),
                node_statuses=node_statuses,
                journal_references=tuple(node.journal_reference for node in node_statuses),
            )
            records_after = self._read_journal_for_evidence()
            journal_manifest = tuple(records_after[len(records_before) :])

        finalized = self._finalize_evidence(record, journal_manifest)
        return self._validated_record_from_evidence(finalized)

    def journal_records(self) -> tuple[JournalRecord, ...]:
        return tuple(self._journal.read_all())

    def apply_decision(
        self,
        workflow_id: str,
        run_id: str,
        request: WorkflowSimulationDecisionRequest,
        *,
        decided_by: str,
    ) -> WorkflowSimulationRunRecord:
        _validated_identifier(workflow_id, "workflow_id")
        _validated_identifier(run_id, "run_id")
        if not isinstance(request, WorkflowSimulationDecisionRequest):
            raise WorkflowSimulationRunError("request must be WorkflowSimulationDecisionRequest")
        _validated_identifier(decided_by, "decided_by")
        if request.actor != decided_by:
            raise WorkflowSimulationRunError("actor must match authenticated operator")
        with self._lock:
            return self._apply_decision_locked(
                workflow_id,
                run_id,
                request,
                decided_by=decided_by,
            )

    def _apply_decision_locked(
        self,
        workflow_id: str,
        run_id: str,
        request: WorkflowSimulationDecisionRequest,
        *,
        decided_by: str,
    ) -> WorkflowSimulationRunRecord:
        evidence = self._load_evidence(run_id)
        if evidence is None or evidence.get("workflow_id") != workflow_id:
            raise WorkflowSimulationRunError("unknown workflow simulation run")
        payload = request.to_payload(workflow_id, run_id)
        decision_state = evidence.get("decision_evidence_state")
        if decision_state is not None:
            if evidence.get("decision_request") != payload:
                raise WorkflowSimulationRunConflictError("conflicting decision")
            return self._validated_record_from_evidence(evidence)

        record = self._validated_record_from_evidence(evidence)
        if record.status != "waiting_for_approval":
            raise WorkflowSimulationRunConflictError("workflow simulation run is already decided")
        if request.expected_workflow_version != evidence.get("expected_workflow_version"):
            raise WorkflowSimulationRunConflictError(
                "expected_workflow_version does not match persisted workflow version"
            )
        if request.approval_ticket_id != record.approval_ticket_id:
            raise WorkflowSimulationRunConflictError(
                "approval_ticket_id does not match persisted workflow run"
            )
        ticket = _pending_ticket_from_evidence(evidence, record)
        _validate_ticket_attribution(ticket, run_id, evidence)
        approval_request = request.to_approval_request()
        ticket_book = ApprovalTicketBook(self._journal)
        ticket_book.restore_pending_ticket(ticket)
        try:
            ticket_book.validate_decision(approval_request)
        except ApprovalTicketError as exc:
            raise WorkflowSimulationRunError(str(exc)) from exc

        if request.decision == "approved" and self._emergency_stop_service is not None:
            try:
                self._emergency_stop_service.ensure_risk_increasing_allowed(
                    resource=f"workflow_simulation_run.{workflow_id}.{run_id}",
                    action="approve",
                    checked_at=request.decided_at,
                    actor=decided_by,
                )
            except EmergencyStopError as exc:
                raise WorkflowSimulationRunError(str(exc)) from exc

        reservation, created = self._reserve_decision(payload)
        if not created:
            return self._record_for_exact_decision(reservation, payload)

        with self._journal.write_session():
            records_before = self._read_journal_for_evidence()
            try:
                decision_record = ticket_book.apply_decision(approval_request)
            except ApprovalTicketError as exc:
                raise WorkflowSimulationRunError(str(exc)) from exc
            node_statuses = self._journal_decision_node_statuses(
                record,
                request,
            )
            updated = replace(
                record,
                status=("approved_not_executed" if request.decision == "approved" else "rejected"),
                updated_at=request.decided_at,
                approval_decision=decision_record,
                node_statuses=node_statuses,
                journal_references=tuple(node.journal_reference for node in node_statuses),
            )
            records_after = self._read_journal_for_evidence()
            new_records = tuple(records_after[len(records_before) :])
            prior_manifest = tuple(
                JournalRecord.from_json_dict(item) for item in _required_manifest(evidence)
            )
            expanded_manifest = (*prior_manifest, *new_records)

        finalized = self._finalize_decision(
            updated,
            decision_record,
            expanded_manifest,
        )
        return self._validated_record_from_evidence(finalized)

    def execute_approved_run(
        self,
        workflow_id: str,
        run_id: str,
        request: WorkflowSimulationExecutionRequest,
        *,
        executed_by: str,
    ) -> WorkflowSimulationRunRecord:
        _validated_identifier(workflow_id, "workflow_id")
        _validated_identifier(run_id, "run_id")
        if not isinstance(request, WorkflowSimulationExecutionRequest):
            raise WorkflowSimulationRunError("request must be WorkflowSimulationExecutionRequest")
        _validated_identifier(executed_by, "executed_by")
        if not self._execution_lock.acquire(blocking=False):
            raise WorkflowSimulationRunConflictError("concurrent execution is blocked")
        try:
            with self._lock:
                return self._execute_approved_run_locked(
                    workflow_id,
                    run_id,
                    request,
                    executed_by=executed_by,
                )
        finally:
            self._execution_lock.release()

    def _execute_approved_run_locked(
        self,
        workflow_id: str,
        run_id: str,
        request: WorkflowSimulationExecutionRequest,
        *,
        executed_by: str,
    ) -> WorkflowSimulationRunRecord:
        evidence = self._load_evidence(run_id)
        if evidence is None or evidence.get("workflow_id") != workflow_id:
            raise WorkflowSimulationRunError("unknown workflow simulation run")
        record = self._validated_record_from_evidence(evidence)
        if request.actor != executed_by:
            self._journal_execution_blocked(record, request, reason="actor_mismatch")
            raise WorkflowSimulationRunError("actor must match authenticated operator")
        payload = request.to_payload(workflow_id, run_id)
        execution_state = evidence.get("execution_evidence_state")
        if execution_state is not None:
            if evidence.get("execution_request") != payload:
                self._journal_execution_blocked(
                    record,
                    request,
                    reason="conflicting_execution_retry",
                )
                raise WorkflowSimulationRunConflictError("conflicting execution")
            return record

        if record.status != "approved_not_executed":
            self._journal_execution_blocked(
                record,
                request,
                reason=f"run_status_{record.status}",
            )
            raise WorkflowSimulationRunConflictError(
                "workflow simulation run is not approved for execution"
            )
        if request.expected_workflow_version != evidence.get("expected_workflow_version"):
            self._journal_execution_blocked(
                record,
                request,
                reason="workflow_version_mismatch",
            )
            raise WorkflowSimulationRunConflictError(
                "expected_workflow_version does not match persisted workflow version"
            )
        decision = record.approval_decision
        if decision is None or decision.new_status != "approved":
            self._journal_execution_blocked(
                record,
                request,
                reason="committed_approval_missing",
            )
            raise WorkflowSimulationRunConflictError(
                "workflow simulation run does not contain committed approval"
            )
        expected_request_bindings = {
            "approval_ticket_id": record.approval_ticket_id,
            "approval_decision_id": decision.decision_id,
            "order_intent_id": f"{run_id}-intent",
            "risk_decision_id": f"{run_id}-risk",
            "order_id": f"{run_id}-order",
        }
        for field_name, expected_value in expected_request_bindings.items():
            if getattr(request, field_name) != expected_value:
                self._journal_execution_blocked(
                    record,
                    request,
                    reason=f"{field_name}_mismatch",
                )
                raise WorkflowSimulationRunConflictError(
                    f"{field_name} does not match persisted workflow run"
                )
        context = _approved_execution_context(evidence, record)
        executed_at = _parse_timestamp(request.executed_at, "executed_at")
        if executed_at < _parse_timestamp(decision.decided_at, "decided_at"):
            self._journal_execution_blocked(
                record,
                request,
                reason="execution_before_approval_decision",
            )
            raise WorkflowSimulationRunError("executed_at must not be before approval decision")
        if executed_at > _parse_timestamp(context.ticket.expires_at, "approval expires_at"):
            self._journal_execution_blocked(
                record,
                request,
                reason="approval_expired",
            )
            raise WorkflowSimulationRunError("approved ticket has expired")
        if not request.broker_state_known:
            self._journal_execution_blocked(
                record,
                request,
                reason="unknown_simulated_broker_state",
            )
            raise WorkflowSimulationRunError("unknown simulated broker state blocks execution")
        if context.proposal.protective_order_plan is None:
            self._journal_execution_blocked(
                record,
                request,
                reason="protective_order_plan_missing",
            )
            raise WorkflowSimulationRunError(
                "risk-increasing execution requires persisted protective-order plan"
            )

        if self._emergency_stop_service is not None:
            try:
                self._emergency_stop_service.ensure_risk_increasing_allowed(
                    resource=f"workflow_simulation_run.{workflow_id}.{run_id}",
                    action="execute",
                    checked_at=request.executed_at,
                    actor=executed_by,
                )
            except EmergencyStopError as exc:
                raise WorkflowSimulationRunError(str(exc)) from exc

        reservation, created = self._reserve_execution(payload)
        if not created:
            return self._record_for_exact_execution(reservation, payload)

        try:
            with self._journal.write_session():
                records_before = self._read_journal_for_evidence()
                (
                    oms_transitions,
                    broker_transitions,
                    position,
                    alert_intents,
                    alert_dispatches,
                ) = self._execute_simulation_domains(record, context, request)
                completion = self._journal.append(
                    "workflow_simulation.execution_completed",
                    {
                        "schema_version": 1,
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "execution_id": request.execution_id,
                        "approval_decision_id": request.approval_decision_id,
                        "order_id": request.order_id,
                        "protection_status": position.protection_status,
                        "risk_increasing_actions_blocked": (
                            position.protection_status == "missing_expected_protection"
                        ),
                    },
                    timestamp=request.executed_at,
                )
                node_statuses = self._journal_execution_node_statuses(
                    record,
                    request,
                    position.protection_status,
                )
                records_after = self._read_journal_for_evidence()
                new_records = tuple(records_after[len(records_before) :])
                execution_record = WorkflowSimulationExecutionRecord(
                    workflow_id=workflow_id,
                    expected_workflow_version=request.expected_workflow_version,
                    run_id=run_id,
                    approval_ticket_id=request.approval_ticket_id,
                    approval_decision_id=request.approval_decision_id,
                    order_intent_id=request.order_intent_id,
                    risk_decision_id=request.risk_decision_id,
                    order_id=request.order_id,
                    execution_id=request.execution_id,
                    executed_at=request.executed_at,
                    actor=request.actor,
                    execution_reference=request.execution_reference,
                    reason=request.reason,
                    broker_state_known=request.broker_state_known,
                    expected_protection_present=request.expected_protection_present,
                    protection_status=position.protection_status,
                    risk_increasing_actions_blocked=(
                        position.protection_status == "missing_expected_protection"
                    ),
                    oms_transitions=oms_transitions,
                    broker_transitions=broker_transitions,
                    position=position,
                    alert_intents=alert_intents,
                    alert_dispatches=alert_dispatches,
                    journal_references=tuple(
                        _journal_reference(item.sequence) for item in new_records
                    ),
                )
                if (
                    _journal_reference(completion.sequence)
                    not in execution_record.journal_references
                ):
                    raise WorkflowSimulationRunError("execution completion reference is missing")
                updated = replace(
                    record,
                    status=(
                        "executed"
                        if request.expected_protection_present
                        else "executed_protection_missing"
                    ),
                    updated_at=request.executed_at,
                    execution=execution_record,
                    node_statuses=node_statuses,
                    journal_references=tuple(node.journal_reference for node in node_statuses),
                )
                prior_manifest = tuple(
                    JournalRecord.from_json_dict(item) for item in _required_manifest(evidence)
                )
                expanded_manifest = (*prior_manifest, *new_records)
        except WorkflowSimulationRunError:
            raise
        except Exception as exc:
            raise _evidence_unavailable() from exc

        finalized = self._finalize_execution(
            updated,
            execution_record,
            expanded_manifest,
        )
        return self._validated_record_from_evidence(finalized)

    def _execute_simulation_domains(
        self,
        record: WorkflowSimulationRunRecord,
        context: _ApprovedExecutionContext,
        request: WorkflowSimulationExecutionRequest,
    ) -> tuple[
        tuple[OrderTransitionRecord, ...],
        tuple[BrokerOrderTransition, ...],
        SimulatedPosition,
        tuple[AlertIntent, ...],
        tuple[AlertDispatchOutcome, ...],
    ]:
        orders = OrderStateMachine(self._journal)
        orders.restore_history(context.oms_history)
        pending = orders.current_snapshot(request.order_id)
        if pending.state != "PENDING_APPROVAL" or pending.requires_reconciliation:
            raise WorkflowSimulationRunError("persisted OMS state blocks execution")
        approval_reference = context.decision.decision_reference

        def transition(
            suffix: str,
            target_state: str,
            reason: str,
            *,
            broker_reference: str | None = None,
            cumulative_filled_quantity: int = 0,
        ) -> OrderTransitionRecord:
            snapshot = orders.current_snapshot(request.order_id)
            return orders.apply_transition(
                OrderTransitionRequest(
                    transition_id=f"{request.execution_id}-{suffix}",
                    order_id=request.order_id,
                    client_order_id=snapshot.client_order_id,
                    symbol=snapshot.symbol,
                    side=snapshot.side,
                    quantity=snapshot.quantity,
                    risk_intent=snapshot.risk_intent,
                    target_state=target_state,
                    occurred_at=request.executed_at,
                    reason=reason,
                    risk_decision_id=request.risk_decision_id,
                    approval_reference=approval_reference,
                    broker_transition_reference=broker_reference,
                    cumulative_filled_quantity=cumulative_filled_quantity,
                )
            )

        approved = transition("oms-approved", "APPROVED", "simulation_ticket_approved")
        submitted = transition(
            "oms-submitted",
            "SUBMITTED",
            "simulation_order_submitted_to_fake_broker",
        )
        broker_order = BrokerOrderRequest(
            client_order_id=pending.client_order_id,
            symbol=context.proposal.symbol,
            side=context.proposal.side,
            quantity=context.proposal.quantity,
            order_type=context.proposal.order_type,
            reference_price=context.proposal.reference_price,
            limit_price=context.proposal.limit_price,
            requested_at=request.executed_at,
            risk_decision_id=request.risk_decision_id,
            risk_decision_result="passed",
            approval_reference=approval_reference,
        )
        broker = FakeBroker(self._journal, FakeBrokerConfig(fill_mode="acknowledge_only"))
        acknowledged = broker.accept_order(broker_order)[0]
        acknowledged_reference = _latest_journal_reference(
            self._journal,
            "fake_broker.order.transitioned",
        )
        acknowledged_oms = transition(
            "oms-acknowledged",
            "ACKNOWLEDGED",
            "fake_broker_acknowledged_order",
            broker_reference=acknowledged_reference,
        )
        filled = broker.fill_order(
            pending.client_order_id,
            filled_at=request.executed_at,
            reason="configured_simulation_fill",
        )
        filled_reference = _latest_journal_reference(
            self._journal,
            "fake_broker.order.transitioned",
        )
        filled_oms = transition(
            "oms-filled",
            "FILLED",
            "fake_broker_filled_order",
            broker_reference=filled_reference,
            cumulative_filled_quantity=pending.quantity,
        )
        protection = SimulatedPositionBook(self._journal).record_fill(
            PositionUpdateRequest(
                update_id=f"{request.execution_id}-position-update",
                position_id=f"{record.run_id}-position",
                fill_transition=filled,
                expected_protection_present=request.expected_protection_present,
                expected_protection_kind=context.proposal.protective_order_plan.kind,
                monitored_at=request.executed_at,
            )
        )
        if protection.alert_intent is not None and protection.alert_dispatch is not None:
            alerts = (protection.alert_intent,)
            dispatches = (protection.alert_dispatch,)
        else:
            alert_book = AlertBook(self._journal)
            alert = alert_book.create_intent(
                AlertIntentRequest(
                    alert_id=f"alert-{request.execution_id}-completed",
                    source_event_type="workflow_simulation.execution_completed",
                    source_event_reference=protection.position.journal_references[-1],
                    severity="informational",
                    channel="local",
                    created_at=request.executed_at,
                    title="Simulation execution completed",
                    message="The approved local simulation execution completed with protection.",
                    metadata={
                        "run_id": record.run_id,
                        "position_id": protection.position.position_id,
                        "protection_status": protection.position.protection_status,
                    },
                )
            )
            dispatch = alert_book.dispatch_alert(
                AlertDispatchRequest(
                    dispatch_id=f"dispatch-{request.execution_id}-completed",
                    alert_id=alert.alert_id,
                    dispatched_at=request.executed_at,
                    reason="record_local_simulation_completion",
                ),
                NoopAlertDispatcher(),
            )
            alerts = (alert,)
            dispatches = (dispatch,)
        return (
            (approved, submitted, acknowledged_oms, filled_oms),
            (acknowledged, filled),
            protection.position,
            alerts,
            dispatches,
        )

    def _journal_execution_blocked(
        self,
        record: WorkflowSimulationRunRecord,
        request: WorkflowSimulationExecutionRequest,
        *,
        reason: str,
    ) -> None:
        payload = {
            "schema_version": 1,
            "workflow_id": record.workflow_id,
            "run_id": record.run_id,
            "execution_id": request.execution_id,
            "actor": request.actor,
            "reason": reason,
        }
        if any(
            item.event_type == "workflow_simulation.execution_blocked" and item.payload == payload
            for item in self._journal.read_all()
        ):
            return
        self._journal.append(
            "workflow_simulation.execution_blocked",
            payload,
            timestamp=request.executed_at,
        )

    def _journal_execution_node_statuses(
        self,
        record: WorkflowSimulationRunRecord,
        request: WorkflowSimulationExecutionRequest,
        protection_status: str,
    ) -> tuple[WorkflowNodeRunStatus, ...]:
        status_map = {
            "approval_ticket": (
                "approved_consumed",
                "Committed manual approval was consumed by explicit simulation execution",
            ),
            "fake_broker": ("filled", "Local fake broker acknowledged and filled the order"),
            "position_update": (
                (
                    "completed"
                    if protection_status == "expected_protection_present"
                    else "critical_missing_protection"
                ),
                (
                    "Simulated position recorded with expected protection"
                    if protection_status == "expected_protection_present"
                    else "Simulated position recorded without expected protection"
                ),
            ),
            "alert": (
                (
                    "completed_local_noop"
                    if protection_status == "expected_protection_present"
                    else "critical_local_noop"
                ),
                "Local alert intent and no-op dispatch were recorded",
            ),
            "audit_sink": ("completed", "Execution evidence was appended to the local journal"),
        }
        replacements: dict[str, WorkflowNodeRunStatus] = {}
        for node in record.node_statuses:
            if node.node_type not in status_map:
                continue
            status, detail = status_map[node.node_type]
            journal_record = self._journal.append(
                "workflow_simulation.node_status",
                {
                    "schema_version": 1,
                    "workflow_id": record.workflow_id,
                    "run_id": record.run_id,
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "status": status,
                    "detail": detail,
                },
                timestamp=request.executed_at,
            )
            replacements[node.node_id] = replace(
                node,
                status=status,
                detail=detail,
                journal_reference=_journal_reference(journal_record.sequence),
            )
        return tuple(replacements.get(node.node_id, node) for node in record.node_statuses)

    def list_runs(self, workflow_id: str) -> tuple[WorkflowSimulationRunRecord, ...]:
        _validated_identifier(workflow_id, "workflow_id")
        with self._lock:
            try:
                evidence_rows = self._persistence_store.list_workflow_simulation_run_evidence(
                    workflow_id
                )
            except Exception as exc:
                raise _evidence_unavailable() from exc
            return tuple(self._validated_record_from_evidence(row) for row in evidence_rows)

    def get_run(self, workflow_id: str, run_id: str) -> WorkflowSimulationRunRecord:
        _validated_identifier(workflow_id, "workflow_id")
        _validated_identifier(run_id, "run_id")
        with self._lock:
            evidence = self._load_evidence(run_id)
            if evidence is None or evidence.get("workflow_id") != workflow_id:
                raise WorkflowSimulationRunError("unknown workflow simulation run")
            return self._validated_record_from_evidence(evidence)

    def _load_evidence(self, run_id: str) -> dict[str, Any] | None:
        try:
            return self._persistence_store.get_workflow_simulation_run_evidence(run_id)
        except Exception as exc:
            raise _evidence_unavailable() from exc

    def _reserve_evidence(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        try:
            return self._persistence_store.reserve_workflow_simulation_run(payload)
        except Exception as exc:
            existing = self._load_evidence(str(payload["run_id"]))
            if existing is not None:
                if existing.get("request") != dict(payload):
                    raise WorkflowSimulationRunError("conflicting run_id") from exc
                if existing.get("evidence_state") == "committed":
                    return existing, False
            raise _evidence_unavailable() from exc

    def _reserve_decision(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        try:
            return self._persistence_store.reserve_workflow_simulation_decision(payload)
        except Exception as exc:
            existing = self._load_evidence(str(payload["run_id"]))
            if existing is not None:
                if existing.get("decision_request") != dict(payload):
                    raise WorkflowSimulationRunConflictError("conflicting decision") from exc
                if existing.get("decision_evidence_state") == "committed":
                    return existing, False
            raise _evidence_unavailable() from exc

    def _reserve_execution(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        try:
            return self._persistence_store.reserve_workflow_simulation_execution(payload)
        except Exception as exc:
            existing = self._load_evidence(str(payload["run_id"]))
            if existing is not None:
                if existing.get("execution_request") != dict(payload):
                    raise WorkflowSimulationRunConflictError("conflicting execution") from exc
                if existing.get("execution_evidence_state") == "committed":
                    return existing, False
            raise _evidence_unavailable() from exc

    def _finalize_evidence(
        self,
        record: WorkflowSimulationRunRecord,
        journal_manifest: tuple[JournalRecord, ...],
    ) -> dict[str, Any]:
        try:
            return self._persistence_store.finalize_workflow_simulation_run(
                record.run_id,
                record,
                journal_manifest,
            )
        except Exception as exc:
            raise _evidence_unavailable() from exc

    def _finalize_decision(
        self,
        record: WorkflowSimulationRunRecord,
        decision_record: ApprovalDecisionRecord,
        journal_manifest: tuple[JournalRecord, ...],
    ) -> dict[str, Any]:
        try:
            return self._persistence_store.finalize_workflow_simulation_decision(
                record.run_id,
                record,
                decision_record,
                journal_manifest,
            )
        except Exception as exc:
            raise _evidence_unavailable() from exc

    def _finalize_execution(
        self,
        record: WorkflowSimulationRunRecord,
        execution_record: WorkflowSimulationExecutionRecord,
        journal_manifest: tuple[JournalRecord, ...],
    ) -> dict[str, Any]:
        try:
            return self._persistence_store.finalize_workflow_simulation_execution(
                record.run_id,
                record,
                execution_record,
                journal_manifest,
            )
        except Exception as exc:
            raise _evidence_unavailable() from exc

    def _record_for_exact_request(
        self,
        evidence: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> WorkflowSimulationRunRecord:
        if evidence.get("request") != dict(payload):
            raise WorkflowSimulationRunError("conflicting run_id")
        return self._validated_record_from_evidence(evidence)

    def _record_for_exact_decision(
        self,
        evidence: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> WorkflowSimulationRunRecord:
        if evidence.get("decision_request") != dict(payload):
            raise WorkflowSimulationRunConflictError("conflicting decision")
        return self._validated_record_from_evidence(evidence)

    def _record_for_exact_execution(
        self,
        evidence: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> WorkflowSimulationRunRecord:
        if evidence.get("execution_request") != dict(payload):
            raise WorkflowSimulationRunConflictError("conflicting execution")
        return self._validated_record_from_evidence(evidence)

    def _read_journal_for_evidence(self) -> tuple[JournalRecord, ...]:
        try:
            return tuple(self._journal.read_all())
        except Exception as exc:
            raise _evidence_unavailable() from exc

    def _validated_record_from_evidence(
        self,
        evidence: Mapping[str, Any],
    ) -> WorkflowSimulationRunRecord:
        try:
            return _validated_persisted_evidence(
                evidence,
                source_records=self._read_journal_for_evidence(),
            )
        except WorkflowSimulationRunUnavailableError:
            raise
        except Exception as exc:
            raise _evidence_unavailable() from exc

    def _load_valid_workflow(self, workflow_id: str, *, expected_version: int):
        try:
            workflow = self._store.get_workflow(workflow_id)
            parse_workflow_dsl_document(workflow.document)
        except (WorkflowDefinitionError, ValueError) as exc:
            raise WorkflowSimulationRunError(str(exc)) from exc
        if workflow.version != expected_version:
            raise WorkflowSimulationRunConflictError(
                "expected_workflow_version does not match current workflow version"
            )
        return workflow

    def _journal_node_statuses(
        self,
        workflow_id: str,
        document: Mapping[str, Any],
        request: WorkflowSimulationRunRequest,
        result: Any,
    ) -> tuple[WorkflowNodeRunStatus, ...]:
        raw_nodes = document.get("nodes")
        if not isinstance(raw_nodes, list):
            raise WorkflowSimulationRunError("workflow document nodes must be a list")

        statuses: list[WorkflowNodeRunStatus] = []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, Mapping):
                raise WorkflowSimulationRunError("workflow document node must be an object")
            node_id = _required_string(raw_node, "id")
            node_type = _required_string(raw_node, "type")
            status, detail = _node_status(node_type, result)
            journal_record = self._journal.append(
                "workflow_simulation.node_status",
                {
                    "schema_version": 1,
                    "workflow_id": workflow_id,
                    "run_id": request.run_id,
                    "node_id": node_id,
                    "node_type": node_type,
                    "status": status,
                    "detail": detail,
                },
                timestamp=request.evaluated_at,
            )
            statuses.append(
                WorkflowNodeRunStatus(
                    node_id=node_id,
                    node_type=node_type,
                    status=status,
                    detail=detail,
                    journal_reference=_journal_reference(journal_record.sequence),
                ),
            )
        return tuple(statuses)

    def _journal_decision_node_statuses(
        self,
        record: WorkflowSimulationRunRecord,
        request: WorkflowSimulationDecisionRequest,
    ) -> tuple[WorkflowNodeRunStatus, ...]:
        replacements: dict[str, WorkflowNodeRunStatus] = {}
        decision_statuses = _decision_node_statuses(request.decision)
        for node in record.node_statuses:
            if node.node_type not in decision_statuses:
                continue
            status, detail = decision_statuses[node.node_type]
            journal_record = self._journal.append(
                "workflow_simulation.node_status",
                {
                    "schema_version": 1,
                    "workflow_id": record.workflow_id,
                    "run_id": record.run_id,
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "status": status,
                    "detail": detail,
                },
                timestamp=request.decided_at,
            )
            replacements[node.node_id] = replace(
                node,
                status=status,
                detail=detail,
                journal_reference=_journal_reference(journal_record.sequence),
            )
        return tuple(replacements.get(node.node_id, node) for node in record.node_statuses)


def _validated_persisted_evidence(
    evidence: Mapping[str, Any],
    *,
    source_records: tuple[JournalRecord, ...],
) -> WorkflowSimulationRunRecord:
    expected_evidence_keys = {
        "run_id",
        "workflow_id",
        "expected_workflow_version",
        "request_sha256",
        "request",
        "evidence_state",
        "record",
        "journal_manifest",
        "journal_manifest_sha256",
        "created_at",
        "updated_at",
        "decision_id",
        "decision_request_sha256",
        "decision_request",
        "decision_evidence_state",
        "decision_record",
        "decision_updated_at",
        "execution_id",
        "execution_request_sha256",
        "execution_request",
        "execution_evidence_state",
        "execution_record",
        "execution_updated_at",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != expected_evidence_keys:
        raise _evidence_unavailable()
    if evidence["evidence_state"] != "committed":
        raise _evidence_unavailable()

    request_payload = evidence["request"]
    record_payload = evidence["record"]
    manifest_payload = evidence["journal_manifest"]
    if not isinstance(request_payload, Mapping) or not isinstance(record_payload, Mapping):
        raise _evidence_unavailable()
    if not isinstance(manifest_payload, list) or not manifest_payload:
        raise _evidence_unavailable()
    expected_request_keys = {
        "schema_version",
        "workflow_id",
        "expected_workflow_version",
        "run_id",
        "requested_at",
        "evaluated_at",
        "approval_expires_at",
        "replay_input_reference",
    }
    if set(request_payload) != expected_request_keys:
        raise _evidence_unavailable()
    request = WorkflowSimulationRunRequest(
        schema_version=request_payload["schema_version"],
        expected_workflow_version=request_payload["expected_workflow_version"],
        run_id=request_payload["run_id"],
        requested_at=request_payload["requested_at"],
        evaluated_at=request_payload["evaluated_at"],
        approval_expires_at=request_payload["approval_expires_at"],
        replay_input_reference=request_payload["replay_input_reference"],
    )
    workflow_id = request_payload["workflow_id"]
    _validated_identifier(workflow_id, "workflow_id")
    record = WorkflowSimulationRunRecord.from_json_dict(
        record_payload,
        fallback_expected_workflow_version=request.expected_workflow_version,
    )
    if (
        evidence["run_id"] != request.run_id
        or evidence["workflow_id"] != workflow_id
        or evidence["expected_workflow_version"] != request.expected_workflow_version
        or record.run_id != request.run_id
        or record.workflow_id != workflow_id
        or record.expected_workflow_version != request.expected_workflow_version
        or record.created_at != request.requested_at
        or record.simulation_run.replay_input_reference != request.replay_input_reference
    ):
        raise _evidence_unavailable()

    decision_state = evidence["decision_evidence_state"]
    decision_payload = evidence["decision_request"]
    persisted_decision_record = evidence["decision_record"]
    execution_state = evidence["execution_evidence_state"]
    execution_payload = evidence["execution_request"]
    persisted_execution_record = evidence["execution_record"]
    if decision_state is None:
        if (
            decision_payload is not None
            or persisted_decision_record is not None
            or record.approval_decision is not None
            or record.updated_at != request.evaluated_at
            or execution_state is not None
            or execution_payload is not None
            or persisted_execution_record is not None
            or record.execution is not None
        ):
            raise _evidence_unavailable()
    elif decision_state == "pending":
        raise _evidence_unavailable()
    elif decision_state == "committed":
        if not isinstance(decision_payload, Mapping) or not isinstance(
            persisted_decision_record,
            Mapping,
        ):
            raise _evidence_unavailable()
        decision_record = ApprovalDecisionRecord.from_json_dict(persisted_decision_record)
        if (
            record.approval_decision != decision_record
            or decision_payload.get("decision_id") != decision_record.decision_id
            or decision_payload.get("approval_ticket_id") != decision_record.ticket_id
            or decision_payload.get("decision") != decision_record.new_status
            or decision_payload.get("workflow_id") != workflow_id
            or decision_payload.get("run_id") != request.run_id
            or decision_payload.get("expected_workflow_version")
            != request.expected_workflow_version
        ):
            raise _evidence_unavailable()
        if execution_state is None and record.updated_at != decision_record.decided_at:
            raise _evidence_unavailable()
    else:
        raise _evidence_unavailable()

    if execution_state is None:
        if (
            execution_payload is not None
            or persisted_execution_record is not None
            or record.execution is not None
        ):
            raise _evidence_unavailable()
    elif execution_state == "pending":
        raise _evidence_unavailable()
    elif execution_state == "committed":
        if (
            decision_state != "committed"
            or not isinstance(execution_payload, Mapping)
            or not isinstance(persisted_execution_record, Mapping)
        ):
            raise _evidence_unavailable()
        execution_record = WorkflowSimulationExecutionRecord.from_json_dict(
            persisted_execution_record
        )
        expected_execution_bindings = {
            "workflow_id": workflow_id,
            "expected_workflow_version": request.expected_workflow_version,
            "run_id": request.run_id,
            "approval_ticket_id": record.approval_ticket_id,
            "approval_decision_id": (
                None if record.approval_decision is None else record.approval_decision.decision_id
            ),
            "order_intent_id": f"{request.run_id}-intent",
            "risk_decision_id": f"{request.run_id}-risk",
            "order_id": f"{request.run_id}-order",
            "execution_id": f"{request.run_id}-execution",
            "executed_at": execution_record.executed_at,
            "actor": execution_record.actor,
            "execution_reference": execution_record.execution_reference,
            "reason": execution_record.reason,
            "broker_state_known": execution_record.broker_state_known,
            "expected_protection_present": execution_record.expected_protection_present,
        }
        if (
            record.execution != execution_record
            or record.updated_at != execution_record.executed_at
            or any(
                execution_payload.get(key) != value
                for key, value in expected_execution_bindings.items()
            )
        ):
            raise _evidence_unavailable()
    else:
        raise _evidence_unavailable()

    manifest_records = tuple(JournalRecord.from_json_dict(item) for item in manifest_payload)
    if any(
        raw_manifest_record != parsed_manifest_record.to_json_dict()
        for raw_manifest_record, parsed_manifest_record in zip(
            manifest_payload,
            manifest_records,
            strict=True,
        )
    ):
        raise _evidence_unavailable()
    for previous, current in zip(manifest_records, manifest_records[1:], strict=False):
        if current.sequence <= previous.sequence:
            raise _evidence_unavailable()
    source_by_sequence = {source.sequence: source for source in source_records}
    if len(source_by_sequence) != len(source_records):
        raise _evidence_unavailable()
    for manifest_record in manifest_records:
        source_record = source_by_sequence.get(manifest_record.sequence)
        if source_record is None or source_record.to_json_dict() != manifest_record.to_json_dict():
            raise _evidence_unavailable()

    manifest_references = {
        _journal_reference(manifest_record.sequence) for manifest_record in manifest_records
    }
    required_references = {
        *record.simulation_run.journal_references,
        *record.journal_references,
        *(node.journal_reference for node in record.node_statuses),
    }
    if not required_references.issubset(manifest_references):
        raise _evidence_unavailable()

    manifest_by_reference = {
        _journal_reference(manifest_record.sequence): manifest_record
        for manifest_record in manifest_records
    }
    for node in record.node_statuses:
        journal_record = manifest_by_reference[node.journal_reference]
        expected_payload = {
            "schema_version": 1,
            "workflow_id": workflow_id,
            "run_id": request.run_id,
            "node_id": node.node_id,
            "node_type": node.node_type,
            "status": node.status,
            "detail": node.detail,
        }
        if (
            journal_record.event_type != "workflow_simulation.node_status"
            or journal_record.payload != expected_payload
        ):
            raise _evidence_unavailable()

    event_types = {journal_record.event_type for journal_record in manifest_records}
    if not {
        "simulation_run.created",
        "risk.decision.evaluated",
        "workflow_simulation.node_status",
    }.issubset(event_types):
        raise _evidence_unavailable()
    if record.approval_ticket_id is not None:
        if not any(
            journal_record.event_type == "approval.ticket.created"
            and _payload_contains_value(journal_record.payload, record.approval_ticket_id)
            for journal_record in manifest_records
        ):
            raise _evidence_unavailable()
    execution_event_types = {
        "fake_broker.order.transitioned",
        "position.updated",
        "alert.intent.created",
        "alert.dispatch.recorded",
        "workflow_simulation.execution_completed",
    }
    if execution_state is None and event_types.intersection(execution_event_types):
        raise _evidence_unavailable()
    if decision_state == "committed":
        decision_record = record.approval_decision
        if decision_record is None or not any(
            journal_record.event_type == "approval.ticket.decided"
            and journal_record.payload == decision_record.to_json_dict()
            for journal_record in manifest_records
        ):
            raise _evidence_unavailable()
    if execution_state == "committed":
        execution_record = record.execution
        if execution_record is None or not execution_event_types.issubset(event_types):
            raise _evidence_unavailable()
        execution_context = _approved_execution_context(evidence, record)
        _validate_committed_execution_attribution(
            record,
            execution_record,
            execution_context,
        )
        manifest_order_history = tuple(
            item.payload
            for item in manifest_records
            if item.event_type == "oms.order.transitioned"
            and item.payload.get("order_id") == execution_record.order_id
        )
        expected_order_history = tuple(
            transition.to_json_dict()
            for transition in (
                *execution_context.oms_history,
                *execution_record.oms_transitions,
            )
        )
        if manifest_order_history != expected_order_history:
            raise _evidence_unavailable()
        if not set(execution_record.journal_references).issubset(manifest_references):
            raise _evidence_unavailable()
        required_execution_payloads = (
            *(
                ("oms.order.transitioned", transition.to_json_dict())
                for transition in execution_record.oms_transitions
            ),
            *(
                ("fake_broker.order.transitioned", transition.to_json_dict())
                for transition in execution_record.broker_transitions
            ),
            ("position.updated", execution_record.position.to_json_dict()),
            *(
                ("alert.intent.created", alert.to_json_dict())
                for alert in execution_record.alert_intents
            ),
            *(
                ("alert.dispatch.recorded", dispatch.to_json_dict())
                for dispatch in execution_record.alert_dispatches
            ),
        )
        for event_type, payload in required_execution_payloads:
            if (
                sum(
                    item.event_type == event_type and item.payload == payload
                    for item in manifest_records
                )
                != 1
            ):
                raise _evidence_unavailable()
        expected_completion_payload = {
            "schema_version": 1,
            "workflow_id": record.workflow_id,
            "run_id": record.run_id,
            "execution_id": execution_record.execution_id,
            "approval_decision_id": execution_record.approval_decision_id,
            "order_id": execution_record.order_id,
            "protection_status": execution_record.protection_status,
            "risk_increasing_actions_blocked": (execution_record.risk_increasing_actions_blocked),
        }
        completion_events = [
            item
            for item in manifest_records
            if item.event_type == "workflow_simulation.execution_completed"
            and item.payload == expected_completion_payload
        ]
        if len(completion_events) != 1:
            raise _evidence_unavailable()
    return record


def _payload_contains_value(value: Any, expected: str) -> bool:
    if value == expected:
        return True
    if isinstance(value, Mapping):
        return any(_payload_contains_value(nested, expected) for nested in value.values())
    if isinstance(value, list):
        return any(_payload_contains_value(item, expected) for item in value)
    return False


def _required_manifest(evidence: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    manifest = evidence.get("journal_manifest")
    if not isinstance(manifest, list) or not manifest:
        raise _evidence_unavailable()
    if not all(isinstance(item, Mapping) for item in manifest):
        raise _evidence_unavailable()
    return manifest


def _pending_ticket_from_evidence(
    evidence: Mapping[str, Any],
    record: WorkflowSimulationRunRecord,
) -> ApprovalTicket:
    candidates = []
    for raw_record in _required_manifest(evidence):
        journal_record = JournalRecord.from_json_dict(raw_record)
        if journal_record.event_type != "approval.ticket.created":
            continue
        if not isinstance(journal_record.payload, Mapping):
            continue
        if journal_record.payload.get("ticket_id") == record.approval_ticket_id:
            candidates.append(journal_record.payload)
    if len(candidates) != 1:
        raise _evidence_unavailable()
    try:
        ticket = ApprovalTicket.from_json_dict(candidates[0])
    except ApprovalTicketError as exc:
        raise _evidence_unavailable() from exc
    if ticket.status != "pending":
        raise _evidence_unavailable()
    return ticket


def _validate_ticket_attribution(
    ticket: ApprovalTicket,
    run_id: str,
    evidence: Mapping[str, Any],
) -> None:
    expected_values = {
        "ticket_id": f"{run_id}-approval-ticket",
        "order_id": f"{run_id}-order",
        "client_order_id": f"{run_id}-client",
        "risk_decision_id": f"{run_id}-risk",
    }
    if any(getattr(ticket, field) != expected for field, expected in expected_values.items()):
        raise _evidence_unavailable()
    records = tuple(JournalRecord.from_json_dict(item) for item in _required_manifest(evidence))
    bindings = {
        "order_intent.proposed": f"{run_id}-intent",
        "risk.decision.evaluated": f"{run_id}-risk",
        "approval.ticket.created": f"{run_id}-approval-ticket",
    }
    for event_type, identifier in bindings.items():
        matches = [
            record
            for record in records
            if record.event_type == event_type
            and _payload_contains_value(record.payload, identifier)
        ]
        if len(matches) != 1:
            raise _evidence_unavailable()
    oms_records = [
        record
        for record in records
        if record.event_type == "oms.order.transitioned"
        and _payload_contains_value(record.payload, ticket.oms_transition_reference)
    ]
    if len(oms_records) != 1:
        raise _evidence_unavailable()


def _approved_execution_context(
    evidence: Mapping[str, Any],
    record: WorkflowSimulationRunRecord,
) -> _ApprovedExecutionContext:
    decision = record.approval_decision
    if decision is None or decision.new_status != "approved":
        raise _evidence_unavailable()
    ticket = decision.ticket
    if ticket.status != "approved" or ticket.ticket_id != record.approval_ticket_id:
        raise _evidence_unavailable()
    _validate_ticket_attribution(ticket, record.run_id, evidence)
    records = tuple(JournalRecord.from_json_dict(item) for item in _required_manifest(evidence))

    proposal_payloads = [
        item.payload
        for item in records
        if item.event_type == "order_intent.proposed"
        and item.payload.get("proposal_id") == f"{record.run_id}-intent"
    ]
    risk_payloads = [
        item.payload
        for item in records
        if item.event_type == "risk.decision.evaluated"
        and item.payload.get("request_id") == f"{record.run_id}-risk"
    ]
    raw_oms_history = [
        item.payload
        for item in records
        if item.event_type == "oms.order.transitioned"
        and item.payload.get("order_id") == f"{record.run_id}-order"
    ]
    if len(proposal_payloads) != 1 or len(risk_payloads) != 1:
        raise _evidence_unavailable()
    try:
        proposal = OrderIntentProposal.from_json_dict(proposal_payloads[0])
        risk_decision = RiskDecision.from_json_dict(risk_payloads[0])
        complete_oms_history = tuple(
            OrderTransitionRecord.from_json_dict(payload) for payload in raw_oms_history
        )
    except ValueError as exc:
        raise _evidence_unavailable() from exc
    oms_history = tuple(
        transition
        for transition in complete_oms_history
        if transition.new_state in {"CREATED", "PENDING_APPROVAL"}
    )
    if tuple(item.new_state for item in oms_history) != ("CREATED", "PENDING_APPROVAL"):
        raise _evidence_unavailable()
    pending = oms_history[-1].snapshot
    risk_request = risk_decision.request
    if (
        proposal.proposal_id != f"{record.run_id}-intent"
        or proposal.protective_order_plan is None
        or proposal.protective_exception_reference is not None
        or risk_decision.request_id != ticket.risk_decision_id
        or risk_decision.result != "passed"
        or risk_request.get("broker_state_known") is not True
        or pending.order_id != ticket.order_id
        or pending.client_order_id != ticket.client_order_id
        or pending.state != "PENDING_APPROVAL"
        or pending.risk_decision_id != risk_decision.request_id
        or pending.symbol != proposal.symbol
        or pending.side != proposal.side
        or pending.quantity != proposal.quantity
        or pending.risk_intent != proposal.risk_intent
        or ticket.symbol != proposal.symbol
        or ticket.side != proposal.side
        or ticket.quantity != proposal.quantity
        or ticket.risk_intent != proposal.risk_intent
        or risk_decision.symbol != proposal.symbol
        or risk_decision.risk_intent != proposal.risk_intent
    ):
        raise _evidence_unavailable()
    raw_risk_plan = risk_request.get("protective_order")
    if not isinstance(raw_risk_plan, Mapping) or (
        raw_risk_plan != proposal.protective_order_plan.to_json_dict()
    ):
        raise _evidence_unavailable()
    return _ApprovedExecutionContext(
        ticket=ticket,
        decision=decision,
        proposal=proposal,
        risk_decision=risk_decision,
        oms_history=oms_history,
    )


def _validate_committed_execution_attribution(
    record: WorkflowSimulationRunRecord,
    execution: WorkflowSimulationExecutionRecord,
    context: _ApprovedExecutionContext,
) -> None:
    expected_ids = {
        "approval_ticket_id": f"{record.run_id}-approval-ticket",
        "order_intent_id": f"{record.run_id}-intent",
        "risk_decision_id": f"{record.run_id}-risk",
        "order_id": f"{record.run_id}-order",
        "execution_id": f"{record.run_id}-execution",
    }
    if any(getattr(execution, field) != value for field, value in expected_ids.items()):
        raise _evidence_unavailable()
    pending = context.oms_history[-1].snapshot
    expected_previous_states = (
        "PENDING_APPROVAL",
        "APPROVED",
        "SUBMITTED",
        "ACKNOWLEDGED",
    )
    if any(
        transition.previous_state != previous_state
        or transition.request.get("target_state") != transition.new_state
        or transition.request.get("order_id") != execution.order_id
        or transition.snapshot.client_order_id != pending.client_order_id
        or transition.snapshot.symbol != context.proposal.symbol
        or transition.snapshot.side != context.proposal.side
        or transition.snapshot.quantity != context.proposal.quantity
        or transition.snapshot.risk_decision_id != execution.risk_decision_id
        or transition.snapshot.approval_reference != context.decision.decision_reference
        for transition, previous_state in zip(
            execution.oms_transitions,
            expected_previous_states,
            strict=True,
        )
    ):
        raise _evidence_unavailable()
    if any(
        transition.client_order_id != pending.client_order_id
        or transition.symbol != context.proposal.symbol
        or transition.side != context.proposal.side
        or transition.quantity != context.proposal.quantity
        or transition.order.get("risk_decision_id") != execution.risk_decision_id
        or transition.order.get("approval_reference") != context.decision.decision_reference
        for transition in execution.broker_transitions
    ):
        raise _evidence_unavailable()
    filled = execution.broker_transitions[-1]
    if (
        execution.position.position_id != f"{record.run_id}-position"
        or execution.position.symbol != context.proposal.symbol
        or execution.position.quantity != context.proposal.quantity
        or execution.position.average_price != filled.fill_price
        or execution.position.source_fill_reference != filled.fake_broker_order_id
    ):
        raise _evidence_unavailable()


def _decision_node_statuses(decision: str) -> dict[str, tuple[str, str]]:
    if decision == "approved":
        return {
            "approval_ticket": (
                "approved_not_executed",
                "Manual simulation approval recorded; execution remains separate",
            ),
            "fake_broker": (
                "blocked_pending_explicit_execution",
                "Fake broker remains blocked pending a separate execution slice",
            ),
            "position_update": (
                "blocked_pending_explicit_execution",
                "Position update remains blocked because no execution occurred",
            ),
            "alert": (
                "blocked_pending_explicit_execution",
                "Execution alert remains blocked because no execution occurred",
            ),
        }
    if decision == "rejected":
        return {
            "approval_ticket": ("rejected", "Manual simulation rejection recorded"),
            "fake_broker": ("blocked_rejected", "Fake broker is blocked by rejection"),
            "position_update": ("blocked_rejected", "Position update is blocked by rejection"),
            "alert": ("blocked_rejected", "Execution alert is blocked by rejection"),
        }
    raise WorkflowSimulationRunError("decision must be approved or rejected")


def _evidence_unavailable() -> WorkflowSimulationRunUnavailableError:
    return WorkflowSimulationRunUnavailableError("workflow simulation evidence is unavailable")


def _node_status(node_type: str, result: Any) -> tuple[str, str]:
    approval_wait = result.approval_ticket is not None
    statuses = {
        "replay_source": ("completed", "Deterministic local replay was loaded"),
        "bar_builder": ("completed", "Replay events produced local bars"),
        "strategy_trigger": ("completed", "First-bar breakout strategy evaluated"),
        "risk_check": ("passed", "Risk checks passed before approval ticket creation"),
        "approval_ticket": ("waiting_for_approval", "Manual approval is required"),
        "fake_broker": (
            "blocked_waiting_for_approval",
            "Downstream simulation node remains blocked until manual approval",
        ),
        "position_update": (
            "blocked_waiting_for_approval",
            "Position update remains blocked until manual approval",
        ),
        "alert": (
            "blocked_waiting_for_approval",
            "Alert node remains blocked until manual approval",
        ),
        "audit_sink": ("completed", "Workflow node statuses were journaled"),
    }
    if not approval_wait and node_type in {
        "approval_ticket",
        "fake_broker",
        "position_update",
        "alert",
    }:
        return ("not_created", "Risk-increasing path did not reach manual approval")
    try:
        return statuses[node_type]
    except KeyError as exc:
        raise WorkflowSimulationRunError(f"unsupported workflow node type: {node_type}") from exc


def _orchestration_config(request: WorkflowSimulationRunRequest) -> ReplayToApprovalConfig:
    return ReplayToApprovalConfig(
        run_id=request.run_id,
        requested_at=request.requested_at,
        replay_input_reference=request.replay_input_reference,
        strategy_id=f"{request.run_id}-strategy",
        proposal_id=f"{request.run_id}-intent",
        risk_request_id=f"{request.run_id}-risk",
        order_id=f"{request.run_id}-order",
        client_order_id=f"{request.run_id}-client",
        ticket_id=f"{request.run_id}-approval-ticket",
        symbol="AAPL",
        quantity=10,
        evaluated_at=request.evaluated_at,
        approval_expires_at=request.approval_expires_at,
        broker_state_known=True,
        existing_risk_request_ids=frozenset(),
        risk_time_domain="replay",
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        max_order_quantity=100,
        max_order_notional=10_000.0,
        max_market_data_age_seconds=30,
        allowed_symbols=("AAPL",),
    )


def _historical_sessions() -> tuple[HistoricalVolumeSession, ...]:
    return tuple(
        HistoricalVolumeSession(
            session_id=f"historical-session-{index:02d}",
            bars=(
                _historical_bar(0, high=101.00, close=100.50, volume=50.0),
                _historical_bar(1, high=101.25, close=100.75, volume=70.0),
                _historical_bar(2, high=101.40, close=101.00, volume=80.0),
            ),
        )
        for index in range(10)
    )


def _historical_bar(index: int, *, high: float, close: float, volume: float) -> Bar:
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


def _deterministic_replay_events() -> tuple[MarketDataReplayEvent, ...]:
    return (
        _replay_event(1, "2026-07-08T13:30:00Z", price=100.50, volume=50.0),
        _replay_event(2, "2026-07-08T13:31:00Z", price=101.50, volume=50.0),
        _replay_event(3, "2026-07-08T13:35:00Z", price=101.40, volume=80.0),
        _replay_event(4, "2026-07-08T13:40:00Z", price=102.20, volume=200.0),
    )


def _replay_event(
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


def _validate_schema_version(schema_version: Any) -> None:
    if isinstance(schema_version, bool) or schema_version != 1:
        raise WorkflowSimulationRunError("schema_version must be 1")


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowSimulationRunError(f"{field_name} must be a non-empty string")
    if value.strip() != value:
        raise WorkflowSimulationRunError(
            f"{field_name} must not contain leading or trailing whitespace"
        )
    return value


def _validated_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowSimulationRunError(f"{field_name} must be a non-empty string")
    return value


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    _validated_identifier(value, key)
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _validated_identifier(value, field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkflowSimulationRunError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WorkflowSimulationRunError(f"{field_name} must include a timezone")
    return parsed


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkflowSimulationRunError(f"{field_name} must be a positive integer")
    return value


def _validated_journal_reference(reference: str) -> None:
    _validated_identifier(reference, "journal_reference")
    if not reference.startswith("journal_sequence:"):
        raise WorkflowSimulationRunError("journal_reference must use journal_sequence references")


def _validated_journal_references(references: tuple[str, ...]) -> None:
    if not isinstance(references, tuple) or not references:
        raise WorkflowSimulationRunError("journal_references must be a non-empty tuple")
    for reference in references:
        _validated_journal_reference(reference)


def _journal_reference(sequence: int) -> str:
    return f"journal_sequence:{sequence}"


def _latest_journal_reference(journal: JsonlEventJournal, event_type: str) -> str:
    for record in reversed(journal.read_all()):
        if record.event_type == event_type:
            return _journal_reference(record.sequence)
    raise WorkflowSimulationRunError(f"journal event does not exist: {event_type}")


def _assert_json_serializable(payload: Mapping[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkflowSimulationRunError(f"{payload_name} must be JSON-serializable") from exc
