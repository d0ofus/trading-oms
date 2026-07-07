from __future__ import annotations

import math
from typing import Any

import pytest

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.fake_broker import (
    BrokerOrderRequest,
    BrokerOrderTransition,
    FakeBroker,
    FakeBrokerConfig,
    FakeBrokerError,
)

REQUESTED_AT = "2026-07-06T00:02:00Z"
FILLED_AT = "2026-07-06T00:02:05Z"
CANCELLED_AT = "2026-07-06T00:02:10Z"
REJECTED_AT = "2026-07-06T00:02:15Z"


def order_request(**overrides) -> BrokerOrderRequest:
    values = {
        "client_order_id": "client-001",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "order_type": "market",
        "reference_price": 100.0,
        "requested_at": REQUESTED_AT,
        "risk_decision_id": "risk-001",
        "risk_decision_result": "passed",
        "approval_reference": "manual-approval-001",
    }
    values.update(overrides)
    return BrokerOrderRequest(**values)


def test_fake_broker_accepts_order_acknowledges_and_journals_transition(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    broker = FakeBroker(journal)

    transitions = broker.accept_order(order_request())

    assert transitions == (
        BrokerOrderTransition(
            client_order_id="client-001",
            fake_broker_order_id="fake-client-001",
            symbol="AAPL",
            side="buy",
            quantity=10,
            state="acknowledged",
            occurred_at=REQUESTED_AT,
            reason="order_acknowledged",
            cumulative_filled_quantity=0,
            leaves_quantity=10,
            order=order_request().to_json_dict(),
        ),
    )
    assert broker.current_state("client-001") == "acknowledged"

    records = journal.read_all()
    assert len(records) == 1
    assert records[0].event_type == "fake_broker.order.transitioned"
    assert records[0].timestamp == REQUESTED_AT
    assert records[0].payload == transitions[0].to_json_dict()


def test_fake_broker_immediate_fill_mode_is_deterministic_and_journaled(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    broker = FakeBroker(journal, FakeBrokerConfig(fill_mode="fill_immediately"))

    transitions = broker.accept_order(
        order_request(order_type="limit", limit_price=99.5),
    )

    assert [transition.state for transition in transitions] == ["acknowledged", "filled"]
    assert transitions[1].occurred_at == REQUESTED_AT
    assert transitions[1].reason == "configured_immediate_fill"
    assert transitions[1].cumulative_filled_quantity == 10
    assert transitions[1].leaves_quantity == 0
    assert transitions[1].fill_price == 99.5
    assert broker.current_state("client-001") == "filled"

    records = journal.read_all()
    assert [record.sequence for record in records] == [1, 2]
    assert [record.payload for record in records] == [
        transition.to_json_dict() for transition in transitions
    ]


def test_fake_broker_can_fill_acknowledged_order_deterministically(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    broker = FakeBroker(journal)
    broker.accept_order(order_request())

    fill = broker.fill_order("client-001", filled_at=FILLED_AT, fill_price=101.25)

    assert fill == BrokerOrderTransition(
        client_order_id="client-001",
        fake_broker_order_id="fake-client-001",
        symbol="AAPL",
        side="buy",
        quantity=10,
        state="filled",
        occurred_at=FILLED_AT,
        reason="manual_fill",
        cumulative_filled_quantity=10,
        leaves_quantity=0,
        fill_price=101.25,
        order=order_request().to_json_dict(),
    )
    assert broker.current_state("client-001") == "filled"
    assert [record.payload["state"] for record in journal.read_all()] == [
        "acknowledged",
        "filled",
    ]


def test_fake_broker_can_cancel_acknowledged_order_deterministically(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    broker = FakeBroker(journal)
    broker.accept_order(order_request())

    cancel = broker.cancel_order("client-001", cancelled_at=CANCELLED_AT)

    assert cancel.state == "cancelled"
    assert cancel.reason == "cancel_requested"
    assert cancel.cumulative_filled_quantity == 0
    assert cancel.leaves_quantity == 0
    assert broker.current_state("client-001") == "cancelled"
    assert [record.payload["state"] for record in journal.read_all()] == [
        "acknowledged",
        "cancelled",
    ]


def test_fake_broker_can_reject_order_explicitly_and_journal_rejection(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    broker = FakeBroker(journal)

    rejection = broker.reject_order(
        order_request(),
        rejected_at=REJECTED_AT,
        reason="simulation_reject",
    )

    assert rejection.state == "rejected"
    assert rejection.occurred_at == REJECTED_AT
    assert rejection.reason == "simulation_reject"
    assert rejection.cumulative_filled_quantity == 0
    assert rejection.leaves_quantity == 0
    assert broker.current_state("client-001") == "rejected"
    assert journal.read_all()[0].payload == rejection.to_json_dict()


def test_fake_broker_blocks_duplicate_client_order_ids_without_new_transition(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")
    broker = FakeBroker(journal)
    broker.accept_order(order_request())

    with pytest.raises(FakeBrokerError, match="client_order_id already exists"):
        broker.accept_order(order_request())

    assert len(journal.read_all()) == 1


@pytest.mark.parametrize(
    ("operation", "match"),
    [
        ("fill_unknown", "unknown client_order_id"),
        ("cancel_unknown", "unknown client_order_id"),
        ("fill_closed", "must be acknowledged"),
        ("cancel_closed", "must be acknowledged"),
    ],
)
def test_fake_broker_rejects_invalid_state_transitions(
    operation: str,
    match: str,
    tmp_path,
) -> None:
    broker = FakeBroker(JsonlEventJournal(tmp_path / "events.jsonl"))

    if operation == "fill_unknown":
        with pytest.raises(FakeBrokerError, match=match):
            broker.fill_order("missing-001", filled_at=FILLED_AT)
        return

    if operation == "cancel_unknown":
        with pytest.raises(FakeBrokerError, match=match):
            broker.cancel_order("missing-001", cancelled_at=CANCELLED_AT)
        return

    broker.accept_order(order_request())
    broker.fill_order("client-001", filled_at=FILLED_AT)

    if operation == "fill_closed":
        with pytest.raises(FakeBrokerError, match=match):
            broker.fill_order("client-001", filled_at=FILLED_AT)
        return

    with pytest.raises(FakeBrokerError, match=match):
        broker.cancel_order("client-001", cancelled_at=CANCELLED_AT)


def test_fake_broker_transition_payload_has_no_live_routing_or_secret_fields(tmp_path) -> None:
    broker = FakeBroker(JsonlEventJournal(tmp_path / "events.jsonl"))

    transition = broker.accept_order(order_request())[0]

    forbidden_keys = {
        "account",
        "broker_host",
        "broker_port",
        "certificate",
        "credential",
        "destination",
        "host",
        "password",
        "private_key",
        "route",
        "secret",
        "socket",
        "token",
        "transmit",
    }
    assert forbidden_keys.isdisjoint(_all_payload_keys(transition.to_json_dict()))


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"client_order_id": ""}, "client_order_id"),
        ({"client_order_id": " client-001"}, "client_order_id"),
        ({"symbol": "aapl"}, "symbol"),
        ({"side": "hold"}, "side"),
        ({"quantity": 0}, "quantity"),
        ({"quantity": 1.5}, "quantity"),
        ({"order_type": "stop"}, "order_type"),
        ({"reference_price": 0.0}, "reference_price"),
        ({"reference_price": math.nan}, "reference_price"),
        ({"requested_at": "not-a-date"}, "requested_at"),
        ({"requested_at": "2026-07-06T00:02:00"}, "requested_at"),
        ({"risk_decision_id": ""}, "risk_decision_id"),
        ({"risk_decision_result": "blocked"}, "risk_decision_result"),
        ({"approval_reference": ""}, "approval_reference"),
        ({"order_type": "limit", "limit_price": None}, "limit_price"),
        ({"order_type": "market", "limit_price": 100.0}, "limit_price"),
        ({"order_type": "limit", "limit_price": 0.0}, "limit_price"),
        ({"order_type": "limit", "limit_price": math.inf}, "limit_price"),
    ],
)
def test_fake_broker_order_request_rejects_invalid_values(
    request_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(FakeBrokerError, match=match):
        order_request(**request_kwargs)


@pytest.mark.parametrize(
    ("config_kwargs", "match"),
    [
        ({"fill_mode": "random"}, "fill_mode"),
        ({"schema_version": 2}, "schema_version"),
    ],
)
def test_fake_broker_config_rejects_invalid_values(
    config_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(FakeBrokerError, match=match):
        FakeBrokerConfig(**config_kwargs)


@pytest.mark.parametrize(
    ("transition_kwargs", "match"),
    [
        ({"state": "submitted"}, "state"),
        ({"occurred_at": "2026-07-06T00:02:00"}, "occurred_at"),
        ({"cumulative_filled_quantity": -1}, "cumulative_filled_quantity"),
        ({"leaves_quantity": -1}, "leaves_quantity"),
        (
            {"state": "acknowledged", "cumulative_filled_quantity": 1, "leaves_quantity": 9},
            "acknowledged",
        ),
        (
            {
                "state": "filled",
                "cumulative_filled_quantity": 10,
                "leaves_quantity": 0,
                "fill_price": None,
            },
            "fill_price",
        ),
        (
            {
                "state": "filled",
                "cumulative_filled_quantity": 10,
                "leaves_quantity": 0,
                "fill_price": math.nan,
            },
            "fill_price",
        ),
        ({"state": "cancelled", "leaves_quantity": 1}, "cancelled"),
        (
            {"state": "rejected", "cumulative_filled_quantity": 1, "leaves_quantity": 0},
            "rejected",
        ),
    ],
)
def test_fake_broker_transition_rejects_invalid_values(
    transition_kwargs: dict[str, Any],
    match: str,
) -> None:
    values = {
        "client_order_id": "client-001",
        "fake_broker_order_id": "fake-client-001",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "state": "acknowledged",
        "occurred_at": REQUESTED_AT,
        "reason": "order_acknowledged",
        "cumulative_filled_quantity": 0,
        "leaves_quantity": 10,
        "order": order_request().to_json_dict(),
    }
    values.update(transition_kwargs)

    with pytest.raises(FakeBrokerError, match=match):
        BrokerOrderTransition(**values)


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
