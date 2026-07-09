from __future__ import annotations

import inspect
from typing import Any

import pytest

from trading_oms_backend import ibkr_paper_adapter
from trading_oms_backend.config import Settings
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.fake_broker import BrokerOrderRequest, FakeBrokerError
from trading_oms_backend.ibkr_paper_adapter import (
    IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE,
    IBKR_PAPER_CONNECTIVITY_PROBE_EVENT_TYPE,
    IBKR_PAPER_CONTRACT_LOOKUP_ATTEMPT_EVENT_TYPE,
    IBKR_PAPER_CONTRACT_LOOKUP_RESULT_EVENT_TYPE,
    IBKR_PAPER_ORDER_PLAN_EVENT_TYPE,
    IBKR_PAPER_ORDER_SUBMISSION_ATTEMPT_EVENT_TYPE,
    IBKR_PAPER_ORDER_SUBMISSION_RESULT_EVENT_TYPE,
    IbkrConnectionStateRecord,
    IbkrPaperAdapter,
    IbkrPaperAdapterConfig,
    IbkrPaperAdapterError,
    IbkrPaperConnectivityProbeResult,
    IbkrPaperContractAmbiguousError,
    IbkrPaperContractLookupRequest,
    IbkrPaperContractLookupResult,
    IbkrPaperContractNotFoundError,
    IbkrPaperOrderPlan,
    IbkrPaperOrderSubmissionRecord,
    IbkrPaperOrderSubmissionRequest,
    IbkrPaperResolvedContract,
)

REQUESTED_AT = "2026-07-06T00:02:00Z"
RECORDED_AT = "2026-07-06T00:01:00Z"
LOOKUP_RECORDED_AT = "2026-07-06T00:03:00Z"
SUBMISSION_REQUESTED_AT = "2026-07-06T00:04:00Z"
SUBMISSION_RECORDED_AT = "2026-07-06T00:04:01Z"


def order_request(**overrides: Any) -> BrokerOrderRequest:
    values: dict[str, Any] = {
        "client_order_id": "client-001",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "order_type": "limit",
        "reference_price": 100.0,
        "limit_price": 99.5,
        "requested_at": REQUESTED_AT,
        "risk_decision_id": "risk-001",
        "risk_decision_result": "passed",
        "approval_reference": "manual-approval-001",
    }
    values.update(overrides)
    return BrokerOrderRequest(**values)


def contract_lookup_request(**overrides: Any) -> IbkrPaperContractLookupRequest:
    values: dict[str, Any] = {
        "lookup_id": "contract-lookup-001",
        "requested_at": LOOKUP_RECORDED_AT,
        "reason": "operator_requested_contract_lookup",
        "symbol": "AAPL",
        "security_type": "stock",
        "currency": "USD",
        "exchange": "SMART",
    }
    values.update(overrides)
    return IbkrPaperContractLookupRequest(**values)


def resolved_contract(**overrides: Any) -> IbkrPaperResolvedContract:
    values: dict[str, Any] = {
        "contract_id": "ibkr-contract-265598",
        "symbol": "AAPL",
        "security_type": "stock",
        "currency": "USD",
        "exchange": "SMART",
        "primary_exchange": "NASDAQ",
        "local_symbol": "AAPL",
        "trading_class": "NMS",
        "min_tick": 0.01,
        "resolved_at": LOOKUP_RECORDED_AT,
    }
    values.update(overrides)
    return IbkrPaperResolvedContract(**values)


def order_submission_request(**overrides: Any) -> IbkrPaperOrderSubmissionRequest:
    values: dict[str, Any] = {
        "submission_id": "paper-submission-001",
        "requested_at": SUBMISSION_REQUESTED_AT,
        "reason": "operator_requested_paper_submission",
        "order_plan": IbkrPaperOrderPlan.from_order_request(order_request()),
        "contract": resolved_contract(),
        "oms_transition_reference": "oms-submitted-001",
        "idempotency_key": "idempotency-client-001",
        "protective_order_plan_reference": "protective-plan-001",
        "approved_protective_exception_reference": None,
    }
    values.update(overrides)
    return IbkrPaperOrderSubmissionRequest(**values)


def test_ibkr_paper_adapter_config_defaults_to_paper_localhost_tws_port() -> None:
    config = IbkrPaperAdapterConfig()

    assert config.to_json_dict() == {
        "schema_version": 1,
        "adapter_name": "ibkr_paper",
        "host": "127.0.0.1",
        "port": 7497,
        "account_mode": "paper",
        "live_trading_enabled": False,
    }


def test_ibkr_paper_adapter_config_can_be_built_from_safe_settings() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "test",
            "APP_MODE": "paper",
            "IBKR_HOST": "localhost",
            "IBKR_PORT": "4002",
            "IBKR_ACCOUNT_MODE": "paper",
        },
    )

    config = IbkrPaperAdapterConfig.from_settings(settings)

    assert config.host == "localhost"
    assert config.port == 4002
    assert config.account_mode == "paper"
    assert config.live_trading_enabled is False


@pytest.mark.parametrize(
    ("settings", "match"),
    [
        (Settings(live_trading_enabled=True), "live trading"),
        (Settings(ibkr_account_mode="live"), "account_mode"),
        (Settings(ibkr_host="0.0.0.0"), "localhost-only"),
        (Settings(ibkr_port=7496), "known IBKR paper"),
    ],
)
def test_ibkr_paper_adapter_config_rejects_unsafe_settings_instances(
    settings: Settings,
    match: str,
) -> None:
    with pytest.raises(IbkrPaperAdapterError, match=match):
        IbkrPaperAdapterConfig.from_settings(settings)


@pytest.mark.parametrize(
    ("config_kwargs", "match"),
    [
        ({"schema_version": 2}, "schema_version"),
        ({"account_mode": "live"}, "account_mode"),
        ({"live_trading_enabled": True}, "live trading"),
        ({"host": "0.0.0.0"}, "localhost-only"),
        ({"host": "broker.example.com"}, "localhost-only"),
        ({"port": 7496}, "known IBKR paper"),
        ({"port": 4001}, "known IBKR paper"),
        ({"port": 9999}, "known IBKR paper"),
        ({"port": True}, "port"),
    ],
)
def test_ibkr_paper_adapter_config_rejects_unsafe_values(
    config_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(IbkrPaperAdapterError, match=match):
        IbkrPaperAdapterConfig(**config_kwargs)


def test_ibkr_paper_adapter_records_connection_state_without_network(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())

    record = adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )

    assert record == IbkrConnectionStateRecord(
        state="connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
        requires_reconciliation=False,
    )
    assert adapter.connection_state == "connected_paper"
    assert adapter.requires_reconciliation is False

    records = journal.read_all()
    assert len(records) == 1
    assert records[0].event_type == IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE
    assert records[0].timestamp == RECORDED_AT
    assert records[0].payload == record.to_json_dict()


def test_ibkr_unknown_state_requires_reconciliation_and_blocks_order_plans(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())

    record = adapter.record_connection_state(
        "unknown_requires_reconciliation",
        recorded_at=RECORDED_AT,
        reason="paper_gateway_state_unknown",
    )

    assert record.requires_reconciliation is True
    assert adapter.requires_reconciliation is True
    with pytest.raises(IbkrPaperAdapterError, match="reconciliation"):
        adapter.create_order_plan(order_request())


def test_ibkr_connectivity_probe_journals_reachable_local_endpoint(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    connector_calls: list[tuple[str, int, float]] = []

    def connector(host: str, port: int, timeout_seconds: float) -> None:
        connector_calls.append((host, port, timeout_seconds))

    result = adapter.probe_local_connectivity(
        probe_id="probe-001",
        recorded_at=RECORDED_AT,
        reason="operator_requested_local_probe",
        timeout_seconds=0.25,
        connector=connector,
    )

    assert connector_calls == [("127.0.0.1", 7497, 0.25)]
    assert result == IbkrPaperConnectivityProbeResult(
        probe_id="probe-001",
        recorded_at=RECORDED_AT,
        reason="operator_requested_local_probe",
        endpoint_kind="tws_paper",
        status="reachable_local_paper_endpoint",
        connection_state="connected_paper",
        requires_reconciliation=False,
        failure_category=None,
    )
    assert adapter.connection_state == "connected_paper"
    assert adapter.requires_reconciliation is False

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        IBKR_PAPER_CONNECTIVITY_PROBE_EVENT_TYPE,
        IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE,
    ]
    assert records[0].payload == result.to_json_dict()
    assert records[1].payload["state"] == "connected_paper"


def test_ibkr_connectivity_probe_records_refused_endpoint_as_disconnected(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig(port=4002))

    def connector(host: str, port: int, timeout_seconds: float) -> None:
        raise ConnectionRefusedError("local endpoint refused connection")

    result = adapter.probe_local_connectivity(
        probe_id="probe-002",
        recorded_at=RECORDED_AT,
        reason="operator_requested_local_probe",
        connector=connector,
    )

    assert result.endpoint_kind == "gateway_paper"
    assert result.status == "unreachable_local_paper_endpoint"
    assert result.connection_state == "disconnected"
    assert result.requires_reconciliation is False
    assert result.failure_category == "connection_refused"
    assert adapter.connection_state == "disconnected"
    assert adapter.requires_reconciliation is False


def test_ibkr_connectivity_probe_records_timeout_as_unknown_reconciliation_required(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())

    def connector(host: str, port: int, timeout_seconds: float) -> None:
        raise TimeoutError("local paper endpoint timed out")

    result = adapter.probe_local_connectivity(
        probe_id="probe-003",
        recorded_at=RECORDED_AT,
        reason="operator_requested_local_probe",
        connector=connector,
    )

    assert result.status == "unknown_requires_reconciliation"
    assert result.connection_state == "unknown_requires_reconciliation"
    assert result.requires_reconciliation is True
    assert result.failure_category == "timeout"
    assert adapter.connection_state == "unknown_requires_reconciliation"
    assert adapter.requires_reconciliation is True
    with pytest.raises(IbkrPaperAdapterError, match="reconciliation"):
        adapter.create_order_plan(order_request())


def test_ibkr_contract_lookup_resolves_stock_metadata_and_journals_attempt_and_result(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    connector_calls: list[tuple[str, int, str, float]] = []

    def connector(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperContractLookupRequest,
        timeout_seconds: float,
    ) -> IbkrPaperResolvedContract:
        connector_calls.append((config.host, config.port, request.symbol, timeout_seconds))
        return resolved_contract()

    result = adapter.lookup_contract(
        contract_lookup_request(),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=connector,
        timeout_seconds=0.5,
    )

    assert connector_calls == [("127.0.0.1", 7497, "AAPL", 0.5)]
    assert result == IbkrPaperContractLookupResult(
        lookup_id="contract-lookup-001",
        requested_at=LOOKUP_RECORDED_AT,
        recorded_at=LOOKUP_RECORDED_AT,
        reason="operator_requested_contract_lookup",
        endpoint_kind="tws_paper",
        status="resolved",
        requires_reconciliation=False,
        failure_category=None,
        contract=resolved_contract(),
    )
    assert adapter.connection_state == "connected_paper"
    assert adapter.requires_reconciliation is False

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE,
        IBKR_PAPER_CONTRACT_LOOKUP_ATTEMPT_EVENT_TYPE,
        IBKR_PAPER_CONTRACT_LOOKUP_RESULT_EVENT_TYPE,
    ]
    assert records[1].payload == contract_lookup_request().to_json_dict() | {
        "endpoint_kind": "tws_paper"
    }
    assert records[2].payload == result.to_json_dict()


def test_ibkr_contract_lookup_records_not_found_and_ambiguous_without_reconciliation(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )

    def not_found(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperContractLookupRequest,
        timeout_seconds: float,
    ) -> IbkrPaperResolvedContract:
        raise IbkrPaperContractNotFoundError("paper contract not found")

    not_found_result = adapter.lookup_contract(
        contract_lookup_request(lookup_id="contract-lookup-002", symbol="MSFT"),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=not_found,
    )

    def ambiguous(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperContractLookupRequest,
        timeout_seconds: float,
    ) -> IbkrPaperResolvedContract:
        raise IbkrPaperContractAmbiguousError("paper contract lookup ambiguous")

    ambiguous_result = adapter.lookup_contract(
        contract_lookup_request(lookup_id="contract-lookup-003", symbol="BRK.B"),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=ambiguous,
    )

    assert not_found_result.status == "not_found"
    assert not_found_result.requires_reconciliation is False
    assert not_found_result.failure_category == "not_found"
    assert not_found_result.contract is None
    assert ambiguous_result.status == "ambiguous"
    assert ambiguous_result.requires_reconciliation is False
    assert ambiguous_result.failure_category == "ambiguous"
    assert ambiguous_result.contract is None
    assert adapter.connection_state == "connected_paper"


def test_ibkr_contract_lookup_rejects_unsupported_instruments_without_connector_call(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    connector_calls: list[str] = []

    def connector(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperContractLookupRequest,
        timeout_seconds: float,
    ) -> IbkrPaperResolvedContract:
        connector_calls.append(request.security_type)
        return resolved_contract()

    result = adapter.lookup_contract(
        contract_lookup_request(security_type="option"),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=connector,
    )

    assert connector_calls == []
    assert result.status == "unsupported_instrument"
    assert result.requires_reconciliation is False
    assert result.failure_category == "unsupported_instrument"
    assert result.contract is None
    assert [record.event_type for record in journal.read_all()][-2:] == [
        IBKR_PAPER_CONTRACT_LOOKUP_ATTEMPT_EVENT_TYPE,
        IBKR_PAPER_CONTRACT_LOOKUP_RESULT_EVENT_TYPE,
    ]


def test_ibkr_contract_lookup_blocks_disconnected_and_reconciliation_required_state(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    connector_calls: list[str] = []

    def connector(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperContractLookupRequest,
        timeout_seconds: float,
    ) -> IbkrPaperResolvedContract:
        connector_calls.append(request.symbol)
        return resolved_contract()

    disconnected_result = adapter.lookup_contract(
        contract_lookup_request(lookup_id="contract-lookup-004"),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=connector,
    )
    adapter.record_connection_state(
        "unknown_requires_reconciliation",
        recorded_at=LOOKUP_RECORDED_AT,
        reason="paper_gateway_state_unknown",
    )
    reconciliation_result = adapter.lookup_contract(
        contract_lookup_request(lookup_id="contract-lookup-005"),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=connector,
    )

    assert connector_calls == []
    assert disconnected_result.status == "blocked_disconnected"
    assert disconnected_result.requires_reconciliation is False
    assert disconnected_result.failure_category == "disconnected"
    assert reconciliation_result.status == "blocked_reconciliation_required"
    assert reconciliation_result.requires_reconciliation is True
    assert reconciliation_result.failure_category == "reconciliation_required"


def test_ibkr_contract_lookup_rejects_stale_metadata_and_requires_reconciliation(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )

    def connector(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperContractLookupRequest,
        timeout_seconds: float,
    ) -> IbkrPaperResolvedContract:
        return resolved_contract(resolved_at="2026-07-06T00:00:00Z")

    result = adapter.lookup_contract(
        contract_lookup_request(),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=connector,
        max_result_age_seconds=30,
    )

    assert result.status == "stale_result_rejected"
    assert result.requires_reconciliation is True
    assert result.failure_category == "stale_result"
    assert result.contract is None
    assert adapter.connection_state == "unknown_requires_reconciliation"
    assert adapter.requires_reconciliation is True
    assert journal.read_all()[-1].event_type == IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE


def test_ibkr_contract_lookup_connector_errors_require_reconciliation(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )

    def connector(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperContractLookupRequest,
        timeout_seconds: float,
    ) -> IbkrPaperResolvedContract:
        raise TimeoutError("paper contract lookup timed out")

    result = adapter.lookup_contract(
        contract_lookup_request(),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=connector,
    )

    assert result.status == "unknown_requires_reconciliation"
    assert result.requires_reconciliation is True
    assert result.failure_category == "timeout"
    assert result.contract is None
    assert adapter.connection_state == "unknown_requires_reconciliation"
    assert adapter.requires_reconciliation is True


def test_ibkr_paper_adapter_builds_and_journals_local_order_plan(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )

    plan = adapter.create_order_plan(order_request())

    assert plan == IbkrPaperOrderPlan(
        plan_id="ibkr-paper-plan-client-001",
        client_order_id="client-001",
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="limit",
        reference_price=100.0,
        requested_at=REQUESTED_AT,
        risk_decision_id="risk-001",
        approval_reference="manual-approval-001",
        limit_price=99.5,
        status="planned_local_only",
        adapter_name="ibkr_paper",
    )

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE,
        IBKR_PAPER_ORDER_PLAN_EVENT_TYPE,
    ]
    assert records[1].timestamp == REQUESTED_AT
    assert records[1].payload == plan.to_json_dict()


def test_ibkr_paper_adapter_records_accepted_paper_submission_with_connector(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    plan = adapter.create_order_plan(order_request())
    connector_calls: list[tuple[str, int, str, float]] = []

    def connector(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperOrderSubmissionRequest,
        timeout_seconds: float,
    ) -> None:
        connector_calls.append((config.host, config.port, request.idempotency_key, timeout_seconds))

    result = adapter.record_paper_order_submission(
        order_submission_request(order_plan=plan),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=connector,
        timeout_seconds=0.5,
    )

    assert connector_calls == [("127.0.0.1", 7497, "idempotency-client-001", 0.5)]
    assert result == IbkrPaperOrderSubmissionRecord(
        submission_id="paper-submission-001",
        requested_at=SUBMISSION_REQUESTED_AT,
        recorded_at=SUBMISSION_RECORDED_AT,
        reason="operator_requested_paper_submission",
        endpoint_kind="tws_paper",
        status="accepted_paper_submission",
        requires_reconciliation=False,
        failure_category=None,
        plan_id=plan.plan_id,
        client_order_id="client-001",
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="limit",
        idempotency_key="idempotency-client-001",
        risk_decision_id="risk-001",
        approval_reference="manual-approval-001",
        oms_transition_reference="oms-submitted-001",
        contract_id="ibkr-contract-265598",
        protective_order_plan_reference="protective-plan-001",
        approved_protective_exception_reference=None,
        local_acknowledgement_reference="paper-ack-idempotency-client-001",
    )

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE,
        IBKR_PAPER_ORDER_PLAN_EVENT_TYPE,
        IBKR_PAPER_ORDER_SUBMISSION_ATTEMPT_EVENT_TYPE,
        IBKR_PAPER_ORDER_SUBMISSION_RESULT_EVENT_TYPE,
    ]
    assert records[2].payload == order_submission_request(order_plan=plan).to_json_dict() | {
        "endpoint_kind": "tws_paper"
    }
    assert records[3].payload == result.to_json_dict()


def test_ibkr_paper_submission_blocks_disconnected_and_reconciliation_required_state(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    disconnected_plan = adapter.create_order_plan(
        order_request(client_order_id="client-002"),
    )
    connector_calls: list[str] = []

    def connector(
        config: IbkrPaperAdapterConfig,
        request: IbkrPaperOrderSubmissionRequest,
        timeout_seconds: float,
    ) -> None:
        connector_calls.append(request.client_order_id)

    disconnected = adapter.record_paper_order_submission(
        order_submission_request(
            submission_id="paper-submission-002",
            order_plan=disconnected_plan,
            idempotency_key="idempotency-client-002",
        ),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=connector,
    )
    adapter.record_connection_state(
        "unknown_requires_reconciliation",
        recorded_at=SUBMISSION_RECORDED_AT,
        reason="paper_gateway_state_unknown",
    )
    reconciliation = adapter.record_paper_order_submission(
        order_submission_request(
            submission_id="paper-submission-003",
            order_plan=disconnected_plan,
            idempotency_key="idempotency-client-003",
        ),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=connector,
    )

    assert connector_calls == []
    assert disconnected.status == "blocked_disconnected"
    assert disconnected.requires_reconciliation is False
    assert disconnected.failure_category == "disconnected"
    assert reconciliation.status == "blocked_reconciliation_required"
    assert reconciliation.requires_reconciliation is True
    assert reconciliation.failure_category == "reconciliation_required"


def test_ibkr_paper_submission_rejects_stale_contract_and_requires_reconciliation(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    plan = adapter.create_order_plan(order_request(client_order_id="client-004"))
    connector_calls: list[str] = []

    result = adapter.record_paper_order_submission(
        order_submission_request(
            submission_id="paper-submission-004",
            order_plan=plan,
            contract=resolved_contract(resolved_at="2026-07-06T00:00:00Z"),
            idempotency_key="idempotency-client-004",
        ),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
        max_contract_age_seconds=30,
    )

    assert connector_calls == []
    assert result.status == "blocked_stale_contract"
    assert result.requires_reconciliation is True
    assert result.failure_category == "stale_contract"
    assert adapter.connection_state == "unknown_requires_reconciliation"
    assert adapter.requires_reconciliation is True
    assert journal.read_all()[-1].event_type == IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE


def test_ibkr_paper_submission_rejects_contract_mismatch_and_missing_protection(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    mismatch_plan = adapter.create_order_plan(order_request(client_order_id="client-005"))
    missing_protection_plan = adapter.create_order_plan(
        order_request(client_order_id="client-006"),
    )
    connector_calls: list[str] = []

    mismatch = adapter.record_paper_order_submission(
        order_submission_request(
            submission_id="paper-submission-005",
            order_plan=mismatch_plan,
            contract=resolved_contract(symbol="MSFT"),
            idempotency_key="idempotency-client-005",
        ),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )
    missing_protection = adapter.record_paper_order_submission(
        order_submission_request(
            submission_id="paper-submission-006",
            order_plan=missing_protection_plan,
            idempotency_key="idempotency-client-006",
            protective_order_plan_reference=None,
            approved_protective_exception_reference=None,
        ),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )

    assert connector_calls == []
    assert mismatch.status == "blocked_contract_mismatch"
    assert mismatch.failure_category == "contract_mismatch"
    assert missing_protection.status == "blocked_missing_protection"
    assert missing_protection.failure_category == "missing_protection"


def test_ibkr_paper_submission_is_idempotent_and_rejects_conflicts(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    plan = adapter.create_order_plan(order_request(client_order_id="client-007"))
    request = order_submission_request(
        submission_id="paper-submission-007",
        order_plan=plan,
        idempotency_key="idempotency-client-007",
    )
    connector_calls: list[str] = []

    first = adapter.record_paper_order_submission(
        request,
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )
    duplicate = adapter.record_paper_order_submission(
        request,
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )
    conflict = adapter.record_paper_order_submission(
        order_submission_request(
            submission_id="paper-submission-008",
            order_plan=plan,
            idempotency_key="idempotency-client-007",
            oms_transition_reference="different-oms-transition",
        ),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )

    assert connector_calls == ["client-007"]
    assert first.status == "accepted_paper_submission"
    assert duplicate.status == "duplicate_accepted"
    assert duplicate.local_acknowledgement_reference == first.local_acknowledgement_reference
    assert conflict.status == "blocked_duplicate_conflict"
    assert conflict.failure_category == "duplicate_conflict"
    assert [record.event_type for record in journal.read_all()].count(
        IBKR_PAPER_ORDER_SUBMISSION_RESULT_EVENT_TYPE
    ) == 3


def test_ibkr_paper_submission_connector_errors_require_reconciliation(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    plan = adapter.create_order_plan(order_request(client_order_id="client-009"))

    result = adapter.record_paper_order_submission(
        order_submission_request(
            submission_id="paper-submission-009",
            order_plan=plan,
            idempotency_key="idempotency-client-009",
        ),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: (_ for _ in ()).throw(
            TimeoutError("paper order transport timed out")
        ),
    )

    assert result.status == "unknown_requires_reconciliation"
    assert result.requires_reconciliation is True
    assert result.failure_category == "timeout"
    assert adapter.connection_state == "unknown_requires_reconciliation"
    assert adapter.requires_reconciliation is True


def test_ibkr_paper_submission_payloads_exclude_accounts_credentials_and_live_fields(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    plan = adapter.create_order_plan(order_request())
    request = order_submission_request(order_plan=plan)
    result = adapter.record_paper_order_submission(
        request,
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: None,
    )

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker_order_id",
        "certificate",
        "credential",
        "fill",
        "host",
        "order_status",
        "password",
        "port",
        "private_key",
        "route",
        "route_live",
        "secret",
        "submit",
        "submit_live",
        "token",
        "transmit",
        "transmit_live",
    }
    payloads = [
        request.to_json_dict(),
        result.to_json_dict(),
        *(record.payload for record in journal.read_all()),
    ]
    for payload in payloads:
        assert forbidden_keys.isdisjoint(_all_payload_keys(payload))


def test_ibkr_paper_adapter_rejects_unsafe_order_inputs(tmp_path) -> None:
    adapter = IbkrPaperAdapter(
        JsonlEventJournal(tmp_path / "events.jsonl"),
        IbkrPaperAdapterConfig(),
    )

    with pytest.raises(IbkrPaperAdapterError, match="BrokerOrderRequest"):
        adapter.create_order_plan(object())  # type: ignore[arg-type]

    with pytest.raises(FakeBrokerError, match="risk_decision_result"):
        order_request(risk_decision_result="blocked")

    with pytest.raises(FakeBrokerError, match="approval_reference"):
        order_request(approval_reference="")


def test_ibkr_paper_payloads_exclude_account_credentials_network_and_submission_fields(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    state = adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )
    plan = adapter.create_order_plan(order_request())

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker_order_id",
        "certificate",
        "credential",
        "host",
        "password",
        "port",
        "private_key",
        "route",
        "secret",
        "socket",
        "submit",
        "token",
        "transmit",
    }
    payloads = [
        state.to_json_dict(),
        plan.to_json_dict(),
        *(record.payload for record in journal.read_all()),
    ]
    for payload in payloads:
        assert forbidden_keys.isdisjoint(_all_payload_keys(payload))


def test_ibkr_connectivity_probe_payloads_exclude_accounts_credentials_and_order_fields(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())

    result = adapter.probe_local_connectivity(
        probe_id="probe-004",
        recorded_at=RECORDED_AT,
        reason="operator_requested_local_probe",
        connector=lambda host, port, timeout_seconds: None,
    )

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker_order_id",
        "certificate",
        "credential",
        "host",
        "password",
        "port",
        "private_key",
        "route",
        "secret",
        "submit",
        "token",
        "transmit",
    }
    payloads = [result.to_json_dict(), *(record.payload for record in journal.read_all())]
    for payload in payloads:
        assert forbidden_keys.isdisjoint(_all_payload_keys(payload))


def test_ibkr_contract_lookup_payloads_exclude_accounts_credentials_and_order_fields(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    adapter.record_connection_state(
        "connected_paper",
        recorded_at=RECORDED_AT,
        reason="operator_confirmed_local_paper_session",
    )

    result = adapter.lookup_contract(
        contract_lookup_request(),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: resolved_contract(),
    )

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker_order_id",
        "certificate",
        "credential",
        "host",
        "order",
        "order_type",
        "password",
        "port",
        "private_key",
        "route",
        "secret",
        "submit",
        "token",
        "transmit",
    }
    payloads = [
        contract_lookup_request().to_json_dict(),
        result.to_json_dict(),
        *(record.payload for record in journal.read_all()),
    ]
    for payload in payloads:
        assert forbidden_keys.isdisjoint(_all_payload_keys(payload))


def test_ibkr_adapter_has_no_sdk_order_market_data_or_callback_surface(tmp_path) -> None:
    source = inspect.getsource(ibkr_paper_adapter).lower()
    forbidden_source_tokens = [
        "ibapi",
        "ib_insync",
        "accountsummary",
        "placeorder",
        "reqcontractdetails",
        "reqmktdata",
        "sendall",
        ".send(",
        ".recv(",
    ]

    for token in forbidden_source_tokens:
        assert token not in source

    adapter = IbkrPaperAdapter(
        JsonlEventJournal(tmp_path / "events.jsonl"),
        IbkrPaperAdapterConfig(),
    )
    for method_name in [
        "accept_order",
        "submit_order",
        "place_order",
        "transmit_order",
        "cancel_order",
        "modify_order",
        "subscribe_market_data",
        "handle_order_status",
        "handle_fill",
    ]:
        assert not hasattr(adapter, method_name)


def _all_payload_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested_value in value.values():
            keys.update(_all_payload_keys(nested_value))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_all_payload_keys(item))
        return keys
    return set()
