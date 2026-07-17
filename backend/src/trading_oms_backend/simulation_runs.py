from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_oms_backend.event_journal import JsonlEventJournal


class SimulationRunError(ValueError):
    """Raised when simulation run records or transitions are invalid."""


SIMULATION_RUN_STATUSES = {"created", "running", "completed", "failed", "cancelled"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ALLOWED_TRANSITIONS = {
    "created": {"running", "completed", "failed", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
}
FORBIDDEN_REFERENCE_FRAGMENTS = {
    "://",
    "account",
    "api_key",
    "authorization",
    "broker",
    "credential",
    "ibkr",
    "password",
    "private_key",
    "secret",
    "socket",
    "token",
    "transmit",
}


@dataclass(frozen=True)
class SimulationRunCreateRequest:
    run_id: str
    requested_at: str
    replay_input_reference: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.run_id, "run_id")
        _parse_timestamp(self.requested_at, "requested_at")
        _validated_replay_reference(self.replay_input_reference)
        _assert_json_serializable(self.to_payload(), "simulation run create request")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "requested_at": self.requested_at,
            "replay_input_reference": self.replay_input_reference,
        }


@dataclass(frozen=True)
class SimulationRunTransitionRequest:
    transition_id: str
    run_id: str
    status: str
    occurred_at: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.transition_id, "transition_id")
        _validated_identifier(self.run_id, "run_id")
        _validated_status(self.status)
        if self.status == "created":
            raise SimulationRunError("transition status must not be created")
        _parse_timestamp(self.occurred_at, "occurred_at")
        _validated_identifier(self.reason, "reason")
        _assert_json_serializable(self.to_payload(), "simulation run transition request")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transition_id": self.transition_id,
            "run_id": self.run_id,
            "status": self.status,
            "occurred_at": self.occurred_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SimulationRunRecord:
    run_id: str
    status: str
    created_at: str
    updated_at: str
    replay_input_reference: str
    journal_references: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.run_id, "run_id")
        _validated_status(self.status)
        created_at = _parse_timestamp(self.created_at, "created_at")
        updated_at = _parse_timestamp(self.updated_at, "updated_at")
        if updated_at < created_at:
            raise SimulationRunError("updated_at must not be before created_at")
        _validated_replay_reference(self.replay_input_reference)
        _validated_journal_references(self.journal_references)
        _assert_json_serializable(self.to_json_dict(), "simulation run record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "replay_input_reference": self.replay_input_reference,
            "journal_references": list(self.journal_references),
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> SimulationRunRecord:
        expected_keys = {
            "schema_version",
            "run_id",
            "status",
            "created_at",
            "updated_at",
            "replay_input_reference",
            "journal_references",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise SimulationRunError("simulation run record fields are invalid")
        journal_references = raw_record["journal_references"]
        if not isinstance(journal_references, list):
            raise SimulationRunError("journal_references must be a list")
        return cls(
            schema_version=raw_record["schema_version"],
            run_id=raw_record["run_id"],
            status=raw_record["status"],
            created_at=raw_record["created_at"],
            updated_at=raw_record["updated_at"],
            replay_input_reference=raw_record["replay_input_reference"],
            journal_references=tuple(journal_references),
        )


class SimulationRunBook:
    def __init__(self, journal: JsonlEventJournal) -> None:
        if not isinstance(journal, JsonlEventJournal):
            raise SimulationRunError("journal must be JsonlEventJournal")
        self._journal = journal
        self._runs: dict[str, SimulationRunRecord] = {}
        self._create_payloads: dict[str, dict[str, Any]] = {}
        self._transition_payloads: dict[str, dict[str, Any]] = {}
        self._transition_results: dict[str, SimulationRunRecord] = {}

    def create_run(self, request: SimulationRunCreateRequest) -> SimulationRunRecord:
        if not isinstance(request, SimulationRunCreateRequest):
            raise SimulationRunError("request must be SimulationRunCreateRequest")

        request_payload = request.to_payload()
        existing_payload = self._create_payloads.get(request.run_id)
        if existing_payload is not None:
            if existing_payload != request_payload:
                raise SimulationRunError("conflicting duplicate run_id")
            return self._runs[request.run_id]
        if request.run_id in self._runs:
            raise SimulationRunError("conflicting duplicate run_id")

        journal_record = self._journal.append(
            "simulation_run.created",
            {
                "schema_version": 1,
                "run_id": request.run_id,
                "status": "created",
                "requested_at": request.requested_at,
                "replay_input_reference": request.replay_input_reference,
            },
            timestamp=request.requested_at,
        )
        run = SimulationRunRecord(
            run_id=request.run_id,
            status="created",
            created_at=request.requested_at,
            updated_at=request.requested_at,
            replay_input_reference=request.replay_input_reference,
            journal_references=(_journal_reference(journal_record.sequence),),
        )
        self._runs[request.run_id] = run
        self._create_payloads[request.run_id] = request_payload
        return run

    def transition_run(self, request: SimulationRunTransitionRequest) -> SimulationRunRecord:
        if not isinstance(request, SimulationRunTransitionRequest):
            raise SimulationRunError("request must be SimulationRunTransitionRequest")

        request_payload = request.to_payload()
        existing_payload = self._transition_payloads.get(request.transition_id)
        if existing_payload is not None:
            if existing_payload != request_payload:
                raise SimulationRunError("conflicting duplicate transition_id")
            return self._transition_results[request.transition_id]

        run = self._runs.get(request.run_id)
        if run is None:
            raise SimulationRunError("unknown simulation run")

        self._validate_transition(run, request)
        journal_record = self._journal.append(
            "simulation_run.status_changed",
            {
                "schema_version": 1,
                "transition_id": request.transition_id,
                "run_id": request.run_id,
                "previous_status": run.status,
                "status": request.status,
                "occurred_at": request.occurred_at,
                "reason": request.reason,
            },
            timestamp=request.occurred_at,
        )
        updated_run = SimulationRunRecord(
            run_id=run.run_id,
            status=request.status,
            created_at=run.created_at,
            updated_at=request.occurred_at,
            replay_input_reference=run.replay_input_reference,
            journal_references=(
                *run.journal_references,
                _journal_reference(journal_record.sequence),
            ),
        )
        self._runs[request.run_id] = updated_run
        self._transition_payloads[request.transition_id] = request_payload
        self._transition_results[request.transition_id] = updated_run
        return updated_run

    def get_run(self, run_id: str) -> SimulationRunRecord:
        _validated_identifier(run_id, "run_id")
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise SimulationRunError("unknown simulation run") from exc

    def list_runs(self) -> tuple[SimulationRunRecord, ...]:
        return tuple(self._runs.values())

    def _validate_transition(
        self,
        run: SimulationRunRecord,
        request: SimulationRunTransitionRequest,
    ) -> None:
        if run.status in TERMINAL_STATUSES:
            raise SimulationRunError("terminal simulation runs cannot transition")
        allowed_statuses = ALLOWED_TRANSITIONS.get(run.status, set())
        if request.status not in allowed_statuses:
            raise SimulationRunError(f"cannot transition from {run.status} to {request.status}")
        if _parse_timestamp(request.occurred_at, "occurred_at") < _parse_timestamp(
            run.updated_at,
            "updated_at",
        ):
            raise SimulationRunError("occurred_at must not be before current run updated_at")


def _validate_schema_version(schema_version: int) -> None:
    if isinstance(schema_version, bool) or schema_version != 1:
        raise SimulationRunError("schema_version must be 1")


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SimulationRunError(f"{field_name} must be a non-empty string")
    if value.strip() != value:
        raise SimulationRunError(f"{field_name} must not contain leading or trailing whitespace")
    return value


def _validated_status(status: str) -> str:
    _validated_identifier(status, "status")
    if status not in SIMULATION_RUN_STATUSES:
        raise SimulationRunError("status must be a known simulation run status")
    return status


def _validated_replay_reference(reference: str) -> str:
    _validated_identifier(reference, "replay_input_reference")
    normalized = reference.lower()
    if any(fragment in normalized for fragment in FORBIDDEN_REFERENCE_FRAGMENTS):
        raise SimulationRunError("replay_input_reference must be a local replay file reference")
    return reference


def _validated_journal_references(references: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(references, tuple) or not references:
        raise SimulationRunError("journal_references must be a non-empty tuple")
    for reference in references:
        _validated_identifier(reference, "journal_references")
        if not reference.startswith("journal_sequence:"):
            raise SimulationRunError("journal_references must use journal_sequence references")
    return references


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _validated_identifier(value, field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SimulationRunError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SimulationRunError(f"{field_name} must include a timezone")
    return parsed


def _journal_reference(sequence: int) -> str:
    return f"journal_sequence:{sequence}"


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SimulationRunError(f"{payload_name} must be JSON-serializable") from exc
