"""Captured FX callback regressions; isolated broker, never a real account."""

from decimal import Decimal

import pytest
from test_workspace_fx_execution import arm, enter, fixture, reconcile_proof

from trading_oms_backend.workspace.fx_order_evidence import quantity_evidence
from trading_oms_backend.workspace.store import now


def observation(engine, order, **changes):
    payload = order["payload"]
    purpose = payload["purpose"]
    return {
        "type": "open_order",
        "broker_id": order["broker_id"],
        "permanent_id": order["broker_id"] + 10000,
        "client_id": engine.broker.client_id,
        "own_account": True,
        "conid": payload["conid"],
        "reference": "oms-" + order["id"],
        "quantity": payload["quantity"],
        "filled": "0",
        "remaining": payload["quantity"],
        "sec_type": "CASH",
        "currency": "USD",
        "routing_exchange": "IDEALPRO",
        "outside_rth": False,
        "action": "BUY" if purpose == "entry" else "SELL",
        "order_type": "MKT" if purpose == "entry" else "STP",
        "tif": "IOC" if purpose == "entry" else "GTC",
        "stop": payload.get("stop"),
        "trigger_method": 4,
        "status": "Submitted" if purpose == "entry" else "PreSubmitted",
        **changes,
    }


def captured(tmp_path, monkeypatch):
    engine, original = fixture(tmp_path, monkeypatch, "broker_held")
    compatibility = engine.fx_compatibility(
        original["strategy_id"], 1, original["conid"], "broker_held"
    )
    run = engine.create_run(
        original["strategy_id"],
        1,
        original["conid"],
        {"quantity": "1000"},
        "broker_held",
        compatibility["plan"]["hash"],
        "fx",
    )
    entry = enter(engine, arm(engine, run))
    engine.observe(observation(engine, entry))
    engine.observe(observation(engine, entry, status="Filled", filled="1000", remaining="0"))
    engine.observe(
        {
            "type": "execution",
            "execution_id": "captured.1",
            "broker_id": entry["broker_id"],
            "client_id": engine.broker.client_id,
            "own_account": True,
            "conid": run["conid"],
            "symbol": "AUD",
            "quantity": "1000",
            "price": "0.70140",
            "side": "BOT",
        }
    )
    stop = next(o for o in engine.store.orders() if o["payload"]["purpose"] == "protection")
    engine.observe(observation(engine, stop))
    engine.observe(
        {"type": "commission", "execution_id": "captured.1", "currency": "USD", "amount": "2"}
    )
    for currency, value in (("USD", "99296.60"), ("AUD", "2000")):
        engine.currency_facts[("CashBalance", currency)] = {"value": value, "received_at": now()}
    return engine, run, entry, stop


def test_accepted_fx_stop_ignored_outside_hours_and_completed_zero_total(tmp_path, monkeypatch):
    engine, run, entry, stop = captured(tmp_path, monkeypatch)
    engine.observe(
        observation(
            engine,
            entry,
            completed=True,
            status="Filled",
            quantity="0",
            filled="1000",
            remaining="0",
        )
    )
    reconcile_proof(engine)
    assert engine.reconciled, engine._identity_issues()
    assert engine.store.get("run", run["id"])["protected"]
    view = next(v for v in engine._fx_protection_view() if v["run_id"] == run["id"])
    assert view["status"] == "active"
    assert view["verification"]["broker_status"] == "PreSubmitted"
    assert Decimal(view["stop"]) == Decimal("0.69440")
    assert engine.store.get("fx_protection", run["id"])["state"] != "awaiting_fill"
    assert len(engine.broker.submitted) == 2
    assert not engine.store.get("cancel_request", str(stop["broker_id"]))
    details = engine.order_diagnostics(entry)["quantity_evidence"]
    assert details["reported"] == "0"
    assert details["effective"] == "1000"


@pytest.mark.parametrize(
    "change",
    [
        {"own_account": False},
        {"conid": -1},
        {"trigger_method": 2},
        {"quantity": "999"},
        {"stop": "0.60000"},
        {"tif": "DAY"},
        {"remaining": "999"},
        {"status": "PendingCancel"},
        {"status": "Inactive"},
    ],
)
def test_real_protection_mismatch_still_blocks(tmp_path, monkeypatch, change):
    engine, run, entry, stop = captured(tmp_path, monkeypatch)
    engine.observe(observation(engine, stop, **change))
    assert not engine._fx_valid_protection(engine.owned()[run["id"]], entry)


def test_zero_total_cannot_infer_fill_from_intent(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch, "broker_held")
    entry = enter(engine, arm(engine, run))
    engine.observe(observation(engine, entry))
    event = observation(
        engine, entry, completed=True, status="Filled", quantity="0", filled="25000", remaining="0"
    )
    engine.observe(event)
    assert engine._fx_identity(entry, engine.broker_orders[entry["broker_id"]])


def test_unknown_399_waits_for_confirmation_without_cancelling(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch, "broker_held")
    entry = enter(engine, arm(engine, run))
    engine.observe({"type": "broker_error", "request": entry["broker_id"], "code": 399})
    assert not engine.store.get("cancel_request", str(entry["broker_id"]))
    assert engine.store.get("run", run["id"])["armed"]
    assert engine.order_diagnostics(entry)["warning"]["state"] == "awaiting_confirmation"
    engine.observe(observation(engine, entry))
    assert engine.order_diagnostics(entry)["warning"]["state"] == "confirmed"


def test_scoped_warning_does_not_erase_rejection(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch, "broker_held")
    entry = enter(engine, arm(engine, run))
    engine.observe({"type": "broker_error", "request": entry["broker_id"], "code": 399})
    engine.observe(observation(engine, entry, status="Rejected"))
    assert engine.store.orders()[0]["state"] == "rejected"
    assert engine.order_diagnostics(entry)["warning"]["state"] == "rejected"


@pytest.mark.parametrize(
    "change",
    [
        {"permanent_id": -1},
        {"own_account": False},
        {"filled": "999"},
        {"remaining": "1"},
        {"status": "Cancelled"},
        {"completed": False},
        {"status_conflict": True},
        {"conid": -1},
    ],
)
def test_completed_zero_total_rejects_insufficient_or_conflicting_evidence(
    tmp_path, monkeypatch, change
):
    engine, _, entry, _ = captured(tmp_path, monkeypatch)
    completed = observation(
        engine,
        entry,
        completed=True,
        status="Filled",
        quantity="0",
        filled="1000",
        remaining="0",
        **{},
    )
    assert quantity_evidence(engine.store, entry, {**completed, **change})["effective"] is None


def test_legacy_journal_reconstruction_and_duplicate_callbacks_are_idempotent(
    tmp_path, monkeypatch
):
    engine, run, entry, stop = captured(tmp_path, monkeypatch)
    with engine.store.transaction() as db:
        db.execute("DELETE FROM documents WHERE kind='fx_accepted_order'")
    event = observation(
        engine, entry, completed=True, status="Filled", quantity="0", filled="1000", remaining="0"
    )
    engine.observe(event)
    engine.observe(event)
    reconcile_proof(engine)
    assert engine.reconciled
    with engine.store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM events WHERE type='fx.order.quantity_verified'"
            ).fetchone()[0]
            == 1
        )
    assert len(engine.broker.submitted) == 2
    assert not engine.store.get("cancel_request", str(stop["broker_id"]))


def test_reconciliation_snapshot_and_late_execution_use_same_quantity_evidence(
    tmp_path, monkeypatch
):
    engine, run, entry, stop = captured(tmp_path, monkeypatch)
    event = observation(
        engine, entry, completed=True, status="Filled", quantity="0", filled="1000", remaining="0"
    )
    engine.reconcile_inflight = True
    engine._pending_snapshot = {"broker_orders": {}}
    engine.observe(event)
    staged = engine._pending_snapshot["broker_orders"][entry["broker_id"]]
    assert not engine._fx_identity(entry, staged)
    assert staged["quantity"] == "0"
    assert engine.order_diagnostics(entry)["quantity_evidence"]["effective"] == "1000"


def test_disconnection_and_pending_cancel_do_not_show_active_stop(tmp_path, monkeypatch):
    engine, run, entry, stop = captured(tmp_path, monkeypatch)
    assert engine._fx_protection_assessment(run)["state"] == "active"
    engine.connected = False
    assert engine._fx_protection_assessment(run)["state"] == "checking"
    engine.connected = True
    engine._queue_cancel(stop["broker_id"], "protection", "fx_protection_resize")
    assert engine._fx_protection_assessment(run)["state"] == "mismatch"


def test_399_stop_confirmation_preserves_stop_and_reports_pending(tmp_path, monkeypatch):
    engine, run, entry, stop = captured(tmp_path, monkeypatch)
    engine.observe({"type": "broker_error", "request": stop["broker_id"], "code": 399})
    assert engine._fx_protection_assessment(run)["state"] == "checking"
    assert not engine.store.get("cancel_request", str(stop["broker_id"]))
    engine.observe(observation(engine, stop))
    assert engine._fx_protection_assessment(run)["state"] == "active"
    assert len(engine.broker.submitted) == 2


def test_quantity_correction_rolls_back_if_audit_append_fails(tmp_path, monkeypatch):
    engine, _, entry, _ = captured(tmp_path, monkeypatch)
    append = engine.store.append

    def fail(db, kind, payload):
        if kind == "fx.order.quantity_verified":
            raise RuntimeError("simulated audit interruption")
        return append(db, kind, payload)

    monkeypatch.setattr(engine.store, "append", fail)
    with pytest.raises(RuntimeError, match="audit interruption"):
        engine.observe(
            observation(
                engine,
                entry,
                completed=True,
                status="Filled",
                quantity="0",
                filled="1000",
                remaining="0",
            )
        )
    assert engine.store.get("fx_quantity_correction", entry["id"]) is None


def test_warning_rolls_back_if_audit_append_fails(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch, "broker_held")
    entry = enter(engine, arm(engine, run))
    append = engine.store.append

    def fail(db, kind, payload):
        if kind == "fx.order.warning":
            raise RuntimeError("simulated audit interruption")
        return append(db, kind, payload)

    monkeypatch.setattr(engine.store, "append", fail)
    with pytest.raises(RuntimeError, match="audit interruption"):
        engine.observe({"type": "broker_error", "request": entry["broker_id"], "code": 399})
    assert engine.store.get("fx_order_warning", entry["id"]) is None


def test_protection_explains_actual_mismatch(tmp_path, monkeypatch):
    engine, run, _, stop = captured(tmp_path, monkeypatch)
    for updates, reason in (
        ({"trigger_method": 2}, "bid/ask trigger method"),
        ({"stop": "0.5"}, "stop price"),
        ({"quantity": "999"}, "quantity evidence"),
    ):
        engine.observe(observation(engine, stop, **updates))
        assert reason in engine._fx_protection_assessment(run)["reasons"][0]


def test_fast_market_fill_acceptance_can_reconstruct_positive_quantity(tmp_path, monkeypatch):
    engine, _, entry, _ = captured(tmp_path, monkeypatch)
    # Reproduce a fast order whose first non-completed detail was already Filled.
    from trading_oms_backend.workspace.fx_order_evidence import accepted_observation

    accepted = observation(engine, entry, status="Filled", filled="1000", remaining="0")
    assert accepted_observation(accepted)
    engine.store.put("fx_accepted_order", entry["id"], accepted)
    completed = observation(
        engine, entry, completed=True, status="Filled", quantity="0", filled="1000", remaining="0"
    )
    assert quantity_evidence(engine.store, entry, completed)["effective"] == "1000"
