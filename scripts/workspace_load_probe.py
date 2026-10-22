"""Offline capacity probe. Temporary state and an adapter with no execution methods."""

import argparse
import json
import os
import statistics
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading_oms_backend.workspace.audit import audit_page
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.graph import templates
from trading_oms_backend.workspace.incidents import POLICY_VERSION
from trading_oms_backend.workspace.store import Store, now
from trading_oms_backend.workspace.watchdog import Watchdog


class OfflineBroker:
    def __init__(self, observations):
        self.observations = observations
        self.epoch = 1
        self.overflow = threading.Event()
        self.paper_context = False
        self.client_id = 71

    def disconnect(self):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=1_000_000)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--incidents", type=int, default=100_000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="oms-capacity-") as directory:
        store = Store(Path(directory))
        engine = Engine(store, OfflineBroker)
        draft = store.save_draft(None, "Synthetic capacity fixture", templates()[1]["document"], 0)
        published = store.publish(draft["id"], draft["revision"])
        with store.transaction() as db:
            for i in range(args.events):
                store.append(db, "fixture.capacity", {"reason": "synthetic audit evidence", "n": i})
            # Synthetic projection load only: no production incident is changed.
            stamp = now()
            def incident_rows():
                for i in range(args.incidents):
                    item = {
                        "id": f"fixture-{i}", "code": "connectivity",
                        "scope": {"type": "workspace", "key": "*"},
                        "condition": "recovered", "restriction": "released",
                        "investigation": "open", "review_policy": "arming",
                        "revision": 3, "occurrences": 1, "first_at": stamp,
                        "last_at": stamp, "timestamp": stamp, "instance": "fixture",
                        "detail": "Synthetic recovered outage", "severity": "critical",
                        "policy_version": POLICY_VERSION, "evidence": None,
                        "failure_sequence": 0, "resolved": True,
                    }
                    yield (item["id"], "connectivity", "workspace", "*", "released", "open", 3, json.dumps(item))
            db.executemany(
                "INSERT INTO incident_episodes(id,code,scope_type,scope_key,restriction,investigation,revision,payload) VALUES(?,?,?,?,?,?,?,?)",
                incident_rows(),
            )
            db.execute("INSERT INTO incident_totals VALUES('released',?)", (args.incidents,))
            for i in range(1000):
                strategy_id = draft["id"] if i == 0 else f"capacity-{i}"
                if i:
                    store.write(db, "draft", strategy_id, {**draft, "id": strategy_id})
                    db.execute("INSERT INTO versions VALUES(?,?,?)", (
                        strategy_id, published["version"], json.dumps({**published, "strategy_id": strategy_id})
                    ))
                store.write(db, "run", str(i), {
                    "id": str(i), "name": "Synthetic saved run", "conid": i % 50 + 1,
                    "strategy_id": strategy_id, "version": published["version"], "symbol": "AAPL",
                    "armed": i < 5, "position": "0", "entries": 0, "state": "armed" if i < 5 else "paused",
                    "expires_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
                    "authorized_at": now(), "session_policy": "xnys",
                })
        for conid in range(1, 51):
            engine.contracts[conid] = {"conid": conid, "symbol": "AAPL", "sec_type": "STK", "currency": "USD", "primary_exchange": "NASDAQ", "routing_exchange": "SMART"}
            engine.data[conid] = {"conid": conid, "symbol": "AAPL", "warm": True, "live": True, "history_loaded": True, "price": "100", "received_at": now(), "source_at": now()}
            engine.quotes[conid] = {side: {"price": "100", "received_at": now()} for side in ("bid", "ask")}
        engine.write_health()
        watchdog = Watchdog(store.directory, os.getpid(), instance=engine.process_identity)
        watchdog.tick()
        print(json.dumps({"fixture_events": args.events, "historical_incidents": args.incidents, "contracts": 50, "saved_strategies": 1000, "saved_runs": 1000, "active_runs": 5}), flush=True)
        stop = threading.Event()
        reads, waits, heartbeat_ages = [], [], []

        def audit_reader():
            while not stop.is_set():
                start = time.monotonic()
                result = audit_page(store, q="synthetic")
                assert len(result["items"]) <= 200
                history = engine.incidents.page(view="investigations")
                assert len(history["items"]) <= 200
                assert engine.incidents.counts()["released"] == args.incidents
                assert not engine.incidents.applicable([])
                reads.append(time.monotonic() - start)
                stop.wait(0.02)

        def supervisor():
            while not stop.is_set():
                watchdog.tick()
                stop.wait(0.5)

        engine.start()
        try:
            with ThreadPoolExecutor(max_workers=3) as workers:
                tasks = [workers.submit(audit_reader), workers.submit(audit_reader), workers.submit(supervisor)]
                try:
                    deadline = time.monotonic() + args.seconds
                    while time.monotonic() < deadline:
                        for conid in range(1, 51):
                            engine.observations.put_nowait({"type": "quote", "epoch": 1, "conid": conid, "side": "ask", "price": "100", "received_at": now()})
                        start = time.monotonic()
                        value = engine.call("overview")
                        waits.append(time.monotonic() - start)
                        heartbeat_ages.append(time.monotonic() - engine.last_loop)
                        assert all("candles" not in data for data in value["data"])
                        assert len(value["runs"]) <= 55
                        assert len(value["incidents"]) <= 200
                        stop.wait(0.2)
                finally:
                    stop.set()
                for task in tasks:
                    task.result()
            print(json.dumps({"audit_queries": len(reads), "overview_max_ms": round(max(waits) * 1000, 2), "max_engine_loop_age_ms": round(max(heartbeat_ages) * 1000, 2)}), flush=True)
            assert not engine.broker.overflow.is_set()
            assert not engine.store.orders()
            assert not engine.store.get("incident", "watchdog")
            assert not engine.store.get("incident", "engine_fault")
            assert max(heartbeat_ages) < 2
            assert max(waits) < 2
            print(json.dumps({"passed": True, "audit_queries": len(reads), "audit_p95_ms": round(statistics.quantiles(reads, n=20)[18] * 1000, 2), "overview_max_ms": round(max(waits) * 1000, 2), "max_engine_loop_age_ms": round(max(heartbeat_ages) * 1000, 2), "overview_bytes": len(json.dumps(value))}), flush=True)
        finally:
            stop.set()
            engine.stop()
            # The existing shutdown audits every saved run. Wait for the fixture's
            # journal writer to finish before TemporaryDirectory removes its files.
            engine.thread.join(timeout=60)
            assert not engine.thread.is_alive(), "Synthetic engine shutdown did not finish"


if __name__ == "__main__":
    main()
