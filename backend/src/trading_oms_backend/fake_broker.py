from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from trading_oms_backend.event_journal import JsonlEventJournal

FAKE_BROKER_TRANSITION_EVENT_TYPE = "fake_broker.order.transitioned"
VALID_FILL_MODES = {"acknowledge_only", "fill_immediately"}
VALID_ORDER_STATES = {"acknowledged", "filled", "cancelled", "rejected"}
VALID_ORDER_TYPES = {"market", "limit"}
VALID_SIDES = {"buy", "sell"}

FillMode = Literal["acknowledge_only", "fill_immediately"]
OrderState = Literal["acknowledged", "filled", "cancelled", "rejected"]


class FakeBrokerError(ValueError):
    """Raised when fake broker requests, transitions, or state changes are invalid."""


class SimulationBrokerAdapter(Protocol):
    """Simulation-only broker adapter contract.

    This protocol intentionally models local fake broker behavior only. It does not provide a
    network, socket, live broker, or external order-transmission capability.
    """

    def accept_order(self, order: BrokerOrderRequest) -> tuple[BrokerOrderTransition, ...]:
        """Accept a simulation order request and return journaled fake broker transitions."""

    def fill_order(
        self,
        client_order_id: str,
        *,
        filled_at: str,
        fill_price: float | None = None,
        reason: str = "manual_fill",
    ) -> BrokerOrderTransition:
        """Fill an acknowledged fake order."""

    def cancel_order(
        self,
        client_order_id: str,
        *,
        cancelled_at: str,
        reason: str = "cancel_requested",
    ) -> BrokerOrderTransition:
        """Cancel an acknowledged fake order."""

    def reject_order(
        self,
        order: BrokerOrderRequest,
        *,
        rejected_at: str,
        reason: str,
    ) -> BrokerOrderTransition:
        """Reject a fake order request without acknowledging it."""


@dataclass(frozen=True)
class FakeBrokerConfig:
    fill_mode: FillMode = "acknowledge_only"
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise FakeBrokerError("schema_version must be 1")
        if self.fill_mode not in VALID_FILL_MODES:
            raise FakeBrokerError("fill_mode must be one of acknowledge_only or fill_immediately")


@dataclass(frozen=True)
class BrokerOrderRequest:
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    reference_price: float
    requested_at: str
    risk_decision_id: str
    risk_decision_result: str
    approval_reference: str
    limit_price: float | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise FakeBrokerError("schema_version must be 1")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_symbol(self.symbol, "symbol")
        if self.side not in VALID_SIDES:
            raise FakeBrokerError("side must be one of buy or sell")
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise FakeBrokerError("quantity must be a positive integer")
        if self.order_type not in VALID_ORDER_TYPES:
            raise FakeBrokerError("order_type must be one of market or limit")
        _positive_finite_number(self.reference_price, "reference_price")
        _parse_timestamp(self.requested_at, "requested_at")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        if self.risk_decision_result != "passed":
            raise FakeBrokerError("risk_decision_result must be passed")
        _validated_identifier(self.approval_reference, "approval_reference")
        self._validate_limit_price()
        _assert_json_serializable(self.to_json_dict(), "order request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "reference_price": self.reference_price,
            "requested_at": self.requested_at,
            "risk_decision_id": self.risk_decision_id,
            "risk_decision_result": self.risk_decision_result,
            "approval_reference": self.approval_reference,
            "limit_price": self.limit_price,
        }

    def default_fill_price(self) -> float:
        if self.order_type == "limit":
            if self.limit_price is None:
                raise FakeBrokerError("limit_price is required for limit orders")
            return self.limit_price
        return self.reference_price

    def _validate_limit_price(self) -> None:
        if self.order_type == "market":
            if self.limit_price is not None:
                raise FakeBrokerError("limit_price must be omitted for market orders")
            return

        if self.limit_price is None:
            raise FakeBrokerError("limit_price is required for limit orders")
        _positive_finite_number(self.limit_price, "limit_price")


@dataclass(frozen=True)
class BrokerOrderTransition:
    client_order_id: str
    fake_broker_order_id: str
    symbol: str
    side: str
    quantity: int
    state: OrderState
    occurred_at: str
    reason: str
    cumulative_filled_quantity: int
    leaves_quantity: int
    order: dict[str, Any]
    fill_price: float | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise FakeBrokerError("schema_version must be 1")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_identifier(self.fake_broker_order_id, "fake_broker_order_id")
        _validated_symbol(self.symbol, "symbol")
        if self.side not in VALID_SIDES:
            raise FakeBrokerError("side must be one of buy or sell")
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise FakeBrokerError("quantity must be a positive integer")
        if self.state not in VALID_ORDER_STATES:
            raise FakeBrokerError(
                "state must be one of acknowledged, filled, cancelled, or rejected"
            )
        _parse_timestamp(self.occurred_at, "occurred_at")
        _validated_identifier(self.reason, "reason")
        _validated_quantity(self.cumulative_filled_quantity, "cumulative_filled_quantity")
        _validated_quantity(self.leaves_quantity, "leaves_quantity")
        if self.cumulative_filled_quantity + self.leaves_quantity > self.quantity:
            raise FakeBrokerError("filled and leaves quantities must not exceed quantity")
        self._validate_state_quantities()
        if not isinstance(self.order, dict):
            raise FakeBrokerError("order must be a JSON object")
        _assert_json_serializable(self.to_json_dict(), "order transition")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "client_order_id": self.client_order_id,
            "fake_broker_order_id": self.fake_broker_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "state": self.state,
            "occurred_at": self.occurred_at,
            "reason": self.reason,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "leaves_quantity": self.leaves_quantity,
            "fill_price": self.fill_price,
            "order": self.order,
        }

    def _validate_state_quantities(self) -> None:
        if self.state == "acknowledged":
            if self.cumulative_filled_quantity != 0 or self.leaves_quantity != self.quantity:
                raise FakeBrokerError("acknowledged transitions must leave the full quantity open")
            if self.fill_price is not None:
                raise FakeBrokerError("fill_price must be omitted unless state is filled")
            return

        if self.state == "filled":
            if self.cumulative_filled_quantity != self.quantity or self.leaves_quantity != 0:
                raise FakeBrokerError("filled transitions must fill the full quantity")
            if self.fill_price is None:
                raise FakeBrokerError("fill_price is required for filled transitions")
            _positive_finite_number(self.fill_price, "fill_price")
            return

        if self.state == "cancelled":
            if self.cumulative_filled_quantity != 0 or self.leaves_quantity != 0:
                raise FakeBrokerError(
                    "cancelled transitions must have zero filled and leaves quantity"
                )
            if self.fill_price is not None:
                raise FakeBrokerError("fill_price must be omitted unless state is filled")
            return

        if self.cumulative_filled_quantity != 0 or self.leaves_quantity != 0:
            raise FakeBrokerError("rejected transitions must have zero filled and leaves quantity")
        if self.fill_price is not None:
            raise FakeBrokerError("fill_price must be omitted unless state is filled")


class FakeBroker:
    def __init__(
        self,
        journal: JsonlEventJournal,
        config: FakeBrokerConfig | None = None,
    ) -> None:
        self._journal = journal
        if config is not None and not isinstance(config, FakeBrokerConfig):
            raise FakeBrokerError("config must be a FakeBrokerConfig")
        self._config = config or FakeBrokerConfig()
        self._orders: dict[str, BrokerOrderRequest] = {}
        self._states: dict[str, OrderState] = {}

    def accept_order(self, order: BrokerOrderRequest) -> tuple[BrokerOrderTransition, ...]:
        self._validate_order_instance(order)
        self._ensure_new_client_order_id(order.client_order_id)

        acknowledged = self._record_transition(
            order=order,
            state="acknowledged",
            occurred_at=order.requested_at,
            reason="order_acknowledged",
            cumulative_filled_quantity=0,
            leaves_quantity=order.quantity,
        )
        if self._config.fill_mode == "acknowledge_only":
            return (acknowledged,)

        filled = self._record_transition(
            order=order,
            state="filled",
            occurred_at=order.requested_at,
            reason="configured_immediate_fill",
            cumulative_filled_quantity=order.quantity,
            leaves_quantity=0,
            fill_price=order.default_fill_price(),
        )
        return (acknowledged, filled)

    def fill_order(
        self,
        client_order_id: str,
        *,
        filled_at: str,
        fill_price: float | None = None,
        reason: str = "manual_fill",
    ) -> BrokerOrderTransition:
        client_order_id = _validated_identifier(client_order_id, "client_order_id")
        _parse_timestamp(filled_at, "filled_at")
        _validated_identifier(reason, "reason")
        order = self._acknowledged_order(client_order_id)

        return self._record_transition(
            order=order,
            state="filled",
            occurred_at=filled_at,
            reason=reason,
            cumulative_filled_quantity=order.quantity,
            leaves_quantity=0,
            fill_price=(
                order.default_fill_price()
                if fill_price is None
                else _positive_finite_number(fill_price, "fill_price")
            ),
        )

    def cancel_order(
        self,
        client_order_id: str,
        *,
        cancelled_at: str,
        reason: str = "cancel_requested",
    ) -> BrokerOrderTransition:
        client_order_id = _validated_identifier(client_order_id, "client_order_id")
        _parse_timestamp(cancelled_at, "cancelled_at")
        _validated_identifier(reason, "reason")
        order = self._acknowledged_order(client_order_id)

        return self._record_transition(
            order=order,
            state="cancelled",
            occurred_at=cancelled_at,
            reason=reason,
            cumulative_filled_quantity=0,
            leaves_quantity=0,
        )

    def reject_order(
        self,
        order: BrokerOrderRequest,
        *,
        rejected_at: str,
        reason: str,
    ) -> BrokerOrderTransition:
        self._validate_order_instance(order)
        self._ensure_new_client_order_id(order.client_order_id)
        _parse_timestamp(rejected_at, "rejected_at")
        _validated_identifier(reason, "reason")

        return self._record_transition(
            order=order,
            state="rejected",
            occurred_at=rejected_at,
            reason=reason,
            cumulative_filled_quantity=0,
            leaves_quantity=0,
        )

    def current_state(self, client_order_id: str) -> OrderState:
        client_order_id = _validated_identifier(client_order_id, "client_order_id")
        if client_order_id not in self._states:
            raise FakeBrokerError("unknown client_order_id")
        return self._states[client_order_id]

    def _record_transition(
        self,
        *,
        order: BrokerOrderRequest,
        state: OrderState,
        occurred_at: str,
        reason: str,
        cumulative_filled_quantity: int,
        leaves_quantity: int,
        fill_price: float | None = None,
    ) -> BrokerOrderTransition:
        transition = BrokerOrderTransition(
            client_order_id=order.client_order_id,
            fake_broker_order_id=self._fake_broker_order_id(order.client_order_id),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            state=state,
            occurred_at=occurred_at,
            reason=reason,
            cumulative_filled_quantity=cumulative_filled_quantity,
            leaves_quantity=leaves_quantity,
            fill_price=fill_price,
            order=order.to_json_dict(),
        )
        self._journal.append(
            event_type=FAKE_BROKER_TRANSITION_EVENT_TYPE,
            payload=transition.to_json_dict(),
            timestamp=transition.occurred_at,
        )
        self._orders[order.client_order_id] = order
        self._states[order.client_order_id] = state
        return transition

    def _validate_order_instance(self, order: BrokerOrderRequest) -> None:
        if not isinstance(order, BrokerOrderRequest):
            raise FakeBrokerError("order must be a BrokerOrderRequest")

    def _ensure_new_client_order_id(self, client_order_id: str) -> None:
        if client_order_id in self._orders:
            raise FakeBrokerError("client_order_id already exists")

    def _acknowledged_order(self, client_order_id: str) -> BrokerOrderRequest:
        if client_order_id not in self._orders:
            raise FakeBrokerError("unknown client_order_id")
        if self._states.get(client_order_id) != "acknowledged":
            raise FakeBrokerError("order must be acknowledged before this transition")
        return self._orders[client_order_id]

    def _fake_broker_order_id(self, client_order_id: str) -> str:
        return f"fake-{client_order_id}"


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FakeBrokerError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise FakeBrokerError(f"{field_name} must not contain leading or trailing whitespace")
    return value


def _validated_symbol(symbol: str, field_name: str) -> str:
    _validated_identifier(symbol, field_name)
    if symbol != symbol.upper():
        raise FakeBrokerError(f"{field_name} must be uppercase")
    return symbol


def _validated_quantity(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FakeBrokerError(f"{field_name} must be a nonnegative integer")
    return value


def _positive_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise FakeBrokerError(f"{field_name} must be a finite number")

    number = float(value)
    if not math.isfinite(number):
        raise FakeBrokerError(f"{field_name} must be a finite number")
    if number <= 0:
        raise FakeBrokerError(f"{field_name} must be greater than zero")
    return number


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FakeBrokerError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FakeBrokerError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FakeBrokerError(f"{field_name} must include a timezone")
    return parsed


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise FakeBrokerError(f"{payload_name} must be JSON-serializable") from exc
