from __future__ import annotations

import inspect
from typing import Any

import pytest

from trading_oms_backend import resilience
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.resilience import (
    RESILIENCE_CHAOS_SCENARIO_EVENT_TYPE,
    RESILIENCE_DISCONNECT_EVENT_TYPE,
    RESILIENCE_RECONCILIATION_COMPLETED_EVENT_TYPE,
    RESILIENCE_RECONCILIATION_STARTED_EVENT_TYPE,
    RESILIENCE_RECONNECT_EVENT_TYPE,
    RESILIENCE_UNKNOWN_BROKER_STATE_EVENT_TYPE,
    ReconciliationSnapshot,
    ResilienceError,
    ResilienceMonitor,
    run_reconnect_reconciliation_chaos_scenario,
)
from trading_oms_backend.risk_engine import (
    ProtectiveOrderPlan,
    RiskEvaluationRequest,
    RiskPolicy,
)

DISCONNECTED_AT = "2026-07-06T00:03:00Z"
RECONNECTED_AT = "2026-07-06T00:03:10Z"
RECONCILIATION_STARTED_AT = "2026-07-06T00:03:20Z"
RECONCILIATION_COMPLETED_AT = "2026-07-06T00:03:30Z"
EVALUATED_AT = "2026-07-06T00:03:25Z"
FRESH_MARKET_DATA = "2026-07-06T00:03:20Z"
STALE_MARKET_DATA = "2026-07-06T00:00:00Z"


def policy(**overrides: Any) -> RiskPolicy:
    values = {
        "max_order_quantity": 100,
        "max_order_notional": 10_000.0,
        "max_market_data_age_seconds": 30,
        "allowed_symbols": ("AAPL", "MSFT"),
    }
    values.update(overrides)
    return RiskPolicy(**values)


def protective_plan(**overrides: Any) -> ProtectiveOrderPlan:
    values = {"kind": "stop_loss", "stop_price": 95.0}
    values.update(overrides)
    return ProtectiveOrderPlan(**values)


def risk_request(**overrides: Any) -> RiskEvaluationRequest:
    values = {
        "request_id": "risk-017",
        "symbol": "AAPL",
        "side": "buy",
        "risk_intent": "increase",
        "quantity": 10,
        "reference_price": 100.0,
        "market_data_timestamp": FRESH_MARKET_DATA,
        "evaluated_at": EVALUATED_AT,
        "broker_state_known": True,
        "protective_order": protective_plan(),
        "existing_request_ids": frozenset(),
    }
    values.update(overrides)
    return RiskEvaluationRequest(**values)


def snapshot(**overrides: Any) -> ReconciliationSnapshot:
    values = {
        "snapshot_id": "snapshot-017",
        "captured_at": RECONCILIATION_COMPLETED_AT,
        "broker_state_known": True,
        "open_order_ids": ("oms-001",),
        "position_symbols": ("AAPL",),
        "requires_operator_review": False,
    }
    values.update(overrides)
    return ReconciliationSnapshot(**values)


def test_resilience_monitor_journals_reconnect_and_reconciliation_flow(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    monitor = ResilienceMonitor(journal)

    disconnected = monitor.record_disconnect(
        event_id="resilience-disconnect-001",
        occurred_at=DISCONNECTED_AT,
        reason="local_paper_session_disconnected",
    )
    reconnected = monitor.record_reconnect(
        event_id="resilience-reconnect-001",
        occurred_at=RECONNECTED_AT,
        reason="local_paper_session_reconnected",
    )
    started = monitor.start_reconciliation(
        event_id="resilience-reconcile-start-001",
        occurred_at=RECONCILIATION_STARTED_AT,
        reason="post_reconnect_reconciliation_required",
        snapshot=snapshot(
            snapshot_id="snapshot-start-017",
            captured_at=RECONCILIATION_STARTED_AT,
            broker_state_known=False,
            open_order_ids=(),
            position_symbols=(),
            requires_operator_review=True,
        ),
    )

    assert monitor.requires_reconciliation is True
    assert monitor.blocks_risk_increasing is True
    assert disconnected.blocks_risk_increasing is True
    assert reconnected.blocks_risk_increasing is True
    assert started.requires_reconciliation is True

    completed = monitor.complete_reconciliation(
        event_id="resilience-reconcile-complete-001",
        occurred_at=RECONCILIATION_COMPLETED_AT,
        reason="local_state_matches_known_paper_snapshot",
        snapshot=snapshot(),
    )

    assert completed.requires_reconciliation is False
    assert completed.blocks_risk_increasing is False
    assert monitor.requires_reconciliation is False
    assert monitor.blocks_risk_increasing is False

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        RESILIENCE_DISCONNECT_EVENT_TYPE,
        RESILIENCE_RECONNECT_EVENT_TYPE,
        RESILIENCE_RECONCILIATION_STARTED_EVENT_TYPE,
        RESILIENCE_RECONCILIATION_COMPLETED_EVENT_TYPE,
    ]
    assert [record.timestamp for record in records] == [
        DISCONNECTED_AT,
        RECONNECTED_AT,
        RECONCILIATION_STARTED_AT,
        RECONCILIATION_COMPLETED_AT,
    ]
    assert records[-1].payload == completed.to_json_dict()


def test_resilience_monitor_replays_matching_duplicates_and_rejects_conflicts(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    monitor = ResilienceMonitor(journal)

    first = monitor.record_disconnect(
        event_id="resilience-duplicate-001",
        occurred_at=DISCONNECTED_AT,
        reason="local_paper_session_disconnected",
    )
    replayed = monitor.record_disconnect(
        event_id="resilience-duplicate-001",
        occurred_at=DISCONNECTED_AT,
        reason="local_paper_session_disconnected",
    )

    assert replayed == first
    assert len(journal.read_all()) == 1

    with pytest.raises(ResilienceError, match="conflicting duplicate"):
        monitor.record_disconnect(
            event_id="resilience-duplicate-001",
            occurred_at=DISCONNECTED_AT,
            reason="different_disconnect_reason",
        )

    assert len(journal.read_all()) == 1


def test_reconnect_reconciliation_chaos_scenario_blocks_stale_and_unknown_state(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    result = run_reconnect_reconciliation_chaos_scenario(
        journal=journal,
        scenario_id="chaos-017",
        policy=policy(),
        stale_market_data_request=risk_request(
            request_id="risk-stale-017",
            market_data_timestamp=STALE_MARKET_DATA,
        ),
        unknown_state_request=risk_request(
            request_id="risk-unknown-017",
            broker_state_known=False,
        ),
    )

    assert result.scenario_id == "chaos-017"
    assert result.stale_market_data_decision.result == "blocked"
    assert (
        result.stale_market_data_decision.check_by_name("market_data_freshness").reason
        == "market_data_stale"
    )
    assert result.unknown_state_decision.result == "blocked"
    assert (
        result.unknown_state_decision.check_by_name("broker_state_known").reason
        == "unknown_broker_state_blocks_risk_increase"
    )
    assert result.requires_reconciliation is False
    assert result.blocks_risk_increasing is False

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        RESILIENCE_DISCONNECT_EVENT_TYPE,
        RESILIENCE_RECONNECT_EVENT_TYPE,
        RESILIENCE_UNKNOWN_BROKER_STATE_EVENT_TYPE,
        RESILIENCE_RECONCILIATION_STARTED_EVENT_TYPE,
        "risk.decision.evaluated",
        "risk.decision.evaluated",
        RESILIENCE_RECONCILIATION_COMPLETED_EVENT_TYPE,
        RESILIENCE_CHAOS_SCENARIO_EVENT_TYPE,
    ]
    assert records[-1].payload == result.to_json_dict()


def test_resilience_payloads_and_module_exclude_credentials_network_and_submission(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    monitor = ResilienceMonitor(journal)
    event = monitor.record_reconnect(
        event_id="resilience-safe-001",
        occurred_at=RECONNECTED_AT,
        reason="local_paper_session_reconnected",
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
        "socket",
        "submit",
        "token",
        "transmit",
    }
    payloads = [
        event.to_json_dict(),
        *(record.payload for record in journal.read_all()),
    ]
    for payload in payloads:
        assert forbidden_keys.isdisjoint(_all_payload_keys(payload))

    source = inspect.getsource(resilience).lower()
    forbidden_source_tokens = [
        "import socket",
        "from socket",
        "ibapi",
        "ib_insync",
        "open_connection",
        "create_connection",
        "submit_order",
        "transmit_order",
        "place_order",
    ]
    for token in forbidden_source_tokens:
        assert token not in source


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
