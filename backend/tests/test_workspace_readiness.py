import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_workspace_engine import BrokerDouble

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.graph import templates
from trading_oms_backend.workspace.qualification import profiles
from trading_oms_backend.workspace.store import Store, now


def test_connecting_message_is_informational_and_correction_is_narrow(tmp_path):
    store = Store(tmp_path)
    for code in (2119, 2105):
        store.put("incident", f"broker_{code}", {"id": f"broker_{code}", "resolved": False})
    engine = Engine(store, BrokerDouble)
    for code in (2119, 2104):
        engine.observe({"type": "broker_error", "request": -1, "code": code})
    assert store.get("incident", "broker_2119")["resolved"]
    assert not store.get("incident", "broker_2105")["resolved"]
    assert len([e for e in store.events() if e["type"] == "incident.reclassified"]) == 1
    Engine(store, BrokerDouble)
    assert len([e for e in store.events() if e["type"] == "incident.reclassified"]) == 1
    engine.connected = True
    engine.observe({"type": "broker_error", "request": -1, "code": 1100})
    assert not engine.connected


@pytest.mark.parametrize(
    "sec_type,quantity,ready",
    [
        ("CASH", "12", True),
        ("STK", "0", True),
        ("STK", "1", False),
        ("", "1", False),
        ("OPT", "1", False),
    ],
)
def test_typed_currency_reconciliation(tmp_path, sec_type, quantity, ready):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.facts = {"NetLiquidation": "10000", "AvailableFunds": "10000", "GrossPositionValue": "0"}
    engine.positions = {
        1: {
            "conid": 1,
            "symbol": "USD",
            "sec_type": sec_type,
            "currency": "JPY",
            "exchange": "IDEALPRO",
            "quantity": quantity,
            "own_account": True,
        }
    }
    engine._finish_reconcile()
    assert engine.reconciled is ready
    if sec_type == "CASH":
        assert len(engine.snapshot()["currency_positions"]) == 1
        assert "currency" in engine.snapshot()["reconciliation"]["detail"]
    elif sec_type in {"", "OPT"}:
        assert "unexpected instrument type" in engine.last_fault


def test_currency_rows_do_not_hide_external_working_orders(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.facts = {"NetLiquidation": "10000", "AvailableFunds": "10000", "GrossPositionValue": "0"}
    engine.broker_orders = {123: {"status": "Submitted"}}
    engine._finish_reconcile()
    assert not engine.reconciled
    assert "working orders" in engine.last_fault


def test_daily_loss_profiles_migrate_without_rewriting_history(tmp_path):
    store = Store(tmp_path)
    legacy = {
        "id": "custom",
        "version": 3,
        "name": "Historical",
        "shares": 1,
        "runs": 1,
        "notional": "1000",
        "planned_stop_risk": "10",
        "entry_timeout": 30,
        "daily_loss": "10",
    }
    store.put("risk_profile", "custom:3", legacy)
    current = profiles(store)
    replacement = next(p for p in current if p["id"] == "custom" and p["version"] == 4)
    assert "daily_loss" not in replacement
    assert store.get("risk_profile", "custom:3") == legacy
    assert len(profiles(store)) == len(current)


@pytest.mark.parametrize("pnl", [None, Decimal("-1000"), Decimal("NaN"), Decimal("0")])
def test_pnl_never_gates_an_otherwise_valid_entry(tmp_path, pnl):
    class ExecutionBroker(BrokerDouble):
        def submit_bracket(self, intent):
            self.submitted.append(intent)

    store = Store(tmp_path)
    engine = Engine(store, ExecutionBroker)
    assert "daily_loss" not in {c["code"] for c in engine.readiness()}
    from test_workspace_health import healthy_watchdog

    healthy_watchdog(engine)
    engine.readiness = lambda *args: [{"passed": True}]
    engine.daily_pnl, engine.pnl_at = pnl, time.monotonic() - 100
    engine.facts = {"AvailableFunds": "10000"}
    draft = store.save_draft(None, "Optional P/L", templates()[1]["document"], 0)
    published = store.publish(draft["id"], 1)
    run = {
        "id": "run",
        "strategy_id": draft["id"],
        "version": published["version"],
        "symbol": "SPY",
        "conid": 1,
        "armed": True,
        "entries": 0,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    store.put("run", "run", run)
    engine.data[1] = {"warm": True, "live": True, "received_at": now(), "source_at": now()}
    engine.contracts[1] = {"market_rule": 1}
    engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
    engine.quotes[1] = {side: {"price": "100", "received_at": now()} for side in ("bid", "ask")}
    engine._enter(
        run,
        {"stop": Decimal("99"), "target": None},
        {"minutes_to_close": 120},
        store.capture({"source": "fixture"}),
    )
    assert len(engine.broker.submitted) == 1


def test_optional_pnl_errors_do_not_mask_connectivity_errors(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.observe({"type": "broker_error", "request": 903, "code": 321, "context": "pnl"})
    assert not engine.store.list("incident")
    engine.connected = True
    engine.observe({"type": "broker_error", "request": 903, "code": 1100, "context": "pnl"})
    assert not engine.connected
