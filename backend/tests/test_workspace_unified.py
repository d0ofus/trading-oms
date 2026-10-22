import copy
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_workspace_engine import BrokerDouble
from test_workspace_health import healthy_watchdog

from trading_oms_backend.workspace.contracts import capabilities, execution_reason
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.graph import compile_graph, templates
from trading_oms_backend.workspace.reusable import bind_graph, reusable_copy, shared_templates
from trading_oms_backend.workspace.store import Store, now


class CryptoBroker(BrokerDouble):
    def subscribe(self, conid):
        return True

    def submit_crypto(self, intent):
        self.submitted.append(intent)

    def resolve(self, symbol="", **filters):
        self.resolved = {"symbol": symbol, **filters}
        return 1


def crypto_engine(tmp_path):
    engine = Engine(Store(tmp_path), CryptoBroker)
    contract = {
        **CRYPTO,
        "exchange": "PAXOS",
        "market_rule": 1,
        "min_size": "0.0001",
        "size_increment": "0.0001",
        "resolved": True,
    }
    engine.contracts[456] = contract
    engine.data[456] = {
        "conid": 456,
        "symbol": "BTC",
        "live": True,
        "warm": True,
        "price": "100",
        "received_at": now(),
        "source_at": now(),
    }
    engine.quotes[456] = {
        side: {"price": price, "received_at": now()}
        for side, price in (("bid", "99.99"), ("ask", "100.01"))
    }
    engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
    engine.connected = engine.attested = engine.reconciled = engine.position_agreement = (
        engine.clock_ok
    ) = True
    engine.reconciled_at = time.monotonic()
    engine.server_version = 220
    engine.next_id = 100
    engine.code_verified = True
    engine.facts = {"NetLiquidation": "10000", "AvailableFunds": "10000", "GrossPositionValue": "0"}
    draft = engine.store.save_draft(None, "Paper crypto", shared_templates()[-1]["document"], 0)
    version = engine.store.publish(draft["id"], draft["revision"])
    run = engine.create_run(draft["id"], version["version"], 456)
    run.update(
        armed=True,
        entries=0,
        authorized_at=(datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
        authorization_id="fixture",
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        limits={"shares": 1, "planned_stop_risk": "10", "notional": "1000", "entry_timeout": 30},
    )
    engine.store.put("run", run["id"], run)
    healthy_watchdog(engine)
    return engine, run


def crypto_entry(engine, run):
    engine._crypto_enter(run, {"capture": "fixture", "candle": now()})
    return engine.store.orders()[-1]


def confirm(engine, order, filled, price="100", status="Filled"):
    p = order["payload"]
    event = {
        "type": "open_order",
        "broker_id": order["broker_id"],
        "client_id": engine.broker.client_id,
        "own_account": True,
        "reference": "oms-" + order["id"],
        "conid": 456,
        "symbol": "BTC",
        "order_type": "MKT",
        "tif": "IOC",
        "parent_id": 0,
        "status": status,
        "action": "BUY" if p["purpose"] == "entry" else "SELL",
        "quantity": p["quantity"],
        "cash_quantity": p.get("cash_quantity"),
        "filled": filled,
    }
    engine.observe(event)
    if Decimal(filled):
        engine.observe(
            {
                "type": "execution",
                "broker_id": order["broker_id"],
                "client_id": engine.broker.client_id,
                "own_account": True,
                "execution_id": "fill-" + order["id"],
                "conid": 456,
                "symbol": "BTC",
                "side": "BOT" if p["purpose"] == "entry" else "SLD",
                "quantity": filled,
                "price": price,
            }
        )
    quantity = sum(p["quantity"] for p in engine.owned().values())
    engine.positions = {
        456: {
            "conid": 456,
            "symbol": "BTC",
            "quantity": str(quantity),
            "sec_type": "CRYPTO",
            "currency": "USD",
            "exchange": "PAXOS",
            "own_account": True,
        }
    }
    engine._finish_reconcile()


EQUITY = {
    "conid": 123,
    "symbol": "MSFT",
    "sec_type": "STK",
    "currency": "USD",
    "primary_exchange": "NASDAQ",
    "routing_exchange": "SMART",
}
CRYPTO = {
    "conid": 456,
    "symbol": "BTC",
    "sec_type": "CRYPTO",
    "currency": "USD",
    "routing_exchange": "PAXOS",
}


def test_reusable_copy_preserves_source_and_binds_without_changing_hash():
    legacy = templates()[-1]["document"]
    original = copy.deepcopy(legacy)
    old_hash = compile_graph(legacy).digest
    reusable = reusable_copy(legacy)
    assert reusable["schema_version"] == 6
    assert "symbol" not in reusable["settings"]
    compiled = compile_graph(reusable)
    one = bind_graph(reusable, {"contract": EQUITY, "sizing": {"shares": 1}})
    two = bind_graph(
        reusable, {"contract": {**EQUITY, "conid": 124, "symbol": "AAPL"}, "sizing": {"shares": 2}}
    )
    assert one.digest == two.digest == compiled.digest
    assert one.document["settings"]["symbol"] == "MSFT"
    assert two.document["settings"]["shares"] == 2
    assert legacy == original and compile_graph(legacy).digest == old_hash


def test_shared_templates_and_capabilities():
    items = shared_templates()
    assert all(t["document"]["schema_version"] == 6 for t in items)
    paired, long = items[-2]["document"], items[-1]["document"]
    assert execution_reason(EQUITY, paired) is None
    assert "PAXOS" in execution_reason(CRYPTO, paired)
    assert execution_reason(CRYPTO, long) is None
    assert capabilities({"sec_type": "CASH"})["candle_source"] == "MIDPOINT"
    assert not capabilities({"sec_type": "FUT"})["executions"]


def test_reusable_schema_rejects_hidden_instrument_and_invalid_fixed_rule():
    document = shared_templates()[-1]["document"]
    document["settings"]["symbol"] = "BTC"
    with pytest.raises(ValueError):
        compile_graph(document)


def test_paper_crypto_partial_entry_local_stop_serialized_exit_and_qualification(tmp_path):
    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    assert entry["payload"]["cash_quantity"] == "25.00"
    assert engine.store.get("crypto_protection", run["id"])["quantity"] == "0"
    assert len(engine.broker.submitted) == 1
    confirm(engine, entry, "0.1", "100.123", "Cancelled")
    plan = engine.store.get("crypto_protection", run["id"])
    assert plan["stop"] == "99.13"
    assert engine.reconciled
    engine.daily_pnl = Decimal("NaN")
    engine._crypto_trade({"conid": 456, "timestamp": time.time(), "price": "99", "sequence": 3})
    engine._crypto_trade({"conid": 456, "timestamp": time.time(), "price": "98", "sequence": 4})
    assert len(engine.broker.submitted) == 2
    exit_order = next(o for o in engine.store.orders() if o["payload"]["purpose"] == "exit")
    assert exit_order["payload"]["quantity"] == "0.1"
    confirm(engine, exit_order, "0.1", "98")
    assert engine.owned()[run["id"]]["quantity"] == 0
    assert engine.store.get("run", run["id"])["state"] == "paused"
    assert not engine.store.get("run", run["id"])["armed"]
    assert engine.store.get("qualification", "crypto_paper")["completed"]
    assert not (engine.store.get("qualification", "broker_evidence") or {}).get("smoke_completed")
    engine.store.verify()


def test_outage_stale_data_emergency_and_notification_failure_do_not_liquidate(tmp_path):
    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    confirm(engine, entry, "0.25")
    engine.requested_connection = True
    engine._connection_lost("fixture outage")
    engine._outage_tick()
    engine._outage_tick()
    engine.emergency(True)
    engine.store.put("notification", "failed", {"state": "failed"})
    engine._crypto_trade({"conid": 456, "timestamp": time.time(), "price": "90"})
    assert len(engine.broker.submitted) == 1
    assert len(engine.store.list("notification")) == 2
    assert not engine.store.get("run", run["id"])["armed"]
    engine.connected = engine.attested = engine.position_agreement = engine.reconciled = True
    engine.data[456].update(live=True, received_at=now(), source_at=now())
    engine._outage_tick()
    assert not engine.store.get("connection_outage", "current")["active"]
    engine._crypto_trade({"conid": 456, "timestamp": time.time(), "price": "90"})
    assert len(engine.broker.submitted) == 2  # Genuine fresh stop breach, even while disarmed.


def test_zero_fill_and_uncertain_dispatch_never_retry_entry(tmp_path):
    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    confirm(engine, entry, "0", status="Cancelled")
    assert not engine.store.get("run", run["id"])["armed"]
    assert not engine.store.get("qualification", "crypto_paper")
    assert len(engine.broker.submitted) == 1


def test_optional_data_error_does_not_create_global_incident(tmp_path):
    engine, run = crypto_engine(tmp_path)
    engine.data[999] = {"warm": False}
    engine.observe(
        {
            "type": "broker_error",
            "code": 354,
            "request": 1001,
            "context": "market_data",
            "conid": 999,
            "request_kind": "quote",
        }
    )
    assert not engine.incidents.applicable([{"id": "healthy", "conid": 456}])
    assert engine.incidents.open()[0]["scope"]["type"] == "contract"
    assert engine.data[999]["subscription_status"] == "rejected"
    assert engine.data[456]["warm"]
    crypto_entry(engine, run)


def test_paper_crypto_sdk_cash_and_quantity_parameters_and_live_guard():
    import queue

    from trading_oms_backend.workspace.broker import PaperGateway

    gateway = PaperGateway(queue.Queue())
    calls = []
    gateway.client = SimpleNamespace(
        isConnected=lambda: True, placeOrder=lambda *args: calls.append(args)
    )
    gateway._attested = True
    gateway._accounts = ("DU000000",)
    gateway._contracts[456] = SimpleNamespace(
        secType="CRYPTO", symbol="BTC", currency="USD", exchange="PAXOS"
    )
    base = {
        "id": "a" * 32,
        "broker_id": 1,
        "conid": 456,
        "purpose": "entry",
        "cash_quantity": "25",
        "protection_type": "locally_monitored",
    }
    gateway.submit_crypto(base)
    order = calls[-1][2]
    assert (order.action, order.orderType, order.tif, order.cashQty, order.totalQuantity) == (
        "BUY",
        "MKT",
        "IOC",
        25,
        0,
    )
    gateway.submit_crypto({**base, "purpose": "exit", "quantity": "0.0001"})
    assert calls[-1][2].totalQuantity == Decimal("0.0001")
    gateway._accounts = ("U000000",)
    with pytest.raises(ValueError, match="paper"):
        gateway.submit_crypto(base)
    assert len(calls) == 2


def test_restart_retains_stop_and_pending_exit_without_resending_unknown_order(tmp_path):
    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    confirm(engine, entry, "0.25")
    engine.close_position(run["id"])
    restarted = Engine(engine.store, CryptoBroker)
    assert not restarted.store.get("run", run["id"])["armed"]
    assert restarted.owned()[run["id"]]["quantity"] == Decimal("0.25")
    assert restarted.store.get("crypto_protection", run["id"])["stop"] == "99.00"
    assert restarted.store.get("exit_request", run["id"])
    assert any(o["state"] == "unknown" for o in restarted.store.orders())
    restarted._crypto_trade({"conid": 456, "timestamp": time.time(), "price": "90"})
    assert not restarted.broker.submitted


def test_manual_exit_survives_outage_and_retries_only_after_reconciliation(tmp_path):
    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    confirm(engine, entry, "0.25")
    engine._connection_lost("fixture")
    with pytest.raises(ValueError):
        engine.close_position(run["id"])
    assert engine.store.get("exit_request", run["id"])
    assert len(engine.broker.submitted) == 1
    engine.connected = engine.attested = True
    engine.data[456].update(live=True, received_at=now(), source_at=now())
    engine._finish_reconcile()
    engine._request_exit(run["id"])
    assert len(engine.broker.submitted) == 2


def test_outage_notices_are_durable_without_repeated_reminders(tmp_path, monkeypatch):
    import trading_oms_backend.workspace.outages as outages

    engine, _ = crypto_engine(tmp_path)
    engine.requested_connection = True
    engine._connection_lost("fixture")
    monkeypatch.setattr(outages.time, "time", lambda: 1000)
    engine._outage_tick()
    engine._outage_tick()
    assert len(engine.store.list("notification")) == 1
    monkeypatch.setattr(outages.time, "time", lambda: 1299)
    engine._outage_tick()
    assert len(engine.store.list("notification")) == 1
    monkeypatch.setattr(outages.time, "time", lambda: 1300)
    engine._outage_tick()
    assert len(engine.store.list("notification")) == 1


def test_migration_backs_up_history_and_preserves_simulation_provenance(tmp_path):
    from trading_oms_backend.workspace.migration import migrate_workspace
    from trading_oms_backend.workspace.recovery import restore_bundle, validate_bundle

    paper = Store(tmp_path / "paper")
    sim = Store(tmp_path / "simulation" / "live-crypto")
    paper.event("fixture.historical", {"source": "paper"})
    sim.event("fixture.historical", {"source": "local_simulator"})
    sim.put("simulated_position", "BTC", {"quantity": "0.1"})
    before_paper, before_sim = paper.events(), sim.events()
    migrate_workspace(paper.directory, sim.directory)
    assert paper.events()[: len(before_paper)] == before_paper
    assert sim.events() == before_sim
    assert sim.get("simulated_position", "BTC")["quantity"] == "0.1"
    assert list((paper.directory / "backups").rglob("*.zip"))
    assert list((tmp_path / "archives").rglob("provenance.json"))
    archive = next((tmp_path / "archives").rglob("local-simulation.zip"))
    assert validate_bundle(archive, environment="live_crypto_simulation")["environment"] == (
        "live_crypto_simulation"
    )
    with pytest.raises(ValueError, match="environment"):
        restore_bundle(archive, tmp_path / "must-not-become-paper")
    assert not (tmp_path / "must-not-become-paper").exists()
    count = len(paper.events())
    migrate_workspace(paper.directory, sim.directory)
    assert len(paper.events()) == count
    assert not paper.list("simulated_position")


def test_migration_rejects_unresolved_paper_orders(tmp_path):
    from trading_oms_backend.workspace.migration import migrate_workspace

    store = Store(tmp_path)
    store.reserve_order("old", {"purpose": "exit", "quantity": 1}, "run", 100)
    with pytest.raises(ValueError, match="flat"):
        migrate_workspace(tmp_path)
    assert not store.get("migration", "unified_workspace")


def test_reconnect_restores_full_identity_and_binding_change_blocks_entry(tmp_path):
    engine, run = crypto_engine(tmp_path)
    engine._restore_subscriptions()
    assert engine.broker.resolved == {"symbol": "", "conid": 456, "exchange": "PAXOS"}
    engine.contracts[456] = {**engine.contracts[456], "routing_exchange": "OTHER"}
    assert not engine._binding_valid(run)
    with pytest.raises(ValueError, match="identity"):
        crypto_entry(engine, run)
    assert not engine.broker.submitted


def test_watchlist_subscription_is_independent_of_five_run_limit():
    import queue

    from trading_oms_backend.workspace.broker import PaperGateway

    gateway = PaperGateway(queue.Queue())
    requests = []
    gateway.client = SimpleNamespace(
        reqMarketDataType=lambda _: None,
        reqMktData=lambda *a: requests.append(a),
        reqTickByTickData=lambda *a: None,
    )
    for conid in range(1, 9):
        gateway._contracts[conid] = SimpleNamespace(secType="STK")
        gateway._next_subscription = 0
        assert gateway.subscribe(conid)
    assert len(requests) == 8
    gateway._contracts[9] = SimpleNamespace(secType="STK")
    assert gateway.subscribe(9) is False  # Pacing queues, rather than a five-symbol rejection.


def test_long_trigger_uses_only_new_live_minute_and_refreshes_without_entries(tmp_path):
    from trading_oms_backend.workspace.market import Candle

    engine, run = crypto_engine(tmp_path)
    stamp = datetime.now(UTC).replace(second=0, microsecond=0)
    run["authorized_at"] = (stamp - timedelta(minutes=1)).isoformat()
    engine.store.put("run", run["id"], run)
    market = SimpleNamespace(
        closed=[
            Candle(
                stamp - timedelta(minutes=2),
                Decimal(100),
                Decimal(101),
                Decimal(99),
                Decimal(100),
                Decimal(1),
            )
        ]
    )
    state = {"market": market, "oca_live_since": run["authorized_at"]}
    engine._crypto_candidate(run, state, {"bar_closed": True}, "history")
    assert engine.store.get("crypto_trigger", run["id"]) is None
    market.closed.append(
        Candle(
            stamp - timedelta(minutes=1),
            Decimal(100),
            Decimal(101),
            Decimal(99),
            Decimal(100),
            Decimal(1),
        )
    )
    engine._crypto_candidate(run, state, {"bar_closed": True}, "live")
    trigger = engine.store.get("crypto_trigger", run["id"])
    assert trigger["state"] == "monitoring"
    assert datetime.fromisoformat(trigger["expires_at"]) == stamp + timedelta(minutes=1)
    assert engine.store.get("run", run["id"])["entries"] == 0
    assert not engine.store.orders()
    engine.data[456]["price"] = "103"
    market.closed.append(
        Candle(stamp, Decimal(100), Decimal(102), Decimal(99), Decimal(100), Decimal(1))
    )
    engine._crypto_candidate(run, state, {"bar_closed": True}, "new-live")
    assert engine.store.get("crypto_trigger", run["id"])["state"] == "skipped"
    assert not engine.broker.submitted


def test_duplicate_fill_and_dispatch_failure_never_duplicate_owned_quantity(tmp_path):
    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    confirm(engine, entry, "0.25")
    confirm(engine, entry, "0.25")
    assert engine.owned()[run["id"]]["quantity"] == Decimal("0.25")
    assert engine.store.get("crypto_protection", run["id"])["quantity"] == "0.25"

    def interrupted(intent):
        raise OSError("synthetic interruption")

    engine.broker.submit_crypto = interrupted
    engine.close_position(run["id"])
    assert any(o["state"] == "unknown" for o in engine.store.orders())
    engine._finish_reconcile()
    assert not engine.reconciled
    with pytest.raises(ValueError):
        engine.close_position(run["id"])
    assert len(engine.store.orders()) == 2


def test_legacy_reservation_and_new_contract_reservation_share_capacity(tmp_path):
    store = Store(tmp_path)
    for key in ("legacy", "new"):
        store.put(
            "run",
            key,
            {
                "id": key,
                "conid": 123,
                "armed": True,
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
        )
    original = {
        "run_id": "legacy",
        "symbol": "MSFT",
        "risk": "1",
        "notional": "100",
        "active": True,
    }
    store.put("reservation", "old", original)
    with pytest.raises(ValueError, match="already has reserved"):
        store.reserve_order(
            "new",
            {"conid": 123, "quantity": 1},
            "new",
            100,
            {"symbol": "MSFT", "conid": 123, "risk": "1", "notional": "100"},
        )
    assert store.get("reservation", "old") == original


def test_migration_blocks_external_security_positions_even_without_owned_fills(tmp_path):
    from trading_oms_backend.workspace.migration import migrate_workspace

    store = Store(tmp_path)
    store.event(
        "reconciliation.finished",
        {"ready": False, "positions": [{"sec_type": "STK", "quantity": "1"}]},
    )
    with pytest.raises(ValueError, match="flat and reconciled"):
        migrate_workspace(tmp_path)
