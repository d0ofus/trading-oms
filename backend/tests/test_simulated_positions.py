from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.fake_broker import BrokerOrderRequest, BrokerOrderTransition
from trading_oms_backend.simulated_positions import (
    POSITION_UPDATED_EVENT_TYPE,
    PositionProtectionError,
    PositionUpdateRequest,
    SimulatedPosition,
    SimulatedPositionBook,
)


def test_position_book_records_filled_position_with_expected_protection(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulatedPositionBook(journal)

    result = book.record_fill(
        PositionUpdateRequest(
            update_id="position-update-001",
            position_id="position-AAPL",
            fill_transition=filled_transition(),
            expected_protection_present=True,
            expected_protection_kind="stop_loss",
            monitored_at="2026-07-08T13:46:05Z",
        ),
    )

    assert result.position == SimulatedPosition(
        position_id="position-AAPL",
        symbol="AAPL",
        quantity=10,
        average_price=102.0,
        protection_status="expected_protection_present",
        expected_protection_kind="stop_loss",
        updated_at="2026-07-08T13:46:05Z",
        source_fill_reference="fake-client-001",
        journal_references=("journal_sequence:1",),
    )
    assert result.alert_intent is None
    assert result.alert_dispatch is None
    assert [record.event_type for record in journal.read_all()] == [POSITION_UPDATED_EVENT_TYPE]


def test_position_book_creates_critical_alert_when_expected_protection_is_missing(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulatedPositionBook(journal)

    result = book.record_fill(
        PositionUpdateRequest(
            update_id="position-update-001",
            position_id="position-AAPL",
            fill_transition=filled_transition(),
            expected_protection_present=False,
            expected_protection_kind="stop_loss",
            monitored_at="2026-07-08T13:46:05Z",
        ),
    )

    assert result.position.protection_status == "missing_expected_protection"
    assert result.alert_intent is not None
    assert result.alert_intent.severity == "critical"
    assert result.alert_intent.channel == "local"
    assert result.alert_dispatch is not None
    assert result.alert_dispatch.status == "recorded"

    assert [record.event_type for record in journal.read_all()] == [
        POSITION_UPDATED_EVENT_TYPE,
        "alert.intent.created",
        "alert.dispatch.recorded",
    ]


def test_position_book_is_idempotent_for_same_update_payload(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulatedPositionBook(journal)
    request = PositionUpdateRequest(
        update_id="position-update-001",
        position_id="position-AAPL",
        fill_transition=filled_transition(),
        expected_protection_present=False,
        expected_protection_kind="stop_loss",
        monitored_at="2026-07-08T13:46:05Z",
    )

    first = book.record_fill(request)
    event_count = len(journal.read_all())
    second = book.record_fill(request)

    assert second == first
    assert len(journal.read_all()) == event_count


def test_position_book_rejects_conflicting_duplicate_update_id(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulatedPositionBook(journal)
    book.record_fill(
        PositionUpdateRequest(
            update_id="position-update-001",
            position_id="position-AAPL",
            fill_transition=filled_transition(),
            expected_protection_present=True,
            expected_protection_kind="stop_loss",
            monitored_at="2026-07-08T13:46:05Z",
        ),
    )

    with pytest.raises(PositionProtectionError, match="conflicting update_id"):
        book.record_fill(
            PositionUpdateRequest(
                update_id="position-update-001",
                position_id="position-AAPL",
                fill_transition=filled_transition(fill_price=103.0),
                expected_protection_present=True,
                expected_protection_kind="stop_loss",
                monitored_at="2026-07-08T13:46:05Z",
            ),
        )


def test_position_book_rejects_non_filled_broker_transition(tmp_path: Path) -> None:
    book = SimulatedPositionBook(JsonlEventJournal(tmp_path / "journal.jsonl"))

    with pytest.raises(PositionProtectionError, match="filled"):
        book.record_fill(
            PositionUpdateRequest(
                update_id="position-update-001",
                position_id="position-AAPL",
                fill_transition=filled_transition(state="acknowledged"),
                expected_protection_present=True,
                expected_protection_kind="stop_loss",
                monitored_at="2026-07-08T13:46:05Z",
            ),
        )


def test_position_alert_payloads_exclude_broker_routing_network_and_secret_fields(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulatedPositionBook(journal)
    result = book.record_fill(
        PositionUpdateRequest(
            update_id="position-update-001",
            position_id="position-AAPL",
            fill_transition=filled_transition(),
            expected_protection_present=False,
            expected_protection_kind="stop_loss",
            monitored_at="2026-07-08T13:46:05Z",
        ),
    )

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker_host",
        "broker_port",
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
    assert forbidden_keys.isdisjoint(_all_payload_keys(result.position.to_json_dict()))
    assert result.alert_dispatch is not None
    assert forbidden_keys.isdisjoint(_all_payload_keys(result.alert_dispatch.to_json_dict()))


def test_simulated_positions_module_does_not_define_transport_or_http_behavior() -> None:
    import trading_oms_backend.simulated_positions as simulated_positions

    source = inspect.getsource(simulated_positions).lower()
    forbidden_source_tokens = [
        "@app.post",
        "@app.put",
        "@app.patch",
        "@app.delete",
        "import socket",
        "from socket",
        "httpx",
        "requests",
        "ibapi",
        "ib_insync",
        "open_connection",
        "create_connection",
        "place_order",
        "submit_order",
        "transmit_order",
    ]
    for token in forbidden_source_tokens:
        assert token not in source


def filled_transition(
    *,
    state: str = "filled",
    fill_price: float = 102.0,
) -> BrokerOrderTransition:
    order = BrokerOrderRequest(
        client_order_id="client-001",
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="market",
        reference_price=102.0,
        requested_at="2026-07-08T13:46:00Z",
        risk_decision_id="risk-001",
        risk_decision_result="passed",
        approval_reference="manual-simulation-approval-001",
    )
    return BrokerOrderTransition(
        client_order_id="client-001",
        fake_broker_order_id="fake-client-001",
        symbol="AAPL",
        side="buy",
        quantity=10,
        state=state,
        occurred_at="2026-07-08T13:46:00Z",
        reason="configured_simulation_fill",
        cumulative_filled_quantity=(10 if state == "filled" else 0),
        leaves_quantity=(0 if state == "filled" else 10),
        fill_price=(fill_price if state == "filled" else None),
        order=order.to_json_dict(),
    )


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
