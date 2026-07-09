from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from trading_oms_backend.config import LOCAL_IBKR_HOSTS, Settings
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.fake_broker import BrokerOrderRequest

IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE = "ibkr.paper.connection_state.recorded"
IBKR_PAPER_CONNECTIVITY_PROBE_EVENT_TYPE = "ibkr.paper.connectivity_probe.recorded"
IBKR_PAPER_CONTRACT_LOOKUP_ATTEMPT_EVENT_TYPE = "ibkr.paper.contract_lookup.attempted"
IBKR_PAPER_CONTRACT_LOOKUP_RESULT_EVENT_TYPE = "ibkr.paper.contract_lookup.recorded"
IBKR_PAPER_ORDER_PLAN_EVENT_TYPE = "ibkr.paper.order_plan.created"
IBKR_PAPER_ORDER_SUBMISSION_ATTEMPT_EVENT_TYPE = "ibkr.paper.order_submission.attempted"
IBKR_PAPER_ORDER_SUBMISSION_RESULT_EVENT_TYPE = "ibkr.paper.order_submission.recorded"
IBKR_PAPER_ORDER_STATUS_CALLBACK_RECEIVED_EVENT_TYPE = "ibkr.paper.order_status_callback.received"
IBKR_PAPER_ORDER_STATUS_CALLBACK_RESULT_EVENT_TYPE = "ibkr.paper.order_status_callback.recorded"
IBKR_PAPER_FILL_CALLBACK_RECEIVED_EVENT_TYPE = "ibkr.paper.fill_callback.received"
IBKR_PAPER_FILL_CALLBACK_RESULT_EVENT_TYPE = "ibkr.paper.fill_callback.recorded"

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
PaperOrderSubmissionStatus = Literal[
    "accepted_paper_submission",
    "duplicate_accepted",
    "blocked_disconnected",
    "blocked_reconciliation_required",
    "blocked_stale_contract",
    "blocked_contract_mismatch",
    "blocked_missing_protection",
    "blocked_duplicate_conflict",
    "unknown_requires_reconciliation",
]
PaperOrderStatusCallbackOutcome = Literal[
    "accepted_status_update",
    "duplicate_status_update",
    "blocked_submission_not_accepted",
    "blocked_disconnected",
    "blocked_reconciliation_required",
    "blocked_correlation_mismatch",
    "blocked_duplicate_conflict",
    "blocked_stale_callback",
    "blocked_out_of_order_callback",
    "blocked_invalid_status",
    "unknown_requires_reconciliation",
]
PaperFillCallbackOutcome = Literal[
    "accepted_fill_update",
    "duplicate_fill_update",
    "blocked_submission_not_accepted",
    "blocked_disconnected",
    "blocked_reconciliation_required",
    "blocked_correlation_mismatch",
    "blocked_duplicate_conflict",
    "blocked_stale_callback",
    "blocked_out_of_order_callback",
    "blocked_invalid_fill",
    "unknown_requires_reconciliation",
]
ConnectivityProbeStatus = Literal[
    "reachable_local_paper_endpoint",
    "unreachable_local_paper_endpoint",
    "unknown_requires_reconciliation",
]
ConnectivityFailureCategory = Literal[
    "connection_refused",
    "timeout",
    "os_error",
    "unexpected_error",
]
EndpointKind = Literal["tws_paper", "gateway_paper"]
ProbeConnector = Callable[[str, int, float], None]
ContractSecurityType = Literal["stock", "option", "future", "forex"]
ContractLookupStatus = Literal[
    "resolved",
    "not_found",
    "ambiguous",
    "unsupported_instrument",
    "blocked_disconnected",
    "blocked_reconciliation_required",
    "stale_result_rejected",
    "unknown_requires_reconciliation",
]
ContractLookupFailureCategory = Literal[
    "not_found",
    "ambiguous",
    "unsupported_instrument",
    "disconnected",
    "reconciliation_required",
    "stale_result",
    "timeout",
    "os_error",
    "unexpected_error",
]
PaperOrderSubmissionFailureCategory = Literal[
    "disconnected",
    "reconciliation_required",
    "stale_contract",
    "contract_mismatch",
    "missing_protection",
    "duplicate_conflict",
    "timeout",
    "os_error",
    "unexpected_error",
]
PaperCallbackFailureCategory = Literal[
    "submission_not_accepted",
    "disconnected",
    "reconciliation_required",
    "correlation_mismatch",
    "duplicate_conflict",
    "stale_callback",
    "out_of_order_callback",
    "invalid_status",
    "invalid_fill",
    "unexpected_error",
]

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


class IbkrPaperContractNotFoundError(IbkrPaperAdapterError):
    """Raised by contract lookup connectors when no matching paper contract exists."""


class IbkrPaperContractAmbiguousError(IbkrPaperAdapterError):
    """Raised by contract lookup connectors when a paper contract lookup is ambiguous."""


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
class IbkrPaperConnectivityProbeResult:
    probe_id: str
    recorded_at: str
    reason: str
    endpoint_kind: EndpointKind
    status: ConnectivityProbeStatus
    connection_state: ConnectionState
    requires_reconciliation: bool
    failure_category: ConnectivityFailureCategory | None
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.probe_id, "probe_id")
        _parse_timestamp(self.recorded_at, "recorded_at")
        _validated_identifier(self.reason, "reason")
        if self.endpoint_kind not in {"tws_paper", "gateway_paper"}:
            raise IbkrPaperAdapterError("endpoint_kind must be tws_paper or gateway_paper")
        if self.status not in {
            "reachable_local_paper_endpoint",
            "unreachable_local_paper_endpoint",
            "unknown_requires_reconciliation",
        }:
            raise IbkrPaperAdapterError("status must be a known connectivity probe status")
        if self.connection_state not in VALID_CONNECTION_STATES:
            raise IbkrPaperAdapterError("connection_state must be a known connection state")

        expected_state: ConnectionState
        expected_reconciliation: bool
        if self.status == "reachable_local_paper_endpoint":
            expected_state = "connected_paper"
            expected_reconciliation = False
            expected_failure_categories: set[ConnectivityFailureCategory | None] = {None}
        elif self.status == "unreachable_local_paper_endpoint":
            expected_state = "disconnected"
            expected_reconciliation = False
            expected_failure_categories = {"connection_refused"}
        else:
            expected_state = "unknown_requires_reconciliation"
            expected_reconciliation = True
            expected_failure_categories = {"timeout", "os_error", "unexpected_error"}

        if self.connection_state != expected_state:
            raise IbkrPaperAdapterError("connection_state must match probe status")
        if self.requires_reconciliation is not expected_reconciliation:
            raise IbkrPaperAdapterError("requires_reconciliation must match probe status")
        if self.failure_category not in expected_failure_categories:
            raise IbkrPaperAdapterError("failure_category must match probe status")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper connectivity probe result")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "probe_id": self.probe_id,
            "recorded_at": self.recorded_at,
            "reason": self.reason,
            "endpoint_kind": self.endpoint_kind,
            "status": self.status,
            "connection_state": self.connection_state,
            "requires_reconciliation": self.requires_reconciliation,
            "failure_category": self.failure_category,
        }


@dataclass(frozen=True)
class IbkrPaperContractLookupRequest:
    lookup_id: str
    requested_at: str
    reason: str
    symbol: str
    security_type: ContractSecurityType
    currency: str
    exchange: str
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.lookup_id, "lookup_id")
        _parse_timestamp(self.requested_at, "requested_at")
        _validated_identifier(self.reason, "reason")
        _validated_symbol(self.symbol)
        if self.security_type not in {"stock", "option", "future", "forex"}:
            raise IbkrPaperAdapterError("security_type must be a known contract security type")
        _validated_currency(self.currency)
        _validated_exchange_token(self.exchange, "exchange")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper contract lookup request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "lookup_id": self.lookup_id,
            "requested_at": self.requested_at,
            "reason": self.reason,
            "symbol": self.symbol,
            "security_type": self.security_type,
            "currency": self.currency,
            "exchange": self.exchange,
        }


@dataclass(frozen=True)
class IbkrPaperResolvedContract:
    contract_id: str
    symbol: str
    security_type: Literal["stock"]
    currency: str
    exchange: str
    primary_exchange: str
    local_symbol: str
    trading_class: str
    min_tick: float
    resolved_at: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        _validated_identifier(self.contract_id, "contract_id")
        _validated_symbol(self.symbol)
        if self.security_type != "stock":
            raise IbkrPaperAdapterError("resolved contract security_type must be stock")
        _validated_currency(self.currency)
        _validated_exchange_token(self.exchange, "exchange")
        _validated_exchange_token(self.primary_exchange, "primary_exchange")
        _validated_identifier(self.local_symbol, "local_symbol")
        _validated_exchange_token(self.trading_class, "trading_class")
        _positive_finite_number(self.min_tick, "min_tick")
        _parse_timestamp(self.resolved_at, "resolved_at")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper resolved contract")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "symbol": self.symbol,
            "security_type": self.security_type,
            "currency": self.currency,
            "exchange": self.exchange,
            "primary_exchange": self.primary_exchange,
            "local_symbol": self.local_symbol,
            "trading_class": self.trading_class,
            "min_tick": self.min_tick,
            "resolved_at": self.resolved_at,
        }


ContractLookupConnector = Callable[
    [IbkrPaperAdapterConfig, IbkrPaperContractLookupRequest, float],
    IbkrPaperResolvedContract,
]


@dataclass(frozen=True)
class IbkrPaperContractLookupResult:
    lookup_id: str
    requested_at: str
    recorded_at: str
    reason: str
    endpoint_kind: EndpointKind
    status: ContractLookupStatus
    requires_reconciliation: bool
    failure_category: ContractLookupFailureCategory | None
    contract: IbkrPaperResolvedContract | None
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.lookup_id, "lookup_id")
        _parse_timestamp(self.requested_at, "requested_at")
        _parse_timestamp(self.recorded_at, "recorded_at")
        _validated_identifier(self.reason, "reason")
        if self.endpoint_kind not in {"tws_paper", "gateway_paper"}:
            raise IbkrPaperAdapterError("endpoint_kind must be tws_paper or gateway_paper")
        if self.status not in {
            "resolved",
            "not_found",
            "ambiguous",
            "unsupported_instrument",
            "blocked_disconnected",
            "blocked_reconciliation_required",
            "stale_result_rejected",
            "unknown_requires_reconciliation",
        }:
            raise IbkrPaperAdapterError("status must be a known contract lookup status")

        expected_failure_categories: set[ContractLookupFailureCategory | None]
        expected_reconciliation: bool
        contract_required = False
        if self.status == "resolved":
            expected_failure_categories = {None}
            expected_reconciliation = False
            contract_required = True
        elif self.status == "not_found":
            expected_failure_categories = {"not_found"}
            expected_reconciliation = False
        elif self.status == "ambiguous":
            expected_failure_categories = {"ambiguous"}
            expected_reconciliation = False
        elif self.status == "unsupported_instrument":
            expected_failure_categories = {"unsupported_instrument"}
            expected_reconciliation = False
        elif self.status == "blocked_disconnected":
            expected_failure_categories = {"disconnected"}
            expected_reconciliation = False
        elif self.status == "blocked_reconciliation_required":
            expected_failure_categories = {"reconciliation_required"}
            expected_reconciliation = True
        elif self.status == "stale_result_rejected":
            expected_failure_categories = {"stale_result"}
            expected_reconciliation = True
        else:
            expected_failure_categories = {"timeout", "os_error", "unexpected_error"}
            expected_reconciliation = True

        if self.requires_reconciliation is not expected_reconciliation:
            raise IbkrPaperAdapterError("requires_reconciliation must match contract lookup status")
        if self.failure_category not in expected_failure_categories:
            raise IbkrPaperAdapterError("failure_category must match contract lookup status")
        if contract_required:
            if not isinstance(self.contract, IbkrPaperResolvedContract):
                raise IbkrPaperAdapterError("resolved contract lookup requires contract metadata")
        elif self.contract is not None:
            raise IbkrPaperAdapterError("contract metadata must be omitted for unresolved lookups")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper contract lookup result")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "lookup_id": self.lookup_id,
            "requested_at": self.requested_at,
            "recorded_at": self.recorded_at,
            "reason": self.reason,
            "endpoint_kind": self.endpoint_kind,
            "status": self.status,
            "requires_reconciliation": self.requires_reconciliation,
            "failure_category": self.failure_category,
            "contract": self.contract.to_json_dict() if self.contract is not None else None,
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


@dataclass(frozen=True)
class IbkrPaperOrderSubmissionRequest:
    submission_id: str
    requested_at: str
    reason: str
    order_plan: IbkrPaperOrderPlan
    contract: IbkrPaperResolvedContract
    oms_transition_reference: str
    idempotency_key: str
    protective_order_plan_reference: str | None
    approved_protective_exception_reference: str | None
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    @property
    def plan_id(self) -> str:
        return self.order_plan.plan_id

    @property
    def client_order_id(self) -> str:
        return self.order_plan.client_order_id

    @property
    def symbol(self) -> str:
        return self.order_plan.symbol

    @property
    def side(self) -> str:
        return self.order_plan.side

    @property
    def quantity(self) -> int:
        return self.order_plan.quantity

    @property
    def order_type(self) -> str:
        return self.order_plan.order_type

    @property
    def risk_decision_id(self) -> str:
        return self.order_plan.risk_decision_id

    @property
    def approval_reference(self) -> str:
        return self.order_plan.approval_reference

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.submission_id, "submission_id")
        _parse_timestamp(self.requested_at, "requested_at")
        _validated_identifier(self.reason, "reason")
        if not isinstance(self.order_plan, IbkrPaperOrderPlan):
            raise IbkrPaperAdapterError("order_plan must be an IbkrPaperOrderPlan")
        if not isinstance(self.contract, IbkrPaperResolvedContract):
            raise IbkrPaperAdapterError("contract must be an IbkrPaperResolvedContract")
        _validated_identifier(self.oms_transition_reference, "oms_transition_reference")
        _validated_identifier(self.idempotency_key, "idempotency_key")
        if self.protective_order_plan_reference is not None:
            _validated_identifier(
                self.protective_order_plan_reference,
                "protective_order_plan_reference",
            )
        if self.approved_protective_exception_reference is not None:
            _validated_identifier(
                self.approved_protective_exception_reference,
                "approved_protective_exception_reference",
            )
        _assert_json_serializable(self.to_json_dict(), "IBKR paper order submission request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "submission_id": self.submission_id,
            "requested_at": self.requested_at,
            "reason": self.reason,
            "order_plan": self.order_plan.to_json_dict(),
            "contract": self.contract.to_json_dict(),
            "oms_transition_reference": self.oms_transition_reference,
            "idempotency_key": self.idempotency_key,
            "protective_order_plan_reference": self.protective_order_plan_reference,
            "approved_protective_exception_reference": (
                self.approved_protective_exception_reference
            ),
        }


@dataclass(frozen=True)
class IbkrPaperOrderSubmissionRecord:
    submission_id: str
    requested_at: str
    recorded_at: str
    reason: str
    endpoint_kind: EndpointKind
    status: PaperOrderSubmissionStatus
    requires_reconciliation: bool
    failure_category: PaperOrderSubmissionFailureCategory | None
    plan_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    idempotency_key: str
    risk_decision_id: str
    approval_reference: str
    oms_transition_reference: str
    contract_id: str
    protective_order_plan_reference: str | None
    approved_protective_exception_reference: str | None
    local_acknowledgement_reference: str | None
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.submission_id, "submission_id")
        _parse_timestamp(self.requested_at, "requested_at")
        _parse_timestamp(self.recorded_at, "recorded_at")
        _validated_identifier(self.reason, "reason")
        if self.endpoint_kind not in {"tws_paper", "gateway_paper"}:
            raise IbkrPaperAdapterError("endpoint_kind must be tws_paper or gateway_paper")
        if self.status not in {
            "accepted_paper_submission",
            "duplicate_accepted",
            "blocked_disconnected",
            "blocked_reconciliation_required",
            "blocked_stale_contract",
            "blocked_contract_mismatch",
            "blocked_missing_protection",
            "blocked_duplicate_conflict",
            "unknown_requires_reconciliation",
        }:
            raise IbkrPaperAdapterError("status must be a known paper submission status")
        _validated_identifier(self.plan_id, "plan_id")
        _validated_identifier(self.client_order_id, "client_order_id")
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
        _validated_identifier(self.idempotency_key, "idempotency_key")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        _validated_identifier(self.approval_reference, "approval_reference")
        _validated_identifier(self.oms_transition_reference, "oms_transition_reference")
        _validated_identifier(self.contract_id, "contract_id")
        if self.protective_order_plan_reference is not None:
            _validated_identifier(
                self.protective_order_plan_reference,
                "protective_order_plan_reference",
            )
        if self.approved_protective_exception_reference is not None:
            _validated_identifier(
                self.approved_protective_exception_reference,
                "approved_protective_exception_reference",
            )
        if self.local_acknowledgement_reference is not None:
            _validated_identifier(
                self.local_acknowledgement_reference,
                "local_acknowledgement_reference",
            )

        expected_failure_categories: set[PaperOrderSubmissionFailureCategory | None]
        expected_reconciliation: bool
        acknowledgement_required = False
        if self.status in {"accepted_paper_submission", "duplicate_accepted"}:
            expected_failure_categories = {None}
            expected_reconciliation = False
            acknowledgement_required = True
        elif self.status == "blocked_disconnected":
            expected_failure_categories = {"disconnected"}
            expected_reconciliation = False
        elif self.status == "blocked_reconciliation_required":
            expected_failure_categories = {"reconciliation_required"}
            expected_reconciliation = True
        elif self.status == "blocked_stale_contract":
            expected_failure_categories = {"stale_contract"}
            expected_reconciliation = True
        elif self.status == "blocked_contract_mismatch":
            expected_failure_categories = {"contract_mismatch"}
            expected_reconciliation = False
        elif self.status == "blocked_missing_protection":
            expected_failure_categories = {"missing_protection"}
            expected_reconciliation = False
        elif self.status == "blocked_duplicate_conflict":
            expected_failure_categories = {"duplicate_conflict"}
            expected_reconciliation = False
        else:
            expected_failure_categories = {"timeout", "os_error", "unexpected_error"}
            expected_reconciliation = True

        if self.requires_reconciliation is not expected_reconciliation:
            raise IbkrPaperAdapterError("requires_reconciliation must match submission status")
        if self.failure_category not in expected_failure_categories:
            raise IbkrPaperAdapterError("failure_category must match submission status")
        if acknowledgement_required:
            if self.local_acknowledgement_reference is None:
                raise IbkrPaperAdapterError(
                    "accepted paper submissions require local acknowledgement"
                )
        elif self.local_acknowledgement_reference is not None:
            raise IbkrPaperAdapterError("blocked submissions must omit local acknowledgement")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper order submission record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "submission_id": self.submission_id,
            "requested_at": self.requested_at,
            "recorded_at": self.recorded_at,
            "reason": self.reason,
            "endpoint_kind": self.endpoint_kind,
            "status": self.status,
            "requires_reconciliation": self.requires_reconciliation,
            "failure_category": self.failure_category,
            "plan_id": self.plan_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "idempotency_key": self.idempotency_key,
            "risk_decision_id": self.risk_decision_id,
            "approval_reference": self.approval_reference,
            "oms_transition_reference": self.oms_transition_reference,
            "contract_id": self.contract_id,
            "protective_order_plan_reference": self.protective_order_plan_reference,
            "approved_protective_exception_reference": (
                self.approved_protective_exception_reference
            ),
            "local_acknowledgement_reference": self.local_acknowledgement_reference,
        }


@dataclass(frozen=True)
class IbkrPaperOrderStatusCallback:
    callback_id: str
    observed_at: str
    received_at: str
    reason: str
    client_order_id: str
    correlation_reference: str
    paper_status: str
    cumulative_filled_quantity: int
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.callback_id, "callback_id")
        _parse_timestamp(self.observed_at, "observed_at")
        _parse_timestamp(self.received_at, "received_at")
        _validated_identifier(self.reason, "reason")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_identifier(self.correlation_reference, "correlation_reference")
        _validated_identifier(self.paper_status, "paper_status")
        _validated_nonnegative_integer(
            self.cumulative_filled_quantity,
            "cumulative_filled_quantity",
        )
        _assert_json_serializable(self.to_json_dict(), "IBKR paper status callback")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "callback_id": self.callback_id,
            "observed_at": self.observed_at,
            "received_at": self.received_at,
            "reason": self.reason,
            "client_order_id": self.client_order_id,
            "correlation_reference": self.correlation_reference,
            "paper_status": self.paper_status,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
        }


@dataclass(frozen=True)
class IbkrPaperOrderStatusCallbackRecord:
    callback_id: str
    observed_at: str
    received_at: str
    recorded_at: str
    reason: str
    endpoint_kind: EndpointKind
    status: PaperOrderStatusCallbackOutcome
    requires_reconciliation: bool
    failure_category: PaperCallbackFailureCategory | None
    submission_id: str
    client_order_id: str
    correlation_reference: str
    paper_status: str
    cumulative_filled_quantity: int
    oms_target_state: str | None
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.callback_id, "callback_id")
        _parse_timestamp(self.observed_at, "observed_at")
        _parse_timestamp(self.received_at, "received_at")
        _parse_timestamp(self.recorded_at, "recorded_at")
        _validated_identifier(self.reason, "reason")
        if self.endpoint_kind not in {"tws_paper", "gateway_paper"}:
            raise IbkrPaperAdapterError("endpoint_kind must be tws_paper or gateway_paper")
        if self.status not in {
            "accepted_status_update",
            "duplicate_status_update",
            "blocked_submission_not_accepted",
            "blocked_disconnected",
            "blocked_reconciliation_required",
            "blocked_correlation_mismatch",
            "blocked_duplicate_conflict",
            "blocked_stale_callback",
            "blocked_out_of_order_callback",
            "blocked_invalid_status",
            "unknown_requires_reconciliation",
        }:
            raise IbkrPaperAdapterError("status must be a known paper status callback outcome")
        _validated_identifier(self.submission_id, "submission_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_identifier(self.correlation_reference, "correlation_reference")
        _validated_identifier(self.paper_status, "paper_status")
        _validated_nonnegative_integer(
            self.cumulative_filled_quantity,
            "cumulative_filled_quantity",
        )
        if self.oms_target_state is not None:
            _validated_identifier(self.oms_target_state, "oms_target_state")

        expected_failure_categories: set[PaperCallbackFailureCategory | None]
        if self.status in {"accepted_status_update", "duplicate_status_update"}:
            expected_failure_categories = {None}
            expected_reconciliation = False
            target_required = True
        elif self.status == "blocked_submission_not_accepted":
            expected_failure_categories = {"submission_not_accepted"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_disconnected":
            expected_failure_categories = {"disconnected"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_reconciliation_required":
            expected_failure_categories = {"reconciliation_required"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_correlation_mismatch":
            expected_failure_categories = {"correlation_mismatch"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_duplicate_conflict":
            expected_failure_categories = {"duplicate_conflict"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_stale_callback":
            expected_failure_categories = {"stale_callback"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_out_of_order_callback":
            expected_failure_categories = {"out_of_order_callback"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_invalid_status":
            expected_failure_categories = {"invalid_status"}
            expected_reconciliation = True
            target_required = False
        else:
            expected_failure_categories = {"unexpected_error"}
            expected_reconciliation = True
            target_required = False

        if self.requires_reconciliation is not expected_reconciliation:
            raise IbkrPaperAdapterError("requires_reconciliation must match callback outcome")
        if self.failure_category not in expected_failure_categories:
            raise IbkrPaperAdapterError("failure_category must match callback outcome")
        if target_required and self.oms_target_state is None:
            raise IbkrPaperAdapterError("accepted callbacks require oms_target_state")
        if not target_required and self.oms_target_state is not None:
            raise IbkrPaperAdapterError("blocked callbacks must omit oms_target_state")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper status callback record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "callback_id": self.callback_id,
            "observed_at": self.observed_at,
            "received_at": self.received_at,
            "recorded_at": self.recorded_at,
            "reason": self.reason,
            "endpoint_kind": self.endpoint_kind,
            "status": self.status,
            "requires_reconciliation": self.requires_reconciliation,
            "failure_category": self.failure_category,
            "submission_id": self.submission_id,
            "client_order_id": self.client_order_id,
            "correlation_reference": self.correlation_reference,
            "paper_status": self.paper_status,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "oms_target_state": self.oms_target_state,
        }


@dataclass(frozen=True)
class IbkrPaperFillCallback:
    callback_id: str
    observed_at: str
    received_at: str
    reason: str
    client_order_id: str
    correlation_reference: str
    fill_quantity: int
    cumulative_filled_quantity: int
    fill_price: float
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.callback_id, "callback_id")
        _parse_timestamp(self.observed_at, "observed_at")
        _parse_timestamp(self.received_at, "received_at")
        _validated_identifier(self.reason, "reason")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_identifier(self.correlation_reference, "correlation_reference")
        _validated_nonnegative_integer(self.fill_quantity, "fill_quantity")
        _validated_nonnegative_integer(
            self.cumulative_filled_quantity,
            "cumulative_filled_quantity",
        )
        _positive_finite_number(self.fill_price, "fill_price")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper fill callback")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "callback_id": self.callback_id,
            "observed_at": self.observed_at,
            "received_at": self.received_at,
            "reason": self.reason,
            "client_order_id": self.client_order_id,
            "correlation_reference": self.correlation_reference,
            "fill_quantity": self.fill_quantity,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "fill_price": self.fill_price,
        }


@dataclass(frozen=True)
class IbkrPaperFillCallbackRecord:
    callback_id: str
    observed_at: str
    received_at: str
    recorded_at: str
    reason: str
    endpoint_kind: EndpointKind
    status: PaperFillCallbackOutcome
    requires_reconciliation: bool
    failure_category: PaperCallbackFailureCategory | None
    submission_id: str
    client_order_id: str
    correlation_reference: str
    fill_quantity: int
    cumulative_filled_quantity: int
    leaves_quantity: int
    fill_price: float
    oms_target_state: str | None
    adapter_name: str = IBKR_PAPER_ADAPTER_NAME
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise IbkrPaperAdapterError("schema_version must be 1")
        if self.adapter_name != IBKR_PAPER_ADAPTER_NAME:
            raise IbkrPaperAdapterError("adapter_name must be ibkr_paper")
        _validated_identifier(self.callback_id, "callback_id")
        _parse_timestamp(self.observed_at, "observed_at")
        _parse_timestamp(self.received_at, "received_at")
        _parse_timestamp(self.recorded_at, "recorded_at")
        _validated_identifier(self.reason, "reason")
        if self.endpoint_kind not in {"tws_paper", "gateway_paper"}:
            raise IbkrPaperAdapterError("endpoint_kind must be tws_paper or gateway_paper")
        if self.status not in {
            "accepted_fill_update",
            "duplicate_fill_update",
            "blocked_submission_not_accepted",
            "blocked_disconnected",
            "blocked_reconciliation_required",
            "blocked_correlation_mismatch",
            "blocked_duplicate_conflict",
            "blocked_stale_callback",
            "blocked_out_of_order_callback",
            "blocked_invalid_fill",
            "unknown_requires_reconciliation",
        }:
            raise IbkrPaperAdapterError("status must be a known paper fill callback outcome")
        _validated_identifier(self.submission_id, "submission_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_identifier(self.correlation_reference, "correlation_reference")
        _validated_nonnegative_integer(self.fill_quantity, "fill_quantity")
        _validated_nonnegative_integer(
            self.cumulative_filled_quantity,
            "cumulative_filled_quantity",
        )
        _validated_nonnegative_integer(self.leaves_quantity, "leaves_quantity")
        _positive_finite_number(self.fill_price, "fill_price")
        if self.oms_target_state is not None:
            _validated_identifier(self.oms_target_state, "oms_target_state")

        expected_failure_categories: set[PaperCallbackFailureCategory | None]
        if self.status in {"accepted_fill_update", "duplicate_fill_update"}:
            expected_failure_categories = {None}
            expected_reconciliation = False
            target_required = True
        elif self.status == "blocked_submission_not_accepted":
            expected_failure_categories = {"submission_not_accepted"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_disconnected":
            expected_failure_categories = {"disconnected"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_reconciliation_required":
            expected_failure_categories = {"reconciliation_required"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_correlation_mismatch":
            expected_failure_categories = {"correlation_mismatch"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_duplicate_conflict":
            expected_failure_categories = {"duplicate_conflict"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_stale_callback":
            expected_failure_categories = {"stale_callback"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_out_of_order_callback":
            expected_failure_categories = {"out_of_order_callback"}
            expected_reconciliation = True
            target_required = False
        elif self.status == "blocked_invalid_fill":
            expected_failure_categories = {"invalid_fill"}
            expected_reconciliation = True
            target_required = False
        else:
            expected_failure_categories = {"unexpected_error"}
            expected_reconciliation = True
            target_required = False

        if self.requires_reconciliation is not expected_reconciliation:
            raise IbkrPaperAdapterError("requires_reconciliation must match callback outcome")
        if self.failure_category not in expected_failure_categories:
            raise IbkrPaperAdapterError("failure_category must match callback outcome")
        if target_required and self.oms_target_state is None:
            raise IbkrPaperAdapterError("accepted callbacks require oms_target_state")
        if not target_required and self.oms_target_state is not None:
            raise IbkrPaperAdapterError("blocked callbacks must omit oms_target_state")
        _assert_json_serializable(self.to_json_dict(), "IBKR paper fill callback record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "callback_id": self.callback_id,
            "observed_at": self.observed_at,
            "received_at": self.received_at,
            "recorded_at": self.recorded_at,
            "reason": self.reason,
            "endpoint_kind": self.endpoint_kind,
            "status": self.status,
            "requires_reconciliation": self.requires_reconciliation,
            "failure_category": self.failure_category,
            "submission_id": self.submission_id,
            "client_order_id": self.client_order_id,
            "correlation_reference": self.correlation_reference,
            "fill_quantity": self.fill_quantity,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "leaves_quantity": self.leaves_quantity,
            "fill_price": self.fill_price,
            "oms_target_state": self.oms_target_state,
        }


PaperOrderSubmissionConnector = Callable[
    [IbkrPaperAdapterConfig, IbkrPaperOrderSubmissionRequest, float],
    None,
]


class IbkrPaperAdapter:
    """Local IBKR paper adapter boundary.

    This class intentionally records local paper adapter state, plans, paper submission outcomes,
    and deterministic paper status/fill callback observations. It does not import a broker SDK,
    authenticate to IBKR, or register network callback listeners.
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
        self._paper_submission_payloads_by_idempotency: dict[str, str] = {}
        self._paper_submission_records_by_idempotency: dict[
            str,
            IbkrPaperOrderSubmissionRecord,
        ] = {}
        self._paper_status_callback_payloads_by_id: dict[str, str] = {}
        self._paper_status_callback_records_by_id: dict[
            str,
            IbkrPaperOrderStatusCallbackRecord,
        ] = {}
        self._paper_fill_callback_payloads_by_id: dict[str, str] = {}
        self._paper_fill_callback_records_by_id: dict[
            str,
            IbkrPaperFillCallbackRecord,
        ] = {}
        self._paper_callback_observed_at_by_client_order_id: dict[str, datetime] = {}
        self._paper_callback_cumulative_by_client_order_id: dict[str, int] = {}

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

    def probe_local_connectivity(
        self,
        *,
        probe_id: str,
        recorded_at: str,
        reason: str,
        timeout_seconds: float = 1.0,
        connector: ProbeConnector | None = None,
    ) -> IbkrPaperConnectivityProbeResult:
        _validated_identifier(probe_id, "probe_id")
        _parse_timestamp(recorded_at, "recorded_at")
        _validated_identifier(reason, "reason")
        timeout = _validated_timeout_seconds(timeout_seconds)
        if connector is not None and not callable(connector):
            raise IbkrPaperAdapterError("connector must be callable")

        probe_connector = connector or _probe_local_tcp_endpoint
        try:
            probe_connector(self._config.host, self._config.port, timeout)
        except ConnectionRefusedError:
            result = IbkrPaperConnectivityProbeResult(
                probe_id=probe_id,
                recorded_at=recorded_at,
                reason=reason,
                endpoint_kind=_endpoint_kind_for_port(self._config.port),
                status="unreachable_local_paper_endpoint",
                connection_state="disconnected",
                requires_reconciliation=False,
                failure_category="connection_refused",
            )
        except TimeoutError:
            result = IbkrPaperConnectivityProbeResult(
                probe_id=probe_id,
                recorded_at=recorded_at,
                reason=reason,
                endpoint_kind=_endpoint_kind_for_port(self._config.port),
                status="unknown_requires_reconciliation",
                connection_state="unknown_requires_reconciliation",
                requires_reconciliation=True,
                failure_category="timeout",
            )
        except OSError:
            result = IbkrPaperConnectivityProbeResult(
                probe_id=probe_id,
                recorded_at=recorded_at,
                reason=reason,
                endpoint_kind=_endpoint_kind_for_port(self._config.port),
                status="unknown_requires_reconciliation",
                connection_state="unknown_requires_reconciliation",
                requires_reconciliation=True,
                failure_category="os_error",
            )
        except Exception:
            result = IbkrPaperConnectivityProbeResult(
                probe_id=probe_id,
                recorded_at=recorded_at,
                reason=reason,
                endpoint_kind=_endpoint_kind_for_port(self._config.port),
                status="unknown_requires_reconciliation",
                connection_state="unknown_requires_reconciliation",
                requires_reconciliation=True,
                failure_category="unexpected_error",
            )
        else:
            result = IbkrPaperConnectivityProbeResult(
                probe_id=probe_id,
                recorded_at=recorded_at,
                reason=reason,
                endpoint_kind=_endpoint_kind_for_port(self._config.port),
                status="reachable_local_paper_endpoint",
                connection_state="connected_paper",
                requires_reconciliation=False,
                failure_category=None,
            )

        self._journal.append(
            event_type=IBKR_PAPER_CONNECTIVITY_PROBE_EVENT_TYPE,
            payload=result.to_json_dict(),
            timestamp=result.recorded_at,
        )
        self.record_connection_state(
            result.connection_state,
            recorded_at=result.recorded_at,
            reason=f"connectivity_probe_{result.status}",
        )
        return result

    def lookup_contract(
        self,
        request: IbkrPaperContractLookupRequest,
        *,
        recorded_at: str,
        connector: ContractLookupConnector | None = None,
        timeout_seconds: float = 1.0,
        max_result_age_seconds: float = 300.0,
    ) -> IbkrPaperContractLookupResult:
        if not isinstance(request, IbkrPaperContractLookupRequest):
            raise IbkrPaperAdapterError("request must be an IbkrPaperContractLookupRequest")
        _parse_timestamp(recorded_at, "recorded_at")
        timeout = _validated_timeout_seconds(timeout_seconds)
        max_result_age = _validated_max_result_age_seconds(max_result_age_seconds)
        if connector is not None and not callable(connector):
            raise IbkrPaperAdapterError("connector must be callable")

        endpoint_kind = _endpoint_kind_for_port(self._config.port)
        self._journal.append(
            event_type=IBKR_PAPER_CONTRACT_LOOKUP_ATTEMPT_EVENT_TYPE,
            payload=request.to_json_dict() | {"endpoint_kind": endpoint_kind},
            timestamp=request.requested_at,
        )

        result: IbkrPaperContractLookupResult
        if self._requires_reconciliation:
            result = _contract_lookup_result(
                request,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_reconciliation_required",
                failure_category="reconciliation_required",
            )
        elif self._connection_state != "connected_paper":
            result = _contract_lookup_result(
                request,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_disconnected",
                failure_category="disconnected",
            )
        elif request.security_type != "stock":
            result = _contract_lookup_result(
                request,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="unsupported_instrument",
                failure_category="unsupported_instrument",
            )
        else:
            lookup_connector = connector or _paper_contract_lookup_connector_unavailable
            try:
                contract = lookup_connector(self._config, request, timeout)
                if not isinstance(contract, IbkrPaperResolvedContract):
                    raise IbkrPaperAdapterError(
                        "contract lookup connector must return IbkrPaperResolvedContract"
                    )
                if _contract_metadata_is_stale(
                    contract,
                    recorded_at=recorded_at,
                    max_result_age_seconds=max_result_age,
                ):
                    result = _contract_lookup_result(
                        request,
                        recorded_at=recorded_at,
                        endpoint_kind=endpoint_kind,
                        status="stale_result_rejected",
                        failure_category="stale_result",
                    )
                else:
                    result = _contract_lookup_result(
                        request,
                        recorded_at=recorded_at,
                        endpoint_kind=endpoint_kind,
                        status="resolved",
                        failure_category=None,
                        contract=contract,
                    )
            except IbkrPaperContractNotFoundError:
                result = _contract_lookup_result(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="not_found",
                    failure_category="not_found",
                )
            except IbkrPaperContractAmbiguousError:
                result = _contract_lookup_result(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="ambiguous",
                    failure_category="ambiguous",
                )
            except TimeoutError:
                result = _contract_lookup_result(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="unknown_requires_reconciliation",
                    failure_category="timeout",
                )
            except OSError:
                result = _contract_lookup_result(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="unknown_requires_reconciliation",
                    failure_category="os_error",
                )
            except Exception:
                result = _contract_lookup_result(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="unknown_requires_reconciliation",
                    failure_category="unexpected_error",
                )

        self._journal.append(
            event_type=IBKR_PAPER_CONTRACT_LOOKUP_RESULT_EVENT_TYPE,
            payload=result.to_json_dict(),
            timestamp=result.recorded_at,
        )
        if (
            result.requires_reconciliation
            and self._connection_state != "unknown_requires_reconciliation"
        ):
            self.record_connection_state(
                "unknown_requires_reconciliation",
                recorded_at=result.recorded_at,
                reason=f"contract_lookup_{result.status}",
            )
        return result

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

    def record_paper_order_submission(
        self,
        request: IbkrPaperOrderSubmissionRequest,
        *,
        recorded_at: str,
        connector: PaperOrderSubmissionConnector | None = None,
        timeout_seconds: float = 1.0,
        max_contract_age_seconds: float = 300.0,
    ) -> IbkrPaperOrderSubmissionRecord:
        if not isinstance(request, IbkrPaperOrderSubmissionRequest):
            raise IbkrPaperAdapterError("request must be an IbkrPaperOrderSubmissionRequest")
        _parse_timestamp(recorded_at, "recorded_at")
        timeout = _validated_timeout_seconds(timeout_seconds)
        max_contract_age = _validated_max_result_age_seconds(max_contract_age_seconds)
        if connector is not None and not callable(connector):
            raise IbkrPaperAdapterError("connector must be callable")

        endpoint_kind = _endpoint_kind_for_port(self._config.port)
        self._journal.append(
            event_type=IBKR_PAPER_ORDER_SUBMISSION_ATTEMPT_EVENT_TYPE,
            payload=request.to_json_dict() | {"endpoint_kind": endpoint_kind},
            timestamp=request.requested_at,
        )

        canonical_payload = _canonical_submission_payload(request)
        existing_payload = self._paper_submission_payloads_by_idempotency.get(
            request.idempotency_key
        )
        if existing_payload is not None:
            if existing_payload == canonical_payload:
                previous_record = self._paper_submission_records_by_idempotency[
                    request.idempotency_key
                ]
                result = _paper_order_submission_record(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="duplicate_accepted",
                    failure_category=None,
                    local_acknowledgement_reference=(
                        previous_record.local_acknowledgement_reference
                    ),
                )
            else:
                result = _paper_order_submission_record(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="blocked_duplicate_conflict",
                    failure_category="duplicate_conflict",
                )
        elif self._requires_reconciliation:
            result = _paper_order_submission_record(
                request,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_reconciliation_required",
                failure_category="reconciliation_required",
            )
        elif self._connection_state != "connected_paper":
            result = _paper_order_submission_record(
                request,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_disconnected",
                failure_category="disconnected",
            )
        elif not _paper_submission_contract_matches_order_plan(request):
            result = _paper_order_submission_record(
                request,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_contract_mismatch",
                failure_category="contract_mismatch",
            )
        elif _contract_metadata_is_stale(
            request.contract,
            recorded_at=recorded_at,
            max_result_age_seconds=max_contract_age,
        ):
            result = _paper_order_submission_record(
                request,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_stale_contract",
                failure_category="stale_contract",
            )
        elif _paper_submission_missing_required_protection(request):
            result = _paper_order_submission_record(
                request,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_missing_protection",
                failure_category="missing_protection",
            )
        else:
            submission_connector = connector or _paper_order_submission_connector_unavailable
            try:
                submission_connector(self._config, request, timeout)
            except TimeoutError:
                result = _paper_order_submission_record(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="unknown_requires_reconciliation",
                    failure_category="timeout",
                )
            except OSError:
                result = _paper_order_submission_record(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="unknown_requires_reconciliation",
                    failure_category="os_error",
                )
            except Exception:
                result = _paper_order_submission_record(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="unknown_requires_reconciliation",
                    failure_category="unexpected_error",
                )
            else:
                result = _paper_order_submission_record(
                    request,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="accepted_paper_submission",
                    failure_category=None,
                    local_acknowledgement_reference=(
                        _local_acknowledgement_reference(request.idempotency_key)
                    ),
                )
                self._paper_submission_payloads_by_idempotency[request.idempotency_key] = (
                    canonical_payload
                )
                self._paper_submission_records_by_idempotency[request.idempotency_key] = result

        self._journal.append(
            event_type=IBKR_PAPER_ORDER_SUBMISSION_RESULT_EVENT_TYPE,
            payload=result.to_json_dict(),
            timestamp=result.recorded_at,
        )
        if (
            result.requires_reconciliation
            and self._connection_state != "unknown_requires_reconciliation"
        ):
            self.record_connection_state(
                "unknown_requires_reconciliation",
                recorded_at=result.recorded_at,
                reason=f"paper_submission_{result.status}",
            )
        return result

    def record_paper_order_status_callback(
        self,
        callback: IbkrPaperOrderStatusCallback,
        *,
        submission: IbkrPaperOrderSubmissionRecord,
        recorded_at: str,
        max_callback_age_seconds: float = 300.0,
    ) -> IbkrPaperOrderStatusCallbackRecord:
        if not isinstance(callback, IbkrPaperOrderStatusCallback):
            raise IbkrPaperAdapterError("callback must be an IbkrPaperOrderStatusCallback")
        if not isinstance(submission, IbkrPaperOrderSubmissionRecord):
            raise IbkrPaperAdapterError("submission must be an IbkrPaperOrderSubmissionRecord")
        _parse_timestamp(recorded_at, "recorded_at")
        max_callback_age = _validated_max_result_age_seconds(max_callback_age_seconds)

        endpoint_kind = _endpoint_kind_for_port(self._config.port)
        self._journal.append(
            event_type=IBKR_PAPER_ORDER_STATUS_CALLBACK_RECEIVED_EVENT_TYPE,
            payload=callback.to_json_dict() | {"endpoint_kind": endpoint_kind},
            timestamp=callback.received_at,
        )

        canonical_payload = _canonical_status_callback_payload(callback)
        existing_payload = self._paper_status_callback_payloads_by_id.get(callback.callback_id)
        if existing_payload is not None:
            if existing_payload == canonical_payload:
                previous_record = self._paper_status_callback_records_by_id[callback.callback_id]
                result = _paper_order_status_callback_record(
                    callback,
                    submission=submission,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="duplicate_status_update",
                    failure_category=None,
                    oms_target_state=previous_record.oms_target_state,
                )
            else:
                result = _paper_order_status_callback_record(
                    callback,
                    submission=submission,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="blocked_duplicate_conflict",
                    failure_category="duplicate_conflict",
                )
        elif self._requires_reconciliation:
            result = _paper_order_status_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_reconciliation_required",
                failure_category="reconciliation_required",
            )
        elif self._connection_state != "connected_paper":
            result = _paper_order_status_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_disconnected",
                failure_category="disconnected",
            )
        elif not _submission_is_accepted_for_callbacks(submission):
            result = _paper_order_status_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_submission_not_accepted",
                failure_category="submission_not_accepted",
            )
        elif not _callback_matches_submission(callback, submission):
            result = _paper_order_status_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_correlation_mismatch",
                failure_category="correlation_mismatch",
            )
        elif _callback_is_stale(
            callback.observed_at,
            recorded_at=recorded_at,
            max_callback_age_seconds=max_callback_age,
        ):
            result = _paper_order_status_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_stale_callback",
                failure_category="stale_callback",
            )
        elif self._callback_is_out_of_order(callback.client_order_id, callback.observed_at):
            result = _paper_order_status_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_out_of_order_callback",
                failure_category="out_of_order_callback",
            )
        else:
            target_state = _status_callback_oms_target_state(callback, submission)
            if target_state is None:
                result = _paper_order_status_callback_record(
                    callback,
                    submission=submission,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="blocked_invalid_status",
                    failure_category="invalid_status",
                )
            else:
                result = _paper_order_status_callback_record(
                    callback,
                    submission=submission,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="accepted_status_update",
                    failure_category=None,
                    oms_target_state=target_state,
                )
                self._paper_status_callback_payloads_by_id[callback.callback_id] = canonical_payload
                self._paper_status_callback_records_by_id[callback.callback_id] = result
                self._remember_callback_progress(
                    callback.client_order_id,
                    observed_at=callback.observed_at,
                    cumulative_filled_quantity=callback.cumulative_filled_quantity,
                )

        self._journal.append(
            event_type=IBKR_PAPER_ORDER_STATUS_CALLBACK_RESULT_EVENT_TYPE,
            payload=result.to_json_dict(),
            timestamp=result.recorded_at,
        )
        self._mark_unknown_if_callback_requires_reconciliation(result)
        return result

    def record_paper_fill_callback(
        self,
        callback: IbkrPaperFillCallback,
        *,
        submission: IbkrPaperOrderSubmissionRecord,
        recorded_at: str,
        max_callback_age_seconds: float = 300.0,
    ) -> IbkrPaperFillCallbackRecord:
        if not isinstance(callback, IbkrPaperFillCallback):
            raise IbkrPaperAdapterError("callback must be an IbkrPaperFillCallback")
        if not isinstance(submission, IbkrPaperOrderSubmissionRecord):
            raise IbkrPaperAdapterError("submission must be an IbkrPaperOrderSubmissionRecord")
        _parse_timestamp(recorded_at, "recorded_at")
        max_callback_age = _validated_max_result_age_seconds(max_callback_age_seconds)

        endpoint_kind = _endpoint_kind_for_port(self._config.port)
        self._journal.append(
            event_type=IBKR_PAPER_FILL_CALLBACK_RECEIVED_EVENT_TYPE,
            payload=callback.to_json_dict() | {"endpoint_kind": endpoint_kind},
            timestamp=callback.received_at,
        )

        canonical_payload = _canonical_fill_callback_payload(callback)
        existing_payload = self._paper_fill_callback_payloads_by_id.get(callback.callback_id)
        if existing_payload is not None:
            if existing_payload == canonical_payload:
                previous_record = self._paper_fill_callback_records_by_id[callback.callback_id]
                result = _paper_fill_callback_record(
                    callback,
                    submission=submission,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="duplicate_fill_update",
                    failure_category=None,
                    leaves_quantity=previous_record.leaves_quantity,
                    oms_target_state=previous_record.oms_target_state,
                )
            else:
                result = _paper_fill_callback_record(
                    callback,
                    submission=submission,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="blocked_duplicate_conflict",
                    failure_category="duplicate_conflict",
                )
        elif self._requires_reconciliation:
            result = _paper_fill_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_reconciliation_required",
                failure_category="reconciliation_required",
            )
        elif self._connection_state != "connected_paper":
            result = _paper_fill_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_disconnected",
                failure_category="disconnected",
            )
        elif not _submission_is_accepted_for_callbacks(submission):
            result = _paper_fill_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_submission_not_accepted",
                failure_category="submission_not_accepted",
            )
        elif not _callback_matches_submission(callback, submission):
            result = _paper_fill_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_correlation_mismatch",
                failure_category="correlation_mismatch",
            )
        elif _callback_is_stale(
            callback.observed_at,
            recorded_at=recorded_at,
            max_callback_age_seconds=max_callback_age,
        ):
            result = _paper_fill_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_stale_callback",
                failure_category="stale_callback",
            )
        elif self._callback_is_out_of_order(callback.client_order_id, callback.observed_at):
            result = _paper_fill_callback_record(
                callback,
                submission=submission,
                recorded_at=recorded_at,
                endpoint_kind=endpoint_kind,
                status="blocked_out_of_order_callback",
                failure_category="out_of_order_callback",
            )
        else:
            target_state = _fill_callback_oms_target_state(callback, submission)
            if target_state is None or not self._fill_callback_increases_cumulative(callback):
                result = _paper_fill_callback_record(
                    callback,
                    submission=submission,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="blocked_invalid_fill",
                    failure_category="invalid_fill",
                )
            else:
                leaves_quantity = submission.quantity - callback.cumulative_filled_quantity
                result = _paper_fill_callback_record(
                    callback,
                    submission=submission,
                    recorded_at=recorded_at,
                    endpoint_kind=endpoint_kind,
                    status="accepted_fill_update",
                    failure_category=None,
                    leaves_quantity=leaves_quantity,
                    oms_target_state=target_state,
                )
                self._paper_fill_callback_payloads_by_id[callback.callback_id] = canonical_payload
                self._paper_fill_callback_records_by_id[callback.callback_id] = result
                self._remember_callback_progress(
                    callback.client_order_id,
                    observed_at=callback.observed_at,
                    cumulative_filled_quantity=callback.cumulative_filled_quantity,
                )

        self._journal.append(
            event_type=IBKR_PAPER_FILL_CALLBACK_RESULT_EVENT_TYPE,
            payload=result.to_json_dict(),
            timestamp=result.recorded_at,
        )
        self._mark_unknown_if_callback_requires_reconciliation(result)
        return result

    def _callback_is_out_of_order(self, client_order_id: str, observed_at: str) -> bool:
        observed = _parse_timestamp(observed_at, "observed_at")
        previous_observed = self._paper_callback_observed_at_by_client_order_id.get(client_order_id)
        return previous_observed is not None and observed < previous_observed

    def _fill_callback_increases_cumulative(self, callback: IbkrPaperFillCallback) -> bool:
        previous_cumulative = self._paper_callback_cumulative_by_client_order_id.get(
            callback.client_order_id,
            0,
        )
        return callback.cumulative_filled_quantity > previous_cumulative

    def _remember_callback_progress(
        self,
        client_order_id: str,
        *,
        observed_at: str,
        cumulative_filled_quantity: int,
    ) -> None:
        self._paper_callback_observed_at_by_client_order_id[client_order_id] = _parse_timestamp(
            observed_at, "observed_at"
        )
        previous_cumulative = self._paper_callback_cumulative_by_client_order_id.get(
            client_order_id,
            0,
        )
        self._paper_callback_cumulative_by_client_order_id[client_order_id] = max(
            previous_cumulative,
            cumulative_filled_quantity,
        )

    def _mark_unknown_if_callback_requires_reconciliation(
        self,
        result: IbkrPaperOrderStatusCallbackRecord | IbkrPaperFillCallbackRecord,
    ) -> None:
        if (
            result.requires_reconciliation
            and self._connection_state != "unknown_requires_reconciliation"
        ):
            self.record_connection_state(
                "unknown_requires_reconciliation",
                recorded_at=result.recorded_at,
                reason=f"paper_callback_{result.status}",
            )


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


def _validated_currency(currency: str) -> str:
    _validated_identifier(currency, "currency")
    if currency != currency.upper() or len(currency) != 3 or not currency.isalpha():
        raise IbkrPaperAdapterError("currency must be a three-letter uppercase code")
    return currency


def _validated_exchange_token(value: str, field_name: str) -> str:
    _validated_identifier(value, field_name)
    if value != value.upper():
        raise IbkrPaperAdapterError(f"{field_name} must be uppercase")
    return value


def _positive_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise IbkrPaperAdapterError(f"{field_name} must be a finite number")

    number = float(value)
    if not (number > 0) or number in {float("inf"), float("-inf")}:
        raise IbkrPaperAdapterError(f"{field_name} must be a finite number greater than zero")
    return number


def _validated_nonnegative_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IbkrPaperAdapterError(f"{field_name} must be a non-negative integer")
    return value


def _validated_timeout_seconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise IbkrPaperAdapterError("timeout_seconds must be a finite number")
    timeout = float(value)
    if not (0 < timeout <= 30) or timeout in {float("inf"), float("-inf")}:
        raise IbkrPaperAdapterError("timeout_seconds must be greater than 0 and no more than 30")
    return timeout


def _validated_max_result_age_seconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise IbkrPaperAdapterError("max_result_age_seconds must be a finite number")
    max_age = float(value)
    if not (0 < max_age <= 86_400) or max_age in {float("inf"), float("-inf")}:
        raise IbkrPaperAdapterError(
            "max_result_age_seconds must be greater than 0 and no more than 86400"
        )
    return max_age


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


def _endpoint_kind_for_port(port: int) -> EndpointKind:
    if port == 7497:
        return "tws_paper"
    if port == 4002:
        return "gateway_paper"
    raise IbkrPaperAdapterError("port must be a known IBKR paper TWS or Gateway port")


def _contract_lookup_result(
    request: IbkrPaperContractLookupRequest,
    *,
    recorded_at: str,
    endpoint_kind: EndpointKind,
    status: ContractLookupStatus,
    failure_category: ContractLookupFailureCategory | None,
    contract: IbkrPaperResolvedContract | None = None,
) -> IbkrPaperContractLookupResult:
    return IbkrPaperContractLookupResult(
        lookup_id=request.lookup_id,
        requested_at=request.requested_at,
        recorded_at=recorded_at,
        reason=request.reason,
        endpoint_kind=endpoint_kind,
        status=status,
        requires_reconciliation=status
        in {
            "blocked_reconciliation_required",
            "stale_result_rejected",
            "unknown_requires_reconciliation",
        },
        failure_category=failure_category,
        contract=contract,
    )


def _contract_metadata_is_stale(
    contract: IbkrPaperResolvedContract,
    *,
    recorded_at: str,
    max_result_age_seconds: float,
) -> bool:
    recorded_timestamp = _parse_timestamp(recorded_at, "recorded_at")
    resolved_timestamp = _parse_timestamp(contract.resolved_at, "resolved_at")
    age_seconds = (recorded_timestamp - resolved_timestamp).total_seconds()
    return age_seconds < 0 or age_seconds > max_result_age_seconds


def _paper_order_submission_record(
    request: IbkrPaperOrderSubmissionRequest,
    *,
    recorded_at: str,
    endpoint_kind: EndpointKind,
    status: PaperOrderSubmissionStatus,
    failure_category: PaperOrderSubmissionFailureCategory | None,
    local_acknowledgement_reference: str | None = None,
) -> IbkrPaperOrderSubmissionRecord:
    return IbkrPaperOrderSubmissionRecord(
        submission_id=request.submission_id,
        requested_at=request.requested_at,
        recorded_at=recorded_at,
        reason=request.reason,
        endpoint_kind=endpoint_kind,
        status=status,
        requires_reconciliation=status
        in {
            "blocked_reconciliation_required",
            "blocked_stale_contract",
            "unknown_requires_reconciliation",
        },
        failure_category=failure_category,
        plan_id=request.plan_id,
        client_order_id=request.client_order_id,
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        order_type=request.order_type,
        idempotency_key=request.idempotency_key,
        risk_decision_id=request.risk_decision_id,
        approval_reference=request.approval_reference,
        oms_transition_reference=request.oms_transition_reference,
        contract_id=request.contract.contract_id,
        protective_order_plan_reference=request.protective_order_plan_reference,
        approved_protective_exception_reference=(request.approved_protective_exception_reference),
        local_acknowledgement_reference=local_acknowledgement_reference,
    )


def _paper_submission_contract_matches_order_plan(
    request: IbkrPaperOrderSubmissionRequest,
) -> bool:
    return (
        request.contract.symbol == request.order_plan.symbol
        and request.contract.security_type == "stock"
        and request.contract.currency == "USD"
    )


def _paper_submission_missing_required_protection(
    request: IbkrPaperOrderSubmissionRequest,
) -> bool:
    if request.order_plan.side != "buy":
        return False
    return (
        request.protective_order_plan_reference is None
        and request.approved_protective_exception_reference is None
    )


def _canonical_submission_payload(request: IbkrPaperOrderSubmissionRequest) -> str:
    return json.dumps(
        request.to_json_dict(),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _local_acknowledgement_reference(idempotency_key: str) -> str:
    _validated_identifier(idempotency_key, "idempotency_key")
    return f"paper-ack-{idempotency_key}"


def _paper_order_status_callback_record(
    callback: IbkrPaperOrderStatusCallback,
    *,
    submission: IbkrPaperOrderSubmissionRecord,
    recorded_at: str,
    endpoint_kind: EndpointKind,
    status: PaperOrderStatusCallbackOutcome,
    failure_category: PaperCallbackFailureCategory | None,
    oms_target_state: str | None = None,
) -> IbkrPaperOrderStatusCallbackRecord:
    return IbkrPaperOrderStatusCallbackRecord(
        callback_id=callback.callback_id,
        observed_at=callback.observed_at,
        received_at=callback.received_at,
        recorded_at=recorded_at,
        reason=callback.reason,
        endpoint_kind=endpoint_kind,
        status=status,
        requires_reconciliation=status not in {"accepted_status_update", "duplicate_status_update"},
        failure_category=failure_category,
        submission_id=submission.submission_id,
        client_order_id=callback.client_order_id,
        correlation_reference=callback.correlation_reference,
        paper_status=callback.paper_status,
        cumulative_filled_quantity=callback.cumulative_filled_quantity,
        oms_target_state=oms_target_state,
    )


def _paper_fill_callback_record(
    callback: IbkrPaperFillCallback,
    *,
    submission: IbkrPaperOrderSubmissionRecord,
    recorded_at: str,
    endpoint_kind: EndpointKind,
    status: PaperFillCallbackOutcome,
    failure_category: PaperCallbackFailureCategory | None,
    leaves_quantity: int | None = None,
    oms_target_state: str | None = None,
) -> IbkrPaperFillCallbackRecord:
    safe_leaves_quantity = (
        max(submission.quantity - callback.cumulative_filled_quantity, 0)
        if leaves_quantity is None
        else leaves_quantity
    )
    return IbkrPaperFillCallbackRecord(
        callback_id=callback.callback_id,
        observed_at=callback.observed_at,
        received_at=callback.received_at,
        recorded_at=recorded_at,
        reason=callback.reason,
        endpoint_kind=endpoint_kind,
        status=status,
        requires_reconciliation=status not in {"accepted_fill_update", "duplicate_fill_update"},
        failure_category=failure_category,
        submission_id=submission.submission_id,
        client_order_id=callback.client_order_id,
        correlation_reference=callback.correlation_reference,
        fill_quantity=callback.fill_quantity,
        cumulative_filled_quantity=callback.cumulative_filled_quantity,
        leaves_quantity=safe_leaves_quantity,
        fill_price=callback.fill_price,
        oms_target_state=oms_target_state,
    )


def _submission_is_accepted_for_callbacks(
    submission: IbkrPaperOrderSubmissionRecord,
) -> bool:
    return (
        submission.status in {"accepted_paper_submission", "duplicate_accepted"}
        and submission.local_acknowledgement_reference is not None
    )


def _callback_matches_submission(
    callback: IbkrPaperOrderStatusCallback | IbkrPaperFillCallback,
    submission: IbkrPaperOrderSubmissionRecord,
) -> bool:
    return (
        callback.client_order_id == submission.client_order_id
        and callback.correlation_reference == submission.local_acknowledgement_reference
    )


def _callback_is_stale(
    observed_at: str,
    *,
    recorded_at: str,
    max_callback_age_seconds: float,
) -> bool:
    recorded_timestamp = _parse_timestamp(recorded_at, "recorded_at")
    observed_timestamp = _parse_timestamp(observed_at, "observed_at")
    age_seconds = (recorded_timestamp - observed_timestamp).total_seconds()
    return age_seconds < 0 or age_seconds > max_callback_age_seconds


def _status_callback_oms_target_state(
    callback: IbkrPaperOrderStatusCallback,
    submission: IbkrPaperOrderSubmissionRecord,
) -> str | None:
    paper_status = callback.paper_status
    cumulative = callback.cumulative_filled_quantity
    if paper_status == "acknowledged" and cumulative == 0:
        return "ACKNOWLEDGED"
    if paper_status == "partially_filled" and 0 < cumulative < submission.quantity:
        return "PARTIALLY_FILLED"
    if paper_status == "filled" and cumulative == submission.quantity:
        return "FILLED"
    if paper_status == "rejected" and cumulative == 0:
        return "REJECTED"
    return None


def _fill_callback_oms_target_state(
    callback: IbkrPaperFillCallback,
    submission: IbkrPaperOrderSubmissionRecord,
) -> str | None:
    if callback.fill_quantity <= 0:
        return None
    if callback.cumulative_filled_quantity <= 0:
        return None
    if callback.fill_quantity > callback.cumulative_filled_quantity:
        return None
    if callback.cumulative_filled_quantity > submission.quantity:
        return None
    if callback.cumulative_filled_quantity < submission.quantity:
        return "PARTIALLY_FILLED"
    return "FILLED"


def _canonical_status_callback_payload(callback: IbkrPaperOrderStatusCallback) -> str:
    return json.dumps(
        callback.to_json_dict(),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_fill_callback_payload(callback: IbkrPaperFillCallback) -> str:
    return json.dumps(
        callback.to_json_dict(),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _paper_contract_lookup_connector_unavailable(
    config: IbkrPaperAdapterConfig,
    request: IbkrPaperContractLookupRequest,
    timeout_seconds: float,
) -> IbkrPaperResolvedContract:
    raise IbkrPaperAdapterError("paper contract lookup connector is unavailable")


def _paper_order_submission_connector_unavailable(
    config: IbkrPaperAdapterConfig,
    request: IbkrPaperOrderSubmissionRequest,
    timeout_seconds: float,
) -> None:
    raise IbkrPaperAdapterError("paper order submission connector is unavailable")


def _probe_local_tcp_endpoint(host: str, port: int, timeout_seconds: float) -> None:
    import socket

    with socket.create_connection((host, port), timeout=timeout_seconds):
        return


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise IbkrPaperAdapterError(f"{payload_name} must be JSON-serializable") from exc
