from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.emergency_stop import EmergencyStopError, EmergencyStopService
from trading_oms_backend.event_journal import JournalRecord, JsonlEventJournal
from trading_oms_backend.market_data_replay import MarketDataReplayEvent
from trading_oms_backend.product_strategy import HistoricalVolumeSession
from trading_oms_backend.risk_engine import RiskPolicy
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
class WorkflowSimulationRunRecord:
    workflow_id: str
    run_id: str
    status: str
    created_at: str
    updated_at: str
    simulation_run: SimulationRunRecord
    node_statuses: tuple[WorkflowNodeRunStatus, ...]
    journal_references: tuple[str, ...]
    approval_ticket_id: str | None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.workflow_id, "workflow_id")
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
        _assert_json_serializable(self.to_json_dict(), "workflow simulation run record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approval_ticket_id": self.approval_ticket_id,
            "simulation_run": self.simulation_run.to_json_dict(),
            "node_statuses": [node.to_json_dict() for node in self.node_statuses],
            "journal_references": list(self.journal_references),
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> WorkflowSimulationRunRecord:
        expected_keys = {
            "schema_version",
            "workflow_id",
            "run_id",
            "status",
            "created_at",
            "updated_at",
            "approval_ticket_id",
            "simulation_run",
            "node_statuses",
            "journal_references",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise WorkflowSimulationRunError("workflow simulation run record fields are invalid")
        simulation_run = raw_record["simulation_run"]
        node_statuses = raw_record["node_statuses"]
        journal_references = raw_record["journal_references"]
        if not isinstance(simulation_run, Mapping):
            raise WorkflowSimulationRunError("simulation_run must be an object")
        if not isinstance(node_statuses, list):
            raise WorkflowSimulationRunError("node_statuses must be a list")
        if not isinstance(journal_references, list):
            raise WorkflowSimulationRunError("journal_references must be a list")
        return cls(
            schema_version=raw_record["schema_version"],
            workflow_id=raw_record["workflow_id"],
            run_id=raw_record["run_id"],
            status=raw_record["status"],
            created_at=raw_record["created_at"],
            updated_at=raw_record["updated_at"],
            approval_ticket_id=raw_record["approval_ticket_id"],
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

    def _record_for_exact_request(
        self,
        evidence: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> WorkflowSimulationRunRecord:
        if evidence.get("request") != dict(payload):
            raise WorkflowSimulationRunError("conflicting run_id")
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
    record = WorkflowSimulationRunRecord.from_json_dict(record_payload)
    if (
        evidence["run_id"] != request.run_id
        or evidence["workflow_id"] != workflow_id
        or evidence["expected_workflow_version"] != request.expected_workflow_version
        or record.run_id != request.run_id
        or record.workflow_id != workflow_id
        or record.created_at != request.requested_at
        or record.updated_at != request.evaluated_at
        or record.simulation_run.replay_input_reference != request.replay_input_reference
    ):
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
        if current.sequence != previous.sequence + 1:
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
    forbidden_event_types = {
        "fake_broker.order.transitioned",
        "position.updated",
        "alert.intent.created",
    }
    if event_types.intersection(forbidden_event_types):
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


def _assert_json_serializable(payload: Mapping[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkflowSimulationRunError(f"{payload_name} must be JSON-serializable") from exc
