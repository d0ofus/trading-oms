"""Regressions for current operational state, isolated from any broker connection."""

import queue
import threading
import time

from test_workspace_fx_execution import fixture
from test_workspace_stable_reconciliation import ready

from trading_oms_backend.workspace.broker import GatewayData


def test_account_timeout_preserves_transport_and_reports_missing_component(tmp_path, monkeypatch):
    engine = ready(tmp_path)
    disconnected = []
    monkeypatch.setattr(engine.broker, "disconnect", lambda: disconnected.append(True))
    engine.begin_reconcile()
    engine.reconcile_parts = {"orders_end", "completed_orders_end", "executions_end", "account_end"}
    engine.reconcile_deadline = time.monotonic() - 1
    engine._maintain_reconciliation(time.monotonic())
    assert engine.connected and engine.reconcile_inflight
    assert not disconnected
    assert not engine.reconciled
    assert engine.reconciliation_progress()["missing"] == ["positions_end"]
    check = next(c for c in engine.readiness([]) if c["code"] == "reconciliation")
    assert check["status"] == "checking" and check["category"] == "progress"
    assert check["remediation"] is None and not check["passed"]


def test_unused_subscription_removes_while_unrelated_snapshot_pending(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.reconciled = False
    monkeypatch.setattr(engine.broker, "unsubscribe", lambda conid: None, raising=False)
    engine.store.put("exit_request", run["id"], {})
    engine.store.put("incident_cancel", run["id"], {"state": "completed"})
    assert engine._data_dependencies()["runs"] == []
    assert engine.unsubscribe(run["conid"]) == {"removed": True}
    assert not engine.store.get("subscription", str(run["conid"]))["active"]
    assert not engine.broker.submitted
    engine._flush_incident_cancellations()  # Empty/terminal work cannot crash maintenance.


def test_working_operation_without_optional_metadata_is_still_a_dependency():
    from trading_oms_backend.workspace.dependencies import operation_active

    assert operation_active("exit_request", {"state": "working"})
    assert not operation_active("exit_request", {})
    assert not operation_active("exit_request", {"state": "completed", "run_id": "old"})


def test_critical_notification_not_suppressed_by_existing_run(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.incident("order_uncertain", "Submitted order outcome unknown.", run=run)
    assert len(engine.store.list("notification")) == 1
    engine.incident("order_uncertain", "Submitted order outcome unknown.", run=run)
    assert len(engine.store.list("notification")) == 1


def test_service_duplicates_are_bounded_but_recurrence_restarts_evidence(tmp_path, monkeypatch):
    engine, _ = fixture(tmp_path, monkeypatch)
    event = {"type": "broker_error", "request": -1, "code": 2103}
    engine.observe(event)
    item = engine.incidents.open()[0]
    for _ in range(20):
        engine.observe(event)
    assert engine.incidents.get(item["id"])["occurrences"] == 1
    with engine.store.connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM events WHERE type='incident.duplicate_observation'"
            ).fetchone()[0]
            == 1
        )
    engine.observe({**event, "code": 2104})
    engine.observe(event)
    current = engine.incidents.get(item["id"])
    assert current["occurrences"] == 2 and current["failure_sequence"] > item["failure_sequence"]


def test_irrelevant_history_is_not_current_attention_or_fx_restriction(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.incident(
        "history_feed_failure",
        "Optional chart download failed.",
        conid=run["conid"],
        diagnostic={"fx": True, "signal_source": "MIDPOINT"},
    )
    assert engine.incidents.applicable([run]) == []
    assert engine.incidents.page()["items"] == []
    assert len(engine.incidents.open()) == 1  # Diagnostic evidence remains durable.


def test_required_unknown_execution_fault_remains_current(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.incident("engine_fault", "Unclassified execution integrity fault.")
    assert engine.incidents.applicable([run])
    assert engine.incidents.page()["items"][0]["category"] == "critical"


def test_run_requirement_is_not_recorded_or_notified_as_critical(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    item = engine.incident("run_configuration", "Published quantity is unsupported.", run=run)
    assert item["category"] == "requirement" and item["severity"] == "warning"
    assert not engine.store.list("notification")


def test_unused_feed_retires_without_observation_timer(tmp_path, monkeypatch):
    from trading_oms_backend.workspace.store import now

    engine, run = fixture(tmp_path, monkeypatch)
    old = engine.incident("quote_feed_failure", "Old unused contract.", conid=88)
    engine.store.put("subscription", "88", {"conid": 88, "active": False})
    engine.reconciliation_evidence = {
        "id": "current",
        "instance": engine.process_identity,
        "epoch": engine.broker.epoch,
        "started_at": now(),
        "completed_at": now(),
        "started_sequence": engine.incidents.watermark(),
        "ready": True,
    }
    engine.refresh_incidents()
    assert engine.incidents.get(old["id"])["release_kind"] == "dependency_retired"
    assert not engine.store.get("run", run["id"])["armed"]


def test_fx_live_signal_does_not_require_display_history(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine._fx_cache(run["conid"])["sources"]["MIDPOINT"]["status"] = "failed"
    health = engine._fx_feed_health(run["conid"], run)
    assert health["execution_fresh"]
    assert health["feed_health"] == "healthy"
    assert not health["history_ready"]


def test_fx_remove_restore_restarts_streams_and_retains_downloaded_candles(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from trading_oms_backend.workspace.store import now

    engine, run = fixture(tmp_path, monkeypatch)
    conid = run["conid"]
    cache = engine._fx_cache(conid)
    bars = cache["sources"]["MIDPOINT"]["bars"]
    bars["fixture"] = {"close": "0.65"}
    monkeypatch.setattr(engine.broker, "unsubscribe", lambda conid: None, raising=False)
    engine.unsubscribe(conid)
    engine.subscribe(conid)
    assert all(s["status"] == "queued" for s in cache["feeds"].values())
    assert cache["sources"]["MIDPOINT"]["status"] == "completed"
    assert "fixture" in bars
    assert not cache.get("fx_bidask") and not cache.get("fx_midpoint")
    for _ in range(2):
        cache["next_tick"] = 0
        engine._fx_data_maintain()
    engine.data[conid]["live"] = True
    for kind, state in cache["feeds"].items():
        engine._fx_data_observation(
            {
                "type": kind,
                "conid": conid,
                "request": state["request"],
                "epoch": engine.broker.epoch,
                "timestamp": int(datetime.now(UTC).timestamp()),
                "received_at": now(),
                "price": "0.65005",
                "bid": "0.65",
                "ask": "0.6501",
            }
        )
    assert engine._fx_feed_health(conid, run)["execution_fresh"]
    assert not engine.broker.submitted


def test_single_account_positions_subscribe_once_and_snapshot_can_be_empty(monkeypatch):
    from ibapi.client import EClient

    monkeypatch.setattr(EClient, "connect", lambda *args: None)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    gateway = GatewayData(queue.Queue())
    gateway.connect()
    gateway._accounts = ("DU000000",)
    calls = []
    for method in (
        "reqPositions",
        "reqPositionsMulti",
        "reqAllOpenOrders",
        "reqCompletedOrders",
        "reqExecutions",
        "reqAccountSummary",
        "reqAccountUpdatesMulti",
        "reqPnL",
    ):
        monkeypatch.setattr(
            gateway.client, method, lambda *args, method=method: calls.append((method, args))
        )
    gateway.reconciliation_id = "first"
    gateway.reconcile()
    assert [c[0] for c in calls].count("reqPositions") == 1
    assert not any(c[0] == "reqPositionsMulti" for c in calls)
    gateway.client.positionEnd()
    event = gateway.observations.get_nowait()
    assert event["type"] == "positions_end"
    assert event["reconciliation_id"] == "first"
    gateway.client.openOrderEnd()
    gateway.client.completedOrdersEnd()
    gateway.reconciliation_id = "second"
    gateway.reconcile()
    assert [c[0] for c in calls].count("reqPositions") == 1
    events = []
    while not gateway.observations.empty():
        events.append(gateway.observations.get_nowait())
    assert any(e["type"] == "positions_end" and e["reconciliation_id"] == "second" for e in events)
    ids = [
        args[0]
        for method, args in calls
        if method in {"reqExecutions", "reqAccountSummary", "reqAccountUpdatesMulti", "reqPnL"}
    ]
    assert len(ids) == len(set(ids)) and min(ids) > 1000


def test_preparation_lease_close_and_expiry_cannot_lock_subscription(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(engine.broker, "reconcile", lambda: None, raising=False)
    engine.prepare_context(run["conid"], "fx", run["strategy_id"], 1, "a" * 32)
    assert any(
        d["code"] == "preparation" for d in engine._data_dependencies()["reasons"][run["conid"]]
    )
    engine.release_preparation("a" * 32)
    result = engine.prepare_context(run["conid"], "fx", run["strategy_id"], 1, "a" * 32)
    assert result["status"] == "cancelled"
    assert not engine._data_dependencies()["reasons"].get(run["conid"])
    engine.prepare_context(run["conid"], "fx", run["strategy_id"], 1, "b" * 32)
    engine._preparation_leases["b" * 32]["expires_clock"] = 0
    assert not engine._data_dependencies()["reasons"].get(run["conid"])


def test_actual_dependency_names_run_and_does_not_cancel_implicitly(tmp_path, monkeypatch):
    import pytest

    from trading_oms_backend.workspace.store import Conflict

    engine, run = fixture(tmp_path, monkeypatch)
    engine.store.put("run", run["id"], {**run, "armed": True})
    with pytest.raises(Conflict) as error:
        engine.unsubscribe(run["conid"])
    assert error.value.dependencies[0]["run_id"] == run["id"]
    assert engine.store.get("run", run["id"])["armed"]
    assert not engine.broker.submitted


def test_fx_virtual_position_does_not_own_a_subscription(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.positions[run["conid"]] = {
        "quantity": "8600",
        "sec_type": "CASH",
        "own_account": True,
        "currency": "USD",
    }
    assert not engine._data_dependencies()["reasons"].get(run["conid"])


def test_unknown_service_notice_is_diagnostic_but_unknown_order_is_not(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.observe({"type": "broker_error", "request": -1, "code": 9999, "context": "broker"})
    assert not engine.incidents.applicable([run])
    assert not engine.incidents.page()["items"]
    assert engine.incidents.page(view="diagnostics")["items"]
    engine.incident("dispatch_uncertain", "Unresolved submitted order.")
    assert engine.incidents.applicable([run])


def test_optional_history_failure_does_not_reset_an_armed_fx_reference(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.store.put("run", run["id"], {**run, "armed": True})
    sentinel = {"live_reference": True}
    engine.runtime[run["id"]] = sentinel
    state = engine._fx_cache(run["conid"])["sources"]["MIDPOINT"]
    engine._fx_data_failure(
        run["conid"], state, "history", "unavailable", "Display history unavailable", "MIDPOINT"
    )
    assert engine.runtime[run["id"]] is sentinel
    assert engine.store.get("run", run["id"])["armed"]
    assert not engine.incidents.applicable([run])


def test_history_service_does_not_suspend_live_only_authorization(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.store.put("run", run["id"], {**run, "armed": True, "position": "0.01"})
    engine.service_incident("broker_2105", "Historical farm unavailable.")
    engine.incident("history_feed_failure", "Optional display history failed.", conid=run["conid"])
    assert engine.store.get("run", run["id"])["armed"]
    assert not engine.incidents.applicable([run])


def test_current_attention_pages_skip_diagnostic_history(tmp_path, monkeypatch):
    engine, _ = fixture(tmp_path, monkeypatch)
    critical = engine.incident("engine_fault", "Unknown execution integrity fault.")
    for conid in range(100, 105):
        engine.incident("history_feed_failure", "Unused chart history.", conid=conid)
    page = engine.incidents.page(limit=2)
    assert [i["id"] for i in page["items"]] == [critical["id"]]
    assert page["next_cursor"] is None


def test_required_graph_history_remains_blocking(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    other = {
        "id": "history-run",
        "conid": 99,
        "binding": {"execution_plan": {"requirements": {"kind": "stock_bracket", "history": True}}},
    }
    engine.incident("history_feed_failure", "Required reference history failed.", conid=99)
    assert engine._requires_downloaded_history(other)
    assert engine.incidents.applicable([other])
    assert not engine.incidents.applicable([run])


def test_positive_never_submitted_proof_allows_removal_without_broker_snapshot(
    tmp_path, monkeypatch
):
    engine, run = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(engine.broker, "unsubscribe", lambda conid: None, raising=False)
    engine.store.reserve_order(
        "local-only", {"conid": run["conid"], "quantity": "0.01"}, run["id"], 42
    )
    engine.store.transition("local-only", "cancelled", {"reason": "fixture"})
    engine.store.event("order.dispatch.blocked", {"id": "local-only", "never_submitted": True})
    engine.reconciled = False
    assert engine.unsubscribe(run["conid"]) == {"removed": True}


def test_order_concern_needs_positive_outcome_then_clears_without_ack(tmp_path, monkeypatch):
    from trading_oms_backend.workspace.store import now

    engine, run = fixture(tmp_path, monkeypatch)
    order = engine.store.reserve_order(
        "unknown-test",
        {"conid": run["conid"], "execution": "fx_breakout", "quantity": "0.01"},
        run["id"],
        42,
    )
    engine.store.transition("unknown-test", "cancelled", {"reason": "fixture"})
    item = engine.incident(
        "order_uncertain",
        "Outcome needs evidence.",
        order_context={
            "order_id": "unknown-test",
            "run_id": run["id"],
            "broker_id": order["broker_id"],
        },
    )
    engine.reconciliation_evidence = {
        "id": "complete-current",
        "instance": engine.process_identity,
        "epoch": engine.broker.epoch,
        "started_at": now(),
        "completed_at": now(),
        "started_sequence": engine.incidents.watermark(),
        "ready": True,
    }
    engine.refresh_incidents()
    assert engine.incidents.get(item["id"])["restriction"] != "released"
    engine.broker_orders[order["broker_id"]] = {"status": "Cancelled"}
    engine.refresh_incidents()
    assert engine.incidents.get(item["id"])["restriction"] == "released"
    assert not engine.store.get("run", run["id"])["armed"]
    assert not engine.broker.submitted
