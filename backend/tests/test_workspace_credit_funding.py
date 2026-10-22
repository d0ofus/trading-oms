from decimal import Decimal

import pytest
from test_workspace_fx_execution import fixture, signal

from trading_oms_backend.workspace.credit import CreditPending
from trading_oms_backend.workspace.credit_policy import POLICY
from trading_oms_backend.workspace.store import Conflict, now


def new_run(tmp_path, monkeypatch):
    engine, old = fixture(tmp_path, monkeypatch)
    c = engine.fx_compatibility(
        old["strategy_id"], 1, old["conid"], "locally_monitored", funding_policy=POLICY
    )
    run = engine.create_run(
        old["strategy_id"],
        1,
        old["conid"],
        {"quantity": "25000"},
        "locally_monitored",
        c["plan"]["hash"],
        "fx",
        POLICY,
    )
    engine.currency_facts.update(
        {
            (tag, "USD"): {"value": value, "received_at": now()}
            for tag, value in {
                "AvailableFunds": "100000",
                "ExcessLiquidity": "100000",
                "EquityWithLoanValue": "100000",
                "InitMarginReq": "0",
                "MaintMarginReq": "0",
            }.items()
        }
    )
    engine.credit_sent = []
    engine.broker.preview_credit = lambda r: engine.credit_sent.append(r)
    return engine, run


def funding(engine, run):
    return engine._fx_funding(run["binding"]["execution_plan"], run["binding"]["sizing"])


def test_new_binding_uses_cash_without_a_credit_preview(tmp_path, monkeypatch):
    engine, run = new_run(tmp_path, monkeypatch)
    reserve = funding(engine, run)
    assert reserve["funding_mode"] == "cash"
    assert reserve["funding_policy"] == POLICY
    assert not engine.credit_sent


@pytest.mark.parametrize("unavailable", [None, "NaN", "1.7976931348623157e308"])
def test_cash_funding_does_not_require_unused_margin_fields(tmp_path, monkeypatch, unavailable):
    engine, run = new_run(tmp_path, monkeypatch)
    for tag in ("ExcessLiquidity", "EquityWithLoanValue", "InitMarginReq", "MaintMarginReq"):
        if unavailable is None:
            engine.currency_facts.pop((tag, "USD"))
        else:
            engine.currency_facts[(tag, "USD")]["value"] = unavailable
    assert funding(engine, run)["funding_mode"] == "cash"
    engine.currency_facts[("SettledCash", "USD")]["value"] = "0"
    with pytest.raises(CreditPending, match="margin evidence"):
        funding(engine, run)
    assert not engine.credit_sent


def test_margin_requires_preview_and_readiness_reads_do_not_send_one(tmp_path, monkeypatch):
    engine, run = new_run(tmp_path, monkeypatch)
    for tag in ("CashBalance", "SettledCash"):
        engine.currency_facts[(tag, "USD")]["value"] = "0"
    with pytest.raises(CreditPending):
        funding(engine, run)
    assert not engine.credit_sent
    engine._credit_maintain()
    assert len(engine.credit_sent) == 1
    request = engine.credit_sent[0]
    engine._credit_observe(
        {
            "type": "credit_preview",
            "key": request["key"],
            "broker_id": request["broker_id"],
            "epoch": engine.broker.epoch,
            "status": "accepted",
            "received_at": now(),
            "initial_change": "500",
            "maintenance_change": "300",
            "initial_after": "500",
            "maintenance_after": "300",
            "equity_after": "100000",
        }
    )
    reserve = funding(engine, run)
    assert reserve["funding_mode"] == "margin"
    assert Decimal(reserve["credit_reserve"]) == Decimal(504)
    assert reserve["currency_reserves"] == {}
    assert not engine.broker.submitted
    engine._credit_maintain()
    assert len(engine.credit_sent) == 1


def test_broker_refusal_is_a_credit_block_not_an_incident(tmp_path, monkeypatch):
    engine, run = new_run(tmp_path, monkeypatch)
    engine.currency_facts[("SettledCash", "USD")]["value"] = "0"
    engine._credit_maintain()
    request = engine.credit_sent[0]
    engine._credit_observe(
        {
            "key": request["key"],
            "broker_id": request["broker_id"],
            "epoch": engine.broker.epoch,
            "status": "rejected",
            "received_at": now(),
        }
    )
    with pytest.raises(Conflict, match="Broker credit"):
        funding(engine, run)
    assert not engine.incidents.open()


def test_credit_evidence_is_invalidated_by_account_state_change(tmp_path, monkeypatch):
    engine, run = new_run(tmp_path, monkeypatch)
    engine.currency_facts[("SettledCash", "USD")]["value"] = "0"
    engine._credit_maintain()
    request = engine.credit_sent[0]
    engine._evidence_revision = 1
    engine._credit_observe(
        {
            "key": request["key"],
            "broker_id": request["broker_id"],
            "epoch": engine.broker.epoch,
            "status": "accepted",
            "received_at": now(),
        }
    )
    assert engine.store.get("credit_evidence", request["key"])["status"] == "pending"
    with pytest.raises(CreditPending):
        funding(engine, run)


def test_credit_reservations_serialize_competing_intents(tmp_path, monkeypatch):
    from trading_oms_backend.workspace.credit import validate_reservation

    engine, run = new_run(tmp_path, monkeypatch)
    reserve = funding(engine, run)
    reserve["credit_snapshot"].update(available="20000", excess="20000")
    first = {**reserve, "active": True, "run_id": "another", "conid": 999}
    engine.store.put("reservation", "competing", first)
    with engine.store.transaction() as db, pytest.raises(Conflict, match="Concurrent"):
        validate_reservation(db, engine.store, reserve)


def test_margin_fx_entry_remains_paper_and_expected_debit_reconciles(tmp_path, monkeypatch):
    from test_workspace_fx_execution import fill

    engine, run = new_run(tmp_path, monkeypatch)
    for tag in ("CashBalance", "SettledCash"):
        engine.currency_facts[(tag, "USD")]["value"] = "0"
    engine._credit_maintain()
    request = engine.credit_sent[0]
    engine._credit_observe(
        {
            "key": request["key"],
            "broker_id": request["broker_id"],
            "status": "accepted",
            "received_at": now(),
            "initial_change": "500",
            "maintenance_change": "300",
            "initial_after": "500",
            "maintenance_after": "300",
            "equity_after": "100000",
        }
    )
    review = engine.arm_preview([run["id"]])
    engine.arm(
        [run["id"]],
        "e" * 32,
        review_fingerprint=review["review_fingerprint"],
        resume_policy=review["resume_policy"],
        review_instance=engine.process_identity,
        fx_policy_revision="idealpro_funded_fx_v1",
        funding_policy_acknowledged=POLICY,
        execution_plan_revisions={run["id"]: run["binding"]["execution_plan"]["hash"]},
        local_protection_acknowledged=True,
    )
    engine._fx_enter(
        engine.store.get("run", run["id"]),
        signal(),
        "fixture",
    )
    assert len(engine.broker.submitted) == 1
    order = engine.store.orders()[0]
    fill(engine, order)
    engine.store.put("commission", "fx.1", {"amount": "2", "currency": "USD"})
    engine.currency_facts[("CashBalance", "USD")].update(value="-16254.5", received_at=now())
    engine.currency_facts[("CashBalance", "AUD")].update(value="26000", received_at=now())
    assert not any(
        "cannot cover" in issue or "differs" in issue for issue in engine._fx_cash_issues()
    )
    engine.currency_facts[("CashBalance", "USD")]["value"] = "-17000"
    assert any("differs" in issue for issue in engine._fx_cash_issues())


def test_preview_pacing_survives_restart_and_late_timeout_is_ignored(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    engine, run = new_run(tmp_path, monkeypatch)
    engine.currency_facts[("SettledCash", "USD")]["value"] = "0"
    engine._credit_maintain()
    request = engine.credit_sent[0]
    engine._credit_next_request = 0
    assert not engine._claim_credit_slot()
    item = engine.store.get("credit_evidence", request["key"])
    item["requested_at"] = (datetime.now(UTC) - timedelta(seconds=31)).isoformat()
    engine.store.put("credit_evidence", request["key"], item)
    engine._credit_maintain()
    assert engine.store.get("credit_evidence", request["key"])["status"] == "expired"
    engine._credit_observe(
        {
            "key": request["key"],
            "broker_id": request["broker_id"],
            "status": "accepted",
            "received_at": now(),
        }
    )
    with pytest.raises(CreditPending):
        funding(engine, run)
    assert len(engine.credit_sent) == 1


def test_credit_queue_does_not_starve_other_runs_or_refresh_idle_runs(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    engine, run = new_run(tmp_path, monkeypatch)
    plan = run["binding"]["execution_plan"]
    engine.currency_facts[("SettledCash", "USD")]["value"] = "0"
    other = engine.create_run(
        run["strategy_id"],
        1,
        run["conid"],
        {"quantity": "30000"},
        "locally_monitored",
        plan["hash"],
        "fx",
        POLICY,
    )
    engine._credit_maintain()
    prior = engine.credit_sent[0]
    past = (datetime.now(UTC) - timedelta(seconds=61)).isoformat()
    engine.store.put("credit_evidence", prior["key"], {**prior, "requested_at": past})
    engine.store.put("workspace", "credit_pacing", {"requested_at": past})
    engine._credit_next_request = 0
    engine._credit_maintain()
    assert engine.credit_sent[0]["key"] != engine.credit_sent[1]["key"]
    for item in (run, other):
        item.update(created_at=past)
        engine.store.put("run", item["id"], item)
    engine._credit_next_request = 0
    engine.store.put("workspace", "credit_pacing", {"requested_at": past})
    engine._credit_maintain()
    assert len(engine.credit_sent) == 2


def test_reflected_margin_is_not_reserved_twice_but_exit_fees_remain():
    from trading_oms_backend.workspace.credit import pending_credit, pending_currency

    reservations = [
        {
            "reservation_id": "known",
            "credit_reserve": "504",
            "maintenance_reserve": "304",
            "fee_reserve_usd": "4",
            "currency_reserves": {"USD": "20000"},
            "credit_fee_currencies": {"USD": "4"},
        }
    ]
    assert pending_credit(reservations, set()) == 504
    assert pending_credit(reservations, {"known"}) == 4
    assert pending_currency(reservations, {"known"}, "USD") == 4


@pytest.mark.parametrize("template", range(4))
@pytest.mark.parametrize("currency", ["HKD", "AUD"])
@pytest.mark.parametrize("policy", [POLICY, "paper_buying_power_v1"])
def test_all_stock_templates_share_margin_evidence(
    tmp_path, monkeypatch, template, currency, policy
):
    from test_workspace_stock_execution import fixture as stock_fixture

    engine, old, published = stock_fixture(tmp_path, monkeypatch, template)
    if currency == "AUD":
        contract = engine.contracts[old["conid"]]
        contract.update(
            symbol="SYNTHETIC",
            currency="AUD",
            routing_exchange="ASX",
            primary_exchange="ASX",
            exchange="ASX",
            time_zone="Australia/Sydney",
        )
        contract["stock_rules"].update(calendar="XASX", currency="AUD")
        engine.fx_quotes[("AUD", "USD")] = {
            "base": "AUD",
            "quote": "USD",
            "bid": "0.65",
            "ask": "0.6501",
            "received_at": now(),
            "live": True,
        }
    engine.account_base_currency = "USD"
    engine.currency_facts.update(
        {
            (tag, "USD"): {"value": value, "received_at": now()}
            for tag, value in {
                "AvailableFunds": "10000",
                "BuyingPower": "100000",
                "ExcessLiquidity": "10000",
                "EquityWithLoanValue": "10000",
                "InitMarginReq": "0",
                "MaintMarginReq": "0",
            }.items()
        }
    )
    engine.currency_facts[("SettledCash", "HKD")]["value"] = "0"
    for quote in engine.quotes[old["conid"]].values():
        quote["price"] = "2" if currency == "AUD" else "10"
    c = engine.stock_compatibility(old["strategy_id"], 1, old["conid"], funding_policy=policy)
    run = engine.create_run(
        old["strategy_id"],
        1,
        old["conid"],
        execution_plan_revision=c["plan"]["hash"],
        funding_policy=policy,
    )
    run["limits"] = old["limits"]
    sent = []
    engine.broker.preview_credit = lambda r: sent.append(r)
    price = Decimal(2 if currency == "AUD" else 10)
    branches = [(price, price * Decimal("0.99"))]
    if engine._paired_run(run):
        branches.append((price * Decimal("0.98"), price * Decimal("0.99")))
    if policy == "paper_buying_power_v1":
        quantity, reserve = engine._stock_size(run, branches)
        assert quantity > 0 and reserve["funding_mode"] == "broker_decision"
        assert Decimal(reserve["buying_power_allocation"]) == (
            Decimal(reserve["notional"]) + Decimal(reserve["fee_reserve_usd"])
        )
        assert reserve["credit_keys"] == [] and not sent
        assert engine.store.version(old["strategy_id"], 1) == published
        return
    # Test the shared funding boundary independently of each template's signal.
    # Preview dispatch remains a background operation; reads only collect here.
    engine._credit_collecting = True
    for _ in branches:
        with pytest.raises(CreditPending):
            engine._stock_size(run, branches)
        demand = next(reversed(engine._credit_demands.values()))
        item = {**demand, "status": "pending", "broker_id": 101 + len(sent)}
        engine.store.put("credit_evidence", item["key"], item)
        sent.append(item)
        engine._credit_observe(
            {
                "key": item["key"],
                "broker_id": item["broker_id"],
                "status": "accepted",
                "received_at": now(),
                "initial_change": "100",
                "maintenance_change": "80",
                "initial_after": "100",
                "maintenance_after": "80",
                "equity_after": "10000",
            }
        )
    quantity, reserve = engine._stock_size(run, branches)
    assert quantity > 0
    assert reserve["funding_mode"] == "margin"
    assert Decimal(reserve["credit_reserve"]) < Decimal(reserve["notional"])
    assert not engine.broker.submitted
    assert engine.store.version(old["strategy_id"], 1) == published
