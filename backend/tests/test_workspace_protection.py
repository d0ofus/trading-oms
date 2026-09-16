from decimal import Decimal

from test_workspace_engine import BrokerDouble

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Store


class ProtectionBroker(BrokerDouble):
    def submit_protection(self, intent):
        self.submitted.append(intent)


def fixture(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store, ProtectionBroker)
    engine.connected = engine.attested = engine.position_agreement = True
    identity = "a" * 32
    store.reserve_order(
        identity,
        {
            "purpose": "entry",
            "conid": 1,
            "symbol": "FIXTURE",
            "quantity": 5,
            "limit": "100",
            "stop": "99",
        },
        "run",
        100,
    )
    store.transition(identity, "working", {})
    entry = store.orders()[0]
    position = {
        "run_id": "run",
        "conid": 1,
        "symbol": "FIXTURE",
        "quantity": Decimal(2),
        "entry_id": identity,
    }
    return store, engine, entry, position


def test_partial_fill_cancels_remaining_then_requires_terminal_proof(tmp_path):
    store, engine, entry, position = fixture(tmp_path)
    engine._repair_protection(position, entry)
    assert engine.broker.cancelled == [100]
    assert not engine.broker.submitted
    store.transition(entry["id"], "cancelled", {})
    entry = store.orders()[0]
    engine._repair_protection(position, entry)
    assert not engine.broker.submitted  # Missing child is uncertain, not absent.
    engine.broker_orders[102] = {"status": "Cancelled"}
    engine._repair_protection(position, entry)
    assert engine.broker.submitted[0]["quantity"] == 2
    assert engine.broker.submitted[0]["stop"] == "99"
    engine._repair_protection(position, entry)
    assert len(engine.broker.submitted) == 1


def test_repair_never_replaces_uncertain_protection_or_disagreed_position(tmp_path):
    store, engine, entry, position = fixture(tmp_path)
    store.transition(entry["id"], "cancelled", {})
    entry = store.orders()[0]
    engine.broker_orders[102] = {"status": "Cancelled"}
    engine.position_agreement = False
    engine._repair_protection(position, entry)
    assert not engine.broker.submitted
    engine.position_agreement = True
    engine._repair_protection(position, entry)
    intent = next(o for o in store.orders() if o["payload"].get("purpose") == "protection")
    store.transition(intent["id"], "unknown", {})
    engine._repair_protection(position, entry)
    assert len(engine.broker.submitted) == 1


def test_protection_requires_exact_owned_quantity_client_and_overfill_block(tmp_path):
    store, engine, entry, position = fixture(tmp_path)
    store.transition(entry["id"], "filled", {})
    entry = store.orders()[0]
    valid = {
        "status": "Submitted",
        "client_id": 71,
        "own_account": True,
        "reference": "oms-" + entry["id"],
        "conid": 1,
        "order_type": "STP",
        "action": "SELL",
        "quantity": "2",
        "tif": "GTC",
        "oca_type": 2,
        "oca_group": "oms-" + entry["id"],
        "stop": "99",
    }
    engine.broker_orders[102] = valid
    assert engine._valid_protection(position, entry)
    for field, value in [
        ("client_id", 72),
        ("quantity", "5"),
        ("oca_type", 3),
        ("stop", "98"),
        ("own_account", False),
    ]:
        engine.broker_orders[102] = {**valid, field: value}
        assert not engine._valid_protection(position, entry)


def test_flat_position_cannot_release_capacity_with_replacement_sell_working(tmp_path):
    store, engine, entry, _ = fixture(tmp_path)
    store.transition(entry["id"], "filled", {})
    engine.broker_orders[102] = {"status": "Cancelled"}
    replacement = store.reserve_order(
        "repair",
        {
            "purpose": "protection",
            "entry_id": entry["id"],
            "quantity": 2,
        },
        "run",
        103,
    )
    engine.broker_orders[replacement["broker_id"]] = {"status": "Submitted"}
    assert engine._flat_sell_issues({})
    assert engine.broker.cancelled == [replacement["broker_id"]]
    engine.broker_orders[replacement["broker_id"]] = {"status": "Cancelled"}
    assert not engine._flat_sell_issues({})
    del engine.broker_orders[102]
    assert engine._flat_sell_issues({})  # Absence cannot prove the original stop terminal.


def test_cancellation_retries_only_after_positive_new_epoch_working_snapshot(tmp_path):
    store, engine, _, _ = fixture(tmp_path)
    engine._queue_cancel(100, "entry")
    engine.broker.epoch = 2
    engine._reconcile_cancellations()
    assert engine.broker.cancelled == [100]
    engine.broker_orders[100] = {"status": "Submitted"}
    engine._reconcile_cancellations()
    engine._reconcile_cancellations()
    assert engine.broker.cancelled == [100, 100]
    engine.broker_orders[100] = {"status": "Cancelled"}
    engine._reconcile_cancellations()
    assert store.get("cancel_request", "100")["state"] == "confirmed"


def test_inactive_order_is_uncertain_without_correlated_rejection(tmp_path):
    store, engine, entry, _ = fixture(tmp_path)
    engine._order_observation({"broker_id": 100, "status": "Inactive"})
    assert store.orders()[0]["state"] == "unknown"
    engine.observe({"type": "broker_error", "request": 100, "code": 201})
    assert store.orders()[0]["state"] == "rejected"
    engine.broker_orders[102] = {"status": "Inactive"}
    assert engine._flat_sell_issues({})  # Child rejection requires its own acknowledgement.
