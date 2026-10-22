import time

import pytest
from test_workspace_engine import BrokerDouble

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Conflict, Store


def fixture(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    for key in ("a", "b"):
        engine.store.put(
            "run",
            key,
            {
                "id": key,
                "name": key,
                "conid": 1,
                "armed": False,
                "position": "0",
                "state": "paused",
            },
        )
    return engine


def test_archive_offline_atomic_idempotent_persistent_and_unarmable(tmp_path):
    e = fixture(tmp_path)
    preview = e.archive_preview(["a", "b"])
    assert preview["eligible"]
    result = e.archive_confirm(preview["preview_id"], "mutation", "operator")
    assert e.archive_confirm(preview["preview_id"], "mutation", "operator") == result
    assert not e.store.display_runs()
    assert e.store.get("run", "a")["archived"]
    assert len([x for x in e.store.events() if x["type"] == "run.archived"]) == 2
    e2 = Engine(Store(tmp_path), BrokerDouble)
    assert not e2.store.display_runs()
    with pytest.raises(Conflict, match="Archived"):
        e2.arm_preview(["a"])


@pytest.mark.parametrize("field,value", [("armed", True), ("position", "0.1")])
def test_archive_rechecks_batch_without_partial_change(tmp_path, field, value):
    e = fixture(tmp_path)
    p = e.archive_preview(["a", "b"])
    e.store.put("run", "b", {**e.store.get("run", "b"), field: value})
    with pytest.raises(Conflict):
        e.archive_confirm(p["preview_id"], "mutation", "operator")
    assert not e.store.get("run", "a").get("archived")


def test_archive_rejects_reservations_exits_and_unresolved_broker_legs(tmp_path):
    e = fixture(tmp_path)
    e.store.put("exit_request", "a", {"requested_at": "fixture"})
    assert not e.archive_preview(["a"])["eligible"]
    e.store.put("exit_request", "a", {})
    order = e.store.reserve_order("intent", {"quantity": 1, "symbol": "TEST"}, "a", 100)
    assert not e.archive_preview(["a"])["eligible"]
    with e.store.transaction() as db:
        db.execute("UPDATE outbox SET state='cancelled' WHERE id='intent'")
    assert not e.archive_preview(["a"])["eligible"]
    e.connected = e.attested = e.reconciled = True
    e.reconciled_at = time.monotonic()
    e.reconciliation_evidence = {
        "ready": True,
        "instance": e.process_identity,
        "epoch": e.broker.epoch,
    }
    for broker_id in (order["broker_id"], order["broker_id"] + 2):
        e.store.put("broker_order", str(broker_id), {"status": "Cancelled"})
    e.store.put("reservation", "intent", {"active": False})
    p = e.archive_preview(["a"])
    assert p["eligible"], p
    e.archive_confirm(p["preview_id"], "mutation", "operator")
    e.restore_archived_observation(
        {
            "type": "order_status",
            "broker_id": order["broker_id"],
            "client_id": e.broker.client_id,
            "status": "ApiPending",
        }
    )
    assert e.store.get("run", "a")["archived"]
    e.restore_archived_observation(
        {
            "type": "order_status",
            "broker_id": order["broker_id"],
            "client_id": e.broker.client_id,
            "status": "Submitted",
        }
    )
    assert not e.store.get("run", "a")["archived"]
    assert e.incidents.applicable([e.store.get("run", "a")])
    assert not e.broker.submitted and not e.broker.cancelled


def test_archive_blocks_orphan_reservations_and_late_position_restores_visibility(tmp_path):
    e = fixture(tmp_path)
    e.store.put("reservation", "orphan", {"run_id": "a", "active": True})
    assert not e.archive_preview(["a"])["eligible"]
    p = e.archive_preview(["b"])
    e.archive_confirm(p["preview_id"], "mutation", "operator")
    e.restore_archived_observation(
        {"type": "position", "conid": 1, "quantity": "1", "own_account": True}
    )
    assert not e.store.get("run", "b")["archived"]
    assert e.store.get("reservation", "orphan")["active"]


def test_archive_endpoints_auth_bounds_and_actor(tmp_path):
    from fastapi.testclient import TestClient

    from trading_oms_backend.workspace.api import create_app

    app = create_app(tmp_path, "synthetic-archive-api-pairing", start_engine=False)
    app.state.engine.store.put("run", "a", {"id": "a", "position": "0", "armed": False})
    origin = "http://127.0.0.1:8000"
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        assert client.post("/api/runs/archive-preview", json={"ids": ["a"]}).status_code == 401
        client.post("/api/auth/pair", json={"token": "synthetic-archive-api-pairing"})
        assert client.post("/api/runs/archive-preview", json={"ids": ["a"] * 51}).status_code == 422
        p = client.post("/api/runs/archive-preview", json={"ids": ["a"]}).json()
        body = {"preview_id": p["preview_id"], "mutation_id": "a" * 32}
        assert (
            client.post("/api/runs/archive-confirm", json={**body, "actor": "forged"}).status_code
            == 422
        )
        assert client.post("/api/runs/archive-confirm", json=body).is_success
        assert client.post("/api/runs/archive-confirm", json=body).is_success
        assert app.state.engine.store.get("run", "a")["archive"]["actor"].startswith("operator-")
