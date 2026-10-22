import copy
import queue
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_workspace_health import healthy_watchdog

from trading_oms_backend.workspace.broker import GatewayData, PaxosDataGateway
from trading_oms_backend.workspace.graph import compile_graph, crypto_copy, templates
from trading_oms_backend.workspace.market import Market, session_bounds
from trading_oms_backend.workspace.runtime import size_entry
from trading_oms_backend.workspace.store import Conflict, Store, now


def test_crypto_conversion_preserves_v3_and_all_nodes():
    source = templates()[0]["document"]
    original = copy.deepcopy(source)
    digest = compile_graph(source).digest
    converted = crypto_copy(source)
    assert source == original
    assert compile_graph(source).digest == digest
    assert converted["nodes"] == compile_graph(source).document["nodes"]
    assert converted["schema_version"] == 4
    assert converted["settings"]["symbol"] == "BTC"
    assert "shares" not in converted["settings"]


def test_crypto_sessions_and_fractional_sizing_on_sunday():
    stamp = datetime(2026, 9, 20, 12, tzinfo=UTC)
    assert session_bounds(stamp) is None
    opened, closed = session_bounds(stamp, "utc_24x7")
    assert closed - opened == timedelta(days=1)
    graph = compile_graph(crypto_copy(templates()[1]["document"]))
    market = Market(graph)
    assert market.accept(stamp, Decimal("60000"), Decimal("0.001")) is not None
    profile = {"notional": "1000", "planned_stop_risk": "10", "quantity": "10"}
    contract = {"min_size": "0.00000001", "size_increment": "0.00000001"}
    qty = size_entry(
        graph.document["settings"],
        profile,
        Decimal(60000),
        Decimal(59000),
        Decimal(10000),
        contract,
    )
    assert qty == Decimal("0.01")
    with pytest.raises(Conflict):
        size_entry(
            graph.document["settings"], profile, Decimal(60000), Decimal(59000), Decimal(10000)
        )


def test_data_transport_has_no_execution_adapter_methods():
    data = PaxosDataGateway(queue.Queue())
    assert not data.execution_enabled
    assert not hasattr(data, "submit_bracket")
    assert not hasattr(data, "submit_exit")
    assert not hasattr(data, "cancel")


class DataDouble(PaxosDataGateway):
    def __init__(self, observations):
        super().__init__(observations)
        self.epoch = 1
        self._accounts = ("DU000000",)  # Synthetic fixture only.
        self._attested = True
        self._contracts[1] = object()

    def _require_paper(self):
        pass


def simulator(tmp_path):
    from trading_oms_backend.workspace.simulator import CryptoSimulator

    store = Store(tmp_path)
    observations = queue.Queue()
    broker = CryptoSimulator(observations, store, data_factory=DataDouble)
    broker.on_market({"type": "data_type", "conid": 1, "live": True})
    broker.set_contract(
        {
            "conid": 1,
            "symbol": "BTC",
            "sec_type": "CRYPTO",
            "currency": "USD",
            "exchange": "PAXOS",
            "min_size": "0.00000001",
            "size_increment": "0.00000001",
        }
    )
    store.put(
        "run",
        "run",
        {
            "id": "run",
            "armed": True,
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    )
    payload = {
        "conid": 1,
        "symbol": "BTC",
        "quantity": "0.001",
        "limit": "60000",
        "stop": "59000",
        "target": "62000",
        "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    }
    intent = store.reserve_order(
        "a" * 32, payload, "run", 100, {"symbol": "BTC", "risk": "1", "notional": "60"}
    )
    store.mark_dispatch(intent["id"])
    broker.submit_bracket({**payload, **intent})
    return broker, store, observations


def market_event(broker, kind="quote", **payload):
    broker.data.sequence += 1
    event = {
        "type": kind,
        "conid": 1,
        "sequence": broker.data.sequence,
        "timestamp": datetime.now(UTC).timestamp(),
        **payload,
    }
    broker.on_market(event)


def test_local_limit_and_gap_stop_are_durable_and_idempotent(tmp_path):
    broker, store, observations = simulator(tmp_path)
    market_event(broker, side="bid", price="59999")
    market_event(broker, side="ask", price="60001")
    assert not broker.state["executions"]
    market_event(broker, side="ask", price="60000")
    assert len(broker.state["executions"]) == 1
    assert broker.state["positions"]["1"]["quantity"] == "0.001"
    market_event(broker, "tick", price="58900", size="0.001")
    market_event(broker, side="bid", price="58800")
    assert len(broker.state["executions"]) == 2
    assert broker.state["executions"][-1]["price"] == "58800"
    assert Decimal(broker.state["positions"]["1"]["quantity"]) == 0
    market_event(broker, side="bid", price="58800")
    assert len(broker.state["executions"]) == 2
    assert store.get("simulator", "ledger")["cash"] == "9998.800"
    store.verify()


def test_local_emergency_prevents_pending_fill_and_restart_preserves_cash(tmp_path):
    broker, store, observations = simulator(tmp_path)
    store.set_emergency(True)
    market_event(broker, side="ask", price="59900")
    assert not broker.state["executions"]
    from trading_oms_backend.workspace.simulator import CryptoSimulator

    restarted = CryptoSimulator(observations, store, data_factory=DataDouble)
    assert restarted.state["cash"] == "10000"
    assert all(o["status"] == "Cancelled" for o in restarted.state["orders"].values())


@pytest.mark.parametrize("gateway_type", [PaxosDataGateway, GatewayData])
def test_sdk_execution_calls_are_rejected_before_transport(monkeypatch, gateway_type):
    import sys
    import types

    from trading_oms_backend.workspace import broker as module

    class EClient:
        def __init__(self, wrapper):
            pass

        def connect(self, *args):
            pass

        def run(self):
            pass

        def placeOrder(self, *args):
            pytest.fail("SDK transport was reached")

        cancelOrder = placeOrder
        placeOrderProtoBuf = placeOrder
        cancelOrderProtoBuf = placeOrder

    client, wrapper = types.ModuleType("ibapi.client"), types.ModuleType("ibapi.wrapper")
    client.EClient, wrapper.EWrapper = EClient, type("EWrapper", (), {})
    monkeypatch.setitem(sys.modules, "ibapi.client", client)
    monkeypatch.setitem(sys.modules, "ibapi.wrapper", wrapper)
    monkeypatch.setattr(module, "version", lambda name: "10.50.2" if name == "ibapi" else "5.29.6")
    data = gateway_type(queue.Queue())
    data.connect()
    data._attested = True  # Read-only account verification must never unlock SDK writes.
    for method in (
        "placeOrder",
        "placeOrderProtoBuf",
        "cancelOrder",
        "cancelOrderProtoBuf",
        "reqGlobalCancel",
        "reqGlobalCancelProtoBuf",
        "exerciseOptions",
        "exerciseOptionsProtoBuf",
        "reqAutoOpenOrders",
    ):
        with pytest.raises(ValueError):
            getattr(data.client, method)(None)


def test_crypto_auth_state_and_profile_are_isolated(tmp_path):
    from fastapi.testclient import TestClient

    from trading_oms_backend.workspace.api import create_app
    from trading_oms_backend.workspace.engine import Engine

    app = create_app(
        tmp_path / "crypto",
        "synthetic-crypto-pairing-test-token",
        start_engine=False,
        environment="live_crypto_simulation",
        port=8001,
    )
    with TestClient(app, base_url="http://127.0.0.1:8001") as client:
        response = client.post(
            "/api/auth/pair",
            json={"token": "synthetic-crypto-pairing-test-token"},
            headers={"Origin": "http://127.0.0.1:8001"},
        )
        assert "oms_crypto_sim_session" in response.headers["set-cookie"]
        state = client.get("/api/workspace/session").json()
        assert state["mode"] == "simulation"
        assert state["execution_provider"] == "local_simulator"
        assert all("daily_loss" not in p for p in client.get("/api/risk-profiles").json())
        assert (
            client.get("/api/strategies/catalog").json()["templates"][0]["document"][
                "schema_version"
            ]
            == 4
        )
        assert (
            client.post(
                "/api/operations/qualification",
                json={"stage": "supervised", "confirmed": True},
                headers={"Origin": "http://127.0.0.1:8001"},
            ).status_code
            == 409
        )
        client.cookies.clear()
        client.cookies.set("oms_session", "synthetic-paper-cookie")
        assert client.get("/api/workspace/session").status_code == 401
    with pytest.raises(Conflict, match="another execution environment"):
        Engine(app.state.store)


def drain(engine):
    while not engine.observations.empty():
        engine.observe(engine.observations.get_nowait())


def test_crypto_engine_reconciles_fractional_fill_exit_and_restart(tmp_path):
    from trading_oms_backend.workspace.engine import Engine
    from trading_oms_backend.workspace.simulator import CryptoSimulator

    store = Store(tmp_path)
    engine = Engine(
        store,
        lambda observations: CryptoSimulator(observations, store, DataDouble),
        environment="live_crypto_simulation",
    )
    healthy_watchdog(engine)
    engine.connected = engine.attested = True
    engine.server_version, engine.clock_ok = 226, True
    engine.next_id = 100
    contract = {
        "conid": 1,
        "symbol": "BTC",
        "sec_type": "CRYPTO",
        "currency": "USD",
        "exchange": "PAXOS",
        "min_size": "0.00000001",
        "size_increment": "0.00000001",
        "market_rule": 1,
    }
    engine.observe({"type": "contract", **contract})
    engine.market_rules[1] = [{"low": "0", "increment": "0.25"}]
    document = crypto_copy(templates()[1]["document"])
    draft = store.save_draft(None, "Crypto fixture", document, 0)
    published = store.publish(draft["id"], 1)
    run = {
        "id": "run",
        "strategy_id": draft["id"],
        "version": published["version"],
        "symbol": "BTC",
        "conid": 1,
        "armed": True,
        "position": "0",
        "entries": 0,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    store.put("run", "run", run)
    engine.data[1] = {
        "conid": 1,
        "symbol": "BTC",
        "warm": True,
        "live": True,
        "price": "60000",
        "received_at": now(),
        "source_at": now(),
    }
    engine.quotes[1] = {side: {"price": "60000", "received_at": now()} for side in ("bid", "ask")}
    engine.broker.on_market({"type": "data_type", "conid": 1, "live": True})
    engine.begin_reconcile()
    drain(engine)
    assert engine.reconciled
    engine._enter(
        run,
        {"stop": Decimal("59000"), "target": None},
        {"minutes_to_close": 120},
        store.capture({"source": "fixture"}),
    )
    drain(engine)
    market_event(engine.broker, side="bid", price="59999")
    market_event(engine.broker, side="ask", price="60000")
    drain(engine)
    engine.begin_reconcile()
    drain(engine)
    assert engine.reconciled, engine.last_fault
    assert engine.owned()["run"]["quantity"] == Decimal("0.01")
    assert store.get("run", "run")["protected"]
    engine.close_position("run")
    drain(engine)
    market_event(engine.broker, side="bid", price="60000")
    drain(engine)
    engine.begin_reconcile()
    drain(engine)
    assert engine.reconciled, engine.last_fault
    assert engine.owned()["run"]["quantity"] == 0
    restarted = Engine(
        store,
        lambda observations: CryptoSimulator(observations, store, DataDouble),
        environment="live_crypto_simulation",
    )
    assert not store.get("run", "run")["armed"]
    restarted.connected = restarted.attested = True
    restarted.begin_reconcile()
    drain(restarted)
    assert restarted.reconciled, restarted.last_fault
    assert not store.get("qualification", "broker_evidence")


@pytest.mark.parametrize("timeframe", [5, 60, 300])
def test_full_crypto_indicator_catalog_seeds_on_utc_weekend(timeframe):
    from trading_oms_backend.workspace.graph import CATALOG

    document = crypto_copy(templates()[0]["document"])
    document["settings"]["timeframe"] = timeframe
    fields = next(spec["fields"] for spec in CATALOG if spec["kind"] == "field")
    for index, field in enumerate(fields):
        document["nodes"].append(
            {
                "id": f"check_{index}",
                "kind": "field",
                "params": {"field": field, "period": 5, "source": "current"},
            }
        )
    graph = compile_graph(document)
    stamp = datetime(2026, 9, 20, 1, 0, tzinfo=UTC)
    start = stamp.replace(hour=0) - timedelta(days=10)

    def bar(at):
        return {
            "timestamp": str(int(at.timestamp())),
            "open": "60000",
            "high": "60001",
            "low": "59999",
            "close": "60000",
            "volume": "0.1",
        }

    minute = [bar(start + timedelta(minutes=i)) for i in range(10 * 1440 + 60)]
    fine = [bar(stamp - timedelta(seconds=i * 5)) for i in range(1, 61)]
    market = Market(graph)
    market.seed(minute, fine, stamp)
    context = market.accept(stamp, Decimal("60000"), Decimal("0.01"))
    assert len(market.history_volumes) == 10
    assert all(context[f"check_{index}"] is not None for index in range(len(fields)))
    # A missing minute cannot silently become zero reference volume.
    market.seed(minute[1:], fine, stamp)
    context = market.accept(stamp, Decimal("60000"), Decimal("0.01"))
    assert len(market.history_volumes) == 9
    assert context["relative_volume"] is None


def test_stale_quotes_and_delayed_feed_cannot_fill_local_orders(tmp_path):
    broker, store, observations = simulator(tmp_path)
    market_event(broker, side="bid", price="59999")
    broker.quotes[1]["bid"]["at"] = (datetime.now(UTC) - timedelta(seconds=16)).isoformat()
    market_event(broker, side="ask", price="60000")
    assert not broker.state["executions"]
    broker.on_market({"type": "data_type", "conid": 1, "live": False})
    market_event(broker, side="bid", price="59999")
    market_event(broker, side="ask", price="60000")
    assert not broker.state["executions"]


def test_restart_keeps_owned_protection_and_replays_fill_once(tmp_path):
    from trading_oms_backend.workspace.simulator import CryptoSimulator

    broker, store, observations = simulator(tmp_path)
    market_event(broker, side="bid", price="59999")
    market_event(broker, side="ask", price="60000")
    restored = CryptoSimulator(observations, store, DataDouble)
    assert restored.state["positions"]["1"]["quantity"] == "0.001"
    assert restored.state["orders"]["102"]["status"] == "Submitted"
    assert len(restored.state["executions"]) == 1
    restored.reconcile()
    restored.reconcile()
    assert len(restored.state["executions"]) == 1


def test_recovered_position_requests_exit_after_utc_authorization_expiry(tmp_path):
    from test_workspace_engine import BrokerDouble

    from trading_oms_backend.workspace.engine import Engine

    store = Store(tmp_path)
    draft = store.save_draft(None, "UTC recovery", crypto_copy(templates()[1]["document"]), 0)
    published = store.publish(draft["id"], 1)
    store.put(
        "run",
        "recovered",
        {
            "id": "recovered",
            "strategy_id": draft["id"],
            "version": published["version"],
            "symbol": "BTC",
            "conid": 1,
            "armed": False,
            "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    # Bind before constructing the engine so its restart guard recognizes this workspace.
    store.put("workspace", "environment", {"name": "live_crypto_simulation"})
    engine = Engine(store, BrokerDouble, environment="live_crypto_simulation")
    engine.owned = lambda: {"recovered": {"quantity": Decimal("0.001")}}
    requested = []
    engine._request_exit = requested.append
    engine._clock_evaluations()
    assert requested == ["recovered"]
