import json
import time

import pytest
from fastapi.testclient import TestClient
from test_workspace_migration import SnapshotBroker, legacy_store, position

from trading_oms_backend.workspace.api import create_app
from trading_oms_backend.workspace.broker import GatewayData
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.startup import DeferredMigration


def pending(tmp_path, factory):
    store = legacy_store(tmp_path)
    gate = DeferredMigration(store.directory, broker_factory=factory)
    engine = Engine(store, migration=gate)
    return store, gate, engine


def finish(engine):
    deadline = time.monotonic() + 3
    while engine.migration.status == "checking" and time.monotonic() < deadline:
        engine.maintain()
        time.sleep(0.01)
    assert engine.migration.status != "checking"


def test_offline_pending_app_opens_with_history_and_no_execution_adapter(tmp_path):
    store = legacy_store(tmp_path)
    original = store.events()
    app = create_app(
        store.directory,
        "x" * 32,
        start_engine=False,
        defer_migration=True,
    )
    engine = app.state.engine
    assert type(engine.broker) is GatewayData
    assert not engine.requested_connection
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/workspace/session").status_code == 401
        client.headers["origin"] = "http://127.0.0.1:8000"
        assert client.post("/api/auth/pair", json={"token": "x" * 32}).is_success
        state = client.get("/api/workspace/session").json()
        assert state["migration"]["pending"]
        assert state["connection"] == "disconnected" and not state["entry_permission"]
        assert client.get("/api/strategies").is_success
        assert client.get("/api/strategies/catalog").is_success
        assert not store.get("migration", "unified_workspace")
    assert store.events()[: len(original)] == original
    assert list((store.directory / "backups" / "before-unification").glob("*.zip"))


@pytest.mark.parametrize(
    "method",
    [
        "attest",
        "begin_reconcile",
        "arm",
        "create_run",
        "cancel_entry",
        "close_position",
        "subscribe",
        "disarm",
        "review_incident",
    ],
)
def test_pending_migration_blocks_execution_commands_before_argument_processing(tmp_path, method):
    store, gate, engine = pending(tmp_path, lambda _: pytest.fail("unexpected Gateway"))
    original = store.orders()
    with pytest.raises(ValueError, match="migration"):
        engine.call(method)
    engine.maintain()
    health = json.loads((store.directory / "engine-health.json").read_text())
    assert health["armed"] is False and health["migration_pending"]
    assert store.orders() == original
    assert not engine.requested_connection and gate.pending


def test_failed_check_keeps_app_available_and_can_retry_without_auto_attestation(tmp_path):
    calls = []

    def factory(events):
        calls.append(1)
        observations = [dict(kind="broker_error", code=502)] if len(calls) == 1 else [position()]
        return SnapshotBroker(events, observations)

    store, gate, engine = pending(tmp_path, factory)
    assert engine.call("connect")["state"] == "checking_migration"
    assert engine.call("connect")["state"] == "checking_migration"
    finish(engine)
    assert gate.status == "blocked" and "502" in gate.detail
    assert engine.call("snapshot")["migration"]["pending"]
    assert not store.get("migration", "unified_workspace")
    engine.call("connect")
    finish(engine)
    assert gate.status == "complete" and not gate.pending
    assert store.get("migration", "unified_workspace")
    assert engine.requested_connection and not engine.attested and not engine.reconciled
    assert engine.call("snapshot")["entry_permission"] is False
    assert len(calls) == 2
    engine.stop()


@pytest.mark.parametrize(
    "observations",
    [
        [position("STK")],
        [position("")],
        [dict(kind="open_order", broker_id=9, status="Submitted", own_account=True)],
    ],
)
def test_fresh_nonflat_snapshot_stays_pending(tmp_path, observations):
    store, gate, engine = pending(tmp_path, lambda q: SnapshotBroker(q, observations))
    engine.call("connect")
    finish(engine)
    assert gate.pending and gate.status == "blocked"
    assert type(engine.broker) is GatewayData
    assert not store.get("migration", "unified_workspace")
    engine.stop()


def test_local_unresolved_order_is_displayed_without_restore_or_broker_recovery(tmp_path):
    store = legacy_store(tmp_path)
    store.reserve_order("pending", {"purpose": "exit", "quantity": 1}, "run", 10)
    gate = DeferredMigration(store.directory, broker_factory=lambda _: pytest.fail("Gateway"))
    engine = Engine(store, migration=gate)
    engine.call("connect")
    engine.maintain()
    assert gate.status == "blocked"
    assert store.orders()[0]["state"] == "reserved"
    assert not engine.requested_connection
    engine.stop()
    assert store.orders()[0]["state"] == "reserved"


def test_disconnect_and_shutdown_cancel_snapshot_without_activation(tmp_path):
    store, gate, engine = pending(tmp_path, lambda q: SnapshotBroker(q, ends=()))
    engine.call("connect")
    engine.call("disconnect")
    finish(engine)
    assert gate.pending and not engine.requested_connection
    assert not store.get("migration", "unified_workspace")
    engine.call("connect")
    engine.stop()
    assert not gate.worker.is_alive()
    assert not store.get("migration", "unified_workspace")


def test_owner_thread_keeps_http_responsive_during_snapshot(tmp_path):
    store, gate, engine = pending(tmp_path, lambda q: SnapshotBroker(q, ends=()))
    engine.start()
    try:
        engine.call("connect")
        assert engine.call("snapshot")["migration"]["status"] == "checking"
        with pytest.raises(ValueError, match="migration"):
            engine.call("arm")
    finally:
        engine.stop()
    assert not engine.thread.is_alive() and not gate.worker.is_alive()


def test_saved_armed_run_is_displayed_paused_and_requires_fresh_authorization(tmp_path):
    store = legacy_store(tmp_path)
    original = {"id": "old", "armed": True, "state": "armed"}
    store.put("run", "old", original)
    gate = DeferredMigration(store.directory, broker_factory=lambda q: SnapshotBroker(q))
    engine = Engine(store, migration=gate)
    assert store.get("run", "old") == original
    view = engine.call("snapshot")
    assert not view["runs"][0]["armed"] and view["runs"][0]["state"] == "paused"
    engine.call("connect")
    finish(engine)
    assert not store.get("run", "old")["armed"]
    assert store.get("run", "old")["state"] == "paused"
    assert not engine.attested and not engine.runtime
    engine.stop()


def test_disconnect_wins_over_completed_but_unconsumed_migration_snapshot(tmp_path):
    store, gate, engine = pending(tmp_path, lambda q: SnapshotBroker(q))
    engine.call("connect")
    gate.worker.join(timeout=3)
    assert gate.result.done()
    engine.call("disconnect")
    finish(engine)
    assert gate.pending and not engine.requested_connection
    assert not store.get("migration", "unified_workspace")
    assert any(e["type"] == "migration.snapshot.cancel_requested" for e in store.events())
    engine.stop()


def test_pending_engine_cannot_process_execution_callbacks(tmp_path):
    store, gate, engine = pending(tmp_path, lambda _: pytest.fail("Gateway"))
    original = store.events()
    engine.observe({"type": "execution", "id": "synthetic", "quantity": 1})
    assert store.events() == original and not store.orders()
    assert gate.pending and not engine.owned()
    with pytest.raises(ValueError, match="migration"):
        engine.activate_after_migration()
