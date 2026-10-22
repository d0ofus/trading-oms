import copy
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_workspace_fx_policy import fx_contract, fx_document
from test_workspace_health import healthy_watchdog
from test_workspace_unified import CryptoBroker

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.fx_ledger import ledger
from trading_oms_backend.workspace.fx_sessions import FXSession
from trading_oms_backend.workspace.graph import digest
from trading_oms_backend.workspace.store import Conflict, Store, now


class FXBroker(CryptoBroker):
    def submit_fx(self, intent):
        self.submitted.append(intent)

    def start_feed(self, conid, kind):
        return 500 if kind == "fx_bidask" else 501

    def history(self, *args, **kwargs):
        return 600


def fixture(tmp_path, monkeypatch, protection="locally_monitored"):
    engine = Engine(Store(tmp_path), FXBroker)
    contract = fx_contract()
    beginning = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y%m%d")
    ending = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y%m%d")
    contract["trading_hours"] = f"{beginning}:0000-{ending}:1700"
    contract.update(metadata_instance=engine.process_identity, metadata_epoch=engine.broker.epoch)
    conid = contract["conid"]
    engine.contracts[conid] = contract
    engine.market_rules[1] = [{"low": "0", "increment": "0.00005"}]
    engine._stock_market_rule_context = {1: (engine.process_identity, engine.broker.epoch)}
    draft = engine.store.save_draft(None, "FX fixture", fx_document(), 0)
    engine.store.publish(draft["id"], 1)
    result = engine.fx_compatibility(draft["id"], 1, conid, protection)
    run = engine.create_run(
        draft["id"], 1, conid, {"quantity": "25000"}, protection, result["plan"]["hash"], "fx"
    )
    engine.connected = engine.attested = engine.reconciled = engine.position_agreement = (
        engine.clock_ok
    ) = True
    engine.server_version, engine.next_id, engine.code_verified = 220, 100, True
    engine.reconciled_at = time.monotonic()
    engine.facts = {
        "AvailableFunds": "100000",
        "NetLiquidation": "100000",
        "GrossPositionValue": "0",
    }
    engine.account_base_currency = "USD"
    for currency, value in (("USD", "100000"), ("AUD", "1000")):
        for tag in ("CashBalance", "SettledCash"):
            engine.currency_facts[(tag, currency)] = {"value": value, "received_at": now()}
    engine.data[conid]["live"] = True
    cache = engine._fx_cache(conid)
    cache["fx_bidask"] = {
        "bid": "0.65",
        "ask": "0.6501",
        "valid": True,
        "source_at": now(),
        "received_at": now(),
    }
    cache["fx_midpoint"] = {
        "price": "0.65005",
        "valid": True,
        "source_at": now(),
        "received_at": now(),
    }
    cache["sources"]["MIDPOINT"].update(status="completed", epoch=engine.broker.epoch)
    for state in cache["feeds"].values():
        state.update(status="healthy", epoch=engine.broker.epoch)
    healthy_watchdog(engine)
    monkeypatch.setattr(FXSession, "tradable", lambda self, stamp: True)
    monkeypatch.setattr(
        FXSession,
        "bounds",
        lambda self, stamp: (stamp - timedelta(hours=1), stamp + timedelta(hours=1)),
    )
    return engine, run


def arm(engine, run, mutation="a" * 32):
    preview = engine.arm_preview([run["id"]])
    assert preview["eligible"], [
        (c["code"], c["detail"]) for c in preview["checks"] if not c["passed"]
    ]
    engine.arm(
        [run["id"]],
        mutation,
        review_fingerprint=preview["review_fingerprint"],
        fx_policy_revision="idealpro_funded_fx_v1",
        resume_policy=preview["resume_policy"],
        review_instance=engine.process_identity,
        local_protection_acknowledged=True,
        execution_plan_revisions={run["id"]: run["binding"]["execution_plan"]["hash"]},
    )
    return engine.store.get("run", run["id"])


def signal():
    at = datetime.now(UTC)
    return {
        "candle": (at - timedelta(minutes=1)).isoformat(),
        "price": "0.65005",
        "high": "0.65",
        "triggered_at": at.isoformat(),
        "expires_at": (at + timedelta(seconds=30)).isoformat(),
    }


def enter(engine, run):
    engine._fx_enter(run, signal(), "fixture")
    return engine.store.orders()[0]


def fill(engine, order, quantity="25000", side="BOT", identity="fx.1"):
    engine._owned_cache = None
    engine.observe(
        {
            "type": "execution",
            "execution_id": identity,
            "broker_id": order["broker_id"],
            "client_id": engine.broker.client_id,
            "own_account": True,
            "conid": order["payload"]["conid"],
            "symbol": "AUD",
            "quantity": quantity,
            "price": "0.6501",
            "side": side,
        }
    )


def test_fx_prepare_arm_entry_and_atomic_consumption(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    assert not engine._stock_run(run)
    assert not engine.broker.submitted
    run = arm(engine, run)
    entry = enter(engine, run)
    assert len(engine.broker.submitted) == 1
    assert engine.broker.submitted[0]["entry_type"] == "MKT"
    assert engine.store.get("run", run["id"])["entries"] == 1
    assert engine.store.get("fx_protection", run["id"])["state"] == "awaiting_fill"
    assert engine.store.get("fx_ledger", "baseline")["balances"]["AUD"] == "1000"
    assert Decimal(engine.store.get("reservation", entry["id"])["notional"]) > 1000
    enter(engine, run)
    assert len(engine.broker.submitted) == 1


def test_stale_quotes_and_insufficient_cash_block_without_incident(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine._fx_cache(run["conid"])["fx_bidask"]["source_at"] = (
        datetime.now(UTC) - timedelta(seconds=16)
    ).isoformat()
    assert not engine.arm_preview([run["id"]])["eligible"]
    engine._fx_cache(run["conid"])["fx_bidask"]["source_at"] = now()
    engine.currency_facts[("SettledCash", "USD")]["value"] = "1"
    assert not engine.arm_preview([run["id"]])["eligible"]
    assert not engine.broker.submitted
    assert not engine.incidents.applicable([run])


def test_partial_fill_protection_uses_actual_fill_and_currency_ledger(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch, "broker_held")
    entry = enter(engine, arm(engine, run))
    fill(engine, entry, "10000")
    plan = engine.store.get("fx_protection", run["id"])
    assert plan["quantity"] == "10000"
    assert Decimal(plan["stop"]) == Decimal("0.64360")
    assert engine.broker.submitted[-1]["purpose"] == "protection"
    assert engine.broker.submitted[-1]["quantity"] == "10000"
    record = ledger(engine.store)
    assert record["flows"]["AUD"] == 10000
    assert record["flows"]["USD"] == Decimal("-6501.0000")
    assert record["missing_commissions"] == ["fx.1"]
    fill(engine, entry, "10000")
    assert len(engine.broker.submitted) == 2


def test_pending_submission_is_not_resubmitted_and_local_stop_is_not_a_fill(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    engine.observe(
        {
            "type": "order_status",
            "broker_id": entry["broker_id"],
            "client_id": engine.broker.client_id,
            "status": "ApiPending",
            "filled": "0",
            "remaining": "25000",
            "average": "0",
        }
    )
    assert not engine.incidents.applicable([run])
    assert engine.store.orders()[0]["state"] == "dispatching"
    fill(engine, entry)
    engine._fx_cache(run["conid"])["fx_bidask"]["bid"] = "0.64"
    engine._fx_sync(engine.store.get("run", run["id"]))
    assert engine.store.get("exit_request", run["id"])["fx"]
    assert engine.owned()[run["id"]]["quantity"] == 25000
    assert len(engine.broker.submitted) == 1  # Reconciliation/cancellation still required.


def test_fx_identity_missing_details_differs_from_mismatch(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    assert "Awaiting" in engine._fx_identity(entry, {"status": "ApiPending"})[0]
    observation = {
        "conid": run["conid"],
        "own_account": True,
        "client_id": engine.broker.client_id,
        "reference": "oms-" + entry["id"],
        "quantity": "25000",
        "order_type": "MKT",
        "action": "BUY",
        "tif": "IOC",
        "sec_type": "CASH",
        "currency": "USD",
        "routing_exchange": "IDEALPRO",
        "outside_rth": True,
    }
    assert not engine._fx_identity(entry, observation)
    assert engine._fx_identity(entry, {**observation, "own_account": False})


def completed(engine, order, status="Filled", filled="25000"):
    event = {
        "type": "open_order",
        "broker_id": order["broker_id"],
        "client_id": engine.broker.client_id,
        "status": status,
        "filled": filled,
        "quantity": order["payload"]["quantity"],
        "remaining": "0",
        "average": "0.6501",
        "conid": order["payload"]["conid"],
        "symbol": "AUD",
        "own_account": True,
        "action": "BUY" if order["payload"]["purpose"] == "entry" else "SELL",
        "reference": "oms-" + order["id"],
        "order_type": "MKT" if order["payload"]["purpose"] == "entry" else "LMT",
        "tif": "IOC" if order["payload"]["purpose"] == "entry" else "GTD",
        "limit": order["payload"]["limit"],
        "good_till_date": order["payload"].get("good_till_date"),
        "completed": True,
        "sec_type": "CASH",
        "currency": "USD",
        "routing_exchange": "IDEALPRO",
        "outside_rth": True,
    }
    if order["payload"]["purpose"] == "protection":
        event.update(order_type="STP", tif="GTC", stop=order["payload"]["stop"], trigger_method=4)
    engine.observe(event)


def reconcile_proof(engine):
    engine._reconciliation_started = {
        "id": "fixture",
        "started_at": now(),
        "instance": engine.process_identity,
        "epoch": engine.broker.epoch,
        "evidence_revision": getattr(engine, "_evidence_revision", 0),
    }
    engine._finish_reconcile()


def test_local_fx_exit_requires_post_cancel_reconciliation_and_no_overlap(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    fill(engine, entry)
    completed(engine, entry)
    engine.observe({"type": "commission", "execution_id": "fx.1", "currency": "USD", "amount": "2"})
    engine.currency_facts[("CashBalance", "USD")]["value"] = "83745.5"
    engine.currency_facts[("CashBalance", "AUD")]["value"] = "26000"
    reconcile_proof(engine)
    assert engine.position_agreement
    engine._fx_cache(run["conid"])["fx_bidask"]["bid"] = "0.64"
    engine._fx_sync(engine.store.get("run", run["id"]))
    exits = [o for o in engine.store.orders() if o["payload"]["purpose"] == "exit"]
    assert len(exits) == 1
    assert Decimal(exits[0]["payload"]["limit"]) == Decimal("0.64")
    assert exits[0]["payload"]["quantity"] == "25000"
    completed(engine, exits[0], "Cancelled", "0")
    engine._fx_exit_maintain(engine.store.get("run", run["id"]))
    assert len(engine.broker.submitted) == 2
    reconcile_proof(engine)
    engine._fx_exit_maintain(engine.store.get("run", run["id"]))
    assert len(engine.broker.submitted) == 3
    engine._fx_exit_maintain(engine.store.get("run", run["id"]))
    assert len(engine.broker.submitted) == 3


def test_currency_ledger_includes_commissions_and_detects_external_cash(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    fill(engine, entry)
    engine.observe({"type": "commission", "execution_id": "fx.1", "currency": "USD", "amount": "2"})
    engine.currency_facts[("CashBalance", "USD")]["value"] = "83745.5"
    engine.currency_facts[("CashBalance", "AUD")]["value"] = "26000"
    assert not engine._fx_cash_issues()
    engine.currency_facts[("CashBalance", "AUD")]["value"] = "25000"
    assert "AUD" in engine._fx_cash_issues()[0]
    assert engine.owned()[run["id"]]["quantity"] == 25000
    restarted = Engine(Store(tmp_path), FXBroker)
    assert ledger(restarted.store) == ledger(engine.store)
    assert not restarted.store.get("run", run["id"])["armed"]
    assert not restarted.broker.submitted


def test_fx_fee_reserve_uses_account_base_currency(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    engine.account_base_currency = "AUD"
    engine.fx_quotes[("AUD", "USD")] = {
        "base": "AUD",
        "quote": "USD",
        "bid": "0.65",
        "ask": "0.6501",
        "live": True,
        "received_at": now(),
    }
    result = engine._fx_funding(run["binding"]["execution_plan"], run["binding"]["sizing"])
    assert result["fee_currency"] == "AUD"
    assert Decimal(result["currency_reserves"]["AUD"]) >= Decimal(4) / Decimal("0.65")
    engine.currency_facts[("SettledCash", "AUD")]["value"] = "0"
    with pytest.raises(Conflict, match="AUD"):
        engine._fx_funding(run["binding"]["execution_plan"], run["binding"]["sizing"])


def test_fx_snapshot_and_order_details_remain_inspectable(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    view = engine.snapshot(compact=True)
    assert view["data"][0]["family"] == "spot_fx"
    assert view["data"][0]["signal_source"] == "MIDPOINT"
    assert view["data"][0]["candle_source"] != "TRADES"
    assert engine.order_detail(entry["id"])["fx_protection"]["quantity"] == "0"


def test_old_client_or_rollback_cannot_arm_fx(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    preview = engine.arm_preview([run["id"]])
    with pytest.raises(Conflict, match="FX signal"):
        engine.arm(
            [run["id"]],
            "b" * 32,
            review_fingerprint=preview["review_fingerprint"],
            resume_policy=preview["resume_policy"],
            review_instance=engine.process_identity,
            execution_plan_revisions={run["id"]: run["binding"]["execution_plan"]["hash"]},
        )
    monkeypatch.setenv("OMS_DISABLE_FX_ARM", "1")
    assert not engine.arm_preview([run["id"]])["eligible"]
    assert not engine.broker.submitted


def test_concurrent_currency_reservations_are_checked_in_the_store_transaction(
    tmp_path, monkeypatch
):
    engine, run = fixture(tmp_path, monkeypatch)
    for tag in ("CashBalance", "SettledCash"):
        engine.currency_facts[(tag, "USD")]["value"] = "20000"
    entry = enter(engine, arm(engine, run))
    other = copy.deepcopy(engine.store.get("run", run["id"]))
    other.update(id="b" * 32, conid=999, entries=0)
    other["binding"]["execution_plan"]["conid"] = 999
    plan = other["binding"]["execution_plan"]
    plan["hash"] = digest({k: v for k, v in plan.items() if k != "hash"})
    engine.store.put("run", other["id"], other)
    payload = copy.deepcopy(entry["payload"])
    payload.update(conid=999, fx_plan=plan)
    reserve = engine.store.get("reservation", entry["id"])
    reserve.update(conid=999, run_id=other["id"])
    # Both preparations saw the original funds. Only one can consume them.
    with pytest.raises(Conflict, match="Concurrent reservations"):
        engine.store.reserve_order("b" * 32, payload, other["id"], 200, reserve)
    assert len(engine.store.orders()) == 1


def test_pending_timeout_keeps_reservation_and_never_retries(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    for name in ("next_reconcile", "next_heartbeat", "_next_health_write", "_next_runtime_clock"):
        setattr(engine, name, float("inf"))
    with engine.store.transaction() as db:
        db.execute(
            "UPDATE outbox SET created_at=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(seconds=31)).isoformat(), entry["id"]),
        )
    engine.maintain()
    engine.maintain()
    assert engine.store.get("reservation", entry["id"])["active"]
    engine._fx_enter(engine.store.get("run", run["id"]), {"candle": now()}, "fixture")
    assert len(engine.broker.submitted) == 1
    assert engine.store.orders()[0]["state"] == "cancel_pending"


def test_settled_purchase_retains_allocation_but_not_duplicate_cash_hold(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    fill(engine, entry)
    completed(engine, entry)
    engine.observe({"type": "commission", "execution_id": "fx.1", "currency": "USD", "amount": "2"})
    engine.currency_facts[("CashBalance", "USD")]["value"] = "83745.5"
    engine.currency_facts[("CashBalance", "AUD")]["value"] = "26000"
    reconcile_proof(engine)
    reservation = engine.store.get("reservation", entry["id"])
    assert reservation["active"] and reservation["purchase_settled"]
    assert reservation["currency_reserves"] == {"USD": "2"}


def test_late_fill_restores_requested_exit_and_outage_does_not_create_one(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    fill(engine, entry)
    engine._connection_lost("Synthetic data interruption")
    assert not engine.store.get("exit_request", run["id"])
    engine._fx_request_exit(engine.store.get("run", run["id"]), "Operator exit")
    engine.store.put("exit_request", run["id"], {})  # Flat reconciliation clears operational work.
    engine._fx_sync(engine.store.get("run", run["id"]))
    assert engine.store.get("exit_request", run["id"])["entry_id"] == entry["id"]
    assert len(engine.broker.submitted) == 1  # Reconnect ownership is not established yet.


def test_reconnect_requires_current_order_ownership_before_new_protection(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    fill(engine, entry)
    engine._fx_reset_data()
    assert not engine._fx_account_ready(run)
    assert "ownership evidence" in " ".join(engine._fx_cash_issues())
    completed(engine, entry)
    assert engine._fx_account_ready(run)
    engine.paper_context_token = "changed-synthetic-context"
    assert not engine._fx_account_ready(run)


def test_restart_restores_published_bid_source_instead_of_default_midpoint(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    run["binding"]["execution_plan"]["signal_source"] = "BID"
    engine.store.put("run", run["id"], run)
    restarted = Engine(Store(tmp_path), FXBroker)
    restarted.contracts[run["conid"]] = engine.contracts[run["conid"]]
    restarted.subscribe(run["conid"])
    assert set(restarted._fx_cache(run["conid"])["sources"]) == {"BID"}


def test_second_partial_fill_replaces_protection_only_after_cancel_reconciliation(
    tmp_path, monkeypatch
):
    engine, run = fixture(tmp_path, monkeypatch, "broker_held")
    entry = enter(engine, arm(engine, run))
    fill(engine, entry, "10000")
    original_stop = next(
        o for o in engine.store.orders() if o["payload"]["purpose"] == "protection"
    )
    completed(engine, original_stop, "Submitted", "0")
    engine.observe(
        {
            "type": "execution",
            "execution_id": "second.1",
            "broker_id": entry["broker_id"],
            "client_id": engine.broker.client_id,
            "own_account": True,
            "conid": run["conid"],
            "symbol": "AUD",
            "quantity": "15000",
            "price": "0.651",
            "side": "BOT",
        }
    )
    assert len(engine.broker.submitted) == 2
    assert engine.store.get("cancel_request", str(original_stop["broker_id"]))["state"] == "pending"
    completed(engine, entry)
    completed(engine, original_stop, "Cancelled", "0")
    for identity, amount in (("fx.1", "2"), ("second.1", "0")):
        engine.observe(
            {"type": "commission", "execution_id": identity, "currency": "USD", "amount": amount}
        )
    engine.currency_facts[("CashBalance", "USD")]["value"] = "83732"
    engine.currency_facts[("CashBalance", "AUD")]["value"] = "26000"
    reconcile_proof(engine)
    engine._fx_sync(engine.store.get("run", run["id"]))
    assert len(engine.broker.submitted) == 3
    assert engine.broker.submitted[-1]["quantity"] == "25000"
    assert Decimal(engine.broker.submitted[-1]["stop"]) == Decimal("0.64415")


def test_zero_fill_pauses_only_after_terminal_reconciliation(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    entry = enter(engine, arm(engine, run))
    completed(engine, entry, "ApiCancelled", "0")
    assert engine.store.get("reservation", entry["id"])["active"]
    reconcile_proof(engine)
    engine._fx_sync(engine.store.get("run", run["id"]))
    assert not engine.store.get("run", run["id"])["armed"]
    assert not engine.store.get("reservation", entry["id"])["active"]
    assert len(engine.broker.submitted) == 1


def test_new_authorization_uses_latest_entry_and_never_reuses_old_exit_intent(
    tmp_path, monkeypatch
):
    engine, run = fixture(tmp_path, monkeypatch)
    first = enter(engine, arm(engine, run))
    completed(engine, first, "ApiCancelled", "0")
    reconcile_proof(engine)
    engine._fx_sync(engine.store.get("run", run["id"]))
    engine._fx_request_exit(engine.store.get("run", run["id"]), "Old completed attempt")
    engine.store.put("exit_request", run["id"], {})
    fresh = arm(engine, engine.store.get("run", run["id"]), "b" * 32)
    second = enter(engine, fresh)
    assert second["id"] != first["id"]
    fill(engine, second, "10000", identity="new.1")
    assert engine.store.get("fx_protection", run["id"])["entry_id"] == second["id"]
    assert not engine.store.get("exit_request", run["id"])
    assert len(engine.broker.submitted) == 2
