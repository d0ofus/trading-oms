"""Deterministic paper-only lifecycle tests; no socket or broker credentials."""

import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_workspace_engine import BrokerDouble
from test_workspace_health import healthy_watchdog

from trading_oms_backend.workspace import engine, operations, paper_test, store
from trading_oms_backend.workspace.graph import templates
from trading_oms_backend.workspace.health_file import publish_health
from trading_oms_backend.workspace.sessions import execution_bounds
from trading_oms_backend.workspace.store import Conflict, Store


class Clock(datetime):
    stamp = datetime(2026, 9, 17, 14, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.stamp.astimezone(tz)


class OfflineBroker(BrokerDouble):
    def submit_bracket(self, intent):
        self.submitted.append(intent)

    def submit_exit(self, intent):
        self.submitted.append(intent)

    def heartbeat(self):
        pass

    def reconcile(self):
        pass


@pytest.fixture
def ready(tmp_path, monkeypatch):
    Clock.stamp = datetime(2026, 9, 17, 14, tzinfo=UTC)
    for module in (engine, operations, paper_test, store):
        monkeypatch.setattr(module, "datetime", Clock)
    subject = engine.Engine(Store(tmp_path), OfflineBroker)
    healthy_watchdog(subject)
    subject.connected = subject.attested = subject.reconciled = subject.clock_ok = True
    subject.code_verified = True
    subject.server_version = 220
    subject.reconciled_at = subject.pnl_at = time.monotonic()
    subject.daily_pnl = Decimal(0)
    subject.next_id = 100
    subject.facts = {
        "AvailableFunds": "10000",
        "GrossPositionValue": "0",
        "NetLiquidation": "10000",
    }
    subject.contracts[1] = {
        "conid": 1,
        "symbol": "AAPL",
        "sec_type": "STK",
        "currency": "USD",
        "primary_exchange": "NASDAQ",
        "market_rule": 1,
        "time_zone": "US/Eastern",
        "trading_hours": "20260917:0400-20260917:2000;20260918:0400-20260918:2000",
    }
    subject.data[1] = {"live": True, "warm": False, "received_at": None}
    subject.quotes[1] = {
        side: {"price": price, "received_at": store.now()}
        for side, price in (("bid", "100"), ("ask", "100.02"))
    }
    subject.market_rules[1] = [{"low": "0", "increment": "0.01"}]
    return subject


def prepared(subject, hours="regular"):
    document = templates()[1]["document"]
    document["schema_version"] = 4
    document["settings"]["trading_hours"] = hours
    draft = subject.store.save_draft(None, "Scheduled test", document, 0)
    version = subject.store.publish(draft["id"], 1)
    run = {
        "id": "run",
        "name": "Scheduled test",
        "strategy_id": draft["id"],
        "version": version["version"],
        "symbol": "AAPL",
        "conid": 1,
        "state": "ready",
        "armed": False,
        "entries": 0,
        "position": "0",
    }
    subject.store.put("run", "run", run)
    return run


def test_quote_only_connection_test_is_one_shot_and_cancels_after_ack(ready):
    assert ready.connection_diagnostics(1)["eligible"]
    assert not ready.broker.submitted
    preview = ready.paper_test_preview(1, "extended")
    assert preview["eligible"]
    assert preview["prices"] == {"limit": "99.00", "stop": "98.00", "stop_limit": "97.90"}
    trial = ready.start_paper_test(preview["id"])
    assert ready.start_paper_test(preview["id"]) == trial
    assert len(ready.broker.submitted) == 1
    payload = ready.store.orders()[0]["payload"]
    assert payload["quantity"] == 1 and payload["outside_rth"] is True
    assert payload["stop_limit"] == "97.90"
    assert ready.store.list("reservation")[0]["risk"] == "1.10"
    assert datetime.fromisoformat(payload["expires_at"]) - Clock.stamp == timedelta(seconds=30)
    order = ready.store.orders()[0]
    ready._order_observation({"broker_id": order["broker_id"], "status": "Submitted"})
    ready._maintain_paper_tests()
    assert not ready.broker.cancelled
    Clock.stamp += timedelta(seconds=5)
    ready._maintain_paper_tests()
    assert ready.broker.cancelled == [100]
    assert ready.store.get("paper_connection_test", trial["id"])["state"] == "cancel_pending"
    ready._order_observation({"broker_id": 100, "status": "Cancelled"})
    ready.reconciled = True
    ready._maintain_paper_tests()
    assert ready.store.get("paper_connection_test", trial["id"])["state"] == "cancel_pending"
    reservation = ready.store.get("reservation", order["id"])
    ready.store.put("reservation", order["id"], {**reservation, "active": False})
    ready._maintain_paper_tests()
    assert ready.store.get("paper_connection_test", trial["id"])["state"] == "cancelled_verified"
    assert not ready.store.get("qualification", "broker_evidence")


def test_closed_session_and_stale_quotes_cannot_dispatch_a_test(ready):
    Clock.stamp = datetime(2026, 9, 17, 7, tzinfo=UTC)
    for quote in ready.quotes[1].values():
        quote["received_at"] = store.now()
    assert ready.connection_diagnostics(1)["eligible"]
    preview = ready.paper_test_preview(1, "extended")
    assert not preview["eligible"]
    with pytest.raises(Conflict):
        ready.start_paper_test(preview["id"])
    Clock.stamp = datetime(2026, 9, 17, 14, tzinfo=UTC)
    assert not ready.connection_diagnostics(1)["eligible"]
    assert not ready.broker.submitted


@pytest.mark.parametrize("change", ["epoch", "context", "contract", "crypto", "fx"])
def test_stock_diagnostic_cannot_cross_contexts_or_instrument_families(ready, change):
    preview = ready.paper_test_preview(1)
    if change == "epoch":
        ready.broker.epoch += 1
    elif change == "context":
        ready.paper_context_token = "synthetic-new-context"
    elif change == "contract":
        ready.contracts[1]["symbol"] = "MSFT"
    else:
        ready.contracts[1]["sec_type"] = "CRYPTO" if change == "crypto" else "CASH"
        assert not ready.connection_diagnostics(1)["eligible"]
    with pytest.raises(Conflict):
        ready.start_paper_test(preview["id"])
    assert not ready.broker.submitted
    assert not ready.store.orders()


@pytest.mark.parametrize("change", ["emergency", "watchdog"])
def test_diagnostic_reservation_cannot_bypass_late_emergency_or_watchdog_failure(ready, change):
    preview = ready.paper_test_preview(1)
    reserve = ready.store.reserve_order

    def interrupted(*args, **kwargs):
        result = reserve(*args, **kwargs)
        if change == "emergency":
            ready.store.set_emergency(True)
        else:
            (ready.store.directory / "watchdog-health.json").unlink()
        return result

    ready.store.reserve_order = interrupted
    ready.start_paper_test(preview["id"])
    assert not ready.broker.submitted
    assert ready.store.orders()[0]["state"] == "cancelled"
    assert not ready.store.list("reservation")[0]["active"]


def test_preview_expiry_and_changed_price_require_new_review(ready):
    preview = ready.paper_test_preview(1)
    Clock.stamp += timedelta(seconds=16)
    with pytest.raises(Conflict, match="current eligible"):
        ready.start_paper_test(preview["id"])
    for quote in ready.quotes[1].values():
        quote["received_at"] = store.now()
    preview = ready.paper_test_preview(1)
    ready.quotes[1]["bid"]["price"] = "98"
    with pytest.raises(Conflict, match="below bid"):
        ready.start_paper_test(preview["id"])
    assert not ready.store.orders()


def test_unexpected_test_fill_stays_visible_and_is_never_repeated(ready):
    preview = ready.paper_test_preview(1)
    trial = ready.start_paper_test(preview["id"])
    ready._execution(
        {
            "type": "execution",
            "client_id": 71,
            "broker_id": 100,
            "execution_id": "test.01",
            "conid": 1,
            "symbol": "AAPL",
            "side": "BOT",
            "quantity": "1",
            "price": "99",
        }
    )
    ready._maintain_paper_tests()
    assert (
        ready.store.get("paper_connection_test", trial["id"])["state"]
        == "position_requires_attention"
    )
    assert not ready.store.get("run", trial["run_id"])["armed"]
    with pytest.raises(Conflict):
        ready.remove_run(trial["run_id"])
    ready.start_paper_test(preview["id"])
    assert len(ready.broker.submitted) == 1


@pytest.mark.parametrize("closed", [False, True])
def test_extended_owned_exit_retains_session_flag_and_waits_when_closed(ready, closed):
    trial = ready.start_paper_test(ready.paper_test_preview(1)["id"])
    ready._execution(
        {
            "type": "execution",
            "client_id": 71,
            "broker_id": 100,
            "execution_id": "exit.fixture.01",
            "conid": 1,
            "symbol": "AAPL",
            "side": "BOT",
            "quantity": "1",
            "price": "99",
        }
    )
    ready.reconciled = True
    if closed:
        ready.contracts[1]["trading_hours"] = "20260917:CLOSED"
        with pytest.raises(Conflict, match="session is closed"):
            ready.close_position(trial["run_id"])
        assert ready.store.get("exit_request", trial["run_id"])
        assert len(ready.broker.submitted) == 1
    else:
        ready.close_position(trial["run_id"])
        assert ready.broker.submitted[-1]["outside_rth"] is True
        assert ready.broker.submitted[-1]["purpose"] == "exit"


def test_future_authorization_defers_data_but_cannot_dispatch_early_or_after_restart(ready):
    prepared(ready)
    preview = ready.arm_preview(["run"], session_date="2026-09-18")
    assert preview["eligible"]
    ready.arm(["run"], "future", session_date="2026-09-18")
    run = ready.store.get("run", "run")
    assert run["state"] == "waiting_session" and run["armed"]
    assert not ready._session_permission(run)
    ready.data[1]["warm"] = True
    with pytest.raises(Conflict, match="not open"):
        ready._enter(
            run,
            {"stop": Decimal(99), "target": None},
            {"minutes_to_close": 120},
            ready.store.capture({"fixture": True}),
        )
    restarted = engine.Engine(ready.store, OfflineBroker)
    assert not restarted.store.get("run", "run")["armed"]
    assert not ready.broker.submitted


def test_batch_date_holiday_and_extended_supervision_checks(ready):
    prepared(ready, "extended")
    assert not ready.arm_preview(["run"], session_date="2026-09-19")["eligible"]
    assert not ready.arm_preview(["run"], session_date="2026-09-25")["eligible"]
    preview = ready.arm_preview(["run"], session_date="2026-09-18", unattended=True)
    assert not next(c for c in preview["checks"] if c["code"] == "extended_qualification_run")[
        "passed"
    ]
    ready.contracts[1]["trading_hours"] = ""
    assert not ready.arm_preview(["run"], session_date="2026-09-18")["eligible"]


def test_calendar_handles_dst_early_close_and_broker_restricted_hours():
    assert execution_bounds("2026-11-27")[1].hour == 18  # 13:00 New York.
    assert execution_bounds("2026-03-06")[0].hour == 14
    assert execution_bounds("2026-03-09")[0].hour == 13
    contract = {"time_zone": "America/New_York", "trading_hours": "20261127:0400-20261127:1700"}
    assert execution_bounds("2026-11-27", "extended", contract)[1].hour == 22
    contract["trading_hours"] = "20261127:0400-20261127:1200,20261127:1300-20261127:1700"
    assert execution_bounds("2026-11-27", "extended", contract) is None


def prove_reconciliation(subject):
    subject.reconciled = True
    subject.last_loop = subject.reconciled_at = time.monotonic()
    subject.reconciliation_evidence = {
        "id": "fixture-reconciliation",
        "instance": subject.process_identity,
        "epoch": subject.broker.epoch,
        "started_at": store.now(),
        "completed_at": store.now(),
        "started_sequence": subject.incidents.watermark(),
        "ready": True,
    }
    healthy_watchdog(subject)


def test_resolution_requires_recovery_evidence_and_fault_free_interval(ready, monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    ready.incident("broker_321", "Rejected request")
    with pytest.raises(Conflict):
        ready.review_incident("broker_321")
    ready.recheck_incident("broker_321")
    prove_reconciliation(ready)
    assert ready.review_incident("broker_321")["restriction"] == "released"
    ready.incident("engine_fault", "Operation failed", diagnostic={"operation": "command:resolve"})
    prove_reconciliation(ready)
    with pytest.raises(Conflict):
        ready.review_incident("engine_fault")
    ready._operation_succeeded("command:unrelated")
    assert not ready.incident_detail("engine_fault")["recovery"]["can_release"]
    ready._operation_succeeded("command:resolve")
    with pytest.raises(Conflict):
        ready.review_incident("engine_fault")
    clock[0] += 31
    prove_reconciliation(ready)
    assert ready.review_incident("engine_fault")["restriction"] == "released"


def test_removal_waits_for_cancel_confirmation_children_and_released_capacity(ready):
    preview = ready.paper_test_preview(1)
    trial = ready.start_paper_test(preview["id"])
    order = ready.store.orders()[0]
    ready._order_observation({"broker_id": 100, "status": "Submitted"})
    ready.reconciled = True
    run = ready.remove_run(trial["run_id"])
    assert run["removal_pending"] and not run.get("archived")
    assert ready.broker.cancelled == [100]
    ready._order_observation({"broker_id": 100, "status": "Cancelled"})
    ready._finish_removals()
    assert not ready.store.get("run", trial["run_id"]).get("archived")
    reservation = ready.store.get("reservation", order["id"])
    ready.store.put("reservation", order["id"], {**reservation, "active": False})
    ready.broker_orders[100] = {"status": "Cancelled"}
    ready._finish_removals()
    assert not ready.store.get("run", trial["run_id"]).get("archived")
    ready.broker_orders[102] = {"status": "Cancelled"}
    for broker_id in (100, 102):
        ready.store.put("broker_order", str(broker_id), {"status": "Cancelled"})
        cancellation = ready.store.get("cancel_request", str(broker_id))
        if cancellation:
            ready.store.put(
                "cancel_request", str(broker_id), {**cancellation, "state": "confirmed"}
            )
    prove_reconciliation(ready)
    ready._finish_removals()
    with ready.store.connect() as db:
        reasons = ready._archive_item(db, trial["run_id"])["reasons"]
    assert ready.store.get("run", trial["run_id"]).get("archived"), reasons


def test_extended_cutoff_uses_broker_session_end_not_twenty_hour_envelope(ready):
    run = prepared(ready, "extended")
    Clock.stamp = datetime(2026, 9, 17, 19, 50, tzinfo=UTC)
    ready.contracts[1]["trading_hours"] = "20260917:0400-20260917:1600"
    run.update(
        armed=True,
        valid_from="2026-09-17T08:00:00+00:00",
        expires_at="2026-09-17T20:00:00+00:00",
        session_date="2026-09-17",
        trading_hours="extended",
    )
    ready.store.put("run", "run", run)
    ready.data[1]["warm"] = True
    with pytest.raises(Conflict, match="not open"):
        ready._enter(
            run,
            {"stop": Decimal(99), "target": None},
            {"minutes_to_close": 250},
            ready.store.capture({"test": True}),
        )
    assert not ready.broker.submitted


def test_late_execution_reactivates_removed_run_for_recovery(ready):
    prepared(ready)
    order = ready.store.reserve_order(
        "late",
        {
            "purpose": "entry",
            "conid": 1,
            "symbol": "AAPL",
            "quantity": 1,
            "limit": "100",
            "stop": "99",
        },
        "run",
        100,
    )
    ready.store.transition(order["id"], "cancelled", {})
    run = ready.store.get("run", "run")
    ready.store.put("run", "run", {**run, "archived": True})
    ready._execution(
        {
            "type": "execution",
            "client_id": 71,
            "broker_id": 100,
            "execution_id": "late.01",
            "conid": 1,
            "symbol": "AAPL",
            "side": "BOT",
            "quantity": "1",
            "price": "100",
        }
    )
    # Identity disagreement prevents attempted repair, but must not hide ownership.
    ready.broker_orders[100] = {"status": "Filled"}
    ready.positions[1] = {"quantity": "1"}
    ready._finish_reconcile()
    run = ready.store.get("run", "run")
    assert not run["archived"] and not run["armed"]
    assert run["state"] == "recovery_required" and run["position"] == "1"
    assert ready.store.get("incident", "late_archived_fill")


def test_health_publication_preserves_last_value_during_windows_sharing_lock(tmp_path, monkeypatch):
    from trading_oms_backend.workspace import health_file

    assert publish_health(tmp_path, {"timestamp": 1})
    replace = health_file.os.replace

    def locked(*args):
        raise PermissionError("synthetic Windows sharing lock")

    monkeypatch.setattr(health_file.os, "replace", locked)
    assert not publish_health(tmp_path, {"timestamp": 2})
    assert json.loads((tmp_path / "engine-health.json").read_text())["timestamp"] == 1
    monkeypatch.setattr(health_file.os, "replace", replace)
    assert publish_health(tmp_path, {"timestamp": 3})
    assert json.loads((tmp_path / "engine-health.json").read_text())["timestamp"] == 3
