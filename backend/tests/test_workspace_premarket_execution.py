import importlib
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_workspace_health import healthy_watchdog
from test_workspace_preparation_policy import meta
from test_workspace_stock_execution import StockBroker, fill

from trading_oms_backend.workspace.broker import PaperGateway
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.premarket import broker_deadline
from trading_oms_backend.workspace.stock_strategies import stock_templates
from trading_oms_backend.workspace.store import Conflict, Store, now


class Clock(datetime):
    stamp = datetime(2026, 9, 22, 12, 0, 10, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.stamp.astimezone(tz) if tz else cls.stamp.replace(tzinfo=None)


def fixture(tmp_path, monkeypatch, shares="1"):
    Clock.stamp = datetime(2026, 9, 22, 12, 0, 10, tzinfo=UTC)
    for name in (
        "engine",
        "premarket",
        "stock_engine",
        "store",
        "oca_engine",
        "crypto_engine",
        "data_views",
        "broker_stocks",
        "broker",
        "stock_references",
    ):
        monkeypatch.setattr(
            importlib.import_module("trading_oms_backend.workspace." + name), "datetime", Clock
        )
    e = Engine(Store(tmp_path), StockBroker)
    c = meta()
    c.update(metadata_instance=e.process_identity, metadata_epoch=e.broker.epoch)
    e.contracts[c["conid"]] = c
    e.stock_fee(c["conid"], "1", 0, "operator")
    doc = stock_templates()[-1]["document"]
    doc["settings"].update(notional="1000", sizing="fixed")
    d = e.store.save_draft(None, "Pre-market fixture", doc, 0)
    e.store.publish(d["id"], 1)
    result = e.stock_compatibility(d["id"], 1, c["conid"], "locally_monitored", "premarket_regular")
    r = e.create_run(
        d["id"],
        1,
        c["conid"],
        protection_type="locally_monitored",
        session_mode="premarket_regular",
        execution_plan_revision=result["plan"]["hash"],
        sizing={"shares": shares},
    )
    r.update(
        armed=True,
        authorized_at=(Clock.stamp - timedelta(minutes=2)).isoformat(),
        authorization_id="fixture",
        expires_at="2026-09-22T20:00:00+00:00",
        limits={"shares": 1, "notional": "1000", "planned_stop_risk": "10", "entry_timeout": 30},
    )
    e.store.put("run", r["id"], r)
    e.store.put(
        "stock_trigger",
        r["id"],
        {
            "state": "triggered",
            "candle": "2026-09-22T11:59:00+00:00",
            "expires_at": "2026-09-22T12:01:00+00:00",
        },
    )
    e.data[c["conid"]].update(
        live=True, warm=False, price="600", received_at=now(), source_at=now()
    )
    e.quotes[c["conid"]] = {
        s: {"price": p, "received_at": now()} for s, p in (("bid", "599.99"), ("ask", "600.001"))
    }
    e.premarket_history[c["conid"]].update(status="completed")
    e.market_rules[1] = [{"low": "0", "increment": "0.01"}]
    e.observe({"type": "market_rule", "rule": 1, "increments": e.market_rules[1]})
    e.facts = {"NetLiquidation": "10000", "AvailableFunds": "10000", "GrossPositionValue": "0"}
    for tag in ("CashBalance", "SettledCash"):
        e.currency_facts[(tag, "USD")] = {"value": "10000", "received_at": now()}
    e.connected = e.attested = e.reconciled = e.position_agreement = e.clock_ok = True
    e.reconciled_at = time.monotonic()
    e.server_version, e.next_id = 220, 100
    healthy_watchdog(e)
    return e, r


def enter(e, r):
    e._enter(r, {"stop": Decimal("594"), "target": None}, {"minutes_to_close": 480}, "fixture")
    return e.store.orders()[0]


def test_limit_deadline_reservation_and_sdk_paper_guard(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    o = enter(e, r)
    p = o["payload"]
    assert p["entry_type"] == "LMT" and p["limit"] == "600.01"
    assert p["expires_at"] == "2026-09-22T12:00:40+00:00"
    assert e.store.get("stock_protection", r["id"])["state"] == "awaiting_fill"
    assert not e.owned()
    calls = []
    g = PaperGateway(e.observations)
    g.client = SimpleNamespace(
        isConnected=lambda: True, placeOrder=lambda *args: calls.append(args)
    )
    g._accounts, g._attested = ["DU0000000"], True
    g._contracts[r["conid"]] = SimpleNamespace(
        conId=r["conid"], secType="STK", currency="USD", exchange="NASDAQ"
    )
    g.submit_bracket({**p, **o})
    assert len(calls) == 1
    order = calls[0][2]
    assert order.outsideRth and order.tif == "GTD" and order.orderType == "LMT"
    assert broker_deadline(order.goodTillDate) == datetime.fromisoformat(p["expires_at"])
    calls.clear()
    with pytest.raises(ValueError):
        g.submit_bracket({**p, **o, "entry_type": "MKT"})
    g._accounts = ["U0000000"]
    with pytest.raises(ValueError):
        g.submit_bracket({**p, **o})
    assert not calls


def test_budget_conflict_before_preparation_and_manual_archive_block(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    response = e.stock_compatibility(
        r["strategy_id"],
        1,
        r["conid"],
        "locally_monitored",
        "premarket_regular",
        {"notional": "25", "shares": "1"},
    )
    assert not response["can_prepare"]
    assert "Minimum 1 shares" in response["blockers"][0]
    assert e.store.version(r["strategy_id"], 1)["document"]["settings"]["notional"] == "1000"


def test_history_failure_and_late_callbacks_do_not_poison_regular_history(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    h = e.premarket_history[r["conid"]]
    h.update(status="pending", request=99)
    e._premarket_observation(
        {
            "type": "broker_error",
            "context": "market_data",
            "request": 99,
            "code": 162,
            "reason": "unknown",
        }
    )
    assert h["status"] == "failed" and e.store.get("run", r["id"])["armed"]
    assert not e.data[r["conid"]].get("history_failed")
    e._premarket_queue(r["conid"], force=True)
    assert e._premarket_observation(
        {"type": "history_end", "history_scope": "extended", "request": 99}
    )
    assert e.premarket_history[r["conid"]]["status"] == "queued"


def test_stop_uses_owned_quantity_and_waits_for_cancel_and_reconciliation(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    entry = enter(e, r)
    fill(e, entry, quantity="1", price="600")
    e.store.transition(entry["id"], "filled", {})
    e._stock_sync()
    assert e.store.get("stock_protection", r["id"])["stop"] == "594.00"
    monkeypatch.setattr(e, "_identity_issues", lambda: [])
    monkeypatch.setattr(e, "_fill_agreement_issues", lambda: [])
    e.reconciled = e.position_agreement = True
    e.quotes[r["conid"]]["bid"].update(price="593.99", received_at=now())
    e._stock_trade({"conid": r["conid"], "timestamp": Clock.stamp.timestamp(), "price": "593.99"})
    exit_order = next(o for o in e.store.orders() if o["payload"].get("purpose") == "exit")
    assert exit_order["payload"]["exit_type"] == "LMT"
    assert exit_order["payload"]["quantity"] == "1"
    assert exit_order["payload"]["limit"] == "593.99"
    count = len(e.broker.submitted)
    e._request_exit(r["id"])
    assert len(e.broker.submitted) == count
    e.store.transition(exit_order["id"], "cancel_pending", {})
    e._request_exit(r["id"])
    assert len(e.broker.submitted) == count
    e.store.transition(exit_order["id"], "cancelled", {})
    e._request_exit(r["id"])
    assert len(e.broker.submitted) == count  # Reconciliation still false.
    e.reconciled = e.position_agreement = True
    e.quotes[r["conid"]]["bid"]["price"] = "593.50"
    e._request_exit(r["id"])
    assert len(e.broker.submitted) == count + 1
    assert e.broker.submitted[-1]["limit"] == "593.50"


def test_rollback_closure_and_gap_do_not_submit(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("OMS_DISABLE_PREMARKET_ARM", "1")
    with pytest.raises(Conflict):
        enter(e, r)
    assert not e.broker.submitted
    e._data_gap(r["conid"], "connection interrupted")
    assert not e.store.get("run", r["id"])["armed"]
    assert e._run_history_ready(r)  # This definition builds its reference live.
    assert not e.broker.submitted


def test_extended_history_is_validated_separate_and_never_generates_orders(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    h = e.premarket_history[r["conid"]]
    h.update(status="pending", request=99)
    bar = {
        "type": "historical_bar",
        "request": 99,
        "conid": r["conid"],
        "history_scope": "extended",
        "seconds": 60,
        "timestamp": str(int((Clock.stamp - timedelta(minutes=2)).timestamp())),
        "open": "599",
        "high": "601",
        "low": "598",
        "close": "600",
        "volume": "1",
    }
    assert e._premarket_observation(bar)
    assert e._premarket_observation({"type": "history_end", "request": 99})
    assert e._run_history_ready(r) and not e.data[r["conid"]]["warm"]
    assert not e.broker.submitted
    h.update(status="pending", request=100)
    e._premarket_observation({**bar, "request": 100, "low": "900"})
    assert h["status"] == "failed" and e._run_history_ready(r)
    # An unrelated order/global error must not be mistaken for a history error.
    assert not e._premarket_observation({"type": "broker_error", "request": 100, "code": 201})
    Clock.stamp += timedelta(days=1)
    h["status"] = "completed"
    assert e._run_history_ready(r)  # This definition builds its reference live.


def test_regular_open_expires_premarket_generation_and_waits_for_live_minute(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    Clock.stamp = datetime(2026, 9, 22, 13, 30, 1, tzinfo=UTC)
    e.data[r["conid"]].update(received_at=now(), source_at=now())
    for quote in e.quotes[r["conid"]].values():
        quote["received_at"] = now()
    e.store.put(
        "stock_trigger",
        r["id"],
        {
            "state": "monitoring",
            "candle": "2026-09-22T13:29:00+00:00",
            "started_at": "2026-09-22T13:29:59+00:00",
            "high": "600",
            "expires_at": "2026-09-22T13:31:00+00:00",
            "authorization_id": "fixture",
        },
    )
    e._stock_trade(
        {"conid": r["conid"], "timestamp": Clock.stamp.timestamp(), "price": "601", "sequence": 50}
    )
    assert e.store.get("stock_trigger", r["id"])["state"] == "skipped"
    assert not e.broker.submitted and e.store.get("run", r["id"])["armed"]


def test_unfilled_exit_remains_requested_across_closure_and_restart(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    entry = enter(e, r)
    fill(e, entry, quantity="1", price="600")
    e.store.transition(entry["id"], "filled", {})
    e._stock_sync()
    Clock.stamp = datetime(2026, 9, 22, 20, 0, 1, tzinfo=UTC)
    e.data[r["conid"]].update(received_at=now(), source_at=now())
    for quote in e.quotes[r["conid"]].values():
        quote["received_at"] = now()
    monkeypatch.setattr(e, "_identity_issues", lambda: [])
    monkeypatch.setattr(e, "_fill_agreement_issues", lambda: [])
    e.reconciled = e.position_agreement = True
    e._request_exit(r["id"])
    request = e.store.get("exit_request", r["id"])
    assert request and len(e.broker.submitted) == 1
    restored = Engine(Store(tmp_path), StockBroker)
    assert restored.store.get("exit_request", r["id"]) == request
    assert restored.owned()[r["id"]]["quantity"] == 1
    assert not restored.store.get("run", r["id"])["armed"]
    restored._request_exit(r["id"])
    assert not restored.broker.submitted


def test_pending_entry_deadline_rejects_expired_and_different_session_identity(
    tmp_path, monkeypatch
):
    e, r = fixture(tmp_path, monkeypatch)
    o = enter(e, r)
    g = PaperGateway(e.observations)
    p = o["payload"]
    with pytest.raises(ValueError, match="another contract"):
        g._stock_extended_deadline({**p, "session_contract": {**p["session_contract"], "conid": 0}})
    Clock.stamp = datetime.fromisoformat(p["expires_at"])
    with pytest.raises(ValueError, match="deadline"):
        g._stock_extended_deadline(p)


def exit_fixture(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    entry = enter(e, r)
    fill(e, entry, quantity="1", price="600")
    e.store.transition(entry["id"], "filled", {})
    e._stock_sync()
    monkeypatch.setattr(e, "_identity_issues", lambda: [])
    monkeypatch.setattr(e, "_fill_agreement_issues", lambda: [])
    e.reconciled = e.position_agreement = True
    e._request_exit(r["id"])
    exit_order = next(o for o in e.store.orders() if o["payload"].get("purpose") == "exit")
    return e, r, entry, exit_order


def test_pending_exit_is_cancelled_after_ten_seconds_without_replacement(tmp_path, monkeypatch):
    e, r, entry, exit_order = exit_fixture(tmp_path, monkeypatch)
    assert exit_order["state"] == "dispatching"
    Clock.stamp += timedelta(seconds=11)
    e.next_reconcile = e.next_heartbeat = e._next_health_write = e._next_runtime_clock = float(
        "inf"
    )
    e.history_jobs = []
    monkeypatch.setattr(e, "_premarket_maintain", lambda clock: None)
    monkeypatch.setattr(e, "_outage_tick", lambda: None)
    e.maintain()
    order = next(o for o in e.store.orders() if o["id"] == exit_order["id"])
    assert order["state"] == "cancel_pending"
    assert exit_order["broker_id"] in e.broker.cancelled
    assert len(e.broker.submitted) == 2
    assert e.store.get("reservation", entry["id"])["active"]


def test_rejection_retained_after_cancel_blocks_automatic_exit_retry(tmp_path, monkeypatch):
    e, r, _, exit_order = exit_fixture(tmp_path, monkeypatch)
    e.store.transition(exit_order["id"], "cancelled", {})
    e.store.put(
        "broker_order", str(exit_order["broker_id"]), {"rejection_code": 201, "status": "Cancelled"}
    )
    e.reconciled = e.position_agreement = True
    e._request_exit(r["id"])
    assert len(e.broker.submitted) == 2
    # Recovery review alone cannot authorize an automatic retry of the rejected exit.
    e.close_position(r["id"])
    assert len(e.broker.submitted) == 3


def test_sdk_standalone_exit_callback_preserves_empty_oca_and_policy_ack(tmp_path, monkeypatch):
    import threading

    from ibapi.client import EClient

    from trading_oms_backend.workspace.protection import ProtectionController

    e, _, _, exit_order = exit_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(EClient, "connect", lambda *args: None)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    g = PaperGateway(e.observations)
    g.connect()
    g._accounts, g._attested = ["DU0000000"], True
    g._contracts[exit_order["payload"]["conid"]] = SimpleNamespace(
        conId=exit_order["payload"]["conid"],
        secType="STK",
        currency="USD",
        exchange="NASDAQ",
        symbol="META",
    )
    calls = []
    monkeypatch.setattr(g.client, "isConnected", lambda: True)
    monkeypatch.setattr(g.client, "placeOrder", lambda *args: calls.append(args))
    g.submit_exit({**exit_order["payload"], **exit_order})
    identity, c, o = calls[0]
    o.clientId = e.broker.client_id
    g.client.openOrder(identity, c, o, SimpleNamespace(status="Submitted"))
    observed = e.observations.get_nowait()
    assert observed["oca_group"] == ""
    e.broker_orders = {identity: observed}
    assert not ProtectionController._identity_issues(e)
    observed["outside_rth"] = False
    assert ProtectionController._identity_issues(e)


def test_partial_fill_cancels_remainder_and_late_execution_updates_protection(
    tmp_path, monkeypatch
):
    e, r = fixture(tmp_path, monkeypatch, shares="2")
    e.store.put("stock_qualification", r["binding"]["execution_plan"]["hash"], {"long": True})
    e.quotes[r["conid"]]["ask"]["price"] = "400"
    e.quotes[r["conid"]]["bid"]["price"] = "399.99"
    entry = enter(e, r)
    assert entry["payload"]["quantity"] == "2"
    fill(e, entry, quantity="1", price="400")
    e._stock_sync()
    assert e.store.get("stock_protection", r["id"])["stop"] == "396.00"
    assert entry["broker_id"] in e.broker.cancelled
    assert next(o for o in e.store.orders() if o["id"] == entry["id"])["state"] == "cancel_pending"
    e.store.transition(entry["id"], "cancelled", {})
    event = {
        "type": "execution",
        "broker_id": entry["broker_id"],
        "client_id": e.broker.client_id,
        "own_account": True,
        "execution_id": "late-fill",
        "conid": r["conid"],
        "symbol": "META",
        "side": "BOT",
        "quantity": "1",
        "price": "398",
    }
    e.observe(event)
    e.observe(event)
    e._stock_sync()
    plan = e.store.get("stock_protection", r["id"])
    assert plan["quantity"] == "2" and plan["average"] == "399"
    assert plan["stop"] == "395.01"
    assert len(e.broker.submitted) == 1
    assert e.store.get("reservation", entry["id"])["active"]
