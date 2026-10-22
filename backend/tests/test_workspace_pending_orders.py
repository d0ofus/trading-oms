"""Realistic asynchronous paper callbacks; every transport is an isolated double."""

import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_workspace_unified import CryptoBroker, confirm, crypto_engine, crypto_entry

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Conflict, Store


def status(engine, order, value, **fields):
    engine.observe(
        {
            "type": "order_status",
            "broker_id": order["broker_id"],
            "client_id": engine.broker.client_id,
            "status": value,
            "filled": "0",
            "remaining": "0",
            "average": "0",
            "parent_id": 0,
            **fields,
        }
    )


def state(engine, order):
    return next(o["state"] for o in engine.store.orders() if o["id"] == order["id"])


def events(engine, kind):
    with engine.store.connect() as db:
        return [
            json.loads(r[0]) for r in db.execute("SELECT payload FROM events WHERE type=?", (kind,))
        ]


def test_api_pending_does_not_reproduce_false_incident_and_cancellation(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    engine._flush_incident_cancellations()
    assert state(engine, order) == "dispatching"
    assert engine.store.get("run", run["id"])["armed"]
    assert not engine.incidents.open()
    assert not engine.broker.cancelled
    assert engine.store.get("reservation", order["id"])["active"]
    assert not engine.owned()
    with pytest.raises(Conflict):
        engine.store.mark_dispatch(order["id"])
    detail = engine.order_detail(order["id"])["order"]["diagnostics"]
    assert detail["acknowledgment_pending"]
    assert detail["broker_status"] == "ApiPending"
    assert detail["identity_status"] == "pending"
    assert detail["status_label"] == "Awaiting broker acknowledgment"
    engine._finish_reconcile()
    assert not engine.reconciled
    assert "Awaiting complete broker order details" in engine.last_fault
    assert "differs" not in engine.last_fault


@pytest.mark.parametrize(
    "value", ["PreSubmitted", "Submitted", "Filled", "Cancelled", "ApiCancelled"]
)
def test_pending_progresses_with_details_and_authoritative_fills(tmp_path, value):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    fill = "0.25" if value == "Filled" else "0"
    confirm(engine, order, fill, status=value)
    assert not engine.incidents.open()
    assert engine.reconciled
    assert (
        state(engine, order)
        == {
            "PreSubmitted": "working",
            "Submitted": "working",
            "Filled": "filled",
            "Cancelled": "cancelled",
            "ApiCancelled": "cancelled",
        }[value]
    )
    assert len(engine.broker.submitted) == 1
    if fill != "0":
        assert engine.owned()[run["id"]]["quantity"] == Decimal(fill)
        assert engine.store.get("crypto_protection", run["id"])["stop"] == "99.00"
    elif value in {"Cancelled", "ApiCancelled"}:
        assert not engine.store.get("run", run["id"])["armed"]
        assert not engine.store.get("reservation", order["id"])["active"]
        assert "permissions" not in engine.store.get("run", run["id"])["blocking_reason"]


@pytest.mark.parametrize("value", ["Inactive", "Rejected", "NotAnIBKRStatus"])
def test_real_unknowns_and_rejections_still_restrict(tmp_path, value):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    status(engine, order, value)
    assert engine.incidents.applicable([run])
    assert not engine.store.get("run", run["id"])["armed"]
    assert engine.store.get("reservation", order["id"])["active"]


@pytest.mark.parametrize(
    "earlier", ["Submitted", "PendingCancel", "Cancelled", "ApiCancelled", "Filled"]
)
@pytest.mark.parametrize("late", ["ApiPending", "PendingSubmit"])
def test_late_pending_never_regresses_projection_or_current_snapshot(tmp_path, earlier, late):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, earlier, filled="0.25" if earlier == "Filled" else "0")
    expected = state(engine, order)
    before = len(events(engine, "order.observed"))
    status(engine, order, late)
    status(engine, order, late)
    assert state(engine, order) == expected
    assert engine.store.get("broker_order", str(order["broker_id"]))["status"] == earlier
    assert engine.broker_orders[order["broker_id"]]["status"] == earlier
    assert len(events(engine, "order.observed")) == before
    assert any(e.get("status") == late for e in events(engine, "broker.order.observed"))
    assert not engine.incidents.open()


def test_cancel_intent_survives_delayed_working_and_requires_terminal_evidence(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    engine.cancel_entry(order["id"])
    confirm(engine, order, "0", status="Submitted")
    assert state(engine, order) == "cancel_pending"
    assert engine.store.get("reservation", order["id"])["active"]
    assert not engine.reconciled
    engine.cancel_entry(order["id"])
    assert engine.broker.cancelled == [order["broker_id"]]
    confirm(engine, order, "0", status="ApiCancelled")
    assert engine.reconciled
    assert not engine.store.get("reservation", order["id"])["active"]
    assert (
        engine.order_detail(order["id"])["order"]["diagnostics"]["cancellation_reason"]
        == "operator"
    )
    assert "operator" in engine.store.get("run", run["id"])["blocking_reason"].lower()


@pytest.mark.parametrize(
    "field,value",
    [
        ("conid", 999),
        ("own_account", False),
        ("action", "SELL"),
        ("cash_quantity", "50"),
        ("reference", "external"),
    ],
)
def test_supplied_wrong_identity_is_mismatch_even_when_other_fields_missing(tmp_path, field, value):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending", **{field: value})
    assert "differs" in " ".join(engine._identity_issues())
    assert engine.order_detail(order["id"])["order"]["diagnostics"]["identity_status"] == "mismatch"
    assert engine.store.get("reservation", order["id"])["active"]


def test_execution_before_details_and_late_fill_after_cancellation_are_retained(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    engine.cancel_entry(order["id"])
    status(engine, order, "ApiCancelled")
    execution = {
        "type": "execution",
        "broker_id": order["broker_id"],
        "client_id": engine.broker.client_id,
        "own_account": True,
        "execution_id": "pending-fill",
        "conid": 456,
        "symbol": "BTC",
        "side": "BOT",
        "quantity": "0.1",
        "price": "100.123",
    }
    engine.observe(execution)
    engine.observe(execution)
    assert engine.owned()[run["id"]]["quantity"] == Decimal("0.1")
    assert not engine.reconciled
    confirm(engine, order, "0", status="ApiCancelled")
    status(engine, order, "ApiCancelled", filled="0.1")
    engine._finish_reconcile()
    assert engine.reconciled
    assert engine.store.get("crypto_protection", run["id"])["stop"] == "99.13"
    assert engine.store.get("reservation", order["id"])["active"]
    assert len(events(engine, "execution.received")) == 1
    engine._crypto_trade({"conid": 456, "timestamp": time.time(), "price": "99", "sequence": 9})
    assert len(engine.broker.submitted) == 2
    assert engine.broker.submitted[-1]["purpose"] == "exit"


def test_pending_deadline_cancels_once_without_releasing_or_resubmitting(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    # Isolate the entry deadline from unrelated scheduling/heartbeat maintenance.
    for name in ("next_reconcile", "next_heartbeat", "_next_health_write", "_next_runtime_clock"):
        setattr(engine, name, float("inf"))
    with engine.store.transaction() as db:
        db.execute(
            "UPDATE outbox SET created_at=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(seconds=31)).isoformat(), order["id"]),
        )
    engine.maintain()
    engine.maintain()
    assert state(engine, order) == "cancel_pending"
    assert engine.broker.cancelled == [order["broker_id"]]
    assert len(engine.broker.submitted) == 1
    assert engine.store.get("reservation", order["id"])["active"]
    assert (
        engine.order_detail(order["id"])["order"]["diagnostics"]["cancellation_reason"]
        == "entry_timeout"
    )


def test_restart_preserves_uncertainty_and_pending_reservation(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    restarted = Engine(Store(tmp_path), CryptoBroker)
    assert not restarted.store.get("run", run["id"])["armed"]
    assert state(restarted, order) == "unknown"
    assert restarted.store.get("reservation", order["id"])["active"]
    assert not restarted.broker.submitted
    status(restarted, order, "ApiPending")
    assert not restarted.store.get("run", run["id"])["armed"]
    assert not restarted.reconciled
    assert not restarted.broker.submitted


def test_terminal_then_working_is_a_conflict_until_fresh_completed_snapshot(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiCancelled")
    status(engine, order, "Submitted")
    engine._finish_reconcile()
    assert not engine.reconciled
    assert engine.incidents.applicable([run])
    assert engine.store.get("reservation", order["id"])["active"]
    assert state(engine, order) == "cancelled"
    confirm(engine, order, "0", status="ApiCancelled")
    assert not engine.reconciled  # An ordinary delayed callback cannot clear the conflict.
    completed = {
        **engine.store.get("broker_order", str(order["broker_id"])),
        "type": "open_order",
        "completed": True,
    }
    completed.pop("status_conflict", None)
    engine.observe(completed)
    engine._finish_reconcile()
    assert engine.reconciled
    assert engine.incidents.applicable([run])  # Explicit recovery is still required.
    assert not engine.store.get("run", run["id"])["armed"]


def test_known_identity_is_not_erased_and_changed_permanent_identity_stays_blocked(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "Submitted", permanent_id=1234)
    status(engine, order, "ApiPending", permanent_id=0)
    assert engine.store.get("broker_order", str(order["broker_id"]))["permanent_id"] == 1234
    status(engine, order, "Submitted", permanent_id=5678)
    assert engine.store.get("broker_order", str(order["broker_id"]))["permanent_id"] == 1234
    assert engine.store.get("broker_order", str(order["broker_id"]))["status_conflict"]
    assert engine.incidents.applicable([run])
    assert not engine.reconciled


def test_reconnect_restores_pending_without_resend_and_retries_known_cancel_only(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    engine._connection_lost("Synthetic interruption during acknowledgment")
    engine._flush_incident_cancellations()
    assert not engine.store.get("run", run["id"])["armed"]
    assert engine.store.get("reservation", order["id"])["active"]
    engine.broker.epoch += 1
    engine.connected = engine.attested = True
    confirm(engine, order, "0", status="Submitted")
    assert len(engine.broker.submitted) == 1
    assert engine.broker.cancelled == [order["broker_id"]]
    assert not engine.reconciled
    confirm(engine, order, "0", status="ApiCancelled")
    assert engine.reconciled
    assert not engine.store.get("run", run["id"])["armed"]


def test_pending_to_partial_ioc_fill_keeps_protection_without_topping_up(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "ApiPending")
    confirm(engine, order, "0.1", price="100.123", status="Cancelled")
    assert engine.reconciled
    assert engine.store.get("reservation", order["id"])["active"]
    assert engine.store.get("crypto_protection", run["id"])["stop"] == "99.13"
    assert len(engine.broker.submitted) == 1
    engine._crypto_trade({"conid": 456, "timestamp": time.time(), "price": "101", "sequence": 7})
    assert len(engine.broker.submitted) == 1


def test_full_order_details_survive_later_partial_callback(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    confirm(engine, order, "0", status="Submitted")
    status(engine, order, "ApiPending")
    observed = engine.store.get("broker_order", str(order["broker_id"]))
    assert engine._crypto_identity_status(order, observed) == "verified"
    assert observed["cash_quantity"] == "25.00"
    assert observed["quantity"] == "0"
    assert not engine.owned()
    assert engine.store.get("reservation", order["id"])["active"]


def test_dispatch_exception_does_not_become_a_known_pending_order(tmp_path):
    engine, run = crypto_engine(tmp_path)

    def uncertain(_intent):
        raise TimeoutError("Synthetic SDK timeout")

    engine.broker.submit_crypto = uncertain
    order = crypto_entry(engine, run)
    assert state(engine, order) == "unknown"
    assert engine.incidents.applicable([run])
    assert engine.store.get("reservation", order["id"])["active"]
    assert not engine.order_diagnostics(order)["acknowledgment_pending"]


def test_changed_crypto_identity_immediately_invalidates_prior_reconciliation(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    confirm(engine, order, "0", status="Submitted")
    assert engine.reconciled
    status(engine, order, "Submitted", cash_quantity="50")
    assert not engine.reconciled
    assert engine.incidents.applicable([run])
    assert not engine.store.get("run", run["id"])["armed"]


def test_conflicting_order_status_is_visible_to_direct_ownership_checks(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    confirm(engine, order, "0.25")
    status(engine, order, "Submitted")
    assert "Conflicting broker order status" in " ".join(engine._identity_issues())
    with pytest.raises(Conflict, match="identity"):
        engine._crypto_close(run["id"])


@pytest.mark.parametrize("terminal", ["Filled", "Cancelled", "ApiCancelled", "Rejected"])
def test_delayed_pending_cancel_cannot_reopen_a_terminal_order(tmp_path, terminal):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, terminal)
    incidents = len(engine.incidents.open())
    expected = state(engine, order)
    status(engine, order, "PendingCancel")
    assert state(engine, order) == expected
    assert not engine.store.get("broker_order", str(order["broker_id"])).get("status_conflict")
    assert len(engine.incidents.open()) == incidents


def test_reconnect_working_snapshot_retries_previously_pending_cancellation(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    confirm(engine, order, "0", status="Submitted")
    engine.cancel_entry(order["id"])
    status(engine, order, "PendingCancel")
    assert engine.broker.cancelled == [order["broker_id"]]
    engine.broker.epoch += 1
    confirm(engine, order, "0", status="Submitted")
    assert state(engine, order) == "cancel_pending"
    assert engine.broker.cancelled == [order["broker_id"], order["broker_id"]]
    confirm(engine, order, "0", status="Submitted")
    assert len(engine.broker.cancelled) == 2
    assert len(engine.broker.submitted) == 1
    assert engine.store.get("reservation", order["id"])["active"]
