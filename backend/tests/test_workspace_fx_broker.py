from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_workspace_fx_policy import fx_contract, fx_document

from trading_oms_backend.workspace.broker_fx import PaperFX
from trading_oms_backend.workspace.fx_policy import compatibility
from trading_oms_backend.workspace.store import now


def adapter():
    gateway = PaperFX()
    gateway._contracts = {
        14433401: SimpleNamespace(secType="CASH", exchange="IDEALPRO", symbol="AUD", currency="USD")
    }
    gateway._accounts = ["paper-fixture"]
    gateway._require_paper = lambda: None
    gateway.sent = []
    gateway.client = SimpleNamespace(placeOrder=lambda *args: gateway.sent.append(args))
    return gateway


def intent(purpose="entry"):
    plan = compatibility(fx_contract(), fx_document())["plan"]
    return {
        "id": "a" * 32,
        "broker_id": 100,
        "conid": 14433401,
        "purpose": purpose,
        "execution": "fx_breakout",
        "fx_plan": plan,
        "quantity": "25000",
        "stop": "0.65",
        "limit": "0.65",
        "protection_intent": True,
        "approved_sizing": {"quantity": "25000", "notional": None, "risk": None},
        "risk_limits": {"notional": None, "planned_stop_risk": None},
        "valuation": {
            "notional": "16250",
            "risk": "162.5",
            "checked_at": now(),
            "risk_policy": "paper_stock_v2",
        },
    }


def test_fx_market_ioc_and_bid_ask_stop_are_explicit():
    gateway = adapter()
    gateway.submit_fx(intent())
    order = gateway.sent[-1][2]
    assert (order.action, order.orderType, order.tif, order.totalQuantity) == (
        "BUY",
        "MKT",
        "IOC",
        Decimal(25000),
    )
    gateway.submit_fx(intent("protection"))
    order = gateway.sent[-1][2]
    assert (order.action, order.orderType, order.triggerMethod) == ("SELL", "STP", 4)


def test_fx_never_transmits_without_paper_guard_or_matching_identity():
    gateway = adapter()
    gateway._require_paper = lambda: (_ for _ in ()).throw(ValueError("paper required"))
    with pytest.raises(ValueError, match="paper"):
        gateway.submit_fx(intent())
    assert not gateway.sent
    gateway._require_paper = lambda: None
    gateway._contracts[14433401].exchange = "FXCONV"
    with pytest.raises(ValueError, match="identity"):
        gateway.submit_fx(intent())
    assert not gateway.sent


def test_fx_invalid_quantity_or_missing_protection_cannot_transmit():
    gateway = adapter()
    for updates in ({"quantity": "0"}, {"quantity": "1.1"}, {"protection_intent": False}):
        with pytest.raises(ValueError):
            gateway.submit_fx({**intent(), **updates})
    assert not gateway.sent


def test_fx_residual_exit_uses_exact_quantity_and_current_deadline():
    gateway = adapter()
    expires = (datetime.now(UTC) + timedelta(seconds=10)).strftime("%Y%m%d-%H:%M:%S")
    request = {**intent("exit"), "quantity": "7", "good_till_date": expires}
    gateway.submit_fx(request)
    order = gateway.sent[-1][2]
    assert (order.totalQuantity, order.orderType, order.tif) == (Decimal(7), "LMT", "GTD")
    assert order.goodTillDate == expires
    with pytest.raises(ValueError, match="deadline"):
        gateway.submit_fx({**request, "good_till_date": "20000101-00:00:00"})
    assert len(gateway.sent) == 1
