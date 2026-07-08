from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any

from trading_oms_backend.config import Settings, get_settings


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
class AuditEventReadModel:
    sequence: int
    event_type: str
    timestamp: str
    summary: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _positive_integer(self.sequence, "sequence")
        _validated_identifier(self.event_type, "event_type")
        _parse_timestamp(self.timestamp, "timestamp")
        _validated_text(self.summary, "summary")
        _assert_json_serializable(self.to_json_dict(), "audit event read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "summary": self.summary,
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
class OperationsReadModel:
    safety: SafetyPostureReadModel
    audit_events: tuple[AuditEventReadModel, ...]
    signals: tuple[SignalReadModel, ...]
    risk_decisions: tuple[RiskDecisionReadModel, ...]
    approval_tickets: tuple[ApprovalTicketReadModel, ...]
    orders: tuple[OrderReadModel, ...]
    positions: tuple[PositionReadModel, ...]
    alerts: tuple[AlertReadModel, ...]
    readiness: ReadinessReadModel
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_model(self.safety, SafetyPostureReadModel, "safety")
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
        _assert_json_serializable(self.to_json_dict(), "operations read model")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "safety": self.safety.to_json_dict(),
            "audit_events": [event.to_json_dict() for event in self.audit_events],
            "signals": [signal.to_json_dict() for signal in self.signals],
            "risk_decisions": [decision.to_json_dict() for decision in self.risk_decisions],
            "approval_tickets": [ticket.to_json_dict() for ticket in self.approval_tickets],
            "orders": [order.to_json_dict() for order in self.orders],
            "positions": [position.to_json_dict() for position in self.positions],
            "alerts": [alert.to_json_dict() for alert in self.alerts],
            "readiness": self.readiness.to_json_dict(),
        }


def build_demo_operations_read_model(settings: Settings | None = None) -> OperationsReadModel:
    safety = SafetyPostureReadModel.from_settings(settings or get_settings())
    return OperationsReadModel(
        safety=safety,
        audit_events=(
            AuditEventReadModel(
                sequence=1,
                event_type="strategy.signal.generated",
                timestamp="2026-07-08T00:00:00Z",
                summary="Replay strategy signal recorded",
            ),
            AuditEventReadModel(
                sequence=2,
                event_type="risk.decision.evaluated",
                timestamp="2026-07-08T00:01:00Z",
                summary="Risk decision available for inspection",
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


def _validated_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadModelError(f"{field_name} must be a non-empty string")
    return value


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
