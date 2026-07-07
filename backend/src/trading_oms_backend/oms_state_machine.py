from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_oms_backend.event_journal import JsonlEventJournal

OMS_TRANSITION_EVENT_TYPE = "oms.order.transitioned"

ORDER_STATES = {
    "CREATED",
    "RISK_REJECTED",
    "PENDING_APPROVAL",
    "APPROVAL_REJECTED",
    "APPROVED",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_REQUESTED",
    "CANCELLED",
    "REJECTED",
    "FAILED",
    "UNKNOWN_REQUIRES_RECONCILIATION",
}
VALID_RISK_INTENTS = {"increase", "reduce"}
VALID_SIDES = {"buy", "sell"}

ALLOWED_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"CREATED"},
    "CREATED": {"PENDING_APPROVAL", "RISK_REJECTED"},
    "PENDING_APPROVAL": {"APPROVED", "APPROVAL_REJECTED"},
    "APPROVED": {"SUBMITTED"},
    "SUBMITTED": {"ACKNOWLEDGED", "REJECTED", "FAILED", "UNKNOWN_REQUIRES_RECONCILIATION"},
    "ACKNOWLEDGED": {
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCEL_REQUESTED",
        "REJECTED",
        "FAILED",
        "UNKNOWN_REQUIRES_RECONCILIATION",
    },
    "PARTIALLY_FILLED": {
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCEL_REQUESTED",
        "FAILED",
        "UNKNOWN_REQUIRES_RECONCILIATION",
    },
    "CANCEL_REQUESTED": {"CANCELLED", "FAILED", "UNKNOWN_REQUIRES_RECONCILIATION"},
    "RISK_REJECTED": set(),
    "APPROVAL_REJECTED": set(),
    "FILLED": set(),
    "CANCELLED": set(),
    "REJECTED": set(),
    "FAILED": set(),
    "UNKNOWN_REQUIRES_RECONCILIATION": set(),
}

APPROVAL_REQUIRED_STATES = {
    "APPROVED",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_REQUESTED",
    "CANCELLED",
    "REJECTED",
    "FAILED",
    "UNKNOWN_REQUIRES_RECONCILIATION",
}
BROKER_REFERENCE_REQUIRED_STATES = {
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "FAILED",
    "UNKNOWN_REQUIRES_RECONCILIATION",
}
TERMINAL_STATES = {
    "RISK_REJECTED",
    "APPROVAL_REJECTED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "FAILED",
}


class OMSStateMachineError(ValueError):
    """Raised when OMS state machine inputs or transitions are invalid."""


@dataclass(frozen=True)
class OrderTransitionRequest:
    transition_id: str
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    risk_intent: str
    target_state: str
    occurred_at: str
    reason: str
    risk_decision_id: str
    approval_reference: str | None = None
    broker_transition_reference: str | None = None
    cumulative_filled_quantity: int = 0
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise OMSStateMachineError("schema_version must be 1")
        _validated_identifier(self.transition_id, "transition_id")
        _validated_identifier(self.order_id, "order_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_symbol(self.symbol, "symbol")
        if self.side not in VALID_SIDES:
            raise OMSStateMachineError("side must be one of buy or sell")
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise OMSStateMachineError("quantity must be a positive integer")
        if self.risk_intent not in VALID_RISK_INTENTS:
            raise OMSStateMachineError("risk_intent must be one of increase or reduce")
        if self.target_state not in ORDER_STATES:
            raise OMSStateMachineError("target_state must be a known OMS state")
        _parse_timestamp(self.occurred_at, "occurred_at")
        _validated_identifier(self.reason, "reason")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        if self.approval_reference is not None:
            _validated_identifier(self.approval_reference, "approval_reference")
        if self.broker_transition_reference is not None:
            _validated_identifier(
                self.broker_transition_reference,
                "broker_transition_reference",
            )
        _validated_nonnegative_quantity(
            self.cumulative_filled_quantity,
            "cumulative_filled_quantity",
        )
        if self.cumulative_filled_quantity > self.quantity:
            raise OMSStateMachineError("cumulative_filled_quantity must not exceed quantity")
        _assert_json_serializable(self.to_json_dict(), "transition request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transition_id": self.transition_id,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "risk_intent": self.risk_intent,
            "target_state": self.target_state,
            "occurred_at": self.occurred_at,
            "reason": self.reason,
            "risk_decision_id": self.risk_decision_id,
            "approval_reference": self.approval_reference,
            "broker_transition_reference": self.broker_transition_reference,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
        }


@dataclass(frozen=True)
class OrderSnapshot:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    risk_intent: str
    state: str
    created_at: str
    updated_at: str
    risk_decision_id: str
    approval_reference: str | None
    broker_transition_reference: str | None
    cumulative_filled_quantity: int
    leaves_quantity: int
    requires_reconciliation: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise OMSStateMachineError("schema_version must be 1")
        _validated_identifier(self.order_id, "order_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_symbol(self.symbol, "symbol")
        if self.side not in VALID_SIDES:
            raise OMSStateMachineError("side must be one of buy or sell")
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise OMSStateMachineError("quantity must be a positive integer")
        if self.risk_intent not in VALID_RISK_INTENTS:
            raise OMSStateMachineError("risk_intent must be one of increase or reduce")
        if self.state not in ORDER_STATES:
            raise OMSStateMachineError("state must be a known OMS state")
        _parse_timestamp(self.created_at, "created_at")
        _parse_timestamp(self.updated_at, "updated_at")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        if self.approval_reference is not None:
            _validated_identifier(self.approval_reference, "approval_reference")
        if self.broker_transition_reference is not None:
            _validated_identifier(
                self.broker_transition_reference,
                "broker_transition_reference",
            )
        _validated_nonnegative_quantity(
            self.cumulative_filled_quantity,
            "cumulative_filled_quantity",
        )
        _validated_nonnegative_quantity(self.leaves_quantity, "leaves_quantity")
        if self.cumulative_filled_quantity + self.leaves_quantity > self.quantity:
            raise OMSStateMachineError("filled and leaves quantities must not exceed quantity")
        if not isinstance(self.requires_reconciliation, bool):
            raise OMSStateMachineError("requires_reconciliation must be a boolean")
        if self.state == "UNKNOWN_REQUIRES_RECONCILIATION" and not self.requires_reconciliation:
            raise OMSStateMachineError("unknown states must require reconciliation")
        if self.state != "UNKNOWN_REQUIRES_RECONCILIATION" and self.requires_reconciliation:
            raise OMSStateMachineError("only unknown states may require reconciliation")
        _assert_json_serializable(self.to_json_dict(), "order snapshot")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "risk_intent": self.risk_intent,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "risk_decision_id": self.risk_decision_id,
            "approval_reference": self.approval_reference,
            "broker_transition_reference": self.broker_transition_reference,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "leaves_quantity": self.leaves_quantity,
            "requires_reconciliation": self.requires_reconciliation,
        }


@dataclass(frozen=True)
class OrderTransitionRecord:
    transition_id: str
    order_id: str
    previous_state: str | None
    new_state: str
    occurred_at: str
    reason: str
    request: dict[str, Any]
    snapshot: OrderSnapshot
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise OMSStateMachineError("schema_version must be 1")
        _validated_identifier(self.transition_id, "transition_id")
        _validated_identifier(self.order_id, "order_id")
        if self.previous_state is not None and self.previous_state not in ORDER_STATES:
            raise OMSStateMachineError("previous_state must be a known OMS state")
        if self.new_state not in ORDER_STATES:
            raise OMSStateMachineError("new_state must be a known OMS state")
        _parse_timestamp(self.occurred_at, "occurred_at")
        _validated_identifier(self.reason, "reason")
        if not isinstance(self.request, dict):
            raise OMSStateMachineError("request must be a JSON object")
        if not isinstance(self.snapshot, OrderSnapshot):
            raise OMSStateMachineError("snapshot must be an OrderSnapshot")
        _assert_json_serializable(self.to_json_dict(), "transition record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transition_id": self.transition_id,
            "order_id": self.order_id,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "occurred_at": self.occurred_at,
            "reason": self.reason,
            "request": self.request,
            "snapshot": self.snapshot.to_json_dict(),
        }


class OrderStateMachine:
    def __init__(self, journal: JsonlEventJournal) -> None:
        self._journal = journal
        self._snapshots: dict[str, OrderSnapshot] = {}
        self._transition_requests: dict[str, dict[str, Any]] = {}
        self._transition_records: dict[str, OrderTransitionRecord] = {}

    def apply_transition(self, request: OrderTransitionRequest) -> OrderTransitionRecord:
        if not isinstance(request, OrderTransitionRequest):
            raise OMSStateMachineError("request must be an OrderTransitionRequest")

        request_payload = request.to_json_dict()
        if request.transition_id in self._transition_requests:
            if self._transition_requests[request.transition_id] != request_payload:
                raise OMSStateMachineError("conflicting transition_id")
            return self._transition_records[request.transition_id]

        previous_snapshot = self._snapshots.get(request.order_id)
        previous_state = None if previous_snapshot is None else previous_snapshot.state
        self._validate_transition(request, previous_snapshot)
        snapshot = self._next_snapshot(request, previous_snapshot)
        record = OrderTransitionRecord(
            transition_id=request.transition_id,
            order_id=request.order_id,
            previous_state=previous_state,
            new_state=request.target_state,
            occurred_at=request.occurred_at,
            reason=request.reason,
            request=request_payload,
            snapshot=snapshot,
        )
        self._journal.append(
            event_type=OMS_TRANSITION_EVENT_TYPE,
            payload=record.to_json_dict(),
            timestamp=record.occurred_at,
        )
        self._snapshots[request.order_id] = snapshot
        self._transition_requests[request.transition_id] = request_payload
        self._transition_records[request.transition_id] = record
        return record

    def current_snapshot(self, order_id: str) -> OrderSnapshot:
        order_id = _validated_identifier(order_id, "order_id")
        if order_id not in self._snapshots:
            raise OMSStateMachineError("unknown order_id")
        return self._snapshots[order_id]

    def risk_increasing_decisions_blocked(self, order_id: str) -> bool:
        return self.current_snapshot(order_id).state == "UNKNOWN_REQUIRES_RECONCILIATION"

    def _validate_transition(
        self,
        request: OrderTransitionRequest,
        previous_snapshot: OrderSnapshot | None,
    ) -> None:
        previous_state = None if previous_snapshot is None else previous_snapshot.state
        if request.target_state not in ALLOWED_TRANSITIONS[previous_state]:
            raise OMSStateMachineError(
                f"invalid transition from {previous_state} to {request.target_state}"
            )
        if previous_snapshot is None:
            if request.cumulative_filled_quantity != 0:
                raise OMSStateMachineError("CREATED transitions must have zero filled quantity")
            return

        self._validate_order_identity(request, previous_snapshot)
        if _parse_timestamp(request.occurred_at, "occurred_at") < _parse_timestamp(
            previous_snapshot.updated_at,
            "updated_at",
        ):
            raise OMSStateMachineError("occurred_at must not be before current snapshot updated_at")

        approval_reference = request.approval_reference or previous_snapshot.approval_reference
        broker_reference = (
            request.broker_transition_reference or previous_snapshot.broker_transition_reference
        )
        if request.target_state in APPROVAL_REQUIRED_STATES and approval_reference is None:
            raise OMSStateMachineError("approval_reference is required for this state")
        if request.target_state in BROKER_REFERENCE_REQUIRED_STATES and broker_reference is None:
            raise OMSStateMachineError("broker_transition_reference is required for this state")
        self._validate_fill_quantity(request, previous_snapshot)

    def _validate_order_identity(
        self,
        request: OrderTransitionRequest,
        snapshot: OrderSnapshot,
    ) -> None:
        expected_values = {
            "client_order_id": snapshot.client_order_id,
            "symbol": snapshot.symbol,
            "side": snapshot.side,
            "quantity": snapshot.quantity,
            "risk_intent": snapshot.risk_intent,
            "risk_decision_id": snapshot.risk_decision_id,
        }
        request_values = {
            "client_order_id": request.client_order_id,
            "symbol": request.symbol,
            "side": request.side,
            "quantity": request.quantity,
            "risk_intent": request.risk_intent,
            "risk_decision_id": request.risk_decision_id,
        }
        if request_values != expected_values:
            raise OMSStateMachineError("order identity fields must match the current snapshot")

    def _validate_fill_quantity(
        self,
        request: OrderTransitionRequest,
        snapshot: OrderSnapshot,
    ) -> None:
        filled_quantity = request.cumulative_filled_quantity
        current_filled_quantity = snapshot.cumulative_filled_quantity
        if request.target_state == "PARTIALLY_FILLED":
            if filled_quantity <= current_filled_quantity or filled_quantity >= request.quantity:
                raise OMSStateMachineError(
                    "PARTIALLY_FILLED transitions must increase filled quantity below total"
                )
            return
        if request.target_state == "FILLED":
            if filled_quantity != request.quantity:
                raise OMSStateMachineError("FILLED transitions must fill the full quantity")
            return
        if filled_quantity != current_filled_quantity:
            raise OMSStateMachineError(
                "cumulative_filled_quantity must match the current snapshot for this state"
            )

    def _next_snapshot(
        self,
        request: OrderTransitionRequest,
        previous_snapshot: OrderSnapshot | None,
    ) -> OrderSnapshot:
        if previous_snapshot is None:
            created_at = request.occurred_at
            approval_reference = request.approval_reference
            broker_reference = request.broker_transition_reference
        else:
            created_at = previous_snapshot.created_at
            approval_reference = request.approval_reference or previous_snapshot.approval_reference
            broker_reference = (
                request.broker_transition_reference or previous_snapshot.broker_transition_reference
            )

        filled_quantity = request.cumulative_filled_quantity
        leaves_quantity = self._leaves_quantity(request, filled_quantity)
        return OrderSnapshot(
            order_id=request.order_id,
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            risk_intent=request.risk_intent,
            state=request.target_state,
            created_at=created_at,
            updated_at=request.occurred_at,
            risk_decision_id=request.risk_decision_id,
            approval_reference=approval_reference,
            broker_transition_reference=broker_reference,
            cumulative_filled_quantity=filled_quantity,
            leaves_quantity=leaves_quantity,
            requires_reconciliation=request.target_state == "UNKNOWN_REQUIRES_RECONCILIATION",
        )

    def _leaves_quantity(
        self,
        request: OrderTransitionRequest,
        filled_quantity: int,
    ) -> int:
        if request.target_state in TERMINAL_STATES:
            return 0
        if request.target_state == "UNKNOWN_REQUIRES_RECONCILIATION":
            return request.quantity - filled_quantity
        return request.quantity - filled_quantity


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OMSStateMachineError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise OMSStateMachineError(f"{field_name} must not contain leading or trailing whitespace")
    return value


def _validated_symbol(symbol: str, field_name: str) -> str:
    _validated_identifier(symbol, field_name)
    if symbol != symbol.upper():
        raise OMSStateMachineError(f"{field_name} must be uppercase")
    return symbol


def _validated_nonnegative_quantity(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OMSStateMachineError(f"{field_name} must be a nonnegative integer")
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise OMSStateMachineError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OMSStateMachineError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OMSStateMachineError(f"{field_name} must include a timezone")
    return parsed


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OMSStateMachineError(f"{payload_name} must be JSON-serializable") from exc
