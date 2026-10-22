"""Paper account capacity and visible signal outcomes; no real broker connection."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_workspace_fx_execution import fixture, signal

from trading_oms_backend.workspace.credit import CreditPending, validate_reservation
from trading_oms_backend.workspace.store import Conflict, now

POLICY = "paper_buying_power_v1"


def setup(tmp_path, monkeypatch, quantity="0.01"):
    engine, old = fixture(tmp_path, monkeypatch)
    contract = engine.contracts[old["conid"]]
    contract.update(min_size="0.01", size_increment="0.01")
    compatible = engine.fx_compatibility(
        old["strategy_id"], 1, old["conid"], "broker_held", funding_policy=POLICY
    )
    run = engine.create_run(
        old["strategy_id"],
        1,
        old["conid"],
        {"quantity": quantity},
        "broker_held",
        compatible["plan"]["hash"],
        "fx",
        POLICY,
    )
    for tag, value in {
        "BuyingPower": "100000",
        "AvailableFunds": "10",
        "ExcessLiquidity": "10",
        "EquityWithLoanValue": "100000",
        "InitMarginReq": "0",
        "MaintMarginReq": "0",
    }.items():
        engine.currency_facts[(tag, "USD")] = {"value": value, "received_at": now()}
    engine.credit_sent = []
    engine.broker.preview_credit = lambda r: engine.credit_sent.append(r)
    return engine, run


def funding(engine, run):
    return engine._fx_funding(run["binding"]["execution_plan"], run["binding"]["sizing"])


def authorize(engine, run):
    preview = engine.arm_preview([run["id"]])
    assert preview["eligible"], [c for c in preview["checks"] if not c["passed"]]
    engine.arm(
        [run["id"]],
        "b" * 32,
        review_fingerprint=preview["review_fingerprint"],
        fx_policy_revision=run["binding"]["execution_plan"]["policy"],
        resume_policy=preview["resume_policy"],
        review_instance=engine.process_identity,
        funding_policy_acknowledged=POLICY,
        execution_plan_revisions={run["id"]: run["binding"]["execution_plan"]["hash"]},
    )
    return engine.store.get("run", run["id"])


@pytest.mark.parametrize("cash", [None, "0", "-100"])
def test_native_currency_cash_does_not_gate_paper_buying_power(tmp_path, monkeypatch, cash):
    engine, run = setup(tmp_path, monkeypatch)
    for currency in ("AUD", "USD"):
        for tag in ("CashBalance", "SettledCash"):
            if cash is None:
                engine.currency_facts.pop((tag, currency), None)
            else:
                engine.currency_facts[(tag, currency)]["value"] = cash
    reserve = funding(engine, run)
    assert reserve["funding_mode"] == "broker_decision"
    assert reserve["funding_policy"] == POLICY
    assert Decimal(reserve["buying_power_allocation"]) == (
        Decimal(reserve["notional"]) + Decimal(reserve["fee_reserve_usd"])
    )
    engine._credit_maintain()
    assert not engine.credit_sent


def test_notional_may_exceed_available_funds_without_preview(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    sizing = {**run["binding"]["sizing"], "quantity": "25000"}
    result = engine._fx_funding(run["binding"]["execution_plan"], sizing)
    assert Decimal(result["notional"]) > 10
    assert Decimal(result["buying_power_allocation"]) < 100000


@pytest.mark.parametrize(
    "tag,value", [("BuyingPower", "1"), ("AvailableFunds", "0"), ("ExcessLiquidity", "-1")]
)
def test_real_account_capacity_blocks_are_specific(tmp_path, monkeypatch, tag, value):
    engine, run = setup(tmp_path, monkeypatch)
    engine.currency_facts[(tag, "USD")]["value"] = value
    with pytest.raises(Conflict, match="buying power|headroom"):
        funding(engine, run)
    assert not engine.credit_sent


def test_missing_and_stale_buying_power_are_checking(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    engine.currency_facts[("BuyingPower", "USD")]["received_at"] = (
        datetime.now(UTC) - timedelta(seconds=31)
    ).isoformat()
    with pytest.raises(CreditPending, match="BuyingPower"):
        funding(engine, run)


def test_transactional_buying_power_allocation_and_reflection(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    reserve = funding(engine, run)
    reserve["credit_snapshot"]["buying_power"] = "6"
    engine.store.put("reservation", "other", {**reserve, "active": True, "run_id": "other"})
    with engine.store.transaction() as db, pytest.raises(Conflict, match="buying power"):
        validate_reservation(db, engine.store, reserve)
    # Reflection removes the entry allocation, while outstanding fees remain allocated.
    reserve["credit_snapshot"]["reflected_reservations"] = ["other"]
    reserve["credit_snapshot"]["buying_power"] = "9"
    with engine.store.transaction() as db:
        validate_reservation(db, engine.store, reserve)


def test_fx_signal_detection_precedes_capacity_failure(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    engine.currency_facts[("BuyingPower", "USD")]["value"] = "1"
    trigger = signal()
    engine._fx_enter(run, trigger, "captured")
    engine._fx_enter(run, trigger, "captured")
    events = engine.store.events(limit=1000)
    assert len([e for e in events if e["type"] == "signal.detected"]) == 1
    outcome = engine.store.get("signal_outcome", run["id"])
    assert outcome["state"] == "blocked" and "buying power" in outcome["detail"]
    assert not engine.store.orders() and not engine.broker.submitted
    assert engine.store.get("run", run["id"])["entries"] == 0


def test_fx_entry_without_preview_reports_submitted_exactly_once(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    trigger = signal()
    engine._fx_enter(run, trigger, "captured")
    engine._fx_enter(run, trigger, "captured")
    assert len(engine.broker.submitted) == 1 and not engine.credit_sent
    assert engine.broker.submitted[0]["quantity"] == "0.01"
    assert engine.store.get("signal_outcome", run["id"])["state"] == "submitted"


def test_expired_signal_is_visible_and_never_submitted(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    trigger = {**signal(), "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
    engine._fx_enter(run, trigger, "captured")
    assert engine.store.get("signal_outcome", run["id"])["state"] == "expired"
    assert not engine.broker.submitted


def test_captured_crossing_reaches_one_paper_submission(tmp_path, monkeypatch):
    import sys

    from test_workspace_fx_data import streams
    from test_workspace_fx_timing import tick
    from test_workspace_health import healthy_watchdog

    from trading_oms_backend.workspace.fx_sessions import FXSession

    start = datetime.now(UTC).replace(second=0, microsecond=0)

    class Frozen(datetime):
        current = start - timedelta(seconds=10)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    for name, module in list(sys.modules.items()):
        if (
            name.startswith("trading_oms_backend.workspace.")
            and getattr(module, "datetime", None) is datetime
        ):
            monkeypatch.setattr(module, "datetime", Frozen)
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    streams(engine, run["conid"])
    monkeypatch.setattr(FXSession, "interval_start", lambda *args: start - timedelta(hours=1))
    for second in [*range(0, 61, 5), 61]:
        Frozen.current = start + timedelta(seconds=second)
        healthy_watchdog(engine)
        for item in engine.currency_facts.values():
            item["received_at"] = now()
        for kind in ("fx_bidask", "fx_midpoint"):
            event = tick(
                engine,
                run,
                Frozen.current,
                Frozen.current,
                kind,
                bid="0.702590",
                ask="0.702600",
                price="0.702595" if second == 61 else "0.702585",
            )
            engine._fx_data_observation(event)
        if second <= 60:
            assert not engine.broker.submitted  # Strict equality never triggers.
    assert len(engine.broker.submitted) == 1 and not engine.credit_sent
    order = engine.broker.submitted[0]
    assert order["entry_type"] == "MKT" and order["quantity"] == "0.01"
    assert order["signal"]["high"] == "0.702585"
    assert order["signal"]["price"] == "0.702595"
    engine._fx_data_observation(event)
    assert len(engine.broker.submitted) == 1
    outcome = engine.store.get("signal_outcome", run["id"])
    assert outcome["state"] == "submitted" and outcome["order_id"]
    progress = engine._signal_run_view(engine.store.get("run", run["id"]))["signal_progress"]
    assert progress["reference_high"] == "0.702585" and progress["above_high"]


def test_uncertain_submission_keeps_allocation_and_durable_signal_link(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)

    def fail(intent):
        record = engine.store.get("signal_outcome", run["id"])
        assert record["order_id"] == intent["id"]
        raise OSError("synthetic transport interruption")

    engine.broker.submit_fx = fail
    engine._fx_enter(run, signal(), "capture")
    order = engine.store.orders()[0]
    assert order["state"] == "unknown"
    assert engine.store.get("reservation", order["id"])["active"]
    assert engine.store.get("signal_outcome", run["id"])["state"] == "uncertain"
    assert engine._buying_power_reflected() == []
    engine._fx_enter(run, signal(), "capture")
    assert len(engine.store.orders()) == 1


def test_reserved_signal_is_not_reported_as_transmitted(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    monkeypatch.setattr(engine, "_fx_transmit", lambda *args: None)
    engine._fx_enter(run, signal(), "capture")
    engine._signal_maintain()
    outcome = engine.store.get("signal_outcome", run["id"])
    assert outcome["state"] == "checking" and "awaiting dispatch" in outcome["detail"]
    assert not engine.broker.submitted


def test_partial_fill_protection_and_debits_keep_entry_outcome(tmp_path, monkeypatch):
    from test_workspace_fx_execution import fill

    engine, run = setup(tmp_path, monkeypatch, quantity="0.02")
    for tag in ("CashBalance", "SettledCash"):
        engine.currency_facts[(tag, "USD")]["value"] = "0"
    run = authorize(engine, run)
    engine._fx_enter(run, signal(), "capture")
    order = engine.store.orders()[0]
    fill(engine, order, "0.01")
    engine._signal_maintain()
    assert engine.store.get("signal_outcome", run["id"])["state"] == "partially_filled"
    assert engine.broker.submitted[-1]["purpose"] == "protection"
    assert engine.broker.submitted[-1]["quantity"] == "0.01"
    engine.store.put("commission", "fx.1", {"amount": "2", "currency": "USD"})
    engine.currency_facts[("CashBalance", "USD")].update(value="-2.006501", received_at=now())
    engine.currency_facts[("CashBalance", "AUD")].update(value="1000.01", received_at=now())
    assert not any(
        "cannot cover" in issue or "differs" in issue for issue in engine._fx_cash_issues()
    )
    assert "USD" in engine._credit_debit_currencies()


def test_existing_base_debit_does_not_block_owned_fx_exit_or_protection(tmp_path, monkeypatch):
    from test_workspace_fx_execution import fill

    engine, run = setup(tmp_path, monkeypatch)
    for tag in ("CashBalance", "SettledCash"):
        engine.currency_facts[(tag, "AUD")]["value"] = "-100"
    run = authorize(engine, run)
    engine._fx_enter(run, signal(), "capture")
    order = engine.store.orders()[0]
    fill(engine, order, "0.01")
    engine.store.put("commission", "fx.1", {"amount": "2", "currency": "USD"})
    engine.currency_facts[("CashBalance", "AUD")].update(value="-99.99", received_at=now())
    engine.currency_facts[("CashBalance", "USD")].update(value="99997.993499", received_at=now())
    assert engine._fx_ownership_agrees(run)
    assert not engine._fx_cash_issues()
    assert engine.broker.submitted[-1]["purpose"] == "protection"
    engine.currency_facts[("CashBalance", "AUD")]["value"] = "-105"
    assert not engine._fx_ownership_agrees(run)
    assert any("differs" in issue for issue in engine._fx_cash_issues())


def test_old_credit_preview_replacement_is_not_reused(tmp_path, monkeypatch):
    from test_workspace_credit_funding import new_run
    from test_workspace_policy_replacement import request

    engine, old = new_run(tmp_path, monkeypatch)
    source_hash = old["binding"]["hash"]
    engine.store.put(
        "policy_replacement",
        old["id"] + ":broker_credit_v1",
        {
            "replacement_id": "old-target",
            "source_binding_hash": source_hash,
        },
    )
    result = engine.policy_replacement(**request(old))
    new = engine.store.get("run", result["review_ids"][0])
    assert new["binding"]["execution_plan"]["funding_policy"] == POLICY
    assert new["binding"]["sizing"] == old["binding"]["sizing"]
    assert engine.store.get("run", old["id"])["binding"]["hash"] == source_hash
    assert not new["armed"] and not engine.broker.submitted


def test_capacity_transfers_only_after_verified_post_dispatch_snapshot(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    engine._fx_enter(run, signal(), "capture")
    order = engine.store.orders()[0]
    engine.store.transition(order["id"], "working", {})
    engine.broker_orders[order["broker_id"]] = {"own_account": True, "status": "Submitted"}
    proof = {
        "ready": True,
        "instance": engine.process_identity,
        "epoch": engine.broker.epoch,
        "started_at": "2000-01-01T00:00:00+00:00",
        "completed_at": now(),
    }
    engine.reconciliation_evidence = proof
    assert engine._buying_power_reflected() == []
    proof["started_at"] = now()
    assert engine._buying_power_reflected() == [order["id"]]
    proof["epoch"] += 1
    assert engine._buying_power_reflected() == []


def test_actual_broker_rejection_is_visible_without_retry_or_early_release(tmp_path, monkeypatch):
    from test_workspace_rejections import reject

    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    engine._fx_enter(run, signal(), "capture")
    order = engine.store.orders()[0]
    reject(engine, order, "insufficient_funds")
    engine._signal_maintain()
    outcome = engine.store.get("signal_outcome", run["id"])
    assert outcome["state"] == "broker_rejected"
    assert outcome["rejection"]["code"] == 201
    assert outcome["rejection"]["category"] == "insufficient_funds"
    assert engine.store.get("reservation", order["id"])["active"]
    engine._fx_enter(run, signal(), "capture")
    assert len(engine.broker.submitted) == 1 and not engine.credit_sent


def test_snapshot_subscription_requests_and_retains_buying_power():
    from types import SimpleNamespace

    from trading_oms_backend.workspace.broker_snapshots import BrokerSnapshots

    broker = BrokerSnapshots()
    broker.reset_snapshots()
    broker._request_id, broker._request_kinds = 100, {}
    broker._accounts, broker.paper_context = ["synthetic"], True
    requests, events = [], []
    broker.client = SimpleNamespace(
        reqAccountSummary=lambda *args: requests.append(args),
        reqAccountUpdatesMulti=lambda *args: None,
    )
    broker.emit = lambda kind, **payload: events.append({"type": kind, **payload})
    broker._request_accounts("snapshot")
    request_id, _, tags = requests[0]
    assert "BuyingPower" in tags.split(",")
    broker.account_snapshot_fact(request_id, "synthetic", "BuyingPower", "100000", "USD")
    assert events[-1]["tag"] == "BuyingPower"
    assert events[-1]["reconciliation_id"] == "snapshot"


def test_account_valuation_currency_and_concurrent_stock_allocation(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    engine.account_base_currency = "AUD"
    for tag, value in {"BuyingPower": "100", "AvailableFunds": "1", "ExcessLiquidity": "1"}.items():
        engine.currency_facts[(tag, "AUD")] = {"value": value, "received_at": now()}
    engine.fx_quotes[("AUD", "USD")] = {
        "base": "AUD",
        "quote": "USD",
        "bid": "0.65",
        "ask": "0.6501",
        "received_at": now(),
        "live": True,
    }
    reserve = funding(engine, run)
    assert reserve["allocation_currency"] == "AUD"
    assert Decimal(reserve["credit_snapshot"]["buying_power"]) == 65
    assert Decimal(reserve["buying_power_allocation_native"]) > 1
    engine.store.put(
        "reservation",
        "stock",
        {
            "run_id": "stock",
            "active": True,
            "funding_policy": POLICY,
            "notional": "63",
            "fee_reserve_usd": "1",
            "buying_power_allocation": "64",
        },
    )
    with pytest.raises(Conflict, match="buying power"):
        funding(engine, run)


def test_new_policy_adapter_and_authorization_require_current_terms(tmp_path, monkeypatch):
    from test_workspace_broker_credit import adapter

    engine, run = setup(tmp_path, monkeypatch)
    preview = engine.arm_preview([run["id"]])
    with pytest.raises(Conflict, match="funding terms"):
        engine.arm(
            [run["id"]],
            "c" * 32,
            review_fingerprint=preview["review_fingerprint"],
            resume_policy=preview["resume_policy"],
            review_instance=engine.process_identity,
            funding_policy_acknowledged="broker_credit_v1",
        )
    gateway = adapter()
    gateway.epoch = engine.broker.epoch
    intent = {"valuation": funding(engine, run), "quantity": "0.01"}
    gateway.validate_credit_intent(run["binding"]["execution_plan"], intent)
    assert not gateway.sent
    intent["valuation"]["buying_power_allocation"] = "0"
    with pytest.raises(Conflict, match="allocation"):
        gateway.validate_credit_intent(run["binding"]["execution_plan"], intent)
