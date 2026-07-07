from __future__ import annotations

import math

import pytest

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.risk_engine import (
    ProtectiveOrderPlan,
    RiskEngineError,
    RiskEvaluationRequest,
    RiskPolicy,
    evaluate_risk,
)

EVALUATED_AT = "2026-07-06T00:01:00Z"
FRESH_MARKET_DATA = "2026-07-06T00:00:45Z"
STALE_MARKET_DATA = "2026-07-05T23:59:00Z"


def policy(**overrides) -> RiskPolicy:
    values = {
        "max_order_quantity": 100,
        "max_order_notional": 10_000.0,
        "max_market_data_age_seconds": 30,
        "allowed_symbols": ("AAPL", "MSFT"),
    }
    values.update(overrides)
    return RiskPolicy(**values)


def protective_plan(**overrides) -> ProtectiveOrderPlan:
    values = {"kind": "stop_loss", "stop_price": 95.0}
    values.update(overrides)
    return ProtectiveOrderPlan(**values)


def request(**overrides) -> RiskEvaluationRequest:
    values = {
        "request_id": "risk-001",
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


def test_risk_engine_passes_protected_risk_increasing_request_and_journals_decision(
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    decision = evaluate_risk(request(), policy(), journal)

    assert decision.result == "passed"
    assert decision.request_id == "risk-001"
    assert [check.status for check in decision.checks] == ["passed"] * 7
    assert [check.name for check in decision.checks] == [
        "allowed_symbol",
        "duplicate_request",
        "market_data_freshness",
        "broker_state_known",
        "max_quantity",
        "max_notional",
        "protective_order",
    ]

    records = journal.read_all()
    assert len(records) == 1
    assert records[0].event_type == "risk.decision.evaluated"
    assert records[0].timestamp == EVALUATED_AT
    assert records[0].payload == decision.to_json_dict()


def test_risk_engine_decision_payload_has_no_broker_routing_or_submission_fields(tmp_path) -> None:
    decision = evaluate_risk(
        request(),
        policy(),
        JsonlEventJournal(tmp_path / "events.jsonl"),
    )

    forbidden_keys = {
        "account",
        "broker",
        "broker_order_id",
        "client_order_id",
        "destination",
        "route",
        "submit",
        "transmit",
    }
    assert forbidden_keys.isdisjoint(decision.to_json_dict())


@pytest.mark.parametrize(
    ("risk_request", "failed_check"),
    [
        (
            request(market_data_timestamp=STALE_MARKET_DATA),
            "market_data_freshness",
        ),
        (
            request(broker_state_known=False),
            "broker_state_known",
        ),
        (
            request(existing_request_ids=frozenset({"risk-001"})),
            "duplicate_request",
        ),
        (
            request(symbol="TSLA"),
            "allowed_symbol",
        ),
        (
            request(quantity=101),
            "max_quantity",
        ),
        (
            request(quantity=100, reference_price=101.0),
            "max_notional",
        ),
        (
            request(protective_order=None),
            "protective_order",
        ),
        (
            request(protective_order=protective_plan(stop_price=105.0)),
            "protective_order",
        ),
        (
            request(side="sell", protective_order=protective_plan(stop_price=95.0)),
            "protective_order",
        ),
    ],
)
def test_risk_engine_blocks_failed_checks(
    risk_request: RiskEvaluationRequest,
    failed_check: str,
    tmp_path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    decision = evaluate_risk(risk_request, policy(), journal)

    assert decision.result == "blocked"
    assert failed_check in [check.name for check in decision.failed_checks()]
    assert journal.read_all()[0].payload == decision.to_json_dict()


def test_risk_engine_allows_protective_exception_when_explicitly_approved(tmp_path) -> None:
    decision = evaluate_risk(
        request(protective_order=None, protective_exception_approved=True),
        policy(),
        JsonlEventJournal(tmp_path / "events.jsonl"),
    )

    assert decision.result == "passed"
    assert decision.check_by_name("protective_order").status == "passed"
    assert decision.check_by_name("protective_order").reason == "approved_exception"


def test_risk_engine_allows_risk_reducing_request_with_unknown_broker_state(tmp_path) -> None:
    decision = evaluate_risk(
        request(
            risk_intent="reduce",
            broker_state_known=False,
            protective_order=None,
        ),
        policy(),
        JsonlEventJournal(tmp_path / "events.jsonl"),
    )

    assert decision.result == "passed"
    assert decision.check_by_name("broker_state_known").reason == "not_risk_increasing"
    assert decision.check_by_name("protective_order").reason == "not_risk_increasing"


@pytest.mark.parametrize(
    ("policy_kwargs", "match"),
    [
        ({"max_order_quantity": 0}, "max_order_quantity"),
        ({"max_order_quantity": 1.5}, "max_order_quantity"),
        ({"max_order_notional": 0.0}, "max_order_notional"),
        ({"max_order_notional": math.nan}, "max_order_notional"),
        ({"max_market_data_age_seconds": 0}, "max_market_data_age_seconds"),
        ({"allowed_symbols": ("aapl",)}, "allowed_symbols"),
        ({"allowed_symbols": ("AAPL", "AAPL")}, "allowed_symbols"),
    ],
)
def test_risk_policy_rejects_invalid_values(policy_kwargs: dict, match: str) -> None:
    with pytest.raises(RiskEngineError, match=match):
        policy(**policy_kwargs)


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"request_id": ""}, "request_id"),
        ({"request_id": " risk-001"}, "request_id"),
        ({"symbol": "aapl"}, "symbol"),
        ({"side": "hold"}, "side"),
        ({"risk_intent": "neutral"}, "risk_intent"),
        ({"quantity": 0}, "quantity"),
        ({"quantity": 1.5}, "quantity"),
        ({"reference_price": 0.0}, "reference_price"),
        ({"reference_price": math.inf}, "reference_price"),
        ({"market_data_timestamp": "not-a-date"}, "market_data_timestamp"),
        ({"market_data_timestamp": "2026-07-06T00:00:45"}, "market_data_timestamp"),
        ({"evaluated_at": "not-a-date"}, "evaluated_at"),
        ({"broker_state_known": "yes"}, "broker_state_known"),
        ({"protective_exception_approved": "yes"}, "protective_exception_approved"),
        ({"existing_request_ids": {" risk-001"}}, "existing_request_ids"),
    ],
)
def test_risk_request_rejects_invalid_values(request_kwargs: dict, match: str) -> None:
    with pytest.raises(RiskEngineError, match=match):
        request(**request_kwargs)


@pytest.mark.parametrize(
    ("plan_kwargs", "match"),
    [
        ({"kind": ""}, "kind"),
        ({"kind": " stop_loss"}, "kind"),
        ({"stop_price": 0.0}, "stop_price"),
        ({"stop_price": math.inf}, "stop_price"),
    ],
)
def test_protective_plan_rejects_invalid_values(plan_kwargs: dict, match: str) -> None:
    with pytest.raises(RiskEngineError, match=match):
        protective_plan(**plan_kwargs)
