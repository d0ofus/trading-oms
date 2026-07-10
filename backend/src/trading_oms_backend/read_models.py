from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any

from trading_oms_backend.config import Settings, get_settings
from trading_oms_backend.operator_auth import (
    ADMINISTER_SYSTEM_PERMISSION,
    APPROVAL_ROLE_REQUIRED,
    APPROVE_SIMULATION_PERMISSION,
    ROLE_SEPARATION_POLICY,
    VIEW_OPERATIONS_PERMISSION,
    OperatorIdentity,
    local_development_operator,
)


class ReadModelError(ValueError):
    """Raised when an inspection read model is invalid."""


@dataclass(frozen=True)
class SafetyPostureReadModel:
    app_env: str
    app_mode: str
    live_trading_enabled: bool
    broker_connectivity: str = "not_configured"
    alert_delivery: str = "local_noop"
    approval_mode: str = "manual_required"
    data_source: str = "local_read_model"
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.app_env, "app_env")
        if self.app_mode not in {"paper", "simulation"}:
            raise ReadModelError("app_mode must be paper or simulation")
        if self.live_trading_enabled is not False:
            raise ReadModelError("live_trading_enabled must remain false")
        _validated_identifier(self.broker_connectivity, "broker_connectivity")
        _validated_identifier(self.alert_delivery, "alert_delivery")
        _validated_identifier(self.approval_mode, "approval_mode")
        _validated_identifier(self.data_source, "data_source")
        _assert_json_serializable(self.to_json_dict(), "safety posture read model")

    @classmethod
    def from_settings(cls, settings: Settings) -> SafetyPostureReadModel:
        if not isinstance(settings, Settings):
            raise ReadModelError("settings must be Settings")
        return cls(
            app_env=settings.app_env,
            app_mode=settings.app_mode,
            live_trading_enabled=settings.live_trading_enabled,
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_env": self.app_env,
            "app_mode": self.app_mode,
            "live_trading_enabled": self.live_trading_enabled,
            "broker_connectivity": self.broker_connectivity,
            "alert_delivery": self.alert_delivery,
            "approval_mode": self.approval_mode,
            "data_source": self.data_source,
        }


@dataclass(frozen=True)
class OperatorSessionReadModel:
    operator_id: str
    auth_state: str
    auth_method: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    approval_role_required: str = APPROVAL_ROLE_REQUIRED
    role_separation: str = ROLE_SEPARATION_POLICY
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.operator_id, "operator_id")
        if self.auth_state != "local_development":
            raise ReadModelError("auth_state must be local_development")
        if self.auth_method != "local_header":
            raise ReadModelError("auth_method must be local_header")
        _validated_identifier_tuple(self.roles, "roles")
        _validated_identifier_tuple(self.permissions, "permissions")
        if VIEW_OPERATIONS_PERMISSION not in self.permissions:
            raise ReadModelError("permissions must include view_operations")
        for permission in self.permissions:
            if permission not in {
                VIEW_OPERATIONS_PERMISSION,
                APPROVE_SIMULATION_PERMISSION,
                ADMINISTER_SYSTEM_PERMISSION,
            }:
                raise ReadModelError("permissions must be known operator permissions")
        if self.approval_role_required != APPROVAL_ROLE_REQUIRED:
            raise ReadModelError("approval_role_required must be approver")
        if self.role_separation != ROLE_SEPARATION_POLICY:
            raise ReadModelError("role_separation must match role policy")
        _assert_json_serializable(self.to_json_dict(), "operator session read model")

    @classmethod
    def from_identity(cls, identity: OperatorIdentity) -> OperatorSessionReadModel:
        if not isinstance(identity, OperatorIdentity):
            raise ReadModelError("identity must be OperatorIdentity")
        return cls(
            operator_id=identity.operator_id,
            auth_state=identity.auth_state,
            auth_method=identity.auth_method,
            roles=identity.roles,
            permissions=identity.permissions,
        )

    @property
    def can_view_operations(self) -> bool:
        return VIEW_OPERATIONS_PERMISSION in self.permissions

    @property
    def can_approve_simulation(self) -> bool:
        return APPROVE_SIMULATION_PERMISSION in self.permissions

    @property
    def can_administer_system(self) -> bool:
        return ADMINISTER_SYSTEM_PERMISSION in self.permissions

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
            "approval_role_required": self.approval_role_required,
            "role_separation": self.role_separation,
        }


@dataclass(frozen=True)
class AuditEventReadModel:
    sequence: int
    event_type: str
    timestamp: str
    summary: str
    run_id: str | None = None
    symbol: str | None = None
    order_id: str | None = None
    ticket_id: str | None = None
    severity: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _positive_integer(self.sequence, "sequence")
        _validated_identifier(self.event_type, "event_type")
        _parse_timestamp(self.timestamp, "timestamp")
        _validated_text(self.summary, "summary")
        _validated_optional_identifier(self.run_id, "run_id")
        if self.symbol is not None:
            _validated_symbol(self.symbol)
        _validated_optional_identifier(self.order_id, "order_id")
        _validated_optional_identifier(self.ticket_id, "ticket_id")
        if self.severity is not None and self.severity not in {
            "informational",
            "warning",
            "critical",
            "emergency",
        }:
            raise ReadModelError("severity must be a known alert severity")
        _assert_json_serializable(self.to_json_dict(), "audit event read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "run_id": self.run_id,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "ticket_id": self.ticket_id,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class SignalReadModel:
    signal_id: str
    strategy_id: str
    symbol: str
    signal: str
    reason: str
    bar_start_timestamp: str
    bar_end_timestamp: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.signal_id, "signal_id")
        _validated_identifier(self.strategy_id, "strategy_id")
        _validated_symbol(self.symbol)
        if self.signal not in {"long_bias", "risk_off_bias"}:
            raise ReadModelError("signal must be long_bias or risk_off_bias")
        _validated_identifier(self.reason, "reason")
        _parse_timestamp(self.bar_start_timestamp, "bar_start_timestamp")
        _parse_timestamp(self.bar_end_timestamp, "bar_end_timestamp")
        _assert_json_serializable(self.to_json_dict(), "signal read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "signal": self.signal,
            "reason": self.reason,
            "bar_start_timestamp": self.bar_start_timestamp,
            "bar_end_timestamp": self.bar_end_timestamp,
        }


@dataclass(frozen=True)
class RiskDecisionReadModel:
    request_id: str
    evaluated_at: str
    symbol: str
    risk_intent: str
    result: str
    failed_check_names: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.request_id, "request_id")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        _validated_symbol(self.symbol)
        if self.risk_intent not in {"increase", "reduce"}:
            raise ReadModelError("risk_intent must be increase or reduce")
        if self.result not in {"passed", "blocked"}:
            raise ReadModelError("result must be passed or blocked")
        _validated_identifier_tuple(self.failed_check_names, "failed_check_names")
        if self.result == "passed" and self.failed_check_names:
            raise ReadModelError("passed risk decisions must not contain failed checks")
        if self.result == "blocked" and not self.failed_check_names:
            raise ReadModelError("blocked risk decisions must contain failed checks")
        _assert_json_serializable(self.to_json_dict(), "risk decision read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "evaluated_at": self.evaluated_at,
            "symbol": self.symbol,
            "risk_intent": self.risk_intent,
            "result": self.result,
            "failed_check_names": list(self.failed_check_names),
        }


@dataclass(frozen=True)
class ApprovalTicketReadModel:
    ticket_id: str
    order_id: str
    symbol: str
    side: str
    quantity: int
    status: str
    risk_decision_id: str
    created_at: str
    expires_at: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.ticket_id, "ticket_id")
        _validated_identifier(self.order_id, "order_id")
        _validated_symbol(self.symbol)
        _validated_side(self.side)
        _positive_integer(self.quantity, "quantity")
        if self.status not in {"pending", "approved", "rejected", "expired", "cancelled"}:
            raise ReadModelError("status must be a known approval ticket status")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        _parse_timestamp(self.created_at, "created_at")
        _parse_timestamp(self.expires_at, "expires_at")
        _assert_json_serializable(self.to_json_dict(), "approval ticket read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticket_id": self.ticket_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "status": self.status,
            "risk_decision_id": self.risk_decision_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class OrderReadModel:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    state: str
    updated_at: str
    risk_decision_id: str
    approval_reference: str | None
    requires_reconciliation: bool
    cumulative_filled_quantity: int
    leaves_quantity: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.order_id, "order_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_symbol(self.symbol)
        _validated_side(self.side)
        _positive_integer(self.quantity, "quantity")
        _validated_identifier(self.state, "state")
        _parse_timestamp(self.updated_at, "updated_at")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        if self.approval_reference is not None:
            _validated_identifier(self.approval_reference, "approval_reference")
        _validated_bool(self.requires_reconciliation, "requires_reconciliation")
        _nonnegative_integer(self.cumulative_filled_quantity, "cumulative_filled_quantity")
        _nonnegative_integer(self.leaves_quantity, "leaves_quantity")
        if self.cumulative_filled_quantity + self.leaves_quantity > self.quantity:
            raise ReadModelError("filled and leaves quantities must not exceed quantity")
        _assert_json_serializable(self.to_json_dict(), "order read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "state": self.state,
            "updated_at": self.updated_at,
            "risk_decision_id": self.risk_decision_id,
            "approval_reference": self.approval_reference,
            "requires_reconciliation": self.requires_reconciliation,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "leaves_quantity": self.leaves_quantity,
        }


@dataclass(frozen=True)
class PositionReadModel:
    position_id: str
    symbol: str
    quantity: int
    average_price: float
    protection_status: str
    updated_at: str
    source: str = "simulation"
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.position_id, "position_id")
        _validated_symbol(self.symbol)
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ReadModelError("quantity must be an integer")
        _positive_finite_number(self.average_price, "average_price")
        if self.protection_status not in {
            "expected_protection_present",
            "missing_expected_protection",
            "not_required",
            "review_required",
        }:
            raise ReadModelError("protection_status must be a known protection state")
        _parse_timestamp(self.updated_at, "updated_at")
        _validated_identifier(self.source, "source")
        _assert_json_serializable(self.to_json_dict(), "position read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "position_id": self.position_id,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "protection_status": self.protection_status,
            "updated_at": self.updated_at,
            "source": self.source,
        }


@dataclass(frozen=True)
class AlertReadModel:
    alert_id: str
    severity: str
    channel: str
    status: str
    title: str
    created_at: str
    source_event_reference: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.alert_id, "alert_id")
        if self.severity not in {"informational", "warning", "critical", "emergency"}:
            raise ReadModelError("severity must be a known alert severity")
        _validated_identifier(self.channel, "channel")
        if self.status not in {"recorded", "failed"}:
            raise ReadModelError("status must be recorded or failed")
        _validated_text(self.title, "title")
        _parse_timestamp(self.created_at, "created_at")
        _validated_identifier(self.source_event_reference, "source_event_reference")
        _assert_json_serializable(self.to_json_dict(), "alert read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "severity": self.severity,
            "channel": self.channel,
            "status": self.status,
            "title": self.title,
            "created_at": self.created_at,
            "source_event_reference": self.source_event_reference,
        }


@dataclass(frozen=True)
class ReadinessReadModel:
    evaluation_id: str
    evaluated_at: str
    result: str
    failed_checks: tuple[str, ...]
    required_human_action: str
    live_trading_enabled: bool = False
    live_trading_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.evaluation_id, "evaluation_id")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        if self.result not in {"not_ready", "ready_for_final_review"}:
            raise ReadModelError("result must be not_ready or ready_for_final_review")
        _validated_identifier_tuple(self.failed_checks, "failed_checks")
        if self.result == "not_ready" and not self.failed_checks:
            raise ReadModelError("not_ready readiness must contain failed checks")
        if self.result == "ready_for_final_review" and self.failed_checks:
            raise ReadModelError("ready_for_final_review must not contain failed checks")
        _validated_identifier(self.required_human_action, "required_human_action")
        if self.live_trading_enabled is not False:
            raise ReadModelError("live_trading_enabled must remain false")
        if self.live_trading_authorized is not False:
            raise ReadModelError("live_trading_authorized must remain false")
        _assert_json_serializable(self.to_json_dict(), "readiness read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_id": self.evaluation_id,
            "evaluated_at": self.evaluated_at,
            "result": self.result,
            "failed_checks": list(self.failed_checks),
            "required_human_action": self.required_human_action,
            "live_trading_enabled": self.live_trading_enabled,
            "live_trading_authorized": self.live_trading_authorized,
        }


@dataclass(frozen=True)
class PaperTradingOperatorReadModel:
    adapter_name: str
    paper_mode: str
    live_trading_enabled: bool
    connection_state: str
    requires_reconciliation: bool
    reconciliation_summary: str
    order_status: str
    order_client_reference: str
    status_callback_state: str
    fill_callback_state: str
    cumulative_filled_quantity: int
    leaves_quantity: int
    updated_at: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.adapter_name, "adapter_name")
        if self.paper_mode != "paper":
            raise ReadModelError("paper_mode must remain paper")
        if self.live_trading_enabled is not False:
            raise ReadModelError("live_trading_enabled must remain false")
        _validated_identifier(self.connection_state, "connection_state")
        _validated_bool(self.requires_reconciliation, "requires_reconciliation")
        _validated_identifier(self.reconciliation_summary, "reconciliation_summary")
        _validated_identifier(self.order_status, "order_status")
        _validated_identifier(self.order_client_reference, "order_client_reference")
        _validated_identifier(self.status_callback_state, "status_callback_state")
        _validated_identifier(self.fill_callback_state, "fill_callback_state")
        _nonnegative_integer(self.cumulative_filled_quantity, "cumulative_filled_quantity")
        _nonnegative_integer(self.leaves_quantity, "leaves_quantity")
        _parse_timestamp(self.updated_at, "updated_at")
        _assert_json_serializable(self.to_json_dict(), "paper trading operator read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "paper_mode": self.paper_mode,
            "live_trading_enabled": self.live_trading_enabled,
            "connection_state": self.connection_state,
            "requires_reconciliation": self.requires_reconciliation,
            "reconciliation_summary": self.reconciliation_summary,
            "order_status": self.order_status,
            "order_client_reference": self.order_client_reference,
            "status_callback_state": self.status_callback_state,
            "fill_callback_state": self.fill_callback_state,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "leaves_quantity": self.leaves_quantity,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class EmergencyStopReadModel:
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
        _validated_bool(self.active, "active")
        if self.status not in {"active", "inactive"}:
            raise ReadModelError("status must be active or inactive")
        if self.active and self.status != "active":
            raise ReadModelError("active emergency stop must have active status")
        if not self.active and self.status != "inactive":
            raise ReadModelError("inactive emergency stop must have inactive status")
        _parse_timestamp(self.updated_at, "updated_at")
        _validated_optional_timestamp(self.activated_at, "activated_at")
        _validated_optional_identifier(self.activated_by, "activated_by")
        _validated_optional_identifier(self.activation_reason, "activation_reason")
        _validated_optional_timestamp(self.deactivated_at, "deactivated_at")
        _validated_optional_identifier(self.deactivated_by, "deactivated_by")
        _validated_optional_identifier(self.deactivation_reason, "deactivation_reason")
        _validated_bool(
            self.blocking_risk_increasing_actions,
            "blocking_risk_increasing_actions",
        )
        if self.active and not self.blocking_risk_increasing_actions:
            raise ReadModelError("active emergency stop must block risk-increasing actions")
        if not self.active and self.blocking_risk_increasing_actions:
            raise ReadModelError("inactive emergency stop must not block risk-increasing actions")
        _assert_json_serializable(self.to_json_dict(), "emergency stop read model")

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
class ObservabilityMetricReadModel:
    metric_name: str
    metric_value: int
    unit: str
    status: str
    observed_at: str
    summary: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_operational_text(self.metric_name, "metric_name")
        _nonnegative_integer(self.metric_value, "metric_value")
        _validated_operational_text(self.unit, "unit")
        if self.status not in {"ok", "warning", "critical"}:
            raise ReadModelError("metric status must be ok, warning, or critical")
        _parse_timestamp(self.observed_at, "observed_at")
        _validated_operational_text(self.summary, "summary")
        _assert_json_serializable(self.to_json_dict(), "observability metric read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "unit": self.unit,
            "status": self.status,
            "observed_at": self.observed_at,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ObservabilityEventReadModel:
    event_id: str
    event_type: str
    observed_at: str
    severity: str
    summary: str
    journal_reference: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_operational_text(self.event_id, "event_id")
        _validated_operational_text(self.event_type, "event_type")
        _parse_timestamp(self.observed_at, "observed_at")
        if self.severity not in {"informational", "warning", "critical", "emergency"}:
            raise ReadModelError("event severity must be a known alert severity")
        _validated_operational_text(self.summary, "summary")
        _validated_operational_text(self.journal_reference, "journal_reference")
        _assert_json_serializable(self.to_json_dict(), "observability event read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "observed_at": self.observed_at,
            "severity": self.severity,
            "summary": self.summary,
            "journal_reference": self.journal_reference,
        }


@dataclass(frozen=True)
class AuditRetentionReadModel:
    policy_id: str
    mode: str
    minimum_retention_days: int
    destructive_retention_enabled: bool
    append_only_journal_required: bool
    next_review_due_at: str
    status: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_operational_text(self.policy_id, "policy_id")
        if self.mode not in {"retain_until_reviewed", "retain_indefinitely"}:
            raise ReadModelError(
                "retention mode must be retain_until_reviewed or retain_indefinitely"
            )
        _positive_integer(self.minimum_retention_days, "minimum_retention_days")
        _validated_bool(self.destructive_retention_enabled, "destructive_retention_enabled")
        if self.destructive_retention_enabled is not False:
            raise ReadModelError("destructive_retention_enabled must remain false")
        _validated_bool(self.append_only_journal_required, "append_only_journal_required")
        if self.append_only_journal_required is not True:
            raise ReadModelError("append_only_journal_required must remain true")
        _parse_timestamp(self.next_review_due_at, "next_review_due_at")
        _validated_operational_text(self.status, "status")
        _assert_json_serializable(self.to_json_dict(), "audit retention read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "mode": self.mode,
            "minimum_retention_days": self.minimum_retention_days,
            "destructive_retention_enabled": self.destructive_retention_enabled,
            "append_only_journal_required": self.append_only_journal_required,
            "next_review_due_at": self.next_review_due_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class BackupRestoreReadModel:
    plan_id: str
    backup_status: str
    restore_verification_status: str
    last_verified_at: str
    storage_mode: str
    external_storage_configured: bool
    redaction_status: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_operational_text(self.plan_id, "plan_id")
        _validated_operational_text(self.backup_status, "backup_status")
        _validated_operational_text(
            self.restore_verification_status,
            "restore_verification_status",
        )
        _parse_timestamp(self.last_verified_at, "last_verified_at")
        _validated_operational_text(self.storage_mode, "storage_mode")
        _validated_bool(self.external_storage_configured, "external_storage_configured")
        if self.external_storage_configured is not False:
            raise ReadModelError("external_storage_configured must remain false")
        _validated_operational_text(self.redaction_status, "redaction_status")
        _assert_json_serializable(self.to_json_dict(), "backup restore read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "backup_status": self.backup_status,
            "restore_verification_status": self.restore_verification_status,
            "last_verified_at": self.last_verified_at,
            "storage_mode": self.storage_mode,
            "external_storage_configured": self.external_storage_configured,
            "redaction_status": self.redaction_status,
        }


@dataclass(frozen=True)
class IncidentResponseReadModel:
    plan_id: str
    active_incident_state: str
    severity_floor_for_operator_review: str
    emergency_stop_required_for_critical_incidents: bool
    post_incident_review_required: bool
    current_runbook_status: str
    last_reviewed_at: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_operational_text(self.plan_id, "plan_id")
        _validated_operational_text(self.active_incident_state, "active_incident_state")
        if self.severity_floor_for_operator_review not in {
            "informational",
            "warning",
            "critical",
            "emergency",
        }:
            raise ReadModelError("severity_floor_for_operator_review must be a known severity")
        _validated_bool(
            self.emergency_stop_required_for_critical_incidents,
            "emergency_stop_required_for_critical_incidents",
        )
        if self.emergency_stop_required_for_critical_incidents is not True:
            raise ReadModelError("emergency stop must be required for critical incidents")
        _validated_bool(self.post_incident_review_required, "post_incident_review_required")
        if self.post_incident_review_required is not True:
            raise ReadModelError("post incident review must be required")
        _validated_operational_text(self.current_runbook_status, "current_runbook_status")
        _parse_timestamp(self.last_reviewed_at, "last_reviewed_at")
        _assert_json_serializable(self.to_json_dict(), "incident response read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "active_incident_state": self.active_incident_state,
            "severity_floor_for_operator_review": self.severity_floor_for_operator_review,
            "emergency_stop_required_for_critical_incidents": (
                self.emergency_stop_required_for_critical_incidents
            ),
            "post_incident_review_required": self.post_incident_review_required,
            "current_runbook_status": self.current_runbook_status,
            "last_reviewed_at": self.last_reviewed_at,
        }


@dataclass(frozen=True)
class OperationalControlsReadModel:
    observed_at: str
    live_trading_enabled: bool
    production_rollout_authorized: bool
    metrics: tuple[ObservabilityMetricReadModel, ...]
    events: tuple[ObservabilityEventReadModel, ...]
    retention: AuditRetentionReadModel
    backup_restore: BackupRestoreReadModel
    incident_response: IncidentResponseReadModel
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _parse_timestamp(self.observed_at, "observed_at")
        _validated_bool(self.live_trading_enabled, "live_trading_enabled")
        if self.live_trading_enabled is not False:
            raise ReadModelError("live_trading_enabled must remain false")
        _validated_bool(
            self.production_rollout_authorized,
            "production_rollout_authorized",
        )
        if self.production_rollout_authorized is not False:
            raise ReadModelError("production_rollout_authorized must remain false")
        _validated_model_tuple(self.metrics, ObservabilityMetricReadModel, "metrics")
        _validated_model_tuple(self.events, ObservabilityEventReadModel, "events")
        if not self.metrics:
            raise ReadModelError("operational controls must include metrics")
        if not self.events:
            raise ReadModelError("operational controls must include events")
        _validated_model(self.retention, AuditRetentionReadModel, "retention")
        _validated_model(self.backup_restore, BackupRestoreReadModel, "backup_restore")
        _validated_model(self.incident_response, IncidentResponseReadModel, "incident_response")
        _assert_json_serializable(self.to_json_dict(), "operational controls read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observed_at": self.observed_at,
            "live_trading_enabled": self.live_trading_enabled,
            "production_rollout_authorized": self.production_rollout_authorized,
            "metrics": [metric.to_json_dict() for metric in self.metrics],
            "events": [event.to_json_dict() for event in self.events],
            "retention": self.retention.to_json_dict(),
            "backup_restore": self.backup_restore.to_json_dict(),
            "incident_response": self.incident_response.to_json_dict(),
        }


@dataclass(frozen=True)
class OperationsReadModel:
    emergency_stop: EmergencyStopReadModel
    safety: SafetyPostureReadModel
    operator_session: OperatorSessionReadModel
    audit_events: tuple[AuditEventReadModel, ...]
    signals: tuple[SignalReadModel, ...]
    risk_decisions: tuple[RiskDecisionReadModel, ...]
    approval_tickets: tuple[ApprovalTicketReadModel, ...]
    orders: tuple[OrderReadModel, ...]
    positions: tuple[PositionReadModel, ...]
    alerts: tuple[AlertReadModel, ...]
    readiness: ReadinessReadModel
    paper_trading: PaperTradingOperatorReadModel
    operational_controls: OperationalControlsReadModel
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_model(self.emergency_stop, EmergencyStopReadModel, "emergency_stop")
        _validated_model(self.safety, SafetyPostureReadModel, "safety")
        _validated_model(self.operator_session, OperatorSessionReadModel, "operator_session")
        _validated_model_tuple(self.audit_events, AuditEventReadModel, "audit_events")
        _validated_model_tuple(self.signals, SignalReadModel, "signals")
        _validated_model_tuple(self.risk_decisions, RiskDecisionReadModel, "risk_decisions")
        _validated_model_tuple(
            self.approval_tickets,
            ApprovalTicketReadModel,
            "approval_tickets",
        )
        _validated_model_tuple(self.orders, OrderReadModel, "orders")
        _validated_model_tuple(self.positions, PositionReadModel, "positions")
        _validated_model_tuple(self.alerts, AlertReadModel, "alerts")
        _validated_model(self.readiness, ReadinessReadModel, "readiness")
        _validated_model(self.paper_trading, PaperTradingOperatorReadModel, "paper_trading")
        _validated_model(
            self.operational_controls,
            OperationalControlsReadModel,
            "operational_controls",
        )
        _assert_json_serializable(self.to_json_dict(), "operations read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "emergency_stop": self.emergency_stop.to_json_dict(),
            "safety": self.safety.to_json_dict(),
            "operator_session": self.operator_session.to_json_dict(),
            "audit_events": [event.to_json_dict() for event in self.audit_events],
            "signals": [signal.to_json_dict() for signal in self.signals],
            "risk_decisions": [decision.to_json_dict() for decision in self.risk_decisions],
            "approval_tickets": [ticket.to_json_dict() for ticket in self.approval_tickets],
            "orders": [order.to_json_dict() for order in self.orders],
            "positions": [position.to_json_dict() for position in self.positions],
            "alerts": [alert.to_json_dict() for alert in self.alerts],
            "readiness": self.readiness.to_json_dict(),
            "paper_trading": self.paper_trading.to_json_dict(),
            "operational_controls": self.operational_controls.to_json_dict(),
        }


def build_demo_operations_read_model(
    settings: Settings | None = None,
    emergency_stop: EmergencyStopReadModel | None = None,
) -> OperationsReadModel:
    safety = SafetyPostureReadModel.from_settings(settings or get_settings())
    return OperationsReadModel(
        emergency_stop=emergency_stop
        or EmergencyStopReadModel(
            active=False,
            status="inactive",
            updated_at="2026-07-08T00:00:00Z",
            activated_at=None,
            activated_by=None,
            activation_reason=None,
            deactivated_at=None,
            deactivated_by=None,
            deactivation_reason=None,
            blocking_risk_increasing_actions=False,
        ),
        safety=safety,
        operator_session=OperatorSessionReadModel.from_identity(local_development_operator()),
        audit_events=(
            AuditEventReadModel(
                sequence=1,
                event_type="strategy.signal.generated",
                timestamp="2026-07-08T00:00:00Z",
                summary="Replay strategy signal recorded",
                run_id="sim-run-001",
                symbol="AAPL",
                order_id="order-001",
                ticket_id="ticket-001",
                severity="informational",
            ),
            AuditEventReadModel(
                sequence=2,
                event_type="risk.decision.evaluated",
                timestamp="2026-07-08T00:01:00Z",
                summary="Risk decision available for inspection",
                run_id="sim-run-001",
                symbol="AAPL",
                order_id="order-001",
                ticket_id="ticket-001",
                severity="warning",
            ),
        ),
        signals=(
            SignalReadModel(
                signal_id="signal-001",
                strategy_id="visual-close-above-sma",
                symbol="AAPL",
                signal="long_bias",
                reason="close_above_sma",
                bar_start_timestamp="2026-07-08T00:00:00Z",
                bar_end_timestamp="2026-07-08T00:01:00Z",
            ),
        ),
        risk_decisions=(
            RiskDecisionReadModel(
                request_id="risk-001",
                evaluated_at="2026-07-08T00:01:00Z",
                symbol="AAPL",
                risk_intent="increase",
                result="blocked",
                failed_check_names=("market_data_freshness",),
            ),
        ),
        approval_tickets=(
            ApprovalTicketReadModel(
                ticket_id="ticket-001",
                order_id="order-001",
                symbol="AAPL",
                side="buy",
                quantity=10,
                status="pending",
                risk_decision_id="risk-001",
                created_at="2026-07-08T00:02:00Z",
                expires_at="2026-07-08T00:12:00Z",
            ),
        ),
        orders=(
            OrderReadModel(
                order_id="order-001",
                client_order_id="client-001",
                symbol="AAPL",
                side="buy",
                quantity=10,
                state="PENDING_APPROVAL",
                updated_at="2026-07-08T00:02:00Z",
                risk_decision_id="risk-001",
                approval_reference=None,
                requires_reconciliation=False,
                cumulative_filled_quantity=0,
                leaves_quantity=10,
            ),
        ),
        positions=(
            PositionReadModel(
                position_id="position-001",
                symbol="AAPL",
                quantity=10,
                average_price=101.25,
                protection_status="expected_protection_present",
                updated_at="2026-07-08T00:03:00Z",
            ),
        ),
        alerts=(
            AlertReadModel(
                alert_id="alert-001",
                severity="critical",
                channel="local",
                status="recorded",
                title="Protection review required",
                created_at="2026-07-08T00:04:00Z",
                source_event_reference="position-001",
            ),
        ),
        readiness=ReadinessReadModel(
            evaluation_id="readiness-001",
            evaluated_at="2026-07-08T00:05:00Z",
            result="not_ready",
            failed_checks=("emergency_stop_implemented",),
            required_human_action="collect_missing_evidence",
        ),
        paper_trading=PaperTradingOperatorReadModel(
            adapter_name="ibkr_paper",
            paper_mode="paper",
            live_trading_enabled=False,
            connection_state="unknown_requires_reconciliation",
            requires_reconciliation=True,
            reconciliation_summary="stale_callback_requires_review",
            order_status="PARTIALLY_FILLED",
            order_client_reference="client-paper-001",
            status_callback_state="accepted_status_update",
            fill_callback_state="accepted_fill_update",
            cumulative_filled_quantity=4,
            leaves_quantity=6,
            updated_at="2026-07-08T00:06:00Z",
        ),
        operational_controls=OperationalControlsReadModel(
            observed_at="2026-07-08T00:07:00Z",
            live_trading_enabled=False,
            production_rollout_authorized=False,
            metrics=(
                ObservabilityMetricReadModel(
                    metric_name="system.health",
                    metric_value=1,
                    unit="status",
                    status="ok",
                    observed_at="2026-07-08T00:07:00Z",
                    summary="Local service health is visible",
                ),
                ObservabilityMetricReadModel(
                    metric_name="safety.posture",
                    metric_value=1,
                    unit="status",
                    status="ok",
                    observed_at="2026-07-08T00:07:00Z",
                    summary="Simulation and paper safety posture is visible",
                ),
                ObservabilityMetricReadModel(
                    metric_name="emergency_stop.state",
                    metric_value=0,
                    unit="active_flag",
                    status="ok",
                    observed_at="2026-07-08T00:07:00Z",
                    summary="Local emergency stop state is inspectable",
                ),
                ObservabilityMetricReadModel(
                    metric_name="audit_journal.health",
                    metric_value=1,
                    unit="status",
                    status="ok",
                    observed_at="2026-07-08T00:07:00Z",
                    summary="Append-only journal remains required",
                ),
                ObservabilityMetricReadModel(
                    metric_name="backup.status",
                    metric_value=0,
                    unit="configured_external_targets",
                    status="warning",
                    observed_at="2026-07-08T00:07:00Z",
                    summary="Local backup verification is documented only",
                ),
                ObservabilityMetricReadModel(
                    metric_name="incident.response",
                    metric_value=0,
                    unit="active_incidents",
                    status="ok",
                    observed_at="2026-07-08T00:07:00Z",
                    summary="No active incident is declared",
                ),
            ),
            events=(
                ObservabilityEventReadModel(
                    event_id="observability-event-001",
                    event_type="system.health",
                    observed_at="2026-07-08T00:07:00Z",
                    severity="informational",
                    summary="Local observability snapshot recorded",
                    journal_reference="journal_sequence:0",
                ),
            ),
            retention=AuditRetentionReadModel(
                policy_id="audit-retention-local-001",
                mode="retain_until_reviewed",
                minimum_retention_days=365,
                destructive_retention_enabled=False,
                append_only_journal_required=True,
                next_review_due_at="2026-08-08T00:00:00Z",
                status="planned_local_only",
            ),
            backup_restore=BackupRestoreReadModel(
                plan_id="backup-restore-local-001",
                backup_status="local_plan_documented",
                restore_verification_status="local_plan_documented",
                last_verified_at="2026-07-08T00:07:00Z",
                storage_mode="local_encrypted_storage_required",
                external_storage_configured=False,
                redaction_status="redaction_required",
            ),
            incident_response=IncidentResponseReadModel(
                plan_id="incident-response-local-001",
                active_incident_state="none_declared",
                severity_floor_for_operator_review="warning",
                emergency_stop_required_for_critical_incidents=True,
                post_incident_review_required=True,
                current_runbook_status="documented_local_playbook",
                last_reviewed_at="2026-07-08T00:07:00Z",
            ),
        ),
    )


def _validate_schema_version(schema_version: int) -> None:
    if isinstance(schema_version, bool) or schema_version != 1:
        raise ReadModelError("schema_version must be 1")


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadModelError(f"{field_name} must be a non-empty string")
    if value.strip() != value:
        raise ReadModelError(f"{field_name} must not contain leading or trailing whitespace")
    return value


def _validated_optional_identifier(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _validated_identifier(value, field_name)


def _validated_optional_timestamp(value: str | None, field_name: str) -> None:
    if value is not None:
        _parse_timestamp(value, field_name)


def _validated_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadModelError(f"{field_name} must be a non-empty string")
    return value


def _validated_operational_text(value: str, field_name: str) -> str:
    validated = _validated_text(value, field_name)
    normalized = validated.lower().replace("-", "_")
    unsafe_tokens = {
        "account_id",
        "api_key",
        "authorization:",
        "bearer ",
        "broker_host",
        "broker_port",
        "credential",
        "eval(",
        "eval:",
        "host:",
        "ibkr connect",
        "javascript:",
        "password:",
        "password=",
        "_".join(("place", "order")),
        "private_key",
        "_".join(("route", "order")),
        "secret:",
        "secret=",
        "_".join(("submit", "order")),
        "token:",
        "token=",
        "_".join(("transmit", "order")),
    }
    for token in unsafe_tokens:
        if token in normalized:
            raise ReadModelError(f"{field_name} contains unsafe observability text")
    return validated


def _validated_symbol(symbol: str) -> str:
    _validated_identifier(symbol, "symbol")
    if symbol.upper() != symbol:
        raise ReadModelError("symbol must be uppercase")
    return symbol


def _validated_side(side: str) -> str:
    if side not in {"buy", "sell"}:
        raise ReadModelError("side must be buy or sell")
    return side


def _validated_bool(value: bool, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ReadModelError(f"{field_name} must be a boolean")
    return value


def _validated_identifier_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ReadModelError(f"{field_name} must be a tuple")
    for value in values:
        _validated_identifier(value, field_name)
    return values


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReadModelError(f"{field_name} must be a positive integer")
    return value


def _nonnegative_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReadModelError(f"{field_name} must be a nonnegative integer")
    return value


def _positive_finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ReadModelError(f"{field_name} must be a positive finite number")
    if not isfinite(float(value)):
        raise ReadModelError(f"{field_name} must be a positive finite number")
    return float(value)


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _validated_identifier(value, field_name)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReadModelError(f"{field_name} must be an ISO-8601 datetime") from exc


def _validated_model(value: Any, expected_type: type, field_name: str) -> None:
    if not isinstance(value, expected_type):
        raise ReadModelError(f"{field_name} must be {expected_type.__name__}")


def _validated_model_tuple(values: tuple[Any, ...], expected_type: type, field_name: str) -> None:
    if not isinstance(values, tuple):
        raise ReadModelError(f"{field_name} must be a tuple")
    for value in values:
        _validated_model(value, expected_type, field_name)


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReadModelError(f"{payload_name} must be JSON-serializable") from exc
