"""Rejection evidence and recovery are exercised only with an isolated broker double."""

import json
import queue

import pytest
from test_workspace_pending_orders import events, state, status
from test_workspace_unified import CryptoBroker, confirm, crypto_engine, crypto_entry

from trading_oms_backend.workspace.broker import GatewayData
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.incidents import IncidentBook
from trading_oms_backend.workspace.store import Conflict, Store


def reject(engine, order, category="unknown"):
    engine.observe(
        {
            "type": "broker_error",
            "code": 201,
            "request": order["broker_id"],
            "context": "broker",
            "rejection": {"category": category},
        }
    )


def details(engine, order, value="Inactive", **extra):
    engine.observe(
        {
            "type": "open_order",
            "broker_id": order["broker_id"],
            "client_id": engine.broker.client_id,
            "own_account": True,
            "reference": "oms-" + order["id"],
            "conid": 456,
            "symbol": "BTC",
            "order_type": "MKT",
            "tif": "IOC",
            "parent_id": 0,
            "status": value,
            "action": "BUY",
            "quantity": "0.25",
            "cash_quantity": "25.0",
            "filled": "0",
            **extra,
        }
    )


def test_recorded_rejection_is_one_incident_and_retains_cause_after_cancel(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    details(engine, order)
    first = engine.incidents.open()[0]
    status(engine, order, "Inactive", remaining="0.25")
    reject(engine, order, "permissions")
    details(engine, order)
    status(engine, order, "Inactive", remaining="0.25")
    incidents = engine.incidents.open()
    assert len(incidents) == 1
    item = incidents[0]
    assert item["id"] == first["id"]
    assert item["occurrences"] == 1
    assert item["scope"] == {"type": "run", "key": run["id"]}
    assert item["order_context"]["order_id"] == order["id"]
    assert item["rejection"]["category"] == "permissions"
    assert not engine.store.get("run", run["id"])["armed"]
    assert engine.store.get("reservation", order["id"])["active"]
    details(engine, order, "Cancelled", completed=True)
    engine._finish_reconcile()
    assert engine.reconciled
    detail = engine.order_detail(order["id"])["order"]["diagnostics"]
    assert detail["broker_status"] == "Cancelled"
    assert detail["rejection"]["code"] == 201
    assert detail["rejection"]["category"] == "permissions"
    assert (
        detail["status_label"] == "Broker rejected entry — no fill; final broker status: Cancelled"
    )
    assert "permissions" in engine._crypto_no_fill_reason(engine.store.orders()[0]).lower()
    assert "permissions" in engine.store.get("run", run["id"])["blocking_reason"].lower()
    assert "no fill" in engine.store.get("run", run["id"])["blocking_reason"]
    assert len(engine.broker.submitted) == 1
    assert not events(engine, "order.cancel.requested")


def test_repeated_rejection_does_not_restart_recovery_or_reopen_released_episode(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    reject(engine, order)
    details(engine, order, "Cancelled", completed=True)
    engine._finish_reconcile()
    before = engine.incidents.open()[0]
    with engine.store.transaction() as db:
        ready = engine.incidents.recover_in(db, before, {"fixture": True})
    for _ in range(3):
        reject(engine, order)
        details(engine, order, "Inactive")
        details(engine, order, "Cancelled", completed=True)
    current = engine.incidents.get(ready["id"])
    assert current["revision"] == ready["revision"]
    assert current["failure_sequence"] == ready["failure_sequence"]
    assert engine.reconciled
    with engine.store.transaction() as db:
        engine.incidents.release_in(db, current["id"], current["revision"], "fixture-operator", "")
    restarted = Engine(Store(tmp_path), CryptoBroker)
    reject(restarted, order)
    details(restarted, order, "Inactive")
    assert not restarted.incidents.open()
    assert not restarted.broker.submitted
    assert state(restarted, order) == "cancelled"


def test_new_conflicting_working_evidence_invalidates_recovery(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    reject(engine, order)
    details(engine, order, "Cancelled", completed=True)
    engine._finish_reconcile()
    status(engine, order, "Submitted")
    assert not engine.reconciled
    assert any(i["code"] == "order_status_conflict" for i in engine.incidents.open())
    assert not engine.store.get("run", run["id"])["armed"]


@pytest.mark.parametrize(
    ("message", "category"),
    [
        ("No trading permission", "permissions"),
        ("Insufficient funds", "insufficient_funds"),
        ("Order size is below the minimum order size", "minimum_size"),
        ("Invalid time in force", "unsupported_parameters"),
        ("Cryptocurrency is not supported in paper trading", "unavailable_capability"),
        ("Cryptocurrency order is not confirmed", "acknowledgment_required"),
        ("Unrecognized private explanation", "unknown"),
        ("", "unknown"),
    ],
)
def test_adapter_emits_only_generated_rejection_diagnostics(message, category):
    broker = GatewayData(queue.Queue())
    broker.data_error(6, 201, message + " private-fixture-value")
    event = broker.observations.get_nowait()
    assert event["rejection"]["category"] == category
    assert event["rejection"]["available"] == (category != "unknown")
    assert "private-fixture-value" not in json.dumps(event)


@pytest.mark.parametrize("advanced", ["{bad-json", "x" * 20000, "[]", "null", 42])
def test_malformed_advanced_rejection_is_safe_and_unknown(advanced):
    broker = GatewayData(queue.Queue())
    broker.data_error(6, 201, "", advanced)
    event = broker.observations.get_nowait()
    assert event["rejection"]["category"] == "unknown"
    assert not event["rejection"]["available"]
    assert len(json.dumps(event)) < 1500


def test_advanced_rejection_is_classified_without_retaining_private_fields():
    broker = GatewayData(queue.Queue())
    broker.data_error(6, 201, "", json.dumps({"8229": "IBDBUYTX", "account": "private-fixture"}))
    event = broker.observations.get_nowait()
    assert event["rejection"]["category"] == "acknowledgment_required"
    assert event["rejection"]["advanced_codes"] == ["IBDBUYTX"]
    assert "private-fixture" not in json.dumps(event)


def test_uncorrelated_broker_error_still_blocks_and_diagnostics_are_sanitized(tmp_path):
    engine, _ = crypto_engine(tmp_path)
    engine.observe({"type": "broker_error", "code": 201, "request": 9999, "context": "broker"})
    assert any(i["code"] == "broker_201" for i in engine.incidents.open())
    assert not engine.broker.submitted


@pytest.mark.parametrize("filled", ["0.1", "0.25"])
def test_executions_remain_authoritative_after_rejection(tmp_path, filled):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    reject(engine, order)
    confirm(engine, order, filled, status="Cancelled")
    detail = engine.order_detail(order["id"])["order"]["diagnostics"]
    assert "no fill" not in detail["status_label"].lower()
    assert engine.owned()[run["id"]]["quantity"] > 0
    assert engine.store.get("crypto_protection", run["id"])["stop"] == "99.00"
    assert engine.store.get("reservation", order["id"])["active"]


def test_incident_correlation_keeps_distinct_orders_and_existing_scope(tmp_path):
    book = IncidentBook(Store(tmp_path))
    one = book.raise_incident("order_uncertain", "fixture", "instance", correlation_key="first")
    two = book.raise_incident("order_uncertain", "fixture", "instance", correlation_key="second")
    assert one["id"] != two["id"]
    assert one["scope"] == two["scope"] == {"type": "workspace", "key": "*"}
    assert len(book.open()) == 2
    with pytest.raises(Conflict, match="ambiguous"):
        book.get("order_uncertain")


def test_new_unknown_after_working_is_a_new_failure_not_a_duplicate(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "Inactive")
    original = engine.incidents.open()[0]
    status(engine, order, "Submitted")
    status(engine, order, "Inactive")
    current = engine.incidents.get(original["id"])
    assert current["occurrences"] == 2
    assert current["failure_sequence"] > original["failure_sequence"]


def test_refined_rejection_invalidates_an_old_recovery_review(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    status(engine, order, "Inactive")
    original = engine.incidents.open()[0]
    with engine.store.transaction() as db:
        ready = engine.incidents.recover_in(db, original, {"fixture": True})
    reject(engine, order, "permissions")
    current = engine.incidents.get(original["id"])
    assert current["revision"] > ready["revision"]
    assert current["occurrences"] == 1
    assert current["restriction"] == "held"
    with pytest.raises(Conflict), engine.store.transaction() as db:
        engine.incidents.release_in(db, ready["id"], ready["revision"], "fixture-operator", "")


def test_unknown_late_rejection_does_not_overwrite_specific_evidence(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    reject(engine, order, "minimum_size")
    before = engine.incidents.open()[0]
    reject(engine, order)
    assert engine.incidents.get(before["id"])["revision"] == before["revision"]
    assert (
        engine.order_diagnostics(engine.store.orders()[0])["rejection"]["category"]
        == "minimum_size"
    )


def test_engine_rebuilds_diagnostics_from_allowlisted_fields(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    engine.observe(
        {
            "type": "broker_error",
            "code": 201,
            "request": order["broker_id"],
            "context": "broker",
            "rejection": {
                "category": "permissions",
                "detail": "private-fixture",
                "advanced_codes": ["private-fixture"],
            },
        }
    )
    with engine.store.connect() as db:
        assert not db.execute(
            "SELECT 1 FROM events WHERE payload LIKE '%private-fixture%'"
        ).fetchone()
        assert not db.execute(
            "SELECT 1 FROM documents WHERE payload LIKE '%private-fixture%'"
        ).fetchone()


def test_data_request_with_same_number_is_not_misclassified_as_order_reject(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    engine.observe(
        {
            "type": "broker_error",
            "code": 201,
            "request": order["broker_id"],
            "context": "retired_data",
            "conid": 456,
            "generation": 1,
        }
    )
    assert state(engine, order) == "dispatching"
    assert not engine.incidents.open()


def test_additive_incident_migration_preserves_history_and_backs_up(tmp_path):
    store = Store(tmp_path)
    book = IncidentBook(store)
    original = book.raise_incident("order_uncertain", "Historical fixture", "old-instance")
    with store.transaction() as db:
        before = db.execute(
            "SELECT payload FROM incident_episodes WHERE id=?", (original["id"],)
        ).fetchone()[0]
        journal = [tuple(r) for r in db.execute("SELECT sequence,type,payload FROM events")]
        db.execute("DROP INDEX incident_open_identity")
        db.execute("ALTER TABLE incident_episodes DROP COLUMN correlation_key")
        db.execute(
            "CREATE UNIQUE INDEX incident_open_identity ON incident_episodes"
            "(code,scope_type,scope_key) WHERE restriction!='released'"
        )
    migrated = IncidentBook(store)
    with store.connect() as db:
        assert (
            before
            == db.execute(
                "SELECT payload FROM incident_episodes WHERE id=?", (original["id"],)
            ).fetchone()[0]
        )
        assert journal == [
            tuple(r)
            for r in db.execute(
                "SELECT sequence,type,payload FROM events "
                "WHERE type!='incident.correlation.migration'"
            )
        ]
    assert list((tmp_path / "backups").glob("incident-correlation-*.sqlite3"))
    assert migrated.get(original["id"])["restriction"] == "held"
    migrated.raise_incident(
        "order_uncertain", "New order", "new-instance", correlation_key="new-order"
    )
    assert len(migrated.open()) == 2
    IncidentBook(store)
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM events WHERE type='incident.correlation.migration'"
            ).fetchone()[0]
            == 1
        )


def test_protection_leg_rejection_is_not_swallowed(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    # A legacy protected equity order owns its base ID and two child IDs.
    with engine.store.transaction() as db:
        payload = {**order["payload"], "execution": "equity"}
        db.execute("UPDATE outbox SET payload=? WHERE id=?", (json.dumps(payload), order["id"]))
    engine.observe(
        {
            "type": "broker_error",
            "code": 201,
            "request": order["broker_id"] + 2,
            "context": "broker",
        }
    )
    item = engine.incidents.open()[0]
    assert item["code"] == "order_uncertain"
    assert item["order_context"]["broker_id"] == order["broker_id"] + 2
    assert not engine.store.get("run", run["id"])["armed"]


def test_rejection_on_reconnect_does_not_reuse_old_snapshot_identity(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    details(engine, order, "Submitted")
    restarted = Engine(Store(tmp_path), CryptoBroker)
    assert not restarted.broker_orders
    reject(restarted, order)
    current = restarted.broker_orders[order["broker_id"]]
    assert "own_account" not in current
    assert "reference" not in current
    assert "conid" not in current
    assert current["status"] == "Rejected"
    assert not restarted.reconciled
    assert restarted.store.get("reservation", order["id"])["active"]


def test_legacy_cancelled_history_does_not_create_a_new_rejection_episode(tmp_path):
    engine, run = crypto_engine(tmp_path)
    order = crypto_entry(engine, run)
    details(engine, order, "Cancelled", completed=True)
    # Emulate a pre-correlation settled broker projection, without new failure documents.
    saved = engine.store.get("broker_order", str(order["broker_id"]))
    engine.store.put("broker_order", str(order["broker_id"]), {**saved, "rejection_code": 201})
    engine._finish_reconcile()
    restarted = Engine(Store(tmp_path), CryptoBroker)
    details(restarted, order, "Cancelled", completed=True)
    assert not restarted.incidents.open()
    assert (
        restarted.order_diagnostics(restarted.store.orders()[0])["rejection"]["category"]
        == "unknown"
    )


def test_rejected_exit_followed_by_cancelled_does_not_automatically_resubmit(tmp_path):
    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    confirm(engine, entry, "0.25")
    engine._crypto_close(run["id"])
    exit_order = next(o for o in engine.store.orders() if o["payload"]["purpose"] == "exit")
    reject(engine, exit_order)
    confirm(engine, exit_order, "0", status="Cancelled")
    assert engine.owned()[run["id"]]["quantity"] > 0
    with pytest.raises(Conflict, match="exit was rejected"):
        engine._crypto_close(run["id"])
    assert len(engine.broker.submitted) == 2
