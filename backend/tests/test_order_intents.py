from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.order_intents import (
    OrderIntentError,
    OrderIntentProposal,
    OrderIntentProposalBook,
    OrderIntentProposalRequest,
    OrderIntentProtectivePlan,
)


def test_order_intent_book_creates_non_routable_proposal_and_journals_it(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = OrderIntentProposalBook(journal)

    proposal = book.propose(_proposal_request())

    assert proposal.to_json_dict() == {
        "schema_version": 1,
        "proposal_id": "intent-001",
        "status": "proposed_non_routable",
        "source_signal_reference": "journal_sequence:1",
        "symbol": "AAPL",
        "side": "buy",
        "risk_intent": "increase",
        "quantity": 10,
        "order_type": "limit",
        "reference_price": 102.0,
        "limit_price": 102.25,
        "proposed_at": "2026-07-08T13:45:05Z",
        "protective_order_plan": {
            "schema_version": 1,
            "kind": "stop_loss",
            "stop_price": 98.0,
        },
        "protective_exception_reference": None,
        "journal_references": ["journal_sequence:1"],
    }

    records = journal.read_all()
    assert len(records) == 1
    assert records[0].event_type == "order_intent.proposed"
    assert records[0].timestamp == "2026-07-08T13:45:05Z"
    assert records[0].payload == proposal.to_json_dict()


def test_order_intent_create_is_idempotent_for_same_payload_without_new_journal_record(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = OrderIntentProposalBook(journal)

    first = book.propose(_proposal_request())
    second = book.propose(_proposal_request())

    assert second == first
    assert len(journal.read_all()) == 1


def test_order_intent_rejects_conflicting_duplicate_proposal_id(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = OrderIntentProposalBook(journal)
    book.propose(_proposal_request())

    with pytest.raises(OrderIntentError, match="conflicting duplicate proposal_id"):
        book.propose(_proposal_request(quantity=11))

    assert len(journal.read_all()) == 1


def test_order_intent_rejects_duplicate_source_signal_reference(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = OrderIntentProposalBook(journal)
    book.propose(_proposal_request())

    with pytest.raises(OrderIntentError, match="source signal"):
        book.propose(_proposal_request(proposal_id="intent-002", quantity=11))

    assert len(journal.read_all()) == 1


def test_order_intent_allows_approved_protective_exception_reference(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = OrderIntentProposalBook(journal)

    proposal = book.propose(
        _proposal_request(
            proposal_id="intent-exception-001",
            protective_order_plan=None,
            protective_exception_reference="approved-exception-001",
        ),
    )

    assert proposal.protective_order_plan is None
    assert proposal.protective_exception_reference == "approved-exception-001"
    assert proposal.status == "proposed_non_routable"
    assert len(journal.read_all()) == 1


def test_order_intent_requires_protection_for_risk_increasing_proposals(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = OrderIntentProposalBook(journal)

    with pytest.raises(OrderIntentError, match="protective"):
        book.propose(
            _proposal_request(
                protective_order_plan=None,
                protective_exception_reference=None,
            ),
        )

    assert journal.read_all() == []


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"proposal_id": ""}, "proposal_id"),
        ({"source_signal_reference": "https://example.test/signal"}, "source_signal_reference"),
        ({"symbol": "aapl"}, "symbol"),
        ({"side": "hold"}, "side"),
        ({"risk_intent": "neutral"}, "risk_intent"),
        ({"quantity": 0}, "quantity"),
        ({"order_type": "stop"}, "order_type"),
        ({"reference_price": -1.0}, "reference_price"),
        ({"limit_price": None}, "limit_price"),
        ({"limit_price": 0.0}, "limit_price"),
        ({"proposed_at": "2026-07-08T13:45:05"}, "timezone"),
    ],
)
def test_order_intent_request_rejects_invalid_values(
    request_kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(OrderIntentError, match=match):
        _proposal_request(**request_kwargs)


def test_market_order_must_not_include_limit_price() -> None:
    with pytest.raises(OrderIntentError, match="limit_price"):
        _proposal_request(order_type="market", limit_price=102.25)


def test_order_intent_record_rejects_executable_status() -> None:
    with pytest.raises(OrderIntentError, match="non-routable"):
        OrderIntentProposal(
            proposal_id="intent-001",
            status="submitted",
            source_signal_reference="journal_sequence:1",
            symbol="AAPL",
            side="buy",
            risk_intent="increase",
            quantity=10,
            order_type="limit",
            reference_price=102.0,
            proposed_at="2026-07-08T13:45:05Z",
            protective_order_plan=OrderIntentProtectivePlan(kind="stop_loss", stop_price=98.0),
            protective_exception_reference=None,
            journal_references=("journal_sequence:1",),
            limit_price=102.25,
        )


def test_order_intent_payloads_exclude_broker_routing_approval_and_secret_fields(
    tmp_path: Path,
) -> None:
    proposal = OrderIntentProposalBook(JsonlEventJournal(tmp_path / "journal.jsonl")).propose(
        _proposal_request(),
    )

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "approval_reference",
        "authorization",
        "broker",
        "broker_host",
        "broker_port",
        "credential",
        "host",
        "password",
        "port",
        "private_key",
        "risk_decision_id",
        "route",
        "secret",
        "socket",
        "submit",
        "token",
        "transmit",
    }
    assert forbidden_keys.isdisjoint(_all_payload_keys(proposal.to_json_dict()))


def test_order_intents_module_does_not_define_transport_or_http_behavior() -> None:
    import trading_oms_backend.order_intents as order_intents

    source = inspect.getsource(order_intents).lower()
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


def _proposal_request(**overrides: Any) -> OrderIntentProposalRequest:
    values = {
        "proposal_id": "intent-001",
        "source_signal_reference": "journal_sequence:1",
        "symbol": "AAPL",
        "side": "buy",
        "risk_intent": "increase",
        "quantity": 10,
        "order_type": "limit",
        "reference_price": 102.0,
        "limit_price": 102.25,
        "proposed_at": "2026-07-08T13:45:05Z",
        "protective_order_plan": OrderIntentProtectivePlan(
            kind="stop_loss",
            stop_price=98.0,
        ),
        "protective_exception_reference": None,
    }
    values.update(overrides)
    return OrderIntentProposalRequest(**values)


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
