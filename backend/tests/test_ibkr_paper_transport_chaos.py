from __future__ import annotations

import inspect
from typing import Any

import pytest

from trading_oms_backend import ibkr_paper_adapter
from trading_oms_backend.config import Settings
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.fake_broker import BrokerOrderRequest
from trading_oms_backend.ibkr_paper_adapter import (
    IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE,
    IBKR_PAPER_CONNECTIVITY_PROBE_EVENT_TYPE,
    IBKR_PAPER_FILL_CALLBACK_RESULT_EVENT_TYPE,
    IBKR_PAPER_ORDER_STATUS_CALLBACK_RESULT_EVENT_TYPE,
    IBKR_PAPER_ORDER_SUBMISSION_RESULT_EVENT_TYPE,
    IbkrPaperAdapter,
    IbkrPaperAdapterConfig,
    IbkrPaperAdapterError,
    IbkrPaperContractLookupRequest,
    IbkrPaperFillCallback,
    IbkrPaperOrderStatusCallback,
    IbkrPaperOrderSubmissionRecord,
    IbkrPaperOrderSubmissionRequest,
    IbkrPaperResolvedContract,
)

REQUESTED_AT = "2026-07-06T00:02:00Z"
LOOKUP_RECORDED_AT = "2026-07-06T00:03:00Z"
SUBMISSION_REQUESTED_AT = "2026-07-06T00:04:00Z"
SUBMISSION_RECORDED_AT = "2026-07-06T00:04:01Z"
CALLBACK_OBSERVED_AT = "2026-07-06T00:05:00Z"
CALLBACK_RECEIVED_AT = "2026-07-06T00:05:01Z"
CALLBACK_RECORDED_AT = "2026-07-06T00:05:02Z"


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
    client_order_id = overrides.pop("client_order_id", "client-001")
    order_plan = overrides.pop("order_plan", None)
    if order_plan is None:
        scratch_journal_path = overrides.pop("scratch_journal_path")
        order_plan = IbkrPaperAdapter(
            JsonlEventJournal(scratch_journal_path),
            IbkrPaperAdapterConfig(),
        ).create_order_plan(order_request(client_order_id=client_order_id))
    values: dict[str, Any] = {
        "submission_id": f"paper-submission-{client_order_id}",
        "requested_at": SUBMISSION_REQUESTED_AT,
        "reason": "operator_requested_paper_submission",
        "order_plan": order_plan,
        "contract": resolved_contract(),
        "oms_transition_reference": f"oms-submitted-{client_order_id}",
        "idempotency_key": f"idempotency-{client_order_id}",
        "protective_order_plan_reference": f"protective-plan-{client_order_id}",
        "approved_protective_exception_reference": None,
    }
    values.update(overrides)
    return IbkrPaperOrderSubmissionRequest(**values)


def status_callback(**overrides: Any) -> IbkrPaperOrderStatusCallback:
    client_order_id = overrides.get("client_order_id", "client-001")
    values: dict[str, Any] = {
        "callback_id": "status-callback-001",
        "observed_at": CALLBACK_OBSERVED_AT,
        "received_at": CALLBACK_RECEIVED_AT,
        "reason": "paper_order_status_callback",
        "client_order_id": client_order_id,
        "correlation_reference": f"paper-ack-idempotency-{client_order_id}",
        "paper_status": "acknowledged",
        "cumulative_filled_quantity": 0,
    }
    values.update(overrides)
    return IbkrPaperOrderStatusCallback(**values)


def fill_callback(**overrides: Any) -> IbkrPaperFillCallback:
    client_order_id = overrides.get("client_order_id", "client-001")
    values: dict[str, Any] = {
        "callback_id": "fill-callback-001",
        "observed_at": CALLBACK_OBSERVED_AT,
        "received_at": CALLBACK_RECEIVED_AT,
        "reason": "paper_fill_callback",
        "client_order_id": client_order_id,
        "correlation_reference": f"paper-ack-idempotency-{client_order_id}",
        "fill_quantity": 4,
        "cumulative_filled_quantity": 4,
        "fill_price": 99.5,
    }
    values.update(overrides)
    return IbkrPaperFillCallback(**values)


def request_from_adapter(
    adapter: IbkrPaperAdapter,
    *,
    client_order_id: str = "client-001",
    **overrides: Any,
) -> IbkrPaperOrderSubmissionRequest:
    plan = adapter.create_order_plan(order_request(client_order_id=client_order_id))
    return order_submission_request(
        order_plan=plan,
        client_order_id=client_order_id,
        **overrides,
    )


def accepted_submission(
    adapter: IbkrPaperAdapter,
    *,
    client_order_id: str = "client-001",
) -> IbkrPaperOrderSubmissionRecord:
    adapter.record_connection_state(
        "connected_paper",
        recorded_at="2026-07-06T00:01:00Z",
        reason="operator_confirmed_local_paper_session",
    )
    return adapter.record_paper_order_submission(
        request_from_adapter(adapter, client_order_id=client_order_id),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: None,
    )


def test_paper_transport_chaos_disconnect_then_reconnect_before_submission(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    request = request_from_adapter(adapter)
    connector_calls: list[str] = []

    blocked = adapter.record_paper_order_submission(
        request,
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )

    assert blocked.status == "blocked_disconnected"
    assert blocked.requires_reconciliation is False
    assert connector_calls == []

    probe = adapter.probe_local_connectivity(
        probe_id="probe-reconnect-001",
        recorded_at="2026-07-06T00:04:30Z",
        reason="operator_reconnect_probe",
        connector=lambda host, port, timeout_seconds: None,
    )
    accepted = adapter.record_paper_order_submission(
        request,
        recorded_at="2026-07-06T00:04:31Z",
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )

    assert probe.status == "reachable_local_paper_endpoint"
    assert adapter.connection_state == "connected_paper"
    assert accepted.status == "accepted_paper_submission"
    assert connector_calls == ["client-001"]
    assert [record.event_type for record in journal.read_all()].count(
        IBKR_PAPER_CONNECTIVITY_PROBE_EVENT_TYPE
    ) == 1
    assert [record.event_type for record in journal.read_all()].count(
        IBKR_PAPER_ORDER_SUBMISSION_RESULT_EVENT_TYPE
    ) == 2


def test_paper_transport_chaos_unknown_state_blocks_risk_increasing_transport(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    accepted = accepted_submission(
        IbkrPaperAdapter(
            JsonlEventJournal(tmp_path / "accepted-events.jsonl"),
            IbkrPaperAdapterConfig(),
        ),
    )
    adapter.record_connection_state(
        "unknown_requires_reconciliation",
        recorded_at="2026-07-06T00:04:20Z",
        reason="chaos_unknown_broker_state",
    )
    connector_calls: list[str] = []

    lookup = adapter.lookup_contract(
        contract_lookup_request(),
        recorded_at=LOOKUP_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: resolved_contract(),
    )
    with pytest.raises(IbkrPaperAdapterError, match="requires reconciliation"):
        adapter.create_order_plan(order_request(client_order_id="client-blocked-plan"))
    submission = adapter.record_paper_order_submission(
        order_submission_request(
            scratch_journal_path=tmp_path / "scratch-events.jsonl",
            client_order_id="client-blocked-submission",
        ),
        recorded_at=SUBMISSION_RECORDED_AT,
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )
    callback = adapter.record_paper_order_status_callback(
        status_callback(),
        submission=accepted,
        recorded_at=CALLBACK_RECORDED_AT,
    )

    assert lookup.status == "blocked_reconciliation_required"
    assert submission.status == "blocked_reconciliation_required"
    assert callback.status == "blocked_reconciliation_required"
    assert lookup.requires_reconciliation is True
    assert submission.requires_reconciliation is True
    assert callback.requires_reconciliation is True
    assert adapter.connection_state == "unknown_requires_reconciliation"
    assert adapter.requires_reconciliation is True
    assert connector_calls == []


def test_paper_transport_chaos_duplicate_callbacks_are_idempotent_until_conflict(
    tmp_path,
) -> None:
    status_journal = JsonlEventJournal(tmp_path / "status-events.jsonl")
    status_adapter = IbkrPaperAdapter(status_journal, IbkrPaperAdapterConfig())
    status_submission = accepted_submission(status_adapter)
    status = status_callback(callback_id="status-duplicate-chaos")

    first_status = status_adapter.record_paper_order_status_callback(
        status,
        submission=status_submission,
        recorded_at=CALLBACK_RECORDED_AT,
    )
    duplicate_status = status_adapter.record_paper_order_status_callback(
        status,
        submission=status_submission,
        recorded_at=CALLBACK_RECORDED_AT,
    )
    conflict_status = status_adapter.record_paper_order_status_callback(
        status_callback(
            callback_id="status-duplicate-chaos",
            paper_status="rejected",
        ),
        submission=status_submission,
        recorded_at=CALLBACK_RECORDED_AT,
    )

    assert first_status.status == "accepted_status_update"
    assert duplicate_status.status == "duplicate_status_update"
    assert duplicate_status.oms_target_state == first_status.oms_target_state
    assert conflict_status.status == "blocked_duplicate_conflict"
    assert conflict_status.requires_reconciliation is True
    assert status_adapter.connection_state == "unknown_requires_reconciliation"
    assert [record.event_type for record in status_journal.read_all()].count(
        IBKR_PAPER_ORDER_STATUS_CALLBACK_RESULT_EVENT_TYPE
    ) == 3

    fill_journal = JsonlEventJournal(tmp_path / "fill-events.jsonl")
    fill_adapter = IbkrPaperAdapter(fill_journal, IbkrPaperAdapterConfig())
    fill_submission = accepted_submission(fill_adapter)
    fill = fill_callback(callback_id="fill-duplicate-chaos")

    first_fill = fill_adapter.record_paper_fill_callback(
        fill,
        submission=fill_submission,
        recorded_at=CALLBACK_RECORDED_AT,
    )
    duplicate_fill = fill_adapter.record_paper_fill_callback(
        fill,
        submission=fill_submission,
        recorded_at=CALLBACK_RECORDED_AT,
    )
    conflict_fill = fill_adapter.record_paper_fill_callback(
        fill_callback(
            callback_id="fill-duplicate-chaos",
            fill_quantity=5,
            cumulative_filled_quantity=5,
        ),
        submission=fill_submission,
        recorded_at=CALLBACK_RECORDED_AT,
    )

    assert first_fill.status == "accepted_fill_update"
    assert duplicate_fill.status == "duplicate_fill_update"
    assert duplicate_fill.leaves_quantity == first_fill.leaves_quantity
    assert conflict_fill.status == "blocked_duplicate_conflict"
    assert conflict_fill.requires_reconciliation is True
    assert fill_adapter.connection_state == "unknown_requires_reconciliation"
    assert [record.event_type for record in fill_journal.read_all()].count(
        IBKR_PAPER_FILL_CALLBACK_RESULT_EVENT_TYPE
    ) == 3


def test_paper_transport_chaos_stale_callback_blocks_later_submission(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    submission = accepted_submission(adapter)
    later_request = request_from_adapter(adapter, client_order_id="client-002")
    connector_calls: list[str] = []

    stale = adapter.record_paper_order_status_callback(
        status_callback(
            callback_id="status-stale-chaos",
            observed_at="2026-07-06T00:00:00Z",
        ),
        submission=submission,
        recorded_at=CALLBACK_RECORDED_AT,
        max_callback_age_seconds=60,
    )
    blocked_after_stale = adapter.record_paper_order_submission(
        later_request,
        recorded_at="2026-07-06T00:05:03Z",
        connector=lambda config, request, timeout_seconds: connector_calls.append(
            request.client_order_id
        ),
    )

    assert stale.status == "blocked_stale_callback"
    assert stale.requires_reconciliation is True
    assert adapter.connection_state == "unknown_requires_reconciliation"
    assert blocked_after_stale.status == "blocked_reconciliation_required"
    assert blocked_after_stale.requires_reconciliation is True
    assert connector_calls == []
    assert journal.read_all()[-1].event_type == IBKR_PAPER_ORDER_SUBMISSION_RESULT_EVENT_TYPE


def test_paper_transport_chaos_out_of_order_callback_requires_reconciliation(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    submission = accepted_submission(adapter)

    first = adapter.record_paper_fill_callback(
        fill_callback(callback_id="fill-ordering-chaos-001"),
        submission=submission,
        recorded_at=CALLBACK_RECORDED_AT,
    )
    out_of_order = adapter.record_paper_fill_callback(
        fill_callback(
            callback_id="fill-ordering-chaos-002",
            observed_at="2026-07-06T00:04:59Z",
            received_at="2026-07-06T00:05:03Z",
            cumulative_filled_quantity=5,
        ),
        submission=submission,
        recorded_at="2026-07-06T00:05:04Z",
    )

    assert first.status == "accepted_fill_update"
    assert out_of_order.status == "blocked_out_of_order_callback"
    assert out_of_order.requires_reconciliation is True
    assert out_of_order.failure_category == "out_of_order_callback"
    assert adapter.connection_state == "unknown_requires_reconciliation"
    assert [record.event_type for record in journal.read_all()].count(
        IBKR_PAPER_CONNECTION_STATE_EVENT_TYPE
    ) == 2


def test_paper_transport_chaos_rejects_live_public_secret_and_listener_surfaces(
    tmp_path,
) -> None:
    with pytest.raises(IbkrPaperAdapterError, match="live trading"):
        IbkrPaperAdapterConfig.from_settings(Settings(live_trading_enabled=True))
    with pytest.raises(IbkrPaperAdapterError, match="account_mode"):
        IbkrPaperAdapterConfig.from_settings(Settings(ibkr_account_mode="live"))
    with pytest.raises(IbkrPaperAdapterError, match="localhost-only"):
        IbkrPaperAdapterConfig.from_settings(Settings(ibkr_host="0.0.0.0"))
    with pytest.raises(IbkrPaperAdapterError, match="known IBKR paper"):
        IbkrPaperAdapterConfig.from_settings(Settings(ibkr_port=7496))

    source = inspect.getsource(ibkr_paper_adapter).lower()
    forbidden_source_tokens = [
        "ibapi",
        "ib_insync",
        "accountsummary",
        "placeorder",
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
        "submit_live_order",
        "place_live_order",
        "transmit_live_order",
        "cancel_order",
        "modify_order",
        "subscribe_market_data",
        "open_callback_listener",
        "register_account",
        "configure_public_host",
        "open_paper_trading_ui",
    ]:
        assert not hasattr(adapter, method_name)


def test_paper_transport_chaos_payloads_exclude_secret_and_live_routing_fields(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    adapter = IbkrPaperAdapter(journal, IbkrPaperAdapterConfig())
    submission = accepted_submission(adapter)
    first = adapter.record_paper_order_status_callback(
        status_callback(callback_id="status-payload-chaos"),
        submission=submission,
        recorded_at=CALLBACK_RECORDED_AT,
    )
    conflict = adapter.record_paper_order_status_callback(
        status_callback(
            callback_id="status-payload-chaos",
            paper_status="rejected",
        ),
        submission=submission,
        recorded_at=CALLBACK_RECORDED_AT,
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
        "market_data",
        "password",
        "port",
        "private_key",
        "production",
        "public_host",
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
        first.to_json_dict(),
        conflict.to_json_dict(),
        *(record.payload for record in journal.read_all()),
    ]
    for payload in payloads:
        assert forbidden_keys.isdisjoint(_all_payload_keys(payload))


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
