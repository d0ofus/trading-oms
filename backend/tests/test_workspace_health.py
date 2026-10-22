import json
import os
import time

import pytest
from test_workspace_engine import BrokerDouble

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.health import atomic_health, watchdog_status
from trading_oms_backend.workspace.store import Conflict, Store
from trading_oms_backend.workspace.watchdog import Watchdog


def healthy_watchdog(engine):
    engine.write_health()
    monitor = Watchdog(
        engine.store.directory,
        os.getpid(),
        instance=engine.process_identity,
        clock=time.monotonic,
        wall_clock=time.time,
    )
    assert monitor.tick()
    return monitor


def test_new_watchdog_waits_for_its_engine_and_old_watchdog_is_fenced(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    atomic_health(tmp_path / "engine-health.json", {"pid": 111, "timestamp": time.time()})
    monitor = Watchdog(tmp_path, os.getpid(), instance=engine.process_identity)
    assert monitor.tick()
    assert not watchdog_status(engine.store)["ready"]
    healthy_watchdog(engine)
    assert engine.watchdog_status()["ready"]
    replacement = Engine(engine.store, BrokerDouble)
    assert not monitor.tick()
    assert not engine.store.emergency()
    assert not replacement.watchdog_status()["ready"]


@pytest.mark.parametrize("change", ["missing", "malformed", "instance", "pid", "future", "stale"])
def test_watchdog_review_and_readiness_reject_invalid_health(tmp_path, change):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.connected = engine.attested = engine.reconciled = True
    healthy_watchdog(engine)
    path = tmp_path / "watchdog-health.json"
    value = json.loads(path.read_text())
    if change == "missing":
        path.unlink()
    elif change == "malformed":
        path.write_text("{")
    else:
        if change == "instance":
            value["instance"] = "previous"
        elif change == "pid":
            value["engine_pid"] = -1
        elif change == "future":
            value["timestamp"] += 100
        else:
            value["monotonic"] -= 16
        atomic_health(path, value)
    engine.incident("watchdog", "Fixture watchdog interruption")
    with pytest.raises(Conflict, match="[Ww]atchdog"):
        engine.review_incident("watchdog")
    assert not next(c for c in engine.readiness() if c["code"] == "watchdog")["passed"]
    assert not engine.store.get("incident", "watchdog")["resolved"]
    healthy_watchdog(engine)
    with pytest.raises(Conflict, match="reconciliation"):
        engine.review_incident("watchdog")


def test_watchdog_loss_disarms_without_liquidating(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    healthy_watchdog(engine)
    engine.monitor_watchdog()
    engine.store.put("run", "r", {"id": "r", "armed": True, "position": "0"})
    (tmp_path / "watchdog-health.json").unlink()
    engine.monitor_watchdog()
    assert not engine.store.get("run", "r")["armed"]
    assert not engine.store.get("incident", "watchdog")["resolved"]
    assert not engine.broker.submitted
    assert not engine.broker.cancelled
    healthy_watchdog(engine)
    engine.monitor_watchdog()
    assert not engine.store.get("incident", "watchdog")["resolved"]


def test_watchdog_failure_does_not_disable_owned_crypto_stop(tmp_path):
    from test_workspace_unified import confirm, crypto_engine, crypto_entry

    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    confirm(engine, entry, "0.1")
    engine.monitor_watchdog()
    (tmp_path / "watchdog-health.json").unlink()
    engine.monitor_watchdog()
    assert not engine.store.get("run", run["id"])["armed"]
    engine._crypto_trade({"conid": 456, "timestamp": time.time(), "price": "98"})
    assert engine.broker.submitted[-1]["purpose"] == "exit"


def test_loss_between_reservation_and_dispatch_never_reaches_broker(tmp_path):
    from test_workspace_unified import crypto_engine, crypto_entry

    engine, run = crypto_engine(tmp_path)
    original = engine.store.reserve_order

    def reserve(*args, **kwargs):
        result = original(*args, **kwargs)
        (tmp_path / "watchdog-health.json").unlink()
        return result

    engine.store.reserve_order = reserve
    crypto_entry(engine, run)
    assert not engine.broker.submitted
    assert engine.store.orders()[0]["state"] == "cancelled"
    assert not engine.store.list("reservation")[0]["active"]
    assert not engine.store.get("run", run["id"])["armed"]


def test_watchdog_startup_timeout_uses_monotonic_time(tmp_path):
    mono, wall = [100.0], [1000.0]
    store = Store(tmp_path)
    store.put("workspace", "engine_owner", {"instance": "fixture", "pid": 123})

    class NoDelivery:
        def __init__(self, *_):
            pass

        def deliver(self, *_):
            return False

    monitor = Watchdog(
        tmp_path,
        123,
        instance="fixture",
        clock=lambda: mono[0],
        wall_clock=lambda: wall[0],
        monitoring=NoDelivery,
    )
    wall[0] += 5000
    assert monitor.tick()
    assert not store.emergency()
    mono[0] += 31
    assert monitor.tick()
    assert store.emergency()
    assert len(store.list("notification")) == 1
    monitor.tick()
    assert len(store.list("notification")) == 1


def test_atomic_heartbeat_retries_windows_reader_contention(tmp_path, monkeypatch):
    import trading_oms_backend.workspace.health as health

    original, calls = os.replace, []

    def replace(source, destination):
        calls.append(source)
        if len(calls) == 1:
            raise PermissionError("Windows reader has not released its handle")
        return original(source, destination)

    monkeypatch.setattr(health.os, "replace", replace)
    path = tmp_path / "heartbeat.json"
    atomic_health(path, {"instance": "fresh"})
    assert json.loads(path.read_text())["instance"] == "fresh"
    assert len(calls) == 2
    assert not list(tmp_path.glob("*.pending"))


def test_watchdog_review_waits_for_post_incident_heartbeat(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.connected = engine.attested = engine.reconciled = True
    healthy_watchdog(engine)
    engine.incident("watchdog", "test loss")
    with pytest.raises(Conflict, match="after this incident"):
        engine.review_incident("watchdog")
    healthy_watchdog(engine)
    with pytest.raises(Conflict, match="reconciliation"):
        engine.review_incident("watchdog")


def test_owner_change_during_heartbeat_read_cannot_overwrite_new_owner_health(
    tmp_path, monkeypatch
):
    import trading_oms_backend.workspace.watchdog as watchdog

    engine = Engine(Store(tmp_path), BrokerDouble)
    monitor = healthy_watchdog(engine)
    read = watchdog.read_health

    def transfer(path):
        result = read(path)
        Engine(engine.store, BrokerDouble)
        atomic_health(tmp_path / "watchdog-health.json", {"instance": "new-health-sentinel"})
        return result

    monkeypatch.setattr(watchdog, "read_health", transfer)
    assert not monitor.tick()
    assert (
        json.loads((tmp_path / "watchdog-health.json").read_text())["instance"]
        == "new-health-sentinel"
    )
    assert not engine.store.emergency()


def test_engine_hang_uses_twenty_seconds_after_matching_startup(tmp_path):
    mono = [100.0]
    store = Store(tmp_path)
    store.put("workspace", "engine_owner", {"instance": "fixture", "pid": 123})
    store.put("run", "r", {"id": "r", "armed": True, "position": "1"})
    atomic_health(
        tmp_path / "engine-health.json",
        {"instance": "fixture", "pid": 123, "sequence": 1, "timestamp": 99, "monotonic": 99},
    )

    class NoDelivery:
        def __init__(self, *_):
            pass

        def deliver(self, *_):
            return False

    monitor = Watchdog(
        tmp_path,
        123,
        instance="fixture",
        clock=lambda: mono[0],
        wall_clock=lambda: 1000,
        monitoring=NoDelivery,
    )
    assert monitor.tick()
    mono[0] = 118
    assert monitor.tick()
    assert not store.emergency()
    mono[0] = 119
    assert monitor.tick()
    assert store.emergency()
    assert not store.get("run", "r")["armed"]
    assert store.get("run", "r")["position"] == "1"
    assert len(store.list("notification")) == 1


def test_same_instance_starting_to_running_does_not_terminate_watchdog(tmp_path, monkeypatch):
    import trading_oms_backend.workspace.watchdog as watchdog

    engine = Engine(Store(tmp_path), BrokerDouble)
    monitor = healthy_watchdog(engine)
    read = watchdog.read_health

    def finish_startup(path):
        value = read(path)
        owner = engine.store.get("workspace", "engine_owner")
        engine.store.put("workspace", "engine_owner", {**owner, "state": "running"})
        return value

    monkeypatch.setattr(watchdog, "read_health", finish_startup)
    assert monitor.tick()
    assert engine.watchdog_status()["ready"]
