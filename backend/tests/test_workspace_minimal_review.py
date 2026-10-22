from datetime import UTC, datetime, timedelta

import pytest
from test_workspace_engine import BrokerDouble
from test_workspace_incidents import arm_fixture, recovered_engine
from test_workspace_premarket_execution import Clock, fixture

from trading_oms_backend.workspace.authorization import RESUME_POLICY
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Store, now


def test_premarket_card_and_arming_use_execution_ticks_not_sampled_last(tmp_path, monkeypatch):
    e, r = fixture(tmp_path, monkeypatch)
    e.contracts[r["conid"]]["symbol"] = "HIVE"
    for state in e.components_for(r["conid"]).values():
        state["status"] = "healthy"
    data = e.data[r["conid"]]
    data["source_at"] = (Clock.stamp - timedelta(seconds=900)).isoformat()
    e.quotes[r["conid"]]["last"] = {"price": "600", "received_at": now()}
    card = e.data_snapshot(False)[0]
    assert card["session_open"] and card["history_ready"]
    assert card["feed_status"] != "market_closed"
    assert not card["execution_fresh"]
    assert "Source observation age" in card["execution_detail"]
    assert not e.incidents.open()  # Waiting for execution evidence is not an incident.
    data["source_at"] = now()
    assert e._run_feed_health(r)["execution_fresh"]


def test_paper_context_is_automatically_verified_without_human_attestation(tmp_path):
    e = Engine(Store(tmp_path), BrokerDouble)
    calls = []
    e.broker.attest = lambda: calls.append("verified")
    e.broker.reconcile = lambda: None
    e.connected = True
    e.observe({"type": "account_context", "paper": True, "count": 1})
    assert calls == ["verified"]
    assert e.attested and e.reconcile_inflight
    assert e.prepare_context(999)["status"] == "blocked"
    e.disconnect()
    assert "Operator disconnected" in e.prepare_context(999)["detail"]
    assert not e.requested_connection


def test_verified_engine_recovery_can_join_final_authorization(tmp_path, monkeypatch):
    e, item, _ = recovered_engine(tmp_path, monkeypatch, "engine_fault")
    r = arm_fixture(e, monkeypatch)
    original = e.arm_preview

    def preview(*args):
        result = original(*args)
        result["eligible_after_recovery_ack"] = True
        return result

    monkeypatch.setattr(e, "arm_preview", preview)
    current = e.incidents.get(item["id"])
    request = dict(
        ids=[r["id"]],
        mutation_id="dedicated-combined",
        review_instance=e.process_identity,
        recovery_acknowledgments=[{"id": current["id"], "revision": current["revision"]}],
    )
    e.arm(**request)
    assert e.incidents.get(item["id"])["restriction"] == "released"
    assert e.incidents.get(item["id"])["investigation"] == "open"
    assert e.store.get("run", r["id"])["armed"]
    assert not e.store.get("run", "other-run")["armed"]
    e.arm(**request)  # Same action is idempotent, including the release.


def suspended_fixture(tmp_path, monkeypatch):
    e, _, _ = recovered_engine(tmp_path, monkeypatch, automatic=True)
    r = arm_fixture(e, monkeypatch)
    r.update(
        armed=True,
        entries=2,
        authorization_status="authorized",
        authorization_instance=e.process_identity,
        authorization_context="context",
        resume_policy=RESUME_POLICY,
        authorization_id="approved",
        authorized_at=now(),
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        limits={"id": "stock_selected", "version": 2},
    )
    e.paper_context_token = "context"
    e.store.put("run", r["id"], r)
    return e, r


@pytest.mark.parametrize(
    "code,expected",
    [
        ("connectivity", "temporarily_suspended"),
        ("broker_2103", "temporarily_suspended"),
        ("watchdog", "revoked"),
        ("engine_fault", "revoked"),
        ("order_uncertain", "revoked"),
        ("missing_protection", "revoked"),
        ("callback_overflow", "revoked"),
    ],
)
def test_only_approved_routine_interruptions_can_suspend(tmp_path, monkeypatch, code, expected):
    e, r = suspended_fixture(tmp_path, monkeypatch)
    e.incident(code, "Fixture interruption")
    changed = e.store.get("run", r["id"])
    assert not changed["armed"]
    assert changed["authorization_status"] == expected
    assert changed["entries"] == 2


def test_integrity_failure_revokes_already_suspended_permission(tmp_path, monkeypatch):
    e, r = suspended_fixture(tmp_path, monkeypatch)
    e.incident("connectivity", "Routine interruption")
    e.incident("order_uncertain", "Uncertain submission")
    assert e.store.get("run", r["id"])["authorization_status"] == "revoked"


def test_invalid_continuity_revokes_suspended_authorization(tmp_path, monkeypatch):
    e, r = suspended_fixture(tmp_path, monkeypatch)
    e.data[r["conid"]] = {}
    e.incident("connectivity", "Routine interruption")
    e._data_gap(r["conid"], "Expected reconnect repair", routine_recovery=True)
    assert e.store.get("run", r["id"])["authorization_status"] == "temporarily_suspended"
    e._data_gap(r["conid"], "Invalid observations")
    assert e.store.get("run", r["id"])["authorization_status"] == "revoked"


@pytest.mark.parametrize(
    "reason, expected", [("transient", "temporarily_suspended"), ("unknown", "revoked")]
)
def test_feed_adapter_reason_reaches_resume_policy(tmp_path, monkeypatch, reason, expected):
    e, r = suspended_fixture(tmp_path, monkeypatch)
    e.data[r["conid"]] = {}
    e.fail_feed(
        {
            "conid": r["conid"],
            "request_kind": "trade",
            "code": 10189,
            "reason": reason,
            "request": 123,
        }
    )
    assert e.store.get("run", r["id"])["authorization_status"] == expected


def test_premarket_history_failure_is_session_scoped_and_resumable(tmp_path, monkeypatch):
    e, r = suspended_fixture(tmp_path, monkeypatch)
    r["binding"] = {"execution_plan": {"session_mode": "premarket_regular"}}
    e.store.put("run", r["id"], r)
    regular = {**r, "id": "regular", "binding": {"execution_plan": {"session_mode": "regular"}}}
    e.store.put("run", regular["id"], regular)
    e.premarket_history = {r["conid"]: {"status": "pending"}}
    e._premarket_history_failure(r["conid"], 162, "transient")
    assert e.store.get("run", r["id"])["authorization_status"] == "temporarily_suspended"
    assert e.store.get("run", "regular")["armed"]
    assert not e.incidents.applicable([regular])


def test_dispatch_exception_cannot_restore_old_authorization(tmp_path, monkeypatch):
    from test_workspace_stock_execution import enter
    from test_workspace_stock_execution import fixture as stock_fixture

    e, r, _ = stock_fixture(tmp_path, monkeypatch)

    def fail(intent):
        raise RuntimeError("Synthetic transport interruption")

    monkeypatch.setattr(e.broker, "submit_bracket", fail)
    order = enter(e, r)
    run = e.store.get("run", r["id"])
    assert order["state"] == "unknown"
    assert not run["armed"] and run["authorization_status"] == "revoked"
    assert run["entries"] == 1 and run["blocking_reason"]
    assert e.store.get("reservation", order["id"])["active"]


def test_resume_retains_counters_and_discards_old_crossing(tmp_path, monkeypatch):
    e, r = suspended_fixture(tmp_path, monkeypatch)
    # Isolate authorization transition; readiness and episode evidence are covered separately.
    r.update(armed=False, authorization_status="temporarily_suspended")
    e.store.put("run", r["id"], r)
    e.store.put("stock_trigger", r["id"], {"state": "triggered"})
    monkeypatch.setattr(e, "arm_preview", lambda *args: {"eligible": True})
    e.resume_authorizations()
    resumed = e.store.get("run", r["id"])
    assert resumed["armed"] and resumed["entries"] == 2
    assert resumed["authorization_id"] == "approved"
    assert resumed["live_after"] >= resumed["authorized_at"]
    assert not e.store.get("stock_trigger", r["id"])
    assert not e.broker.submitted
    restarted = Engine(e.store, BrokerDouble)
    assert restarted.store.get("run", r["id"])["authorization_status"] == "revoked"


@pytest.mark.parametrize("change", ["context", "expired", "disarm", "emergency"])
def test_resume_cannot_bypass_manual_or_context_restrictions(tmp_path, monkeypatch, change):
    e, r = suspended_fixture(tmp_path, monkeypatch)
    r.update(armed=False, authorization_status="temporarily_suspended")
    if change == "expired":
        r["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    e.store.put("run", r["id"], r)
    if change == "context":
        e.paper_context_token = "different"
    elif change == "disarm":
        e.disarm(r["id"])
    elif change == "emergency":
        e.store.set_emergency(True)
    monkeypatch.setattr(e, "arm_preview", lambda *args: {"eligible": True})
    e.resume_authorizations()
    assert not e.store.get("run", r["id"])["armed"]
