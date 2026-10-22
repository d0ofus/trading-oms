import time

from test_workspace_stock_execution import StockBroker

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Store, now


def ready(tmp_path):
    engine = Engine(Store(tmp_path), StockBroker)
    engine.broker.reconcile = lambda: None
    engine.connected = engine.attested = engine.reconciled = engine.position_agreement = True
    engine.reconciled_at = time.monotonic()
    engine.facts = {"AvailableFunds": "10000", "NetLiquidation": "10000", "GrossPositionValue": "0"}
    engine.currency_facts = {
        (k, "USD"): {"value": v, "received_at": now()} for k, v in engine.facts.items()
    }
    return engine


def test_background_refresh_keeps_verified_funding_until_atomic_completion(tmp_path):
    engine = ready(tmp_path)
    engine.begin_reconcile()
    assert engine.reconciled and engine.position_agreement
    assert engine.facts["AvailableFunds"] == "10000"
    for tag, value in {
        "AvailableFunds": "11000",
        "NetLiquidation": "11000",
        "GrossPositionValue": "0",
    }.items():
        engine.observe({"type": "account_fact", "tag": tag, "value": value, "currency": "USD"})
    assert engine.facts["AvailableFunds"] == "10000"
    for kind in (
        "positions_end",
        "orders_end",
        "completed_orders_end",
        "executions_end",
        "account_end",
    ):
        engine.observe({"type": kind})
    assert engine.reconciled
    assert engine.facts["AvailableFunds"] == "11000"


def test_lower_funds_invalidate_entry_evidence_before_snapshot_completion(tmp_path):
    engine = ready(tmp_path)
    engine.begin_reconcile()
    engine.observe(
        {"type": "account_fact", "tag": "AvailableFunds", "value": "0", "currency": "USD"}
    )
    assert not engine.reconciled
    assert engine.position_agreement
    assert engine.facts["AvailableFunds"] == "10000"  # Retained history is explicitly invalid.


def test_intervening_state_revision_requires_a_new_snapshot(tmp_path):
    engine = ready(tmp_path)
    engine.begin_reconcile()
    engine.invalidate_reconciliation()
    for kind in (
        "positions_end",
        "orders_end",
        "completed_orders_end",
        "executions_end",
        "account_end",
    ):
        engine.observe({"type": kind})
    assert not engine.reconciled
    assert engine.facts["AvailableFunds"] == "10000"


def test_old_generation_completion_cannot_publish(tmp_path):
    engine = ready(tmp_path)
    engine.begin_reconcile()
    for kind in (
        "positions_end",
        "orders_end",
        "completed_orders_end",
        "executions_end",
        "account_end",
    ):
        engine.observe({"type": kind, "reconciliation_id": "retired"})
    assert engine.reconcile_inflight
    assert not engine.reconcile_parts
