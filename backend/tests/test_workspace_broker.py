import queue
import sys
import types
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from trading_oms_backend.workspace.broker import PaperGateway


class Client:
    def isConnected(self):
        return True


def test_endpoint_attestation_cannot_accept_live_or_multiple_accounts():
    gateway = PaperGateway(queue.Queue(2))
    gateway.client = Client()
    gateway._next_id = 1
    for accounts in [("U000000",), ("DU000000", "DU000001"), ()]:
        gateway._accounts = accounts
        with pytest.raises(ValueError):
            gateway.attest()
        with pytest.raises(ValueError):
            gateway.submit_bracket({})


def test_overflow_invalidates_paper_dispatch_permission():
    gateway = PaperGateway(queue.Queue(1))
    gateway.client = Client()
    gateway._next_id = 1
    gateway._accounts = ("DU000000",)  # Synthetic fixture, never a real identifier.
    gateway.attest()
    gateway.emit("heartbeat")
    gateway.emit("heartbeat")
    assert gateway.overflow.is_set()
    with pytest.raises(ValueError):
        gateway.submit_bracket({})


def test_restart_never_inherits_attestation():
    gateway = PaperGateway(queue.Queue(2))
    assert gateway._attested is False
    with pytest.raises(ValueError):
        gateway._require_paper()


def test_bracket_transmission_and_gtd_are_exact_and_live_context_stops_all_orders(monkeypatch):
    module = types.ModuleType("ibapi.order")
    module.Order = type("Order", (), {})
    monkeypatch.setitem(sys.modules, "ibapi.order", module)
    gateway = PaperGateway(queue.Queue(20))
    sent = []
    gateway.client = SimpleNamespace(
        isConnected=lambda: True, placeOrder=lambda identity, contract, order: sent.append(order)
    )
    gateway._next_id = 100
    gateway._accounts = ("DU000000",)
    gateway._contracts[1] = SimpleNamespace(secType="STK", currency="USD")
    gateway.attest()
    intent = {
        "id": "a" * 32,
        "broker_id": 100,
        "conid": 1,
        "quantity": 2,
        "limit": "100",
        "stop": "99",
        "target": "102",
        "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    }
    gateway.submit_bracket(intent)
    assert [order.orderId for order in sent] == [100, 101, 102]
    assert [order.transmit for order in sent] == [False, False, True]
    assert sent[0].tif == "GTD"
    assert sent[-1].tif == "GTC"
    assert sent[-1].ocaType == 2
    assert sent[-1].parentId == 100
    gateway._accounts = ("U000000",)
    for action in (gateway.submit_bracket, gateway.submit_exit, gateway.submit_protection):
        with pytest.raises(ValueError):
            action(intent)
    assert len(sent) == 3


def test_expired_durable_entry_is_never_transmitted(monkeypatch):
    module = types.ModuleType("ibapi.order")
    module.Order = type("Order", (), {})
    monkeypatch.setitem(sys.modules, "ibapi.order", module)
    gateway = PaperGateway(queue.Queue(2))
    sent = []
    gateway.client = SimpleNamespace(
        isConnected=lambda: True, placeOrder=lambda *args: sent.append(args)
    )
    gateway._next_id = 100
    gateway._accounts = ("DU000000",)
    gateway._contracts[1] = SimpleNamespace(secType="STK", currency="USD")
    gateway.attest()
    with pytest.raises(ValueError, match="deadline"):
        gateway.submit_bracket(
            {
                "id": "a" * 32,
                "broker_id": 100,
                "conid": 1,
                "quantity": 1,
                "limit": "100",
                "stop": "99",
                "expires_at": "2000-01-01T00:00:00+00:00",
            }
        )
    assert not sent
