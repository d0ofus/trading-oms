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
    IBKR_PAPER_ORDER_PLAN_EVENT_TYPE,
    IbkrConnectionStateRecord,
    IbkrPaperAdapter,
    IbkrPaperAdapterConfig,
    IbkrPaperAdapterError,
    IbkrPaperConnectivityProbeResult,
    IbkrPaperOrderPlan,
)

REQUESTED_AT = "2026-07-06T00:02:00Z"
RECORDED_AT = "2026-07-06T00:01:00Z"


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


def test_ibkr_adapter_has_no_sdk_order_contract_or_market_data_surface(tmp_path) -> None:
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
        "lookup_contract",
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
