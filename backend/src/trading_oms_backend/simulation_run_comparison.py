from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from trading_oms_backend.event_journal import JournalRecord
from trading_oms_backend.read_models import build_demo_operations_read_model
from trading_oms_backend.simulation_execution_projections import (
    SimulationExecutionProjectionError,
    project_simulation_executions,
    validated_simulation_lifecycle,
)
from trading_oms_backend.workflow_simulation_runs import WorkflowSimulationProjectionSource

ComparisonStatus = Literal["added", "removed", "changed", "unchanged"]
JournalScope = Literal["complete_run_manifest", "single_journal_event"]

SECTION_NAMES = (
    "workflow",
    "run",
    "signal",
    "order_intent",
    "risk_decision",
    "approval_ticket",
    "approval_decision",
    "execution",
    "protection",
    "alerts",
    "journal_provenance",
)

_BASE_CLASSIFICATIONS = (
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
_MISSING = object()


class SimulationRunComparisonError(ValueError):
    """Raised when committed simulation evidence cannot form a safe comparison."""


class SimulationRunNotFoundError(SimulationRunComparisonError):
    """Raised when a selected committed simulation run does not exist."""


class AuditExportSelectionConflictError(SimulationRunComparisonError):
    """Raised when a selected manifest digest is stale."""


class AuditExportSelectionError(SimulationRunComparisonError):
    """Raised when an audit export selection request is invalid."""


@dataclass(frozen=True)
class SimulationRunSelector:
    workflow_id: str
    run_id: str

    def __post_init__(self) -> None:
        _validated_identifier(self.workflow_id, "workflow_id")
        _validated_identifier(self.run_id, "run_id")

    def to_json_dict(self) -> dict[str, str]:
        return {
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class JournalEvidenceRecord:
    sequence: int
    journal_reference: str
    event_type: str
    timestamp: str
    record_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 1
        ):
            raise SimulationRunComparisonError("journal evidence sequence is invalid")
        if self.journal_reference != _journal_reference(self.sequence):
            raise SimulationRunComparisonError("journal evidence reference is invalid")
        _validated_identifier(self.event_type, "event_type")
        _validated_identifier(self.timestamp, "timestamp")
        _validated_sha256(self.record_sha256, "record_sha256")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "journal_reference": self.journal_reference,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "record_sha256": self.record_sha256,
        }


@dataclass(frozen=True)
class SimulationJournalProvenance:
    manifest_sha256: str
    journal_references: tuple[str, ...]
    records: tuple[JournalEvidenceRecord, ...]

    def __post_init__(self) -> None:
        _validated_sha256(self.manifest_sha256, "manifest_sha256")
        if not self.journal_references or len(self.journal_references) != len(self.records):
            raise SimulationRunComparisonError("journal provenance is incomplete")
        if len(set(self.journal_references)) != len(self.journal_references):
            raise SimulationRunComparisonError("journal provenance references are duplicated")
        if tuple(item.journal_reference for item in self.records) != self.journal_references:
            raise SimulationRunComparisonError("journal provenance references are inconsistent")
        if tuple(item.sequence for item in self.records) != tuple(
            sorted(item.sequence for item in self.records)
        ):
            raise SimulationRunComparisonError("journal provenance records are not ordered")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "manifest_sha256": self.manifest_sha256,
            "journal_references": list(self.journal_references),
            "records": [item.to_json_dict() for item in self.records],
        }


@dataclass(frozen=True)
class SimulationRunEvidenceSnapshot:
    selector: SimulationRunSelector
    workflow: dict[str, Any]
    run: dict[str, Any]
    signal: dict[str, Any]
    order_intent: dict[str, Any]
    risk_decision: dict[str, Any]
    approval_ticket: dict[str, Any]
    approval_decision: dict[str, Any] | None
    execution: dict[str, Any] | None
    protection: dict[str, Any] | None
    alerts: tuple[dict[str, Any], ...]
    journal_provenance: SimulationJournalProvenance
    classifications: tuple[str, ...]
    broker_derived: bool = False
    externally_verified: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise SimulationRunComparisonError("snapshot schema version is invalid")
        if not isinstance(self.selector, SimulationRunSelector):
            raise SimulationRunComparisonError("snapshot selector is invalid")
        for name in (
            "workflow",
            "run",
            "signal",
            "order_intent",
            "risk_decision",
            "approval_ticket",
        ):
            _validated_json_object(getattr(self, name), name)
        for name in ("approval_decision", "execution", "protection"):
            value = getattr(self, name)
            if value is not None:
                _validated_json_object(value, name)
        if not isinstance(self.alerts, tuple) or any(
            not isinstance(item, dict) for item in self.alerts
        ):
            raise SimulationRunComparisonError("snapshot alerts are invalid")
        if not isinstance(self.journal_provenance, SimulationJournalProvenance):
            raise SimulationRunComparisonError("snapshot journal provenance is invalid")
        expected_classifications = (
            _EXECUTION_CLASSIFICATIONS if self.execution is not None else _BASE_CLASSIFICATIONS
        )
        if self.classifications != expected_classifications:
            raise SimulationRunComparisonError("snapshot classifications are invalid")
        if self.broker_derived is not False or self.externally_verified is not False:
            raise SimulationRunComparisonError("snapshot provenance is unsafe")
        _validated_json_object(self.to_json_dict(), "simulation run evidence snapshot")

    def section_value(self, name: str) -> Any:
        if name not in SECTION_NAMES:
            raise SimulationRunComparisonError("comparison section is invalid")
        if name == "journal_provenance":
            return self.journal_provenance.to_json_dict()
        if name == "alerts":
            return [dict(item) for item in self.alerts]
        return getattr(self, name)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "selector": self.selector.to_json_dict(),
            "workflow": _normalized_json(self.workflow),
            "run": _normalized_json(self.run),
            "signal": _normalized_json(self.signal),
            "order_intent": _normalized_json(self.order_intent),
            "risk_decision": _normalized_json(self.risk_decision),
            "approval_ticket": _normalized_json(self.approval_ticket),
            "approval_decision": _normalized_json(self.approval_decision),
            "execution": _normalized_json(self.execution),
            "protection": _normalized_json(self.protection),
            "alerts": _normalized_json(list(self.alerts)),
            "journal_provenance": self.journal_provenance.to_json_dict(),
            "provenance": {
                "classifications": list(self.classifications),
                "broker_derived": self.broker_derived,
                "externally_verified": self.externally_verified,
            },
        }


@dataclass(frozen=True)
class SimulationRunComparisonField:
    path: str
    status: ComparisonStatus
    left_value: Any
    right_value: Any

    def __post_init__(self) -> None:
        _validated_identifier(self.path, "comparison field path")
        if self.status not in {"added", "removed", "changed", "unchanged"}:
            raise SimulationRunComparisonError("comparison field status is invalid")
        _normalized_json(self.left_value)
        _normalized_json(self.right_value)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "left_value": _normalized_json(self.left_value),
            "right_value": _normalized_json(self.right_value),
        }


@dataclass(frozen=True)
class SimulationRunComparisonSection:
    name: str
    status: ComparisonStatus
    left_value: Any
    right_value: Any
    differences: tuple[SimulationRunComparisonField, ...]

    def __post_init__(self) -> None:
        if self.name not in SECTION_NAMES:
            raise SimulationRunComparisonError("comparison section name is invalid")
        if self.status not in {"added", "removed", "changed", "unchanged"}:
            raise SimulationRunComparisonError("comparison section status is invalid")
        if tuple(item.path for item in self.differences) != tuple(
            sorted(item.path for item in self.differences)
        ):
            raise SimulationRunComparisonError("comparison fields are not ordered")
        if self.status == "unchanged" and self.differences:
            raise SimulationRunComparisonError("unchanged section contains differences")
        if self.status != "unchanged" and not self.differences:
            raise SimulationRunComparisonError("changed section lacks differences")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "left_value": _normalized_json(self.left_value),
            "right_value": _normalized_json(self.right_value),
            "differences": [item.to_json_dict() for item in self.differences],
        }


@dataclass(frozen=True)
class SimulationRunComparison:
    left: SimulationRunEvidenceSnapshot
    right: SimulationRunEvidenceSnapshot
    selection_state: Literal["same_run", "different_runs"]
    sections: tuple[SimulationRunComparisonSection, ...]
    comparison_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise SimulationRunComparisonError("comparison schema version is invalid")
        if self.selection_state not in {"same_run", "different_runs"}:
            raise SimulationRunComparisonError("comparison selection state is invalid")
        if tuple(item.name for item in self.sections) != SECTION_NAMES:
            raise SimulationRunComparisonError("comparison sections are incomplete")
        _validated_sha256(self.comparison_sha256, "comparison_sha256")
        if self.comparison_sha256 != _comparison_sha256(
            self.left,
            self.right,
            self.selection_state,
            self.sections,
        ):
            raise SimulationRunComparisonError("comparison digest is inconsistent")

    @property
    def summary(self) -> dict[str, int]:
        return {
            status: sum(item.status == status for item in self.sections)
            for status in ("added", "removed", "changed", "unchanged")
        }

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "selection_state": self.selection_state,
            "comparison_sha256": self.comparison_sha256,
            "summary": self.summary,
            "left": self.left.to_json_dict(),
            "right": self.right.to_json_dict(),
            "sections": [item.to_json_dict() for item in self.sections],
        }

    def to_stable_json(self) -> str:
        return _stable_json(self.to_json_dict())


@dataclass(frozen=True)
class AuditExportSelection:
    workflow_id: str
    workflow_version: int
    run_id: str
    run_status: str
    source_manifest_sha256: str
    source_manifest_journal_references: tuple[str, ...]
    journal_scope: JournalScope
    selected_journal_references: tuple[str, ...]
    selected_record_sha256: tuple[str, ...]
    classifications: tuple[str, ...]
    selection_sha256: str
    broker_derived: bool = False
    externally_verified: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.workflow_version < 1:
            raise SimulationRunComparisonError("audit selection version is invalid")
        for value, name in (
            (self.workflow_id, "workflow_id"),
            (self.run_id, "run_id"),
            (self.run_status, "run_status"),
        ):
            _validated_identifier(value, name)
        _validated_sha256(self.source_manifest_sha256, "source_manifest_sha256")
        if self.journal_scope not in {"complete_run_manifest", "single_journal_event"}:
            raise SimulationRunComparisonError("audit journal scope is invalid")
        if (
            not isinstance(self.source_manifest_journal_references, tuple)
            or not self.source_manifest_journal_references
            or len(set(self.source_manifest_journal_references))
            != len(self.source_manifest_journal_references)
        ):
            raise SimulationRunComparisonError("source manifest references are empty")
        for reference in self.source_manifest_journal_references:
            _validated_journal_reference(reference)
        if (
            not isinstance(self.selected_journal_references, tuple)
            or not self.selected_journal_references
            or len(set(self.selected_journal_references)) != len(self.selected_journal_references)
            or not isinstance(self.selected_record_sha256, tuple)
            or len(self.selected_journal_references) != len(self.selected_record_sha256)
        ):
            raise SimulationRunComparisonError("selected audit records are incomplete")
        for reference in self.selected_journal_references:
            _validated_journal_reference(reference)
        if not set(self.selected_journal_references).issubset(
            self.source_manifest_journal_references
        ):
            raise SimulationRunComparisonError("selected audit records are outside the manifest")
        for digest in self.selected_record_sha256:
            _validated_sha256(digest, "selected_record_sha256")
        if self.journal_scope == "complete_run_manifest" and (
            self.selected_journal_references != self.source_manifest_journal_references
        ):
            raise SimulationRunComparisonError("complete audit scope is incomplete")
        if (
            self.journal_scope == "single_journal_event"
            and len(self.selected_journal_references) != 1
        ):
            raise SimulationRunComparisonError("single-event audit scope is invalid")
        if self.classifications not in {
            _BASE_CLASSIFICATIONS,
            _EXECUTION_CLASSIFICATIONS,
        }:
            raise SimulationRunComparisonError("audit selection classifications are invalid")
        if self.broker_derived is not False or self.externally_verified is not False:
            raise SimulationRunComparisonError("audit selection provenance is unsafe")
        _validated_sha256(self.selection_sha256, "selection_sha256")
        if self.selection_sha256 != _audit_selection_sha256(self, include_digest=False):
            raise SimulationRunComparisonError("audit selection digest is inconsistent")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "workflow_version": self.workflow_version,
            "run_id": self.run_id,
            "run_status": self.run_status,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_manifest_journal_references": list(self.source_manifest_journal_references),
            "journal_scope": self.journal_scope,
            "selected_journal_references": list(self.selected_journal_references),
            "selected_record_sha256": list(self.selected_record_sha256),
            "classifications": list(self.classifications),
            "broker_derived": self.broker_derived,
            "externally_verified": self.externally_verified,
            "selection_sha256": self.selection_sha256,
        }


@dataclass(frozen=True)
class SelectedSimulationRunAuditEvidence:
    source: WorkflowSimulationProjectionSource
    snapshot: SimulationRunEvidenceSnapshot
    journal_records: tuple[JournalRecord, ...]
    selection: AuditExportSelection


def build_simulation_run_comparison(
    sources: tuple[WorkflowSimulationProjectionSource, ...],
    *,
    left: SimulationRunSelector,
    right: SimulationRunSelector,
) -> SimulationRunComparison:
    _validated_sources(sources)
    if not isinstance(left, SimulationRunSelector) or not isinstance(right, SimulationRunSelector):
        raise SimulationRunComparisonError("comparison selectors are invalid")
    source_by_selector = {(item.run.workflow_id, item.run.run_id): item for item in sources}
    if len(source_by_selector) != len(sources):
        raise SimulationRunComparisonError("duplicate simulation run selector")
    left_source = source_by_selector.get((left.workflow_id, left.run_id))
    right_source = source_by_selector.get((right.workflow_id, right.run_id))
    if left_source is None or right_source is None:
        raise SimulationRunNotFoundError("selected simulation run was not found")
    left_snapshot = _snapshot(left_source, left)
    right_snapshot = left_snapshot if left == right else _snapshot(right_source, right)
    sections = tuple(
        _compare_section(
            name,
            left_snapshot.section_value(name),
            right_snapshot.section_value(name),
        )
        for name in SECTION_NAMES
    )
    selection_state = "same_run" if left == right else "different_runs"
    return SimulationRunComparison(
        left=left_snapshot,
        right=right_snapshot,
        selection_state=selection_state,
        sections=sections,
        comparison_sha256=_comparison_sha256(
            left_snapshot,
            right_snapshot,
            selection_state,
            sections,
        ),
    )


def select_simulation_run_audit_evidence(
    sources: tuple[WorkflowSimulationProjectionSource, ...],
    *,
    selector: SimulationRunSelector,
    expected_manifest_sha256: str,
    journal_scope: str,
    journal_sequence: int | None = None,
) -> SelectedSimulationRunAuditEvidence:
    try:
        _validated_sha256(expected_manifest_sha256, "expected_manifest_sha256")
    except SimulationRunComparisonError as exc:
        raise AuditExportSelectionError("expected manifest digest is invalid") from exc
    if journal_scope == "complete_run_manifest":
        if journal_sequence is not None:
            raise AuditExportSelectionError("complete manifest scope forbids journal sequence")
    elif journal_scope == "single_journal_event":
        if not isinstance(journal_sequence, int) or isinstance(journal_sequence, bool):
            raise AuditExportSelectionError("single-event scope requires journal sequence")
    else:
        raise AuditExportSelectionError("audit journal scope is invalid")
    comparison = build_simulation_run_comparison(
        sources,
        left=selector,
        right=selector,
    )
    snapshot = comparison.left
    if expected_manifest_sha256 != snapshot.journal_provenance.manifest_sha256:
        raise AuditExportSelectionConflictError("selected manifest digest is stale")
    if journal_scope == "complete_run_manifest":
        selected_records = _selected_source(sources, selector).journal_manifest
    else:
        selected_records = tuple(
            item
            for item in _selected_source(sources, selector).journal_manifest
            if item.sequence == journal_sequence
        )
        if len(selected_records) != 1:
            raise AuditExportSelectionError("selected journal sequence is outside the manifest")
    selected_references = tuple(_journal_reference(item.sequence) for item in selected_records)
    selected_digests = tuple(_sha256(item.to_json_dict()) for item in selected_records)
    selection_payload = {
        "schema_version": 1,
        "workflow_id": selector.workflow_id,
        "workflow_version": int(snapshot.workflow["expected_workflow_version"]),
        "run_id": selector.run_id,
        "run_status": str(snapshot.run["status"]),
        "source_manifest_sha256": snapshot.journal_provenance.manifest_sha256,
        "source_manifest_journal_references": list(snapshot.journal_provenance.journal_references),
        "journal_scope": journal_scope,
        "selected_journal_references": list(selected_references),
        "selected_record_sha256": list(selected_digests),
        "classifications": list(snapshot.classifications),
        "broker_derived": False,
        "externally_verified": False,
    }
    selection = AuditExportSelection(
        workflow_id=selector.workflow_id,
        workflow_version=int(snapshot.workflow["expected_workflow_version"]),
        run_id=selector.run_id,
        run_status=str(snapshot.run["status"]),
        source_manifest_sha256=snapshot.journal_provenance.manifest_sha256,
        source_manifest_journal_references=snapshot.journal_provenance.journal_references,
        journal_scope=journal_scope,
        selected_journal_references=selected_references,
        selected_record_sha256=selected_digests,
        classifications=snapshot.classifications,
        broker_derived=False,
        externally_verified=False,
        selection_sha256=_sha256(selection_payload),
    )
    return SelectedSimulationRunAuditEvidence(
        source=_selected_source(sources, selector),
        snapshot=snapshot,
        journal_records=selected_records,
        selection=selection,
    )


def _validated_sources(sources: tuple[WorkflowSimulationProjectionSource, ...]) -> None:
    if not isinstance(sources, tuple) or not sources:
        raise SimulationRunNotFoundError("no committed simulation runs are available")
    if any(not isinstance(item, WorkflowSimulationProjectionSource) for item in sources):
        raise SimulationRunComparisonError("simulation projection sources are invalid")
    try:
        project_simulation_executions(build_demo_operations_read_model(), sources)
    except Exception as exc:
        raise SimulationRunComparisonError("simulation comparison evidence is invalid") from exc


def _selected_source(
    sources: tuple[WorkflowSimulationProjectionSource, ...],
    selector: SimulationRunSelector,
) -> WorkflowSimulationProjectionSource:
    matches = tuple(
        source
        for source in sources
        if source.run.workflow_id == selector.workflow_id and source.run.run_id == selector.run_id
    )
    if len(matches) != 1:
        raise SimulationRunNotFoundError("selected simulation run was not found")
    return matches[0]


def _snapshot(
    source: WorkflowSimulationProjectionSource,
    selector: SimulationRunSelector,
) -> SimulationRunEvidenceSnapshot:
    _validate_manifest_attribution(source)
    try:
        lifecycle = validated_simulation_lifecycle(source)
    except SimulationExecutionProjectionError as exc:
        raise SimulationRunComparisonError("simulation lifecycle evidence is invalid") from exc
    run = source.run
    if run.workflow_id != selector.workflow_id or run.run_id != selector.run_id:
        raise SimulationRunComparisonError("simulation selector attribution is inconsistent")
    journal_provenance = _journal_provenance(source.journal_manifest)
    execution = None if run.execution is None else run.execution.to_json_dict()
    protection = None
    alerts: tuple[dict[str, Any], ...] = ()
    if run.execution is not None:
        protection = {
            "status": run.execution.protection_status,
            "expected_protection_present": run.execution.expected_protection_present,
            "expected_protection_kind": run.execution.position.expected_protection_kind,
            "risk_increasing_actions_blocked": run.execution.risk_increasing_actions_blocked,
            "position_id": run.execution.position.position_id,
            "journal_references": list(run.execution.position.journal_references),
        }
        alerts = tuple(
            {
                "alert_id": intent.alert_id,
                "channel": intent.channel,
                "severity": intent.severity,
                "title": intent.title,
                "created_at": intent.created_at,
                "source_event_reference": intent.source_event_reference,
                "dispatch_status": dispatch.status,
                "dispatcher": dispatch.dispatcher,
            }
            for intent, dispatch in zip(
                run.execution.alert_intents,
                run.execution.alert_dispatches,
                strict=True,
            )
        )
    classifications = _EXECUTION_CLASSIFICATIONS if execution is not None else _BASE_CLASSIFICATIONS
    return SimulationRunEvidenceSnapshot(
        selector=selector,
        workflow={
            "workflow_id": run.workflow_id,
            "expected_workflow_version": run.expected_workflow_version,
        },
        run={
            "run_id": run.run_id,
            "status": run.status,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "replay_input_reference": run.simulation_run.replay_input_reference,
            "simulation_status": run.simulation_run.status,
        },
        signal=lifecycle.signal.to_json_dict(),
        order_intent=lifecycle.proposal.to_json_dict(),
        risk_decision=lifecycle.risk_decision.to_json_dict(),
        approval_ticket=lifecycle.current_ticket.to_json_dict(),
        approval_decision=(
            None
            if lifecycle.approval_decision is None
            else lifecycle.approval_decision.to_json_dict()
        ),
        execution=execution,
        protection=protection,
        alerts=alerts,
        journal_provenance=journal_provenance,
        classifications=classifications,
    )


def _validate_manifest_attribution(source: WorkflowSimulationProjectionSource) -> None:
    for record in source.journal_manifest:
        workflow_id = record.payload.get("workflow_id")
        run_id = record.payload.get("run_id")
        if workflow_id is not None and workflow_id != source.run.workflow_id:
            raise SimulationRunComparisonError(
                "simulation manifest workflow attribution is inconsistent"
            )
        if run_id is not None and run_id != source.run.run_id:
            raise SimulationRunComparisonError(
                "simulation manifest run attribution is inconsistent"
            )


def _journal_provenance(
    records: tuple[JournalRecord, ...],
) -> SimulationJournalProvenance:
    if not records:
        raise SimulationRunComparisonError("simulation journal manifest is empty")
    ordered_records = tuple(sorted(records, key=lambda item: item.sequence))
    if ordered_records != records:
        raise SimulationRunComparisonError("simulation journal manifest is not ordered")
    evidence_records = tuple(
        JournalEvidenceRecord(
            sequence=item.sequence,
            journal_reference=_journal_reference(item.sequence),
            event_type=item.event_type,
            timestamp=item.timestamp,
            record_sha256=_sha256(item.to_json_dict()),
        )
        for item in records
    )
    return SimulationJournalProvenance(
        manifest_sha256=_sha256([item.to_json_dict() for item in records]),
        journal_references=tuple(item.journal_reference for item in evidence_records),
        records=evidence_records,
    )


def _compare_section(name: str, left: Any, right: Any) -> SimulationRunComparisonSection:
    status = _comparison_status(left, right)
    differences = (
        ()
        if status == "unchanged"
        else tuple(sorted(_field_differences(left, right), key=lambda item: item.path))
    )
    return SimulationRunComparisonSection(
        name=name,
        status=status,
        left_value=_normalized_json(left),
        right_value=_normalized_json(right),
        differences=differences,
    )


def _comparison_status(left: Any, right: Any) -> ComparisonStatus:
    if _normalized_json(left) == _normalized_json(right):
        return "unchanged"
    if _absent(left) and not _absent(right):
        return "added"
    if not _absent(left) and _absent(right):
        return "removed"
    return "changed"


def _field_differences(
    left: Any, right: Any, path: str = "$"
) -> list[SimulationRunComparisonField]:
    if left is not _MISSING and right is not _MISSING:
        left = _normalized_json(left)
        right = _normalized_json(right)
        if left == right:
            return []
    if isinstance(left, dict) or isinstance(right, dict):
        left_mapping = left if isinstance(left, dict) else {}
        right_mapping = right if isinstance(right, dict) else {}
        differences: list[SimulationRunComparisonField] = []
        for key in sorted(set(left_mapping) | set(right_mapping)):
            differences.extend(
                _field_differences(
                    left_mapping.get(key, _MISSING),
                    right_mapping.get(key, _MISSING),
                    key if path == "$" else f"{path}.{key}",
                )
            )
        return differences
    if isinstance(left, list) or isinstance(right, list):
        left_list = left if isinstance(left, list) else []
        right_list = right if isinstance(right, list) else []
        differences = []
        for index in range(max(len(left_list), len(right_list))):
            differences.extend(
                _field_differences(
                    left_list[index] if index < len(left_list) else _MISSING,
                    right_list[index] if index < len(right_list) else _MISSING,
                    f"{path}[{index}]",
                )
            )
        return differences
    left_missing = left is _MISSING
    right_missing = right is _MISSING
    left_value = None if left_missing else left
    right_value = None if right_missing else right
    status: ComparisonStatus
    if left_missing or _absent(left_value):
        status = "added"
    elif right_missing or _absent(right_value):
        status = "removed"
    else:
        status = "changed"
    return [
        SimulationRunComparisonField(
            path=path,
            status=status,
            left_value=left_value,
            right_value=right_value,
        )
    ]


def _comparison_sha256(
    left: SimulationRunEvidenceSnapshot,
    right: SimulationRunEvidenceSnapshot,
    selection_state: str,
    sections: tuple[SimulationRunComparisonSection, ...],
) -> str:
    return _sha256(
        {
            "schema_version": 1,
            "selection_state": selection_state,
            "left": left.to_json_dict(),
            "right": right.to_json_dict(),
            "sections": [item.to_json_dict() for item in sections],
        }
    )


def _audit_selection_sha256(
    selection: AuditExportSelection,
    *,
    include_digest: bool,
) -> str:
    payload = selection.to_json_dict()
    if not include_digest:
        payload.pop("selection_sha256")
    return _sha256(payload)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(
        _normalized_json(value),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _normalized_json(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=True))
    except (TypeError, ValueError) as exc:
        raise SimulationRunComparisonError("comparison evidence is not JSON-compatible") from exc


def _validated_json_object(value: Any, field_name: str) -> dict[str, Any]:
    normalized = _normalized_json(value)
    if not isinstance(normalized, dict):
        raise SimulationRunComparisonError(f"{field_name} must be a JSON object")
    return normalized


def _validated_identifier(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise SimulationRunComparisonError(f"{field_name} is invalid")
    return value


def _validated_sha256(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SimulationRunComparisonError(f"{field_name} is invalid")
    return value


def _absent(value: Any) -> bool:
    return value is None or value == [] or value == {}


def _journal_reference(sequence: int) -> str:
    return f"journal_sequence:{sequence}"


def _validated_journal_reference(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("journal_sequence:"):
        raise SimulationRunComparisonError("journal reference is invalid")
    raw_sequence = value.removeprefix("journal_sequence:")
    if not raw_sequence.isdigit() or raw_sequence.startswith("0"):
        raise SimulationRunComparisonError("journal reference is invalid")
    sequence = int(raw_sequence)
    if sequence < 1 or _journal_reference(sequence) != value:
        raise SimulationRunComparisonError("journal reference is invalid")
    return value
