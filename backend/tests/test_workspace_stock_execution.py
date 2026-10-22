"""New stock path with isolated broker transport and synthetic contract evidence."""

import copy
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_workspace_health import healthy_watchdog
from test_workspace_stock_policy import contract
from test_workspace_unified import CryptoBroker

from trading_oms_backend.workspace.broker import PaperGateway
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.graph import compile_graph
from trading_oms_backend.workspace.stock_sessions import StockSession
from trading_oms_backend.workspace.stock_strategies import stock_templates
from trading_oms_backend.workspace.store import Conflict, Store, now


class StockBroker(CryptoBroker):
    def submit_bracket(self, intent):
        self.submitted.append(intent)

    submit_exit = submit_bracket
    submit_protection = submit_bracket

    def amend_stock_stop(self, intent, amendment):
        self.submitted.append({"amendment": amendment, "intent": intent})


def fixture(tmp_path, monkeypatch, template=-1, protection="broker_held"):
    engine = Engine(Store(tmp_path), StockBroker)
    c = contract()
    engine.contracts[c["conid"]] = c
    # Preserve coverage of previously qualified/manual bindings, including their
    # odd-lot workflow. New automatic-policy tests use broker/reference fixtures.
    monkeypatch.setattr(
        engine,
        "_resolve_stock_rules",
        lambda conid, **kwargs: (engine.contracts[conid]["stock_rules"], {}, None),
    )
    document = stock_templates()[template]["document"]
    document["settings"].update(notional="1000", sizing="risk")
    draft = engine.store.save_draft(None, "Synthetic stock", document, 0)
    published = engine.store.publish(draft["id"], draft["revision"])
    compatibility = engine.stock_compatibility(draft["id"], 1, c["conid"], protection)
    run = engine.create_run(
        draft["id"],
        1,
        c["conid"],
        protection_type=protection,
        execution_plan_revision=compatibility["plan"]["hash"],
    )
    run.update(
        armed=True,
        authorized_at=(datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
        authorization_id="test",
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        limits={"shares": 1, "notional": "1000", "planned_stop_risk": "10", "entry_timeout": 30},
    )
    engine.store.put("run", run["id"], run)
    engine.data[c["conid"]].update(
        live=True, warm=True, price="30", source_at=now(), received_at=now()
    )
    engine.quotes[c["conid"]] = {
        s: {"price": v, "received_at": now()} for s, v in (("bid", "29.95"), ("ask", "30"))
    }
    engine.fx_quotes[("USD", "HKD")] = {
        "base": "USD",
        "quote": "HKD",
        "bid": "7.8",
        "ask": "7.82",
        "live": True,
        "received_at": now(),
    }
    engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
    engine.facts = {"NetLiquidation": "10000", "AvailableFunds": "10000", "GrossPositionValue": "0"}
    for tag in ("CashBalance", "SettledCash"):
        engine.currency_facts[(tag, "HKD")] = {"value": "10000", "received_at": now()}
    engine.connected = engine.attested = engine.reconciled = engine.position_agreement = (
        engine.clock_ok
    ) = True
    engine.reconciled_at = time.monotonic()
    engine.server_version, engine.next_id = 220, 100
    healthy_watchdog(engine)
    monkeypatch.setattr(StockSession, "tradable", lambda self, stamp: True)
    return engine, run, published


def enter(engine, run):
    engine._enter(
        run, {"stop": Decimal("29.70"), "target": None}, {"minutes_to_close": 60}, "synthetic"
    )
    return engine.store.orders()[-1]


def test_hk_stock_share_entry_reserves_usd_and_native_cash(tmp_path, monkeypatch):
    engine, run, published = fixture(tmp_path, monkeypatch)
    order = enter(engine, run)
    assert order["payload"]["entry_type"] == "MKT"
    assert order["payload"]["quantity"] == "200"
    assert "cash_quantity" not in order["payload"]
    reserve = engine.store.get("reservation", order["id"])
    assert Decimal(reserve["notional"]) == Decimal(6000) / Decimal("7.8")
    assert reserve["native_funds"] == "6025"
    assert len(engine.broker.submitted) == 1
    assert engine._runtime(run)["graph"].digest == published["hash"]


@pytest.mark.parametrize("template", range(4))
def test_all_templates_bind_without_changing_published_hash(tmp_path, monkeypatch, template):
    engine, run, published = fixture(tmp_path, monkeypatch, template)
    original = copy.deepcopy(published)
    runtime = engine._runtime(run)
    assert runtime["graph"].document["settings"]["symbol"] == "1810"
    assert runtime["market"].schedule.contract["stock_rules"]["calendar"] == "XHKG"
    assert (
        compile_graph(engine.store.version(run["strategy_id"], 1)["document"]).digest
        == original["hash"]
    )


def test_stale_fx_and_missing_native_funding_never_submit(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch)
    engine.fx_quotes[("USD", "HKD")]["received_at"] = (
        datetime.now(UTC) - timedelta(seconds=61)
    ).isoformat()
    with pytest.raises(Conflict, match="valuation"):
        enter(engine, run)
    engine.fx_quotes[("USD", "HKD")]["received_at"] = now()
    engine.currency_facts.clear()
    with pytest.raises(Conflict, match="settled"):
        enter(engine, run)
    assert not engine.broker.submitted


def test_rule_revision_invalidates_binding_without_rewriting_history(tmp_path, monkeypatch):
    engine, run, published = fixture(tmp_path, monkeypatch)
    engine.contracts[run["conid"]]["stock_rules"]["revision"] += 1
    with pytest.raises(Conflict, match="identity changed"):
        enter(engine, run)
    assert engine.store.version(run["strategy_id"], 1) == published
    assert not engine.broker.submitted


def test_local_protection_has_no_native_child_and_never_fabricates_fill(tmp_path, monkeypatch):
    from trading_oms_backend.workspace.protection import order_ids

    engine, run, _ = fixture(tmp_path, monkeypatch, protection="locally_monitored")
    order = enter(engine, run)
    assert order_ids(order) == {order["broker_id"]}
    assert not engine.owned()
    assert not engine.store.get("stock_protection", run["id"])


def test_sdk_guard_checks_currency_lots_risk_and_rejects_live_context(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch)
    entry = enter(engine, run)
    intent = {**entry["payload"], **entry}
    gateway = PaperGateway(engine.observations)
    calls = []
    gateway.client = SimpleNamespace(
        isConnected=lambda: True, placeOrder=lambda *args: calls.append(args)
    )
    gateway._accounts = ["DU0000000"]  # Synthetic fixture identity, never a configured account.
    gateway._attested = True
    gateway._contracts[run["conid"]] = SimpleNamespace(
        conId=run["conid"], secType="STK", currency="HKD", exchange="SEHK"
    )
    gateway.submit_bracket(intent)
    assert [args[2].orderType for args in calls] == ["MKT", "STP"]
    assert calls[0][2].totalQuantity == Decimal(200)
    assert not calls[0][2].transmit and calls[1][2].transmit
    calls.clear()
    with pytest.raises(ValueError):
        gateway.submit_bracket({**intent, "quantity": "201"})
    gateway._accounts = ["U123456"]
    with pytest.raises(ValueError):
        gateway.submit_bracket(intent)
    assert not calls


def test_account_summary_normalization_does_not_double_count_currency_copies(tmp_path, monkeypatch):
    engine, _, _ = fixture(tmp_path, monkeypatch)
    engine._stock_fact({"tag": "AvailableFunds", "currency": "HKD", "value": "7820"})
    assert Decimal(engine.facts["AvailableFunds"]) == 1000
    engine._stock_fact({"tag": "AvailableFunds", "currency": "USD", "value": "999"})
    assert engine.facts["AvailableFunds"] == "999"


def observation(engine, order, status="Filled", *, child=False, filled="200", stop="29.70"):
    p = order["payload"]
    event = {
        "type": "open_order",
        "broker_id": order["broker_id"] + (2 if child else 0),
        "client_id": engine.broker.client_id,
        "own_account": True,
        "reference": "oms-" + order["id"],
        "conid": p["conid"],
        "symbol": p["symbol"],
        "order_type": "STP" if child else p.get("entry_type", "LMT"),
        "action": "SELL" if child or p.get("purpose") == "exit" else "BUY",
        "quantity": p["quantity"],
        "filled": "0" if child else filled,
        "parent_id": order["broker_id"] if child else 0,
        "status": status,
        "tif": "GTC" if child else "DAY",
        "limit": p.get("limit"),
        "stop": stop,
        "oca_type": 2 if child or p.get("purpose") == "exit" else 0,
        "oca_group": "oms-" + p.get("entry_id", order["id"])
        if child or p.get("purpose") == "exit"
        else "",
    }
    engine.observe(event)


def fill(engine, order, quantity="200", price="30.10"):
    p = order["payload"]
    engine.observe(
        {
            "type": "execution",
            "broker_id": order["broker_id"],
            "client_id": engine.broker.client_id,
            "own_account": True,
            "execution_id": "synthetic-" + order["id"],
            "conid": p["conid"],
            "symbol": p["symbol"],
            "side": "SLD" if p.get("purpose") == "exit" else "BOT",
            "quantity": quantity,
            "price": price,
        }
    )
    engine.positions[p["conid"]] = {
        "conid": p["conid"],
        "quantity": str(engine.owned()[order["run_id"]]["quantity"]),
        "sec_type": "STK",
        "own_account": True,
        "currency": "HKD",
    }


def test_native_actual_fill_protection_ack_exit_and_pause(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch)
    entry = enter(engine, run)
    observation(engine, entry)
    observation(engine, entry, status="Submitted", child=True)
    fill(engine, entry)
    engine._finish_reconcile()
    assert engine.store.get("stock_protection", run["id"])["stop"] == "29.80"
    assert not engine.reconciled
    assert not engine.incidents.open()
    assert engine.broker.submitted[-1]["amendment"]["stop"] == "29.80"
    observation(engine, entry, status="Submitted", child=True, stop="29.80")
    engine._finish_reconcile()
    assert engine.reconciled, engine.last_fault
    assert engine.store.get("run", run["id"])["protected"]
    engine.close_position(run["id"])
    exit_order = engine.store.orders()[0]
    assert exit_order["payload"]["quantity"] == "200"
    observation(engine, exit_order)
    fill(engine, exit_order, price="30.05")
    observation(engine, entry, status="Cancelled", child=True, stop="29.80")
    engine._finish_reconcile()
    assert engine.reconciled, engine.last_fault
    assert engine.store.get("run", run["id"])["state"] == "paused"
    assert not engine.store.get("reservation", entry["id"])["active"]
    assert not engine.store.list("stock_qualification")  # A fake broker is not paper evidence.


def test_partial_odd_lot_local_stop_no_topup_duplicate_exit_or_outage_liquidation(
    tmp_path, monkeypatch
):
    engine, run, _ = fixture(tmp_path, monkeypatch, protection="locally_monitored")
    entry = enter(engine, run)
    observation(engine, entry, status="Cancelled", filled="37")
    fill(engine, entry, quantity="37")
    engine._finish_reconcile()
    assert engine.reconciled, engine.last_fault
    plan = engine.store.get("stock_protection", run["id"])
    assert plan["quantity"] == "37" and plan["stop"] == "29.80"
    engine.connected = False
    assert engine._stock_protection_view()[0]["status"] == "suspended"
    engine._outage_tick()
    engine._outage_tick()
    assert engine.store.get("connection_outage", "current")["active"]
    assert len(engine.store.list("notification")) == 1
    event = {"conid": run["conid"], "price": "29", "timestamp": time.time(), "sequence": 55}
    engine._stock_trade(event)
    assert len(engine.broker.submitted) == 1
    engine.connected = True
    assert engine._stock_protection_view()[0]["status"] == "active"
    engine._outage_tick()
    assert not engine.store.get("connection_outage", "current")["active"]
    engine._stock_trade(event)
    engine._stock_trade(event)
    assert len(engine.broker.submitted) == 2
    assert engine.broker.submitted[-1]["quantity"] == "37"
    assert engine.broker.submitted[-1]["purpose"] == "exit"


def test_arming_requires_reviewed_policy_and_explicit_local_ack(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch, protection="locally_monitored")
    preview = {
        "eligible": True,
        "runs": [run],
        "expires_at": run["expires_at"],
        "limits": run["limits"],
        "authorization": "supervised_paper_session",
    }
    monkeypatch.setattr(engine, "arm_preview", lambda *args: preview)
    with pytest.raises(Conflict, match="execution plan"):
        engine.arm([run["id"]], "review")
    revisions = {run["id"]: run["binding"]["execution_plan"]["hash"]}
    with pytest.raises(Conflict, match="acknowledge"):
        engine.arm([run["id"]], "review", execution_plan_revisions=revisions)
    engine.arm(
        [run["id"]],
        "review",
        execution_plan_revisions=revisions,
        local_protection_acknowledged=True,
    )
    assert engine.arm(
        [run["id"]],
        "review",
        execution_plan_revisions=revisions,
        local_protection_acknowledged=True,
    ) == {"armed": [run["id"]]}


def test_restart_never_resends_pending_stock_order(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch)
    entry = enter(engine, run)
    restored = Engine(engine.store, StockBroker)
    assert not restored.store.get("run", run["id"])["armed"]
    assert restored.store.orders()[-1]["state"] == "unknown"
    assert restored.store.get("reservation", entry["id"])["active"]
    assert not restored.broker.submitted


def test_working_partial_fill_cancels_only_remainder_and_reserves_actual_gap(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch)
    entry = enter(engine, run)
    observation(engine, entry, status="Submitted", filled="37")
    fill(engine, entry, quantity="37", price="40")
    current = next(o for o in engine.store.orders() if o["id"] == entry["id"])
    assert current["state"] == "cancel_pending"
    assert engine.store.get("stock_protection", run["id"])["quantity"] == "37"
    assert len(engine.broker.submitted) == 1
    engine._stock_sync()
    assert len(engine.broker.submitted) == 1


def test_fill_gap_over_budget_retains_protection_and_blocks_new_risk(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch)
    entry = enter(engine, run)
    observation(engine, entry)
    fill(engine, entry, price="40")
    reserved = engine.store.get("reservation", entry["id"])
    assert Decimal(reserved["notional"]) > 1000
    assert reserved["native_funds"] == "8025"
    assert reserved["active"]
    assert engine.store.get("stock_protection", run["id"])["stop"] == "39.60"
    assert any(i["code"] == "stock_fill_gap_limit" for i in engine.incidents.open())
    assert not engine.store.get("run", run["id"])["armed"]


def test_superseded_history_jobs_do_not_prevent_completed_coverage(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch)
    conid = run["conid"]
    old = (conid, "obsolete", 60)
    engine.register_history_jobs([old])
    engine.history_units[old]["status"] = "failed"
    engine._queue_history(conid, extend=True)
    assert old not in engine.history_contract_jobs[conid]
    for job in engine.history_contract_jobs[conid]:
        engine.history_units[job]["status"] = "completed"
    engine.history_jobs = []
    engine.observe({"type": "history_end", "request": 99999, "conid": conid})
    assert engine.data[conid]["history_loaded"]


def test_shared_contract_risk_is_serialized_without_touching_another_allocation(
    tmp_path, monkeypatch
):
    engine, run, published = fixture(tmp_path, monkeypatch)
    first = enter(engine, run)
    other = engine.create_run(
        run["strategy_id"],
        1,
        run["conid"],
        execution_plan_revision=run["binding"]["execution_plan"]["hash"],
    )
    other.update(
        armed=True, expires_at=run["expires_at"], authorization_id="other", limits=run["limits"]
    )
    engine.store.put("run", other["id"], other)
    with pytest.raises(Conflict, match="already has reserved"):
        engine.store.reserve_order(
            "other-entry",
            first["payload"],
            other["id"],
            200,
            engine.store.get("reservation", first["id"]),
        )
    assert len(engine.broker.submitted) == 1
    assert engine.store.get("reservation", first["id"])["run_id"] == run["id"]


def test_stock_session_exit_uses_qualified_broker_close_not_us_or_full_hk_day(
    tmp_path, monkeypatch
):
    import trading_oms_backend.workspace.engine as module

    engine, run, _ = fixture(tmp_path, monkeypatch)
    run["binding"]["contract"]["liquid_hours"] = "20260922:0930-20260922:1200,1300-20260922:1400"
    engine.contracts[run["conid"]]["liquid_hours"] = run["binding"]["contract"]["liquid_hours"]
    engine.store.put("run", run["id"], run)
    engine.runtime.clear()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 22, 5, 59, tzinfo=UTC)

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(engine, "owned", lambda: {run["id"]: {"quantity": Decimal(200)}})
    exits = []
    monkeypatch.setattr(engine, "_request_exit", exits.append)
    engine._clock_evaluations()
    assert exits == [run["id"]]


def test_scheduled_break_does_not_report_quiet_local_protection_as_an_outage(tmp_path, monkeypatch):
    engine, run, _ = fixture(tmp_path, monkeypatch, protection="locally_monitored")
    entry = enter(engine, run)
    observation(engine, entry)
    fill(engine, entry)
    engine._finish_reconcile()
    monkeypatch.setattr(StockSession, "tradable", lambda self, stamp: False)
    engine.data[run["conid"]]["received_at"] = (
        datetime.now(UTC) - timedelta(minutes=30)
    ).isoformat()
    engine._outage_tick()
    assert not engine.store.get("connection_outage", "current")
    assert engine._stock_protection_view()[0]["status"] == "waiting_for_session"
    assert len(engine.broker.submitted) == 1
    engine.connected = False
    engine._outage_tick()
    assert engine.store.get("connection_outage", "current")["active"]
