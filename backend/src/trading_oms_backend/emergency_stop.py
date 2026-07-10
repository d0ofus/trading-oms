from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_oms_backend.event_journal import JsonlEventJournal

EMERGENCY_STOP_ACTIVATED_EVENT_TYPE = "emergency_stop.activated"
EMERGENCY_STOP_DEACTIVATED_EVENT_TYPE = "emergency_stop.deactivated"
EMERGENCY_STOP_BLOCKED_EVENT_TYPE = "emergency_stop.risk_increasing_action_blocked"
INITIAL_EMERGENCY_STOP_TIMESTAMP = "2026-07-08T00:00:00Z"

_SECRET_SHAPED_TERMS = {
    "account",
    "api-key",
    "apikey",
    "certificate",
    "credential",
    "password",
    "private-key",
    "secret",
    "token",
}
_ALLOWED_IDENTIFIER_CHARACTERS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-",
)


class EmergencyStopError(ValueError):
    """Raised when emergency stop state or requests are unsafe."""


@dataclass(frozen=True)
class EmergencyStopChangeRequest:
    event_id: str
    requested_at: str
    actor: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.event_id, "event_id")
        _parse_timestamp(self.requested_at, "requested_at")
        _validated_identifier(self.actor, "actor")
        _validated_identifier(self.reason, "reason")
        _assert_json_serializable(self.to_json_dict(), "emergency stop change request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "requested_at": self.requested_at,
            "actor": self.actor,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EmergencyStopState:
    active: bool
    status: str
    updated_at: str
    activated_at: str | None
    activated_by: str | None
    activation_reason: str | None
    deactivated_at: str | None
    deactivated_by: str | None
    deactivation_reason: str | None
    blocking_risk_increasing_actions: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        if not isinstance(self.active, bool):
            raise EmergencyStopError("active must be a boolean")
        if self.status not in {"active", "inactive"}:
            raise EmergencyStopError("status must be active or inactive")
        if self.active and self.status != "active":
            raise EmergencyStopError("active state must have active status")
        if not self.active and self.status != "inactive":
            raise EmergencyStopError("inactive state must have inactive status")
        _parse_timestamp(self.updated_at, "updated_at")
        _validated_optional_timestamp(self.activated_at, "activated_at")
        _validated_optional_identifier(self.activated_by, "activated_by")
        _validated_optional_identifier(self.activation_reason, "activation_reason")
        _validated_optional_timestamp(self.deactivated_at, "deactivated_at")
        _validated_optional_identifier(self.deactivated_by, "deactivated_by")
        _validated_optional_identifier(self.deactivation_reason, "deactivation_reason")
        if not isinstance(self.blocking_risk_increasing_actions, bool):
            raise EmergencyStopError("blocking_risk_increasing_actions must be a boolean")
        if self.active and not self.blocking_risk_increasing_actions:
            raise EmergencyStopError("active emergency stop must block risk-increasing actions")
        if not self.active and self.blocking_risk_increasing_actions:
            raise EmergencyStopError(
                "inactive emergency stop must not block risk-increasing actions"
            )
        _assert_json_serializable(self.to_json_dict(), "emergency stop state")

    @classmethod
    def inactive(cls) -> EmergencyStopState:
        return cls(
            active=False,
            status="inactive",
            updated_at=INITIAL_EMERGENCY_STOP_TIMESTAMP,
            activated_at=None,
            activated_by=None,
            activation_reason=None,
            deactivated_at=None,
            deactivated_by=None,
            deactivation_reason=None,
            blocking_risk_increasing_actions=False,
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "active": self.active,
            "status": self.status,
            "updated_at": self.updated_at,
            "activated_at": self.activated_at,
            "activated_by": self.activated_by,
            "activation_reason": self.activation_reason,
            "deactivated_at": self.deactivated_at,
            "deactivated_by": self.deactivated_by,
            "deactivation_reason": self.deactivation_reason,
            "blocking_risk_increasing_actions": self.blocking_risk_increasing_actions,
        }


@dataclass(frozen=True)
class EmergencyStopChangeRecord:
    event_id: str
    action: str
    requested_at: str
    actor: str
    reason: str
    previous_state: EmergencyStopState
    state: EmergencyStopState
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.event_id, "event_id")
        if self.action not in {"activated", "deactivated"}:
            raise EmergencyStopError("action must be activated or deactivated")
        _parse_timestamp(self.requested_at, "requested_at")
        _validated_identifier(self.actor, "actor")
        _validated_identifier(self.reason, "reason")
        if not isinstance(self.previous_state, EmergencyStopState):
            raise EmergencyStopError("previous_state must be EmergencyStopState")
        if not isinstance(self.state, EmergencyStopState):
            raise EmergencyStopError("state must be EmergencyStopState")
        _assert_json_serializable(self.to_json_dict(), "emergency stop change record")

    def matches_request(self, action: str, request: EmergencyStopChangeRequest) -> bool:
        return (
            self.action == action
            and self.event_id == request.event_id
            and self.requested_at == request.requested_at
            and self.actor == request.actor
            and self.reason == request.reason
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "action": self.action,
            "requested_at": self.requested_at,
            "actor": self.actor,
            "reason": self.reason,
            "previous_state": self.previous_state.to_json_dict(),
            "state": self.state.to_json_dict(),
        }


class EmergencyStopService:
    def __init__(self, journal: JsonlEventJournal) -> None:
        if not isinstance(journal, JsonlEventJournal):
            raise EmergencyStopError("journal must be JsonlEventJournal")
        self._journal = journal
        self._state = EmergencyStopState.inactive()
        self._changes_by_event_id: dict[str, EmergencyStopChangeRecord] = {}

    def current_state(self) -> EmergencyStopState:
        return self._state

    def activate(self, request: EmergencyStopChangeRequest) -> EmergencyStopChangeRecord:
        if not isinstance(request, EmergencyStopChangeRequest):
            raise EmergencyStopError("request must be EmergencyStopChangeRequest")
        existing = self._changes_by_event_id.get(request.event_id)
        if existing is not None:
            if existing.matches_request("activated", request):
                return existing
            raise EmergencyStopError("conflicting event_id")
        if self._state.active:
            raise EmergencyStopError("emergency stop is already active")

        previous_state = self._state
        next_state = EmergencyStopState(
            active=True,
            status="active",
            updated_at=request.requested_at,
            activated_at=request.requested_at,
            activated_by=request.actor,
            activation_reason=request.reason,
            deactivated_at=None,
            deactivated_by=None,
            deactivation_reason=None,
            blocking_risk_increasing_actions=True,
        )
        record = EmergencyStopChangeRecord(
            event_id=request.event_id,
            action="activated",
            requested_at=request.requested_at,
            actor=request.actor,
            reason=request.reason,
            previous_state=previous_state,
            state=next_state,
        )
        self._journal.append(
            EMERGENCY_STOP_ACTIVATED_EVENT_TYPE,
            record.to_json_dict(),
            timestamp=request.requested_at,
        )
        self._state = next_state
        self._changes_by_event_id[request.event_id] = record
        return record

    def deactivate(self, request: EmergencyStopChangeRequest) -> EmergencyStopChangeRecord:
        if not isinstance(request, EmergencyStopChangeRequest):
            raise EmergencyStopError("request must be EmergencyStopChangeRequest")
        existing = self._changes_by_event_id.get(request.event_id)
        if existing is not None:
            if existing.matches_request("deactivated", request):
                return existing
            raise EmergencyStopError("conflicting event_id")
        if not self._state.active:
            raise EmergencyStopError("emergency stop is not active")

        previous_state = self._state
        next_state = EmergencyStopState(
            active=False,
            status="inactive",
            updated_at=request.requested_at,
            activated_at=previous_state.activated_at,
            activated_by=previous_state.activated_by,
            activation_reason=previous_state.activation_reason,
            deactivated_at=request.requested_at,
            deactivated_by=request.actor,
            deactivation_reason=request.reason,
            blocking_risk_increasing_actions=False,
        )
        record = EmergencyStopChangeRecord(
            event_id=request.event_id,
            action="deactivated",
            requested_at=request.requested_at,
            actor=request.actor,
            reason=request.reason,
            previous_state=previous_state,
            state=next_state,
        )
        self._journal.append(
            EMERGENCY_STOP_DEACTIVATED_EVENT_TYPE,
            record.to_json_dict(),
            timestamp=request.requested_at,
        )
        self._state = next_state
        self._changes_by_event_id[request.event_id] = record
        return record

    def ensure_risk_increasing_allowed(
        self,
        *,
        resource: str,
        action: str,
        checked_at: str,
        actor: str,
    ) -> None:
        _validated_identifier(resource, "resource")
        _validated_identifier(action, "action")
        _parse_timestamp(checked_at, "checked_at")
        _validated_identifier(actor, "actor")
        if not self._state.active:
            return

        payload = {
            "schema_version": 1,
            "resource": resource,
            "action": action,
            "checked_at": checked_at,
            "actor": actor,
            "emergency_stop_active": True,
            "reason": "emergency_stop_active_blocks_risk_increase",
        }
        _assert_json_serializable(payload, "emergency stop block event")
        self._journal.append(
            EMERGENCY_STOP_BLOCKED_EVENT_TYPE,
            payload,
            timestamp=checked_at,
        )
        raise EmergencyStopError("emergency stop is active")


def _validate_schema_version(schema_version: int) -> None:
    if isinstance(schema_version, bool) or schema_version != 1:
        raise EmergencyStopError("schema_version must be 1")


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EmergencyStopError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise EmergencyStopError(f"{field_name} must not contain leading or trailing whitespace")
    if any(character not in _ALLOWED_IDENTIFIER_CHARACTERS for character in value):
        raise EmergencyStopError(f"{field_name} contains unsupported characters")
    normalized = value.lower().replace("_", "-")
    if any(term in normalized for term in _SECRET_SHAPED_TERMS):
        raise EmergencyStopError(f"{field_name} must not contain secret-shaped text")
    return value


def _validated_optional_identifier(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _validated_identifier(value, field_name)


def _validated_optional_timestamp(value: str | None, field_name: str) -> None:
    if value is not None:
        _parse_timestamp(value, field_name)


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EmergencyStopError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise EmergencyStopError(f"{field_name} must not contain leading or trailing whitespace")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EmergencyStopError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EmergencyStopError(f"{field_name} must include a timezone")
    return parsed


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EmergencyStopError(f"{payload_name} must be JSON-serializable") from exc
