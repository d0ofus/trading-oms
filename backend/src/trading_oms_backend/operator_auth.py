from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from trading_oms_backend.config import Settings
from trading_oms_backend.event_journal import JsonlEventJournal

AUTHZ_DECISION_EVENT_TYPE = "authz.decision.evaluated"

VIEW_OPERATIONS_PERMISSION = "view_operations"
APPROVE_SIMULATION_PERMISSION = "approve_simulation"
ADMINISTER_SYSTEM_PERMISSION = "administer_system"
APPROVAL_ROLE_REQUIRED = "approver"
ROLE_SEPARATION_POLICY = "admin_approver_separated"

VALID_PERMISSIONS = (
    VIEW_OPERATIONS_PERMISSION,
    APPROVE_SIMULATION_PERMISSION,
    ADMINISTER_SYSTEM_PERMISSION,
)
ROLE_PERMISSIONS = {
    "viewer": (VIEW_OPERATIONS_PERMISSION,),
    "approver": (
        VIEW_OPERATIONS_PERMISSION,
        APPROVE_SIMULATION_PERMISSION,
    ),
    "admin": (
        VIEW_OPERATIONS_PERMISSION,
        ADMINISTER_SYSTEM_PERMISSION,
    ),
}
DEFAULT_LOCAL_OPERATOR_ID = "human-operator-001"
DEFAULT_LOCAL_OPERATOR_ROLES = ("admin",)
LOCAL_AUTH_METHOD = "local_header"
LOCAL_AUTH_STATE = "local_development"

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


class OperatorAuthError(ValueError):
    """Raised when local operator authentication or authorization is unsafe."""


@dataclass(frozen=True)
class OperatorIdentity:
    operator_id: str
    auth_state: str
    auth_method: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise OperatorAuthError("schema_version must be 1")
        _validated_identifier(self.operator_id, "operator_id")
        if self.auth_state != LOCAL_AUTH_STATE:
            raise OperatorAuthError("auth_state must be local_development")
        if self.auth_method != LOCAL_AUTH_METHOD:
            raise OperatorAuthError("auth_method must be local_header")
        _validated_role_tuple(self.roles)
        _validated_permission_tuple(self.permissions)
        expected_permissions = permissions_for_roles(self.roles)
        if self.permissions != expected_permissions:
            raise OperatorAuthError("permissions must match roles")
        _assert_json_serializable(self.to_json_dict(), "operator identity")

    @property
    def can_view_operations(self) -> bool:
        return VIEW_OPERATIONS_PERMISSION in self.permissions

    @property
    def can_approve_simulation(self) -> bool:
        return APPROVE_SIMULATION_PERMISSION in self.permissions

    @property
    def can_administer_system(self) -> bool:
        return ADMINISTER_SYSTEM_PERMISSION in self.permissions

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operator_id": self.operator_id,
            "auth_state": self.auth_state,
            "auth_method": self.auth_method,
            "roles": list(self.roles),
            "permissions": list(self.permissions),
            "can_view_operations": self.can_view_operations,
            "can_approve_simulation": self.can_approve_simulation,
            "can_administer_system": self.can_administer_system,
            "approval_role_required": APPROVAL_ROLE_REQUIRED,
            "role_separation": ROLE_SEPARATION_POLICY,
        }


@dataclass(frozen=True)
class AuthzDecision:
    decision_id: str
    evaluated_at: str
    operator_id: str
    permission: str
    resource: str
    action: str
    operator_roles: tuple[str, ...]
    required_role: str
    role_separation: str
    result: str
    reason: str
    auth_state: str
    auth_method: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise OperatorAuthError("schema_version must be 1")
        _validated_identifier(self.decision_id, "decision_id")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        _validated_identifier(self.operator_id, "operator_id")
        _validated_permission(self.permission)
        _validated_identifier(self.resource, "resource")
        _validated_identifier(self.action, "action")
        _validated_role_tuple(self.operator_roles)
        _validated_identifier(self.required_role, "required_role")
        if self.role_separation != ROLE_SEPARATION_POLICY:
            raise OperatorAuthError("role_separation must match policy")
        if self.result not in {"allowed", "denied"}:
            raise OperatorAuthError("result must be allowed or denied")
        if self.reason not in {"permission_present", "missing_permission"}:
            raise OperatorAuthError("reason must be a known authorization reason")
        if self.auth_state != LOCAL_AUTH_STATE:
            raise OperatorAuthError("auth_state must be local_development")
        if self.auth_method != LOCAL_AUTH_METHOD:
            raise OperatorAuthError("auth_method must be local_header")
        _assert_json_serializable(self.to_json_dict(), "authorization decision")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "evaluated_at": self.evaluated_at,
            "operator_id": self.operator_id,
            "permission": self.permission,
            "resource": self.resource,
            "action": self.action,
            "operator_roles": list(self.operator_roles),
            "required_role": self.required_role,
            "role_separation": self.role_separation,
            "result": self.result,
            "reason": self.reason,
            "auth_state": self.auth_state,
            "auth_method": self.auth_method,
        }


def local_development_operator() -> OperatorIdentity:
    return OperatorIdentity(
        operator_id=DEFAULT_LOCAL_OPERATOR_ID,
        auth_state=LOCAL_AUTH_STATE,
        auth_method=LOCAL_AUTH_METHOD,
        roles=DEFAULT_LOCAL_OPERATOR_ROLES,
        permissions=permissions_for_roles(DEFAULT_LOCAL_OPERATOR_ROLES),
    )


def operator_identity_from_headers(
    headers: Mapping[str, str],
    *,
    settings: Settings,
) -> OperatorIdentity:
    if not isinstance(settings, Settings):
        raise OperatorAuthError("settings must be Settings")
    if settings.app_env == "production":
        raise OperatorAuthError("local operator auth is not available in production")

    operator_id = _header_value(headers, "x-operator-id") or DEFAULT_LOCAL_OPERATOR_ID
    roles = _roles_from_header(_header_value(headers, "x-operator-roles"))
    return OperatorIdentity(
        operator_id=operator_id,
        auth_state=LOCAL_AUTH_STATE,
        auth_method=LOCAL_AUTH_METHOD,
        roles=roles,
        permissions=permissions_for_roles(roles),
    )


def permissions_for_roles(roles: tuple[str, ...]) -> tuple[str, ...]:
    _validated_role_tuple(roles)
    permissions: list[str] = []
    for permission in VALID_PERMISSIONS:
        if any(permission in ROLE_PERMISSIONS[role] for role in roles):
            permissions.append(permission)
    return tuple(permissions)


def authorize_operator(
    identity: OperatorIdentity,
    *,
    permission: str,
    resource: str,
    action: str,
    journal: JsonlEventJournal | None = None,
    decision_id: str | None = None,
    evaluated_at: str | None = None,
) -> AuthzDecision:
    if not isinstance(identity, OperatorIdentity):
        raise OperatorAuthError("identity must be OperatorIdentity")
    _validated_permission(permission)
    _validated_identifier(resource, "resource")
    _validated_identifier(action, "action")
    allowed = identity.has_permission(permission)
    decision = AuthzDecision(
        decision_id=decision_id or f"authz-{identity.operator_id}-{permission}-{resource}-{action}",
        evaluated_at=evaluated_at or _utc_timestamp(),
        operator_id=identity.operator_id,
        permission=permission,
        resource=resource,
        action=action,
        operator_roles=identity.roles,
        required_role=required_role_for_permission(permission),
        role_separation=ROLE_SEPARATION_POLICY,
        result="allowed" if allowed else "denied",
        reason="permission_present" if allowed else "missing_permission",
        auth_state=identity.auth_state,
        auth_method=identity.auth_method,
    )
    if journal is not None:
        journal.append(
            event_type=AUTHZ_DECISION_EVENT_TYPE,
            payload=decision.to_json_dict(),
            timestamp=decision.evaluated_at,
        )
    return decision


def required_role_for_permission(permission: str) -> str:
    _validated_permission(permission)
    if permission == APPROVE_SIMULATION_PERMISSION:
        return APPROVAL_ROLE_REQUIRED
    if permission == ADMINISTER_SYSTEM_PERMISSION:
        return "admin"
    return "viewer_or_higher"


def _roles_from_header(raw_roles: str | None) -> tuple[str, ...]:
    if raw_roles is None or not raw_roles.strip():
        return DEFAULT_LOCAL_OPERATOR_ROLES
    roles = tuple(role.strip().lower() for role in raw_roles.split(",") if role.strip())
    if not roles:
        raise OperatorAuthError("x-operator-roles must contain at least one role")
    return _validated_role_tuple(roles)


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    if hasattr(headers, "get"):
        value = headers.get(name)
        return None if value is None else str(value)
    return None


def _validated_role_tuple(roles: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(roles, tuple):
        raise OperatorAuthError("roles must be a tuple")
    if not roles:
        raise OperatorAuthError("roles must not be empty")
    if len(set(roles)) != len(roles):
        raise OperatorAuthError("roles must not contain duplicates")
    for role in roles:
        if role not in ROLE_PERMISSIONS:
            raise OperatorAuthError(f"unknown operator role: {role}")
    if "admin" in roles and "approver" in roles:
        raise OperatorAuthError("admin and approver roles must remain separated")
    return roles


def _validated_permission_tuple(permissions: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(permissions, tuple):
        raise OperatorAuthError("permissions must be a tuple")
    if not permissions:
        raise OperatorAuthError("permissions must include view_operations")
    for permission in permissions:
        _validated_permission(permission)
    if VIEW_OPERATIONS_PERMISSION not in permissions:
        raise OperatorAuthError("permissions must include view_operations")
    return permissions


def _validated_permission(permission: str) -> str:
    if permission not in VALID_PERMISSIONS:
        raise OperatorAuthError("permission must be a known operator permission")
    return permission


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperatorAuthError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise OperatorAuthError(f"{field_name} must not contain leading or trailing whitespace")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(character not in allowed for character in value):
        raise OperatorAuthError(f"{field_name} contains unsupported characters")
    normalized = value.lower().replace("_", "-")
    for term in _SECRET_SHAPED_TERMS:
        if term in normalized:
            raise OperatorAuthError(f"{field_name} must not contain secret-shaped text")
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise OperatorAuthError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise OperatorAuthError(f"{field_name} must not contain leading or trailing whitespace")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperatorAuthError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperatorAuthError(f"{field_name} must include a timezone")
    return parsed


def _utc_timestamp() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OperatorAuthError(f"{payload_name} must be JSON-serializable") from exc
