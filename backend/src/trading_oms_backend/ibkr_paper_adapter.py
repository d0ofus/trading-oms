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


def _paper_contract_lookup_connector_unavailable(
    config: IbkrPaperAdapterConfig,
    request: IbkrPaperContractLookupRequest,
    timeout_seconds: float,
) -> IbkrPaperResolvedContract:
    raise IbkrPaperAdapterError("paper contract lookup connector is unavailable")


def _probe_local_tcp_endpoint(host: str, port: int, timeout_seconds: float) -> None:
    import socket

    with socket.create_connection((host, port), timeout=timeout_seconds):
        return


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise IbkrPaperAdapterError(f"{payload_name} must be JSON-serializable") from exc
