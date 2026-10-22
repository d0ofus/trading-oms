from decimal import Decimal
from types import SimpleNamespace

import pytest

from trading_oms_backend.workspace.broker_credit import PaperCredit


def adapter():
    gateway = PaperCredit()
    gateway._require_paper = lambda: None
    gateway._accounts = ["paper-fixture"]
    gateway.epoch = 2
    gateway._credit_previews = {}
    gateway._contracts = {
        12: SimpleNamespace(
            conId=12, secType="CASH", exchange="IDEALPRO", symbol="AUD", currency="USD"
        )
    }
    gateway.sent, gateway.events, gateway.cancelled = [], [], []
    gateway.client = SimpleNamespace(
        placeOrder=lambda *a: gateway.sent.append(a),
        cancelOrder=lambda *a: gateway.cancelled.append(a),
    )
    gateway.emit = lambda kind, **value: gateway.events.append({"type": kind, **value})
    return gateway


def request():
    return {
        "broker_id": 101,
        "key": "a" * 64,
        "epoch": 2,
        "conid": 12,
        "sec_type": "CASH",
        "currency": "USD",
        "route": "IDEALPRO",
        "symbol": "AUD",
        "action": "BUY",
        "order_type": "MKT",
        "quantity": "25000",
        "tif": "IOC",
        "outside_rth": True,
        "price": "0.65",
    }


def test_credit_preview_is_incapable_of_becoming_executable():
    gateway = adapter()
    gateway.preview_credit({**request(), "whatIf": False, "transmit": False})
    _, _, order = gateway.sent[0]
    assert order.whatIf is True
    assert order.totalQuantity == Decimal(25000)
    assert (order.action, order.orderType, order.tif) == ("BUY", "MKT", "IOC")
    assert not hasattr(gateway, "submit")
    gateway._require_paper = lambda: (_ for _ in ()).throw(ValueError("paper required"))
    with pytest.raises(ValueError):
        gateway.preview_credit(request())
    assert len(gateway.sent) == 1


def test_credit_callback_requires_exact_terms_and_redacts_warnings():
    gateway = adapter()
    gateway.preview_credit(request())
    _, contract, order = gateway.sent[0]
    state = SimpleNamespace(
        initMarginChange="100",
        maintMarginChange="80",
        initMarginAfter="200",
        maintMarginAfter="150",
        equityWithLoanAfter="10000",
        warningText="",
        status="PreSubmitted",
    )
    gateway.credit_observation(101, contract, order, state)
    assert gateway.events[-1]["status"] == "accepted"
    assert gateway.events[-1]["initial_change"] == "100"
    assert gateway.cancelled
    gateway.preview_credit({**request(), "broker_id": 102})
    _, contract, order = gateway.sent[-1]
    order.totalQuantity = Decimal(25001)
    state.warningText = "sensitive broker message"
    gateway.credit_observation(102, contract, order, state)
    assert gateway.events[-1]["status"] == "rejected"
    assert gateway.events[-1]["validation_fields"] == ["quantity", "broker_warning"]
    assert "sensitive" not in str(gateway.events)


def test_stale_generation_preview_callback_is_ignored():
    gateway = adapter()
    gateway.preview_credit(request())
    gateway.epoch += 1
    gateway.credit_observation(101, gateway.sent[0][1], gateway.sent[0][2], SimpleNamespace())
    assert not gateway.events


def test_entry_boundary_rejects_missing_or_different_credit_evidence():
    from trading_oms_backend.workspace.credit_policy import POLICY
    from trading_oms_backend.workspace.store import now

    gateway = adapter()
    plan = {"funding_policy": POLICY, "hash": "plan", "family": "spot_fx", "conid": 12}
    intent = {
        "quantity": "25000",
        "valuation": {
            "funding_policy": POLICY,
            "funding_mode": "margin",
            "credit_keys": [],
            "credit_snapshot": {"epoch": 2, "checked_at": now(), "margin_ready": True},
        },
    }
    with pytest.raises(ValueError, match="credit"):
        gateway.validate_credit_intent(plan, intent)
    gateway.preview_credit({**request(), "plan_hash": "plan"})
    _, contract, order = gateway.sent[0]
    state = SimpleNamespace(
        initMarginChange="100",
        maintMarginChange="80",
        initMarginAfter="200",
        maintMarginAfter="150",
        equityWithLoanAfter="10000",
        warningText="",
        status="PreSubmitted",
    )
    gateway.credit_observation(101, contract, order, state)
    intent["valuation"]["credit_keys"] = [request()["key"]]
    gateway.validate_credit_intent(plan, intent)
    intent["quantity"] = "25001"
    with pytest.raises(ValueError, match="credit"):
        gateway.validate_credit_intent(plan, intent)


def test_credit_warning_classification_never_returns_private_text():
    from trading_oms_backend.workspace.credit_policy import CREDIT_DETAILS, credit_category

    category = credit_category("Insufficient margin: synthetic private broker details")
    assert category == "insufficient_funds"
    assert "private" not in CREDIT_DETAILS[category]
    assert credit_category("x" * 4097) == "unknown"


def test_informational_2109_does_not_reject_credit_preview():
    gateway = adapter()
    gateway.preview_credit(request())
    assert gateway.credit_error(101, 2109, "Outside RTH ignored")
    assert gateway._credit_previews[101]["status"] == "pending"
    _, contract, order = gateway.sent[0]
    order.outsideRth = False  # Broker normalization described by 2109.
    state = SimpleNamespace(
        initMarginChange="100",
        maintMarginChange="80",
        initMarginAfter="200",
        maintMarginAfter="150",
        equityWithLoanAfter="10000",
        warningText="",
        status="PreSubmitted",
    )
    gateway.credit_observation(101, contract, order, state)
    assert gateway.events[-1]["status"] == "accepted"


def test_credit_rejection_exposes_code_and_safe_validation_reason():
    gateway = adapter()
    gateway.preview_credit(request())
    gateway.credit_error(101, 201, "Insufficient margin private account details")
    assert gateway.events[-1]["code"] == 201
    assert gateway.events[-1]["category"] == "insufficient_funds"
    assert "private" not in str(gateway.events)
