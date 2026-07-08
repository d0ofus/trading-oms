from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from trading_oms_backend.config import LOCAL_IBKR_HOSTS, Settings
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.fake_broker import BrokerOrderRequest

IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE = "ibkr.paper.connection_state.recorded"
IBKR_PAPER_ORDER_PLAN_EVENT_TYPE = "ibkr.paper.order_plan.created"

IBKR_PAPER_ADAPTER_NAME = "ibkr_paper"
IBKR_PAPER_PORTS = {4002, 7497}
VALID_CONNECTION_STATES = {
    "disconnected",
    "connected_paper",
    "unknown_requires_reconciliation",
}

ConnectionState = Literal[
    "disconnected",
    "connected_paper",
    "unknown_requires_reconciliation",
]
PaperOrderPlanStatus = Literal["planned_local_only"]

_FORBIDDEN_TEXT_MARKERS = (
    "account=",
    "account:",
    "api_key=",
    "api_key:",
    "authorization=",
    "authorization:",
    "password=",
    "password:",
    "private_key=",
    "private_key:",
    "secret=",
    "secret:",
    "submit order",
    "token=",
    "token:",
    "transmit order",
)


class IbkrPaperAdapterError(ValueError):
    """Raised when IBKR paper adapter state or requests violate safety rules."""


@dataclass(frozen=True)
class IbkrPaperAdapterConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    account_mode: str = "paper"
    live_trading_enabled: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_settings(cls, settings: Settings) -> IbkrPaperAdapterConfig:
        if not isinstance(settings, Settings):
            raise IbkrPaperAdapterError("settings must be Settings")

        return cls(
            host=settings.ibkr_host,
            port=settings.ibkr_port,
            account_mode=settings.ibkr_account_mode,
            live_trading_enabled=settings.live_trading_enabled,
        )

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.account_mode != "paper":
            raise IbkrPaperAdapterError("account_mode must be paper")
        if self.live_trading_enabled:
            raise IbkrPaperAdapterError("live trading must remain disabled")
        if not isinstance(self.host, str):
            raise IbkrPaperAdapterError("host must be a string")
        normalized_host = self.host.strip().lower()
        if normalized_host != self.host:
            raise IbkrPaperAdapterError("host must be normalized lowercase without whitespace")
        if normalized_host not in LOCAL_IBKR_HOSTS:
            raise IbkrPaperAdapterError("host must be localhost-only")
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise IbkrPaperAdapterError("port must be an integer")
        if self.port not in IBKR_PAPER_PORTS:
            raise IbkrPaperAdapterError("port must be a known IBKR paper TWS or Gateway port")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper adapter config")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": IBKR_PAPER_ADAPTER_NAME,
            "host": self.host,
            "port": self.port,
            "account_mode": self.account_mode,
            "live_trading_enabled": self.live_trading_enabled,
        }


@dataclass(frozen=True)
class IbkrConnectionStateRecord:
    state: ConnectionState
    recorded_at: str
    reason: str
    requires_reconciliation: bool
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        if self.state not in VALID_CONNECTION_STATES:
            raise IbkrPaperAdapterError(
                "state must be disconnected, connected_paper, or unknown_requires_reconciliation"
            )
        _parse_timestamp(self.recorded_at, "recorded_at")
        _validated_identifier(self.reason, "reason")
        expected_reconciliation = self.state == "unknown_requires_reconciliation"
        if self.requires_reconciliation is not expected_reconciliation:
            raise IbkrPaperAdapterError("requires_reconciliation must match connection state")
        _assert_json_serializable(self.to_json_dict(), "IBKR connection state record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "state": self.state,
            "recorded_at": self.recorded_at,
            "reason": self.reason,
            "requires_reconciliation": self.requires_reconciliation,
        }


@dataclass(frozen=True)
class IbkrPaperOrderPlan:
    plan_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    reference_price: float
    requested_at: str
    risk_decision_id: str
    approval_reference: str
    limit_price: float | None
    status: PaperOrderPlanStatus = "planned_local_only"
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    local_only: bool = True
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_order_request(cls, order: BrokerOrderRequest) -> IbkrPaperOrderPlan:
        if not isinstance(order, BrokerOrderRequest):
            raise IbkrPaperAdapterError("order must be a BrokerOrderRequest")

        return cls(
            plan_id=f"ibkr-paper-plan-{order.client_order_id}",
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            reference_price=order.reference_price,
            requested_at=order.requested_at,
            risk_decision_id=order.risk_decision_id,
            approval_reference=order.approval_reference,
            limit_price=order.limit_price,
        )

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        if self.status != "planned_local_only":
            raise IbkrPaperAdapterError("status must be planned_local_only")
        if self.local_only is not True:
            raise IbkrPaperAdapterError("local_only must be true")
        _validated_identifier(self.plan_id, "plan_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        _validated_identifier(self.approval_reference, "approval_reference")
        _validated_symbol(self.symbol)
        if self.side not in {"buy", "sell"}:
            raise IbkrPaperAdapterError("side must be one of buy or sell")
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise IbkrPaperAdapterError("quantity must be a positive integer")
        if self.order_type not in {"market", "limit"}:
            raise IbkrPaperAdapterError("order_type must be one of market or limit")
        _positive_finite_number(self.reference_price, "reference_price")
        _parse_timestamp(self.requested_at, "requested_at")
        if self.order_type == "market" and self.limit_price is not None:
            raise IbkrPaperAdapterError("limit_price must be omitted for market plans")
        if self.order_type == "limit":
            if self.limit_price is None:
                raise IbkrPaperAdapterError("limit_price is required for limit plans")
            _positive_finite_number(self.limit_price, "limit_price")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper order plan")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "status": self.status,
            "local_only": self.local_only,
            "plan_id": self.plan_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "reference_price": self.reference_price,
            "limit_price": self.limit_price,
            "requested_at": self.requested_at,
            "risk_decision_id": self.risk_decision_id,
            "approval_reference": self.approval_reference,
        }


class IbkrPaperAdapter:
    """Local IBKR paper adapter boundary.

    This class intentionally records local paper adapter state and plans only. It does not connect
    to TWS/Gateway, import a broker SDK, or expose any method that sends instructions outside this
    process.
    """

    def __init__(self, journal: JsonlEventJournal, config: IbkrPaperAdapterConfig) -> None:
        if not isinstance(journal, JsonlEventJournal):
            raise IbkrPaperAdapterError("journal must be a JsonlEventJournal")
        if not isinstance(config, IbkrPaperAdapterConfig):
            raise IbkrPaperAdapterError("config must be an IbkrPaperAdapterConfig")
        self._journal = journal
        self._config = config
        self._connection_state: ConnectionState = "disconnected"
        self._requires_reconciliation = False

    @property
    def config(self) -> IbkrPaperAdapterConfig:
        return self._config

    @property
    def connection_state(self) -> ConnectionState:
        return self._connection_state

    @property
    def requires_reconciliation(self) -> bool:
        return self._requires_reconciliation

    def record_connection_state(
        self,
        state: ConnectionState,
        *,
        recorded_at: str,
        reason: str,
    ) -> IbkrConnectionStateRecord:
        record = IbkrConnectionStateRecord(
            state=state,
            recorded_at=recorded_at,
            reason=reason,
            requires_reconciliation=state == "unknown_requires_reconciliation",
        )
        self._journal.append(
            event_type=IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE,
            payload=record.to_json_dict(),
            timestamp=record.recorded_at,
        )
        self._connection_state = record.state
        self._requires_reconciliation = record.requires_reconciliation
        return record

    def create_order_plan(self, order: BrokerOrderRequest) -> IbkrPaperOrderPlan:
        if not isinstance(order, BrokerOrderRequest):
            raise IbkrPaperAdapterError("order must be a BrokerOrderRequest")
        if self._requires_reconciliation:
            raise IbkrPaperAdapterError("IBKR state requires reconciliation before order planning")

        plan = IbkrPaperOrderPlan.from_order_request(order)
        self._journal.append(
            event_type=IBKR_PAPER_ORDER_PLAN_EVENT_TYPE,
            payload=plan.to_json_dict(),
            timestamp=plan.requested_at,
        )
        return plan


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IbkrPaperAdapterError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise IbkrPaperAdapterError(f"{field_name} must not contain leading or trailing whitespace")
    _reject_forbidden_text(value, field_name)
    return value


def _validated_symbol(symbol: str) -> str:
    _validated_identifier(symbol, "symbol")
    if symbol != symbol.upper():
        raise IbkrPaperAdapterError("symbol must be uppercase")
    return symbol


def _positive_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise IbkrPaperAdapterError(f"{field_name} must be a finite number")

    number = float(value)
    if not (number > 0) or number in {float("inf"), float("-inf")}:
        raise IbkrPaperAdapterError(f"{field_name} must be a finite number greater than zero")
    return number


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise IbkrPaperAdapterError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IbkrPaperAdapterError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IbkrPaperAdapterError(f"{field_name} must include a timezone")
    return parsed


def _reject_forbidden_text(value: str, field_name: str) -> None:
    normalized = value.lower()
    if any(marker in normalized for marker in _FORBIDDEN_TEXT_MARKERS):
        raise IbkrPaperAdapterError(f"{field_name} contains credential or transmission text")


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise IbkrPaperAdapterError(f"{payload_name} must be JSON-serializable") from exc
