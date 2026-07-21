from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from trading_oms_backend.event_journal import JsonlEventJournal

RISK_DECISION_EVENT_TYPE = "risk.decision.evaluated"
VALID_SIDES = {"buy", "sell"}
VALID_RISK_INTENTS = {"increase", "reduce"}

CheckStatus = Literal["passed", "failed"]
DecisionResult = Literal["passed", "blocked"]


class RiskEngineError(ValueError):
    """Raised when risk inputs, policy, or decisions are invalid."""


@dataclass(frozen=True)
class RiskPolicy:
    max_order_quantity: int
    max_order_notional: float
    max_market_data_age_seconds: int
    allowed_symbols: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.schema_version != 1:
            raise RiskEngineError("schema_version must be 1")
        if not isinstance(self.max_order_quantity, int) or self.max_order_quantity < 1:
            raise RiskEngineError("max_order_quantity must be a positive integer")
        _positive_finite_number(self.max_order_notional, "max_order_notional")
        if (
            not isinstance(self.max_market_data_age_seconds, int)
            or self.max_market_data_age_seconds < 1
        ):
            raise RiskEngineError("max_market_data_age_seconds must be a positive integer")
        if not isinstance(self.allowed_symbols, tuple):
            raise RiskEngineError("allowed_symbols must be a tuple")
        if len(set(self.allowed_symbols)) != len(self.allowed_symbols):
            raise RiskEngineError("allowed_symbols must not contain duplicates")
        for symbol in self.allowed_symbols:
            _validated_symbol(symbol, "allowed_symbols")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "max_order_quantity": self.max_order_quantity,
            "max_order_notional": self.max_order_notional,
            "max_market_data_age_seconds": self.max_market_data_age_seconds,
            "allowed_symbols": list(self.allowed_symbols),
        }


@dataclass(frozen=True)
class ProtectiveOrderPlan:
    kind: str
    stop_price: float
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.schema_version != 1:
            raise RiskEngineError("schema_version must be 1")
        _validated_identifier(self.kind, "kind")
        _positive_finite_number(self.stop_price, "stop_price")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "stop_price": self.stop_price,
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> ProtectiveOrderPlan:
        if not isinstance(raw_record, Mapping) or set(raw_record) != {
            "schema_version",
            "kind",
            "stop_price",
        }:
            raise RiskEngineError("protective order fields are invalid")
        return cls(**dict(raw_record))


@dataclass(frozen=True)
class RiskEvaluationRequest:
    request_id: str
    symbol: str
    side: str
    risk_intent: str
    quantity: int
    reference_price: float
    market_data_timestamp: str
    evaluated_at: str
    broker_state_known: bool
    protective_order: ProtectiveOrderPlan | None = None
    protective_exception_approved: bool = False
    existing_request_ids: frozenset[str] = field(default_factory=frozenset)
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.schema_version != 1:
            raise RiskEngineError("schema_version must be 1")
        _validated_identifier(self.request_id, "request_id")
        _validated_symbol(self.symbol, "symbol")
        if self.side not in VALID_SIDES:
            raise RiskEngineError("side must be one of buy or sell")
        if self.risk_intent not in VALID_RISK_INTENTS:
            raise RiskEngineError("risk_intent must be one of increase or reduce")
        if not isinstance(self.quantity, int) or self.quantity < 1:
            raise RiskEngineError("quantity must be a positive integer")
        _positive_finite_number(self.reference_price, "reference_price")
        _parse_timestamp(self.market_data_timestamp, "market_data_timestamp")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        if not isinstance(self.broker_state_known, bool):
            raise RiskEngineError("broker_state_known must be a boolean")
        if not isinstance(self.protective_exception_approved, bool):
            raise RiskEngineError("protective_exception_approved must be a boolean")
        if self.protective_order is not None and not isinstance(
            self.protective_order,
            ProtectiveOrderPlan,
        ):
            raise RiskEngineError("protective_order must be a ProtectiveOrderPlan")
        if not isinstance(self.existing_request_ids, frozenset):
            raise RiskEngineError("existing_request_ids must be a frozenset")
        for request_id in self.existing_request_ids:
            _validated_identifier(request_id, "existing_request_ids")

    def notional(self) -> float:
        return self.quantity * self.reference_price

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "symbol": self.symbol,
            "side": self.side,
            "risk_intent": self.risk_intent,
            "quantity": self.quantity,
            "reference_price": self.reference_price,
            "market_data_timestamp": self.market_data_timestamp,
            "evaluated_at": self.evaluated_at,
            "broker_state_known": self.broker_state_known,
            "protective_order": (
                None if self.protective_order is None else self.protective_order.to_json_dict()
            ),
            "protective_exception_approved": self.protective_exception_approved,
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> RiskEvaluationRequest:
        expected_keys = {
            "schema_version",
            "request_id",
            "symbol",
            "side",
            "risk_intent",
            "quantity",
            "reference_price",
            "market_data_timestamp",
            "evaluated_at",
            "broker_state_known",
            "protective_order",
            "protective_exception_approved",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise RiskEngineError("risk evaluation request fields are invalid")
        raw_plan = raw_record["protective_order"]
        if raw_plan is not None and not isinstance(raw_plan, Mapping):
            raise RiskEngineError("protective_order must be an object or null")
        return cls(
            schema_version=raw_record["schema_version"],
            request_id=raw_record["request_id"],
            symbol=raw_record["symbol"],
            side=raw_record["side"],
            risk_intent=raw_record["risk_intent"],
            quantity=raw_record["quantity"],
            reference_price=raw_record["reference_price"],
            market_data_timestamp=raw_record["market_data_timestamp"],
            evaluated_at=raw_record["evaluated_at"],
            broker_state_known=raw_record["broker_state_known"],
            protective_order=(
                None if raw_plan is None else ProtectiveOrderPlan.from_json_dict(raw_plan)
            ),
            protective_exception_approved=raw_record["protective_exception_approved"],
        )


@dataclass(frozen=True)
class RiskCheckResult:
    name: str
    status: CheckStatus
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.schema_version != 1:
            raise RiskEngineError("schema_version must be 1")
        _validated_identifier(self.name, "name")
        if self.status not in {"passed", "failed"}:
            raise RiskEngineError("status must be one of passed or failed")
        _validated_identifier(self.reason, "reason")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "status": self.status,
            "reason": self.reason,
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> RiskCheckResult:
        if not isinstance(raw_record, Mapping) or set(raw_record) != {
            "schema_version",
            "name",
            "status",
            "reason",
        }:
            raise RiskEngineError("risk check fields are invalid")
        return cls(**dict(raw_record))


@dataclass(frozen=True)
class RiskDecision:
    request_id: str
    evaluated_at: str
    symbol: str
    risk_intent: str
    result: DecisionResult
    checks: tuple[RiskCheckResult, ...]
    request: dict[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def failed_checks(self) -> list[RiskCheckResult]:
        return [check for check in self.checks if check.status == "failed"]

    def check_by_name(self, name: str) -> RiskCheckResult:
        for check in self.checks:
            if check.name == name:
                return check
        raise RiskEngineError(f"risk check does not exist: {name}")

    def validate(self) -> None:
        if self.schema_version != 1:
            raise RiskEngineError("schema_version must be 1")
        _validated_identifier(self.request_id, "request_id")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        _validated_symbol(self.symbol, "symbol")
        if self.risk_intent not in VALID_RISK_INTENTS:
            raise RiskEngineError("risk_intent must be one of increase or reduce")
        if self.result not in {"passed", "blocked"}:
            raise RiskEngineError("result must be one of passed or blocked")
        if not self.checks:
            raise RiskEngineError("checks must not be empty")
        for check in self.checks:
            if not isinstance(check, RiskCheckResult):
                raise RiskEngineError("checks must contain RiskCheckResult values")
        failed_checks = [check for check in self.checks if check.status == "failed"]
        if self.result == "passed" and failed_checks:
            raise RiskEngineError("passed risk decisions must not contain failed checks")
        if self.result == "blocked" and not failed_checks:
            raise RiskEngineError("blocked risk decisions must contain failed checks")
        try:
            json.dumps(self.to_json_dict(), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise RiskEngineError("risk decision payload must be JSON-serializable") from exc

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "evaluated_at": self.evaluated_at,
            "symbol": self.symbol,
            "risk_intent": self.risk_intent,
            "result": self.result,
            "request": self.request,
            "checks": [check.to_json_dict() for check in self.checks],
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> RiskDecision:
        expected_keys = {
            "schema_version",
            "request_id",
            "evaluated_at",
            "symbol",
            "risk_intent",
            "result",
            "request",
            "checks",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise RiskEngineError("risk decision fields are invalid")
        request = raw_record["request"]
        checks = raw_record["checks"]
        if not isinstance(request, Mapping) or not isinstance(checks, list):
            raise RiskEngineError("risk decision nested fields are invalid")
        typed_request = RiskEvaluationRequest.from_json_dict(request)
        return cls(
            schema_version=raw_record["schema_version"],
            request_id=raw_record["request_id"],
            evaluated_at=raw_record["evaluated_at"],
            symbol=raw_record["symbol"],
            risk_intent=raw_record["risk_intent"],
            result=raw_record["result"],
            request=typed_request.to_json_dict(),
            checks=tuple(RiskCheckResult.from_json_dict(check) for check in checks),
        )


def evaluate_risk(
    risk_request: RiskEvaluationRequest,
    policy: RiskPolicy,
    journal: JsonlEventJournal,
) -> RiskDecision:
    checks = tuple(_run_checks(risk_request, policy))
    result: DecisionResult = (
        "blocked" if any(check.status == "failed" for check in checks) else "passed"
    )
    decision = RiskDecision(
        request_id=risk_request.request_id,
        evaluated_at=risk_request.evaluated_at,
        symbol=risk_request.symbol,
        risk_intent=risk_request.risk_intent,
        result=result,
        checks=checks,
        request=risk_request.to_json_dict(),
    )
    journal.append(
        event_type=RISK_DECISION_EVENT_TYPE,
        payload=decision.to_json_dict(),
        timestamp=decision.evaluated_at,
    )
    return decision


def _run_checks(
    risk_request: RiskEvaluationRequest,
    policy: RiskPolicy,
) -> Iterable[RiskCheckResult]:
    yield _check_allowed_symbol(risk_request, policy)
    yield _check_duplicate_request(risk_request)
    yield _check_market_data_freshness(risk_request, policy)
    yield _check_broker_state(risk_request)
    yield _check_max_quantity(risk_request, policy)
    yield _check_max_notional(risk_request, policy)
    yield _check_protective_order(risk_request)


def _check_allowed_symbol(
    risk_request: RiskEvaluationRequest,
    policy: RiskPolicy,
) -> RiskCheckResult:
    if policy.allowed_symbols and risk_request.symbol not in policy.allowed_symbols:
        return _failed("allowed_symbol", "symbol_not_allowed")
    return _passed("allowed_symbol", "symbol_allowed")


def _check_duplicate_request(risk_request: RiskEvaluationRequest) -> RiskCheckResult:
    if risk_request.request_id in risk_request.existing_request_ids:
        return _failed("duplicate_request", "request_id_already_exists")
    return _passed("duplicate_request", "request_id_unique")


def _check_market_data_freshness(
    risk_request: RiskEvaluationRequest,
    policy: RiskPolicy,
) -> RiskCheckResult:
    market_data_timestamp = _parse_timestamp(
        risk_request.market_data_timestamp,
        "market_data_timestamp",
    )
    evaluated_at = _parse_timestamp(risk_request.evaluated_at, "evaluated_at")
    age_seconds = (evaluated_at - market_data_timestamp).total_seconds()
    if age_seconds < 0:
        return _failed("market_data_freshness", "market_data_timestamp_after_evaluation")
    if age_seconds > policy.max_market_data_age_seconds:
        return _failed("market_data_freshness", "market_data_stale")
    return _passed("market_data_freshness", "market_data_fresh")


def _check_broker_state(risk_request: RiskEvaluationRequest) -> RiskCheckResult:
    if risk_request.risk_intent == "reduce":
        return _passed("broker_state_known", "not_risk_increasing")
    if not risk_request.broker_state_known:
        return _failed("broker_state_known", "unknown_broker_state_blocks_risk_increase")
    return _passed("broker_state_known", "broker_state_known")


def _check_max_quantity(
    risk_request: RiskEvaluationRequest,
    policy: RiskPolicy,
) -> RiskCheckResult:
    if risk_request.quantity > policy.max_order_quantity:
        return _failed("max_quantity", "quantity_exceeds_limit")
    return _passed("max_quantity", "quantity_within_limit")


def _check_max_notional(
    risk_request: RiskEvaluationRequest,
    policy: RiskPolicy,
) -> RiskCheckResult:
    if risk_request.notional() > policy.max_order_notional:
        return _failed("max_notional", "notional_exceeds_limit")
    return _passed("max_notional", "notional_within_limit")


def _check_protective_order(risk_request: RiskEvaluationRequest) -> RiskCheckResult:
    if risk_request.risk_intent == "reduce":
        return _passed("protective_order", "not_risk_increasing")
    if risk_request.protective_exception_approved:
        return _passed("protective_order", "approved_exception")
    if risk_request.protective_order is None:
        return _failed("protective_order", "missing_protective_order")
    if (
        risk_request.side == "buy"
        and risk_request.protective_order.stop_price >= risk_request.reference_price
    ):
        return _failed("protective_order", "buy_stop_must_be_below_reference_price")
    if (
        risk_request.side == "sell"
        and risk_request.protective_order.stop_price <= risk_request.reference_price
    ):
        return _failed("protective_order", "sell_stop_must_be_above_reference_price")
    return _passed("protective_order", "protective_order_valid")


def _passed(name: str, reason: str) -> RiskCheckResult:
    return RiskCheckResult(name=name, status="passed", reason=reason)


def _failed(name: str, reason: str) -> RiskCheckResult:
    return RiskCheckResult(name=name, status="failed", reason=reason)


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RiskEngineError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise RiskEngineError(f"{field_name} must not contain leading or trailing whitespace")
    return value


def _validated_symbol(symbol: str, field_name: str) -> str:
    _validated_identifier(symbol, field_name)
    if symbol != symbol.upper():
        raise RiskEngineError(f"{field_name} must be uppercase")
    return symbol


def _positive_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RiskEngineError(f"{field_name} must be a finite number")

    number = float(value)
    if not math.isfinite(number):
        raise RiskEngineError(f"{field_name} must be a finite number")
    if number <= 0:
        raise RiskEngineError(f"{field_name} must be greater than zero")
    return number


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RiskEngineError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RiskEngineError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RiskEngineError(f"{field_name} must include a timezone")
    return parsed
