import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_workspace_engine import BrokerDouble

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Conflict, Store, now


def test_emergency_between_reservation_and_dispatch_prevents_submission(tmp_path):
    store = Store(tmp_path)
    store.put(
        "run",
        "run",
        {"armed": True, "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    )
    store.reserve_order(
        "intent",
        {"purpose": "entry", "quantity": 1},
        "run",
        100,
        {"symbol": "FIXTURE", "risk": "1", "notional": "100"},
    )
    store.set_emergency(True)
    with pytest.raises(Conflict):
        store.mark_dispatch("intent")
    assert store.orders()[0]["state"] == "reserved"


def test_changed_login_disarms_without_sending_cancels_into_new_account(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store, BrokerDouble)
    store.put("run", "run", {"id": "run", "armed": True})
    engine._resume_attestation = True
    engine.broker.can_resume_attestation = False
    engine.observe({"type": "account_context", "paper": True, "count": 1})
    assert not store.get("run", "run")["armed"]
    assert not engine.broker.cancelled
    assert not engine.attested


def test_disconnect_followed_by_closed_callback_preserves_recovery_context(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.attested = True
    engine._connection_lost("upstream interrupted")
    engine._connection_lost("socket closed")
    assert engine._resume_attestation


def test_offline_cancellation_is_durable_and_sent_only_after_paper_attestation(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store, BrokerDouble)
    store.reserve_order("entry", {"purpose": "entry", "quantity": 1}, "run", 100)
    store.transition("entry", "working", {})
    engine.cancel_entry("entry")
    assert not engine.broker.cancelled
    assert store.get("cancel_request", "100")["state"] == "queued"
    engine.connected = engine.attested = True
    engine._flush_cancellations()
    engine._flush_cancellations()
    assert engine.broker.cancelled == [100]


def test_missing_working_order_is_unknown_and_cannot_release_capacity(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store, BrokerDouble)
    store.reserve_order("entry", {"purpose": "entry", "quantity": 1}, "run", 100)
    store.transition("entry", "working", {})
    assert engine._identity_issues()
    assert store.orders()[0]["state"] == "unknown"


def test_tick_after_data_gap_never_evaluates_a_retrospective_entry(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.data[1] = {
        "warm": True,
        "live": True,
        "history_loaded": True,
        "received_at": (datetime.now(UTC) - timedelta(seconds=30)).isoformat(),
    }
    engine._tick(
        {
            "type": "tick",
            "conid": 1,
            "timestamp": int(datetime.now(UTC).timestamp()),
            "price": "100",
            "size": "1",
            "sequence": 1,
        }
    )
    assert not engine.data[1]["warm"]
    assert any(e["type"] == "market.gap" for e in engine.store.events())
    assert not engine.broker.submitted


def test_serialized_exit_blocks_a_competing_or_uncertain_exit(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store, BrokerDouble)
    engine.owned = lambda: {
        "run": {"quantity": Decimal(2), "conid": 1, "entry_id": "entry", "symbol": "FIXTURE"}
    }
    engine.reconciled = engine.attested = True
    engine.reconciled_at = time.monotonic()
    engine.quotes[1] = {"bid": {"price": "100", "received_at": now()}}
    store.reserve_order("exit", {"purpose": "exit", "quantity": 2}, "run", 103)
    store.transition("exit", "unknown", {})
    assert engine.close_position("run")["state"] == "exit_pending"
    assert len(store.orders()) == 1


def test_reconciliation_snapshots_cannot_overlap_and_mix_completion_callbacks(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    calls = []
    engine.broker.reconcile = lambda: calls.append("snapshot")
    engine.connected = True
    engine.begin_reconcile()
    engine.observe({"type": "positions_end"})
    engine.begin_reconcile()
    assert calls == ["snapshot"]
    assert engine.reconcile_parts == {"positions_end"}
    engine._connection_lost("interrupted")
    engine.observe({"type": "orders_end"})
    assert "orders_end" not in engine.reconcile_parts


def test_foreign_account_execution_never_changes_owned_position(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store, BrokerDouble)
    engine._execution({"client_id": 71, "own_account": False})
    assert not engine.owned()
    assert store.get("incident", "foreign_execution")
