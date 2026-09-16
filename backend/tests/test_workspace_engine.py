import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Conflict, Store


class BrokerDouble:
    def __init__(self, observations: queue.Queue):
        self.observations = observations
        self.client_id = 71
        self.epoch = 1
        self.overflow = threading.Event()
        self.paper_context = True
        self.can_resume_attestation = True
        self.cancelled = []
        self.submitted = []

    def cancel(self, broker_id):
        self.cancelled.append(broker_id)

    def disconnect(self):
        pass


def test_shared_capacity_is_reserved_atomically_across_concurrent_signals(tmp_path):
    store = Store(tmp_path)
    for i in range(6):
        store.put(
            "run",
            f"run-{i}",
            {"armed": True, "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        )

    def reserve(i):
        try:
            store.reserve_order(
                f"order-{i}",
                {"quantity": 1},
                f"run-{i}",
                100,
                {"symbol": f"FIXTURE{i}", "risk": "10", "notional": "1000"},
            )
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(reserve, range(6)))
    assert sum(results) == 5
    assert len({order["broker_id"] for order in store.orders()}) == 5


def test_restart_disarms_and_marks_unfinished_intents_uncertain(tmp_path):
    store = Store(tmp_path)
    store.put("run", "run", {"id": "run", "armed": True})
    store.reserve_order("intent", {"quantity": 1}, "run", 100)
    Engine(store, BrokerDouble)
    assert store.get("run", "run")["armed"] is False
    assert store.orders()[0]["state"] == "unknown"
    with pytest.raises(Conflict):
        store.mark_dispatch("intent")


def test_duplicate_execution_across_reconnect_is_idempotent_and_corrections_replace(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store, BrokerDouble)
    order = store.reserve_order("intent", {"quantity": 2, "symbol": "FIXTURE"}, "run", 100)
    event = {
        "type": "execution",
        "epoch": 1,
        "client_id": 71,
        "broker_id": order["broker_id"],
        "execution_id": "fixture.01",
        "conid": 100,
        "symbol": "FIXTURE",
        "side": "BOT",
        "quantity": "2",
        "price": "100",
    }
    engine._execution(event)
    engine._execution({**event, "epoch": 2})
    assert engine.owned()["run"]["quantity"] == 2
    assert not store.list("incident")
    engine._execution({**event, "execution_id": "fixture.02", "quantity": "1"})
    assert engine.owned()["run"]["quantity"] == 1


def test_fill_after_cancel_is_not_discarded_and_late_cancel_cannot_erase_fill(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store, BrokerDouble)
    order = store.reserve_order("intent", {"quantity": 1}, "run", 100)
    engine._order_observation({"broker_id": order["broker_id"], "status": "Cancelled"})
    engine._order_observation({"broker_id": order["broker_id"], "status": "Filled"})
    engine._order_observation({"broker_id": order["broker_id"], "status": "Cancelled"})
    assert store.orders()[0]["state"] == "filled"


def test_emergency_blocks_entry_reservation_after_risk_preview(tmp_path):
    store = Store(tmp_path)
    store.set_emergency(True)
    with pytest.raises(Conflict):
        store.reserve_order("intent", {"quantity": 1}, "run", 100)
    assert not store.orders()


def test_five_distinct_signals_use_shared_oms_capacity_and_never_duplicate(tmp_path):
    import time
    from decimal import Decimal

    from trading_oms_backend.workspace.graph import templates
    from trading_oms_backend.workspace.store import now

    class ExecutionBroker(BrokerDouble):
        def submit_bracket(self, intent):
            self.submitted.append(intent)

    store = Store(tmp_path)
    engine = Engine(store, ExecutionBroker)
    engine.readiness = lambda: [{"passed": True}]
    engine.facts = {"AvailableFunds": "10000"}
    engine.daily_pnl, engine.pnl_at = Decimal(0), time.monotonic()
    graph = templates()[1]["document"]
    draft = store.save_draft(None, "Five-run test", graph, 0)
    version = store.publish(draft["id"], 1)
    runs = []
    for i in range(5):
        symbol = f"FIXTURE{i}"
        run = {
            "id": str(i),
            "strategy_id": draft["id"],
            "version": version["version"],
            "symbol": symbol,
            "conid": i + 1,
            "armed": True,
            "entries": 0,
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
        store.put("run", run["id"], run)
        engine.data[i + 1] = {"warm": True, "live": True}
        engine.contracts[i + 1] = {"market_rule": 1}
        engine.quotes[i + 1] = {
            side: {"price": "100", "received_at": now()} for side in ["bid", "ask"]
        }
        runs.append(run)
    engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
    result = {"stop": Decimal(99), "target": None}
    capture = store.capture({"source": "five_symbol_test"})
    for run in runs:
        engine._enter(run, result, {"minutes_to_close": 120}, capture)
    assert len(engine.broker.submitted) == 5
    assert len({order["broker_id"] for order in store.orders()}) == 5
    with pytest.raises(Conflict):
        engine._enter(runs[0], result, {"minutes_to_close": 120}, capture)
    assert len(engine.broker.submitted) == 5
    assert all(order["payload"].get("quote_capture") for order in store.orders())
