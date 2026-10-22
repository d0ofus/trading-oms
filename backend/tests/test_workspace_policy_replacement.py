import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_workspace_fx_execution import fixture

from trading_oms_backend.workspace.credit_policy import CURRENT_POLICY as POLICY
from trading_oms_backend.workspace.store import Conflict


def request(run, mutation="a" * 32):
    return {
        "ids": [run["id"]],
        "expected_binding_hashes": {run["id"]: run["binding"]["hash"]},
        "target_policy_revision": POLICY,
        "mutation_id": mutation,
        "actor": "synthetic-operator",
    }


def test_restore_archived_unused_replacement_requires_explicit_fresh_action(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    run = small_run(engine, run)
    original = copy.deepcopy(run)
    created = engine.policy_replacement(**request(run))
    target = engine.store.get("run", created["review_ids"][0])
    target.update(archived=True, archive={"at": "2026-09-24T08:15:34+00:00", "actor": "operator"})
    engine.store.put("run", target["id"], target)
    preview = engine.policy_replacement_preview([run])
    assert preview["eligible"]
    item = preview["items"][0]
    assert item["action"] == "restore"
    assert engine.policy_replacement(**request(run)) == created
    assert engine.store.get("run", target["id"])["archived"]
    with pytest.raises(Conflict, match="restor"):
        engine.policy_replacement(**request(run, "b" * 32))
    body = {
        **request(run, "c" * 32),
        "action": "restore",
        "expected_replacement_states": {target["id"]: item["replacement_state"]},
    }
    restored = engine.policy_replacement(**body)
    assert restored["review_ids"] == created["review_ids"]
    assert engine.policy_replacement(**body) == restored
    actual = engine.store.get("run", target["id"])
    assert not actual["archived"] and not actual["armed"]
    assert actual["binding"] == target["binding"]
    assert actual["archive"] == target["archive"]
    assert engine.store.get("run", run["id"]) == original
    assert len(engine.store.list("run")) == 2
    assert not engine.store.orders() and not engine.broker.submitted


@pytest.mark.parametrize(
    "change", ["armed", "position", "reservation", "exit", "protection", "binding", "state"]
)
def test_restoration_rejects_changed_or_unsafe_target_atomically(tmp_path, monkeypatch, change):
    engine, run = fixture(tmp_path, monkeypatch)
    created = engine.policy_replacement(**request(run))
    target = engine.store.get("run", created["review_ids"][0])
    target["archived"] = True
    engine.store.put("run", target["id"], target)
    item = engine.policy_replacement_preview([run])["items"][0]
    body = {
        **request(run, "d" * 32),
        "action": "restore",
        "expected_replacement_states": {target["id"]: item["replacement_state"]},
    }
    if change in {"armed", "position"}:
        target[change] = True if change == "armed" else "0.01"
    elif change == "binding":
        target["binding"]["hash"] = "changed"
    elif change == "state":
        target["archive"] = {"at": "later archive"}
    elif change == "reservation":
        engine.store.put("reservation", "pending", {"run_id": target["id"], "active": True})
    else:
        engine.store.put(
            "exit_request" if change == "exit" else "fx_protection",
            target["id"],
            {"state": "working"},
        )
    engine.store.put("run", target["id"], target)
    with pytest.raises(Conflict):
        engine.policy_replacement(**body)
    assert engine.store.get("run", target["id"])["archived"]
    assert len(engine.store.list("run")) == 2
    assert not engine.broker.submitted


def small_run(engine, run):
    engine.contracts[run["conid"]].update(min_size="0.01", size_increment="0.01")
    result = engine.fx_compatibility(run["strategy_id"], 1, run["conid"], run["protection_type"])
    run = {
        **engine._build_run(
            run["strategy_id"],
            1,
            run["conid"],
            {"quantity": "0.01"},
            run["protection_type"],
            result["plan"]["hash"],
            "fx",
        ),
        "id": run["id"],
    }
    engine.store.put("run", run["id"], run)
    return run


def test_legacy_preview_and_inline_replacement_preserve_original(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    run = small_run(engine, run)
    original = copy.deepcopy(run)
    published = engine.store.version(run["strategy_id"], 1)
    preview = engine.arm_preview([run["id"]])["policy_replacement"]
    assert preview["eligible"] and preview["items"][0]["needs_replacement"]
    result = engine.policy_replacement(**request(run))
    new = engine.store.get("run", result["review_ids"][0])
    assert new["id"] != run["id"] and not new["armed"]
    assert new["binding"]["sizing"] == run["binding"]["sizing"]
    assert new["binding"]["strategy_hash"] == published["hash"]
    assert new["binding"]["execution_plan"]["funding_policy"] == POLICY
    assert new["binding"]["execution_plan"]["authorization_policy"] == "quiet_fx_v1"
    assert new["protection_type"] == run["protection_type"]
    assert engine.store.get("run", run["id"]) == original
    assert engine.store.version(run["strategy_id"], 1) == published
    assert not engine.store.orders() and not engine.broker.submitted
    assert list((tmp_path / "backups").glob("*.sqlite3"))


def test_retries_and_concurrent_reviews_reuse_one_unchanged_replacement(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    first = engine.policy_replacement(**request(run))
    assert engine.policy_replacement(**request(run)) == first
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda m: engine.policy_replacement(**request(run, m)), ["b" * 32, "c" * 32])
        )
    assert all(r["review_ids"] == first["review_ids"] for r in results)
    assert len(engine.store.list("run")) == 2
    new = engine.store.get("run", first["review_ids"][0])
    engine.store.put("run", new["id"], {**new, "armed": True})
    with pytest.raises(Conflict, match="replacement"):
        engine.policy_replacement(**request(run, "d" * 32))
    assert len(engine.store.list("run")) == 2


@pytest.mark.parametrize(
    "change", ["armed", "position", "reservation", "exit", "protection", "hash", "route"]
)
def test_replacement_rechecks_source_without_partial_creation(tmp_path, monkeypatch, change):
    engine, run = fixture(tmp_path, monkeypatch)
    body = request(run)
    if change in {"armed", "position"}:
        engine.store.put("run", run["id"], {**run, change: True if change == "armed" else "0.01"})
    elif change == "reservation":
        engine.store.put("reservation", "active", {"run_id": run["id"], "active": True})
    elif change in {"exit", "protection"}:
        kind = "exit_request" if change == "exit" else "fx_protection"
        engine.store.put(kind, run["id"], {"quantity": "0.01", "state": "working"})
    elif change == "hash":
        body["expected_binding_hashes"][run["id"]] = "stale"
    else:
        engine.contracts[run["conid"]]["routing_exchange"] = "OTHER"
    with pytest.raises(Conflict):
        engine.policy_replacement(**body)
    assert len(engine.store.list("run")) == 1
    assert not engine.store.list("policy_replacement")
    assert not engine.broker.submitted


def test_batch_failure_is_atomic_and_changed_quantity_does_not_resize(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    other = copy.deepcopy(run)
    other.update(id="b" * 32, armed=True)
    engine.store.put("run", other["id"], other)
    body = request(run)
    body["ids"].append(other["id"])
    body["expected_binding_hashes"][other["id"]] = other["binding"]["hash"]
    with pytest.raises(Conflict):
        engine.policy_replacement(**body)
    assert len(engine.store.list("run")) == 2
    assert not engine.store.list("policy_replacement")


def test_new_quantity_rules_block_replacement_without_resizing(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    run = small_run(engine, run)
    engine.contracts[run["conid"]].update(min_size="1", size_increment="1")
    preview = engine.policy_replacement_preview([run])
    assert not preview["eligible"] and preview["items"][0]["blockers"]
    with pytest.raises(Conflict):
        engine.policy_replacement(**request(run))
    assert engine.store.get("run", run["id"])["binding"]["sizing"]["quantity"] == "0.01"
    assert len(engine.store.list("run")) == 1


def test_batch_database_failure_rolls_back_first_replacement(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    other = {**run, "id": "b" * 32}
    engine.store.put("run", other["id"], other)
    original_write = engine.store.write
    created = []

    def fail_second(db, kind, key, value):
        if kind == "run" and key not in {run["id"], other["id"]}:
            created.append(key)
            if len(created) == 2:
                raise Conflict("Synthetic transaction failure")
        return original_write(db, kind, key, value)

    monkeypatch.setattr(engine.store, "write", fail_second)
    body = request(run)
    body["ids"].append(other["id"])
    body["expected_binding_hashes"][other["id"]] = other["binding"]["hash"]
    with pytest.raises(Conflict, match="transaction failure"):
        engine.policy_replacement(**body)
    assert len(created) == 2 and len(engine.store.list("run")) == 2
    assert not engine.store.list("policy_replacement")
    assert not engine.store.list("policy_replacement_receipt")


@pytest.mark.parametrize("template", range(4))
def test_stock_templates_keep_published_limits_and_protection(tmp_path, monkeypatch, template):
    from test_workspace_stock_execution import fixture as stock_fixture

    engine, run, published = stock_fixture(tmp_path, monkeypatch, template)
    engine.quotes[run["conid"]]["ask"]["price"] = "10"
    engine.quotes[run["conid"]]["bid"]["price"] = "9.95"
    run.update(armed=False, state="paused")
    engine.store.put("run", run["id"], run)
    result = engine.policy_replacement(**request(run))
    target = engine.store.get("run", result["review_ids"][0])
    assert target["binding"]["sizing"] == run["binding"]["sizing"]
    assert target["binding"]["strategy_hash"] == published["hash"]
    assert target["protection_type"] == run["protection_type"]
    assert target["binding"]["execution_plan"]["funding_policy"] == POLICY
    assert engine.store.get("run", run["id"]) == run
    assert not engine.broker.submitted


def test_past_broker_activity_needs_reconciliation_and_no_pending_cancellation(
    tmp_path, monkeypatch
):
    engine, run = fixture(tmp_path, monkeypatch)
    order = engine.store.reserve_order(
        "old", {"execution": "fx_breakout", "quantity": "1", "symbol": "AUD"}, run["id"], 100
    )
    assert not engine.policy_replacement_preview([run])["eligible"]
    with engine.store.transaction() as db:
        db.execute("UPDATE outbox SET state='cancelled' WHERE id='old'")
    engine.store.put("broker_order", str(order["broker_id"]), {"status": "Cancelled"})
    engine.store.put("reservation", "old", {"active": False})
    assert not engine.policy_replacement_preview([run])["eligible"]
    engine.reconciliation_evidence = {
        "ready": True,
        "instance": engine.process_identity,
        "epoch": engine.broker.epoch,
    }
    engine.store.put("cancel_request", str(order["broker_id"]), {"state": "requested"})
    assert not engine.policy_replacement_preview([run])["eligible"]
    engine.store.put("cancel_request", str(order["broker_id"]), {"state": "confirmed"})
    assert engine.policy_replacement_preview([run])["eligible"]
    original_orders = engine.store.orders()
    result = engine.policy_replacement(**request(run))
    assert engine.store.orders() == original_orders
    assert not engine.store.get("run", result["review_ids"][0])["armed"]


def test_replacement_receipts_survive_restart_and_rollback_blocks_new_mutations(
    tmp_path, monkeypatch
):
    from test_workspace_fx_execution import FXBroker

    from trading_oms_backend.workspace.engine import Engine
    from trading_oms_backend.workspace.store import Store

    engine, run = fixture(tmp_path, monkeypatch)
    result = engine.policy_replacement(**request(run))
    restarted = Engine(Store(tmp_path), FXBroker)
    assert restarted.policy_replacement(**request(run)) == result
    assert len(restarted.store.list("run")) == 2
    assert not restarted.store.get("run", result["review_ids"][0])["armed"]
    with pytest.raises(Conflict, match="identifier"):
        restarted.policy_replacement(**{**request(run), "actor": "different-operator"})
    monkeypatch.setenv("OMS_DISABLE_POLICY_REPLACEMENT", "1")
    with pytest.raises(Conflict, match="unavailable"):
        restarted.policy_replacement(**request(run, "b" * 32))


@pytest.mark.parametrize("stream", ["fx_midpoint", "fx_bidask"])
@pytest.mark.parametrize("clock", ["source_at", "received_at"])
def test_independent_freshness_is_neutral_but_dispatch_stays_blocked(
    tmp_path, monkeypatch, stream, clock
):
    from datetime import UTC, datetime, timedelta

    from test_workspace_credit_funding import new_run

    engine, run = new_run(tmp_path, monkeypatch)
    cache = engine._fx_cache(run["conid"])
    cache[stream][clock] = (datetime.now(UTC) - timedelta(seconds=16)).isoformat()
    preview = engine.arm_preview([run["id"]])
    assert preview["can_authorize"] and not preview["can_dispatch"]
    check = next(c for c in preview["checks"] if c["code"].startswith("fx_data_"))
    assert check["feed_health"] == "healthy" and check["execution_state"] == "waiting_quotes"
    assert not engine._fx_guard(run)
    assert not engine.broker.submitted


def test_authenticated_replacement_endpoint_bounds_and_audit_actor(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from trading_oms_backend.workspace.api import create_app

    fixture_engine, run = fixture(tmp_path, monkeypatch)
    app = create_app(tmp_path, "synthetic-replacement-pairing", start_engine=False)
    engine = app.state.engine
    monkeypatch.setattr(engine.broker, "subscribe", lambda conid: None)
    engine.contracts = fixture_engine.contracts
    engine.market_rules = fixture_engine.market_rules
    body = request(run)
    body.pop("actor")
    origin = "http://127.0.0.1:8000"
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        assert client.post("/api/runs/policy-replacement", json=body).status_code == 401
        client.post("/api/auth/pair", json={"token": "synthetic-replacement-pairing"})
        assert (
            client.post(
                "/api/runs/policy-replacement", json={**body, "ids": [run["id"]] * 6}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/runs/policy-replacement", json={**body, "actor": "forged"}
            ).status_code
            == 422
        )
        response = client.post("/api/runs/policy-replacement", json=body)
        assert response.is_success, response.text
        assert client.post("/api/runs/policy-replacement", json=body).json() == response.json()
    events = [e for e in engine.store.events() if e["type"] == "run.policy_replaced"]
    assert len(events) == 1 and events[0]["payload"]["actor"]
    assert not engine.store.orders()


def test_legacy_cash_failure_and_neutral_feed_health_remain_distinct(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    engine, run = fixture(tmp_path, monkeypatch)
    engine.currency_facts.pop(("SettledCash", "USD"))
    checks = {c["code"]: c for c in engine._fx_checks(run)}
    assert not checks["fx_funding"]["passed"]
    assert "cash balances" in checks["fx_funding"]["detail"]
    assert checks["fx_data"]["feed_health"] == "healthy"
    cache = engine._fx_cache(run["conid"])
    cache["fx_midpoint"]["source_at"] = (datetime.now(UTC) - timedelta(seconds=16)).isoformat()
    checks = {c["code"]: c for c in engine._fx_checks(run)}
    assert checks["fx_data"]["feed_health"] == "healthy"
    assert checks["fx_data"]["execution_state"] == "waiting_quotes"
    assert not checks["fx_data"]["passed"] and not checks["fx_data"]["authorization_ready"]
    cache["feeds"]["fx_midpoint"]["status"] = "failed"
    assert engine._fx_checks(run)[6]["feed_health"] == "blocked"
