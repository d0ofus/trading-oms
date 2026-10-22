"""Paired stop entries: deterministic risk, cancellation and signed protection."""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_workspace_crypto import DataDouble
from test_workspace_health import healthy_watchdog

from trading_oms_backend.workspace.graph import GraphError, compile_graph, crypto_copy, templates
from trading_oms_backend.workspace.oca import pair_prices, size_pair
from trading_oms_backend.workspace.store import Conflict, Store, now


@pytest.fixture(autouse=True)
def deterministic_weekend(monkeypatch):
    import trading_oms_backend.workspace.broker_oca as broker_oca
    import trading_oms_backend.workspace.data_views as data_views
    import trading_oms_backend.workspace.engine as engine
    import trading_oms_backend.workspace.oca_engine as oca_engine
    import trading_oms_backend.workspace.simulator as sim
    import trading_oms_backend.workspace.store as store

    class Clock(datetime):
        stamp = datetime(2026, 9, 20, 12, 10, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.stamp.astimezone(tz) if tz else cls.stamp.replace(tzinfo=None)

    for module in (broker_oca, data_views, engine, oca_engine, sim, store):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setitem(globals(), "datetime", Clock)
    return Clock


def paired_engine(tmp_path):
    from trading_oms_backend.workspace.engine import Engine
    from trading_oms_backend.workspace.simulator import CryptoSimulator

    store = Store(tmp_path)
    engine = Engine(
        store,
        broker_factory=lambda q: CryptoSimulator(q, store, data_factory=DataDouble),
        environment="live_crypto_simulation",
    )
    contract = {
        "conid": 1,
        "symbol": "BTC",
        "sec_type": "CRYPTO",
        "currency": "USD",
        "exchange": "PAXOS",
        "market_rule": 1,
        "min_size": "0.0001",
        "size_increment": "0.0001",
    }
    engine.contracts[1] = contract
    engine.broker.set_contract(contract)
    engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
    engine.data[1] = {
        "live": True,
        "warm": True,
        "price": "100",
        "received_at": now(),
        "source_at": now(),
    }
    engine.quotes[1] = {
        side: {"price": price, "received_at": now()}
        for side, price in (("bid", "99.99"), ("ask", "100.01"))
    }
    engine.facts = {"NetLiquidation": "10000", "AvailableFunds": "10000", "GrossPositionValue": "0"}
    engine.connected = engine.attested = engine.reconciled = engine.clock_ok = (
        engine.position_agreement
    ) = True
    engine.reconciled_at = time.monotonic()
    engine.server_version = 220
    engine.next_id = 100
    doc = template(True)
    doc["settings"].update(sizing="fixed", quantity="1")
    draft = store.save_draft(None, "OCA", doc, 0)
    published = store.publish(draft["id"], draft["revision"])
    run = {
        "id": "run",
        "strategy_id": draft["id"],
        "version": published["version"],
        "symbol": "BTC",
        "conid": 1,
        "armed": True,
        "state": "armed",
        "position": "0",
        "entries": 0,
        "authorized_at": (datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
        "authorization_id": "authorization",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "limits": {"quantity": "10", "planned_stop_risk": "10", "notional": "1000"},
    }
    store.put("run", "run", run)
    candidate = {
        "candle": (
            datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
        ).isoformat(),
        "high": "101",
        "low": "99",
        "expires_at": (datetime.now(UTC) + timedelta(seconds=45)).isoformat(),
        "capture": "fixture",
        "authorization_id": "authorization",
    }
    healthy_watchdog(engine)
    engine._oca_submit(run, candidate)
    drain(engine)
    engine._oca_maintain()
    engine.broker.on_market({"type": "data_type", "conid": 1, "live": True})
    return engine


def drain(engine):
    while not engine.observations.empty():
        engine.observe(engine.observations.get_nowait())


def market(engine, kind="quote", **payload):
    engine.broker.data.sequence += 1
    event = {
        "type": kind,
        "conid": 1,
        "sequence": engine.broker.data.sequence,
        "timestamp": datetime.now(UTC).timestamp(),
        **payload,
    }
    # Exercise the execution adapter independently of constructing an entire live minute.
    engine.broker.on_market(event)
    drain(engine)
    engine._oca_maintain()
    drain(engine)


def reconcile(engine):
    engine.begin_reconcile()
    drain(engine)


def template(crypto=False):
    document = next(t["document"] for t in templates() if t["id"] == "previous-minute-oca")
    return crypto_copy(document) if crypto else document


@pytest.mark.parametrize("crypto", [False, True])
def test_paired_template_compiles_and_explains_both_directions(crypto):
    graph = compile_graph(template(crypto))
    assert graph.document["schema_version"] == 5
    assert graph.document["settings"]["timeframe"] == 60
    assert graph.document["settings"]["max_entries"] == 1
    assert len([n for n in graph.ordered if n["kind"] == "paired_stop"]) == 1
    assert "1%" in str(graph.explain())
    assert "short" in str(graph.explain()).lower()


def test_paired_template_cannot_be_disguised_as_legacy_or_change_lifetime():
    doc = template()
    doc["schema_version"] = 3
    with pytest.raises(GraphError):
        compile_graph(doc)
    doc = template()
    doc["settings"]["timeframe"] = 5
    with pytest.raises(GraphError):
        compile_graph(doc)


def test_protection_rounds_toward_actual_entry_and_trigger_levels_outwards():
    rules = [{"low": "0", "increment": "0.01"}]
    prices = pair_prices(Decimal("100.123"), Decimal("98.127"), rules)
    assert prices == {
        "long_entry": "100.13",
        "short_entry": "98.12",
        "long_stop": "99.13",
        "short_stop": "99.10",
    }


def test_combined_risk_and_notional_cap_both_legs():
    settings = compile_graph(template(True)).document["settings"]
    profile = {"quantity": "10", "planned_stop_risk": "10", "notional": "1000"}
    prices = pair_prices(Decimal("100000"), Decimal("99000"), [{"low": "0", "increment": "0.01"}])
    quantity, reservation = size_pair(
        settings,
        profile,
        prices,
        Decimal("10000"),
        {"size_increment": "0.0001", "min_size": "0.0001"},
    )
    assert quantity == Decimal("0.0050")
    assert Decimal(reservation["notional"]) == Decimal("995")
    assert Decimal(reservation["risk"]) == Decimal("9.95")
    with pytest.raises(Conflict):
        size_pair(
            settings,
            profile,
            prices,
            Decimal("1"),
            {"size_increment": "0.0001", "min_size": "0.0001"},
        )


@pytest.mark.parametrize("direction", ["long", "short"])
def test_pair_first_fill_protection_exit_and_one_trade_pause(tmp_path, direction):
    engine = paired_engine(tmp_path)
    order = engine.store.orders()[0]
    ids = order["payload"]["leg_ids"]
    market(engine, side="bid", price="99.99")
    market(engine, side="ask", price="100.01")
    assert not engine.broker.state["executions"]
    trigger, fill, side = (
        ("101", "101.20", "ask") if direction == "long" else ("99", "98.80", "bid")
    )
    market(engine, "tick", price=trigger, size="1")
    assert not engine.broker.state["executions"]
    market(engine, side=side, price=fill)
    assert len(engine.broker.state["executions"]) == 1
    opposite = "short" if direction == "long" else "long"
    assert engine.broker.state["orders"][str(ids[opposite + "_entry"])]["status"] == "Cancelled"
    assert engine.broker.state["orders"][str(ids[opposite + "_stop"])]["status"] == "Cancelled"
    stop = "100.19" if direction == "long" else "99.78"
    assert engine.broker.state["orders"][str(ids[direction + "_stop"])]["stop"] == stop
    reconcile(engine)
    assert engine.reconciled, engine.last_fault
    assert engine.owned()["run"]["protected"]
    assert engine.store.get("run", "run")["entries"] == 1
    market(engine, "tick", price=stop, size="1")
    market(
        engine,
        side="bid" if direction == "long" else "ask",
        price="100" if direction == "long" else "100.10",
    )
    reconcile(engine)
    assert engine.reconciled, engine.last_fault
    assert engine.owned()["run"]["quantity"] == 0
    assert not engine.store.get("run", "run")["armed"]
    assert engine.store.get("oca_group", order["id"])["state"] == "complete"
    engine.store.verify()


def test_short_proceeds_cannot_increase_buying_power_and_cover_is_risk_reducing(tmp_path):
    engine = paired_engine(tmp_path)
    market(engine, side="ask", price="100.01")
    market(engine, "tick", price="99", size="1")
    market(engine, side="bid", price="99")
    facts, _, _ = engine.broker.account_values()
    assert Decimal(engine.broker.state["cash"]) == Decimal("10099")
    assert Decimal(facts["AvailableFunds"]) < Decimal("9901")
    assert Decimal(facts["GrossPositionValue"]) == Decimal("100.01")
    reconcile(engine)
    assert engine.reconciled, engine.last_fault
    engine.close_position("run")
    drain(engine)
    cover = next(o for o in engine.store.orders() if o["payload"].get("purpose") == "exit")
    assert cover["payload"]["action"] == "BUY"
    market(engine, side="ask", price="100")
    reconcile(engine)
    assert engine.owned()["run"]["quantity"] == 0
    assert not engine.store.get("run", "run")["armed"]


def test_id_allocator_reserves_all_four_legs_and_preview_ids(tmp_path):
    engine = paired_engine(tmp_path)
    first = engine.store.orders()[0]
    extra = engine.store.reserve_order("e" * 32, {"purpose": "exit"}, "run", 100)
    assert extra["broker_id"] > max(first["payload"]["leg_ids"].values())
    assert engine.store.allocate_broker_id(100) > extra["broker_id"] + 2


def test_cancel_without_fill_keeps_trade_count_and_requires_all_acknowledgments(tmp_path):
    engine = paired_engine(tmp_path)
    order = engine.store.orders()[0]
    engine.cancel_entry(order["id"])
    assert engine.store.get("oca_group", order["id"])["state"] == "cancelling"
    drain(engine)
    reconcile(engine)
    assert engine.reconciled, engine.last_fault
    assert engine.store.get("oca_group", order["id"])["state"] == "cancelled"
    assert engine.store.get("run", "run")["entries"] == 0
    assert not engine.store.get("reservation", order["id"])["active"]


def test_duplicate_fill_does_not_count_twice_or_reenter(tmp_path):
    engine = paired_engine(tmp_path)
    market(engine, side="bid", price="100")
    market(engine, "tick", price="101", size="1")
    market(engine, side="ask", price="101.10")
    execution = engine.broker.state["executions"][0]
    engine.observe({"type": "execution", **execution})
    engine._oca_maintain()
    assert engine.store.get("run", "run")["entries"] == 1
    assert engine.owned()["run"]["quantity"] == 1
    assert len(engine.store.orders()) == 1


def test_new_candle_waits_for_cancel_ack_and_fresh_reconciliation(tmp_path, deterministic_weekend):
    from trading_oms_backend.workspace.market import Candle

    engine = paired_engine(tmp_path)
    old = engine.store.orders()[0]
    delayed = []
    cancel = engine.broker.cancel
    engine.broker.cancel = lambda identity: delayed.append(identity)
    deterministic_weekend.stamp += timedelta(seconds=61)
    engine.data[1].update(received_at=now(), source_at=now())
    for quote in engine.quotes[1].values():
        quote["received_at"] = now()
    state = engine._runtime(engine.store.get("run", "run"))
    state["oca_live_since"] = (datetime.now(UTC) - timedelta(minutes=3)).isoformat()
    state["market"].closed.append(
        Candle(
            datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1),
            Decimal(100),
            Decimal(102),
            Decimal(98),
            Decimal(100),
            Decimal(10),
        )
    )
    engine._oca_candidate(engine.store.get("run", "run"), state, {"bar_closed": True}, "new-candle")
    assert len(delayed) == 2
    assert len(engine.store.orders()) == 1
    for broker_id in delayed:
        cancel(broker_id)
    drain(engine)
    engine._oca_maintain()
    assert len(engine.store.orders()) == 1  # Cancellation alone does not release reserved capacity.
    reconcile(engine)
    engine._oca_maintain()
    assert len(engine.store.orders()) == 2
    assert engine.store.get("run", "run")["entries"] == 0
    assert engine.store.get("oca_group", old["id"])["state"] == "cancelled"


def test_historical_or_partial_minute_does_not_create_candidate(tmp_path):
    from trading_oms_backend.workspace.market import Candle

    engine = paired_engine(tmp_path)
    state = engine._runtime(engine.store.get("run", "run"))
    state["market"].closed.append(
        Candle(
            datetime.now(UTC) - timedelta(minutes=10),
            Decimal(100),
            Decimal(102),
            Decimal(98),
            Decimal(100),
            Decimal(10),
        )
    )
    engine._oca_candidate(engine.store.get("run", "run"), state, {"bar_closed": True}, "history")
    assert engine.store.get("oca_candidate", "run") is None


@pytest.mark.parametrize("short", [False, True])
def test_restart_retains_signed_position_protection_and_disarms_entries(tmp_path, short):
    from trading_oms_backend.workspace.engine import Engine
    from trading_oms_backend.workspace.simulator import CryptoSimulator

    engine = paired_engine(tmp_path)
    market(engine, side="ask" if short else "bid", price="100")
    market(engine, "tick", price="99" if short else "101", size="1")
    market(engine, side="bid" if short else "ask", price="99" if short else "101")
    reconcile(engine)
    cash = engine.broker.state["cash"]
    restarted = Engine(
        engine.store,
        broker_factory=lambda q: CryptoSimulator(q, engine.store, data_factory=DataDouble),
        environment="live_crypto_simulation",
    )
    assert not restarted.store.get("run", "run")["armed"]
    assert restarted.requested_connection
    assert restarted.owned()["run"]["quantity"] == (-1 if short else 1)
    assert restarted.broker.state["cash"] == cash
    working = [o for o in restarted.broker.state["orders"].values() if o["status"] == "Submitted"]
    assert len(working) == 1 and working[0]["purpose"] == "protection"
    assert working[0]["action"] == ("BUY" if short else "SELL")


def test_emergency_and_disconnect_cancel_both_entry_directions(tmp_path):
    engine = paired_engine(tmp_path)
    engine._connection_lost("fixture disconnect")
    assert not engine.store.get("run", "run")["armed"]
    engine.connected = engine.attested = True
    engine._oca_maintain()
    drain(engine)
    assert all(o["status"] == "Cancelled" for o in engine.broker.state["orders"].values())


def test_partial_short_repair_waits_for_terminal_orders_and_agreement(tmp_path, monkeypatch):
    engine = paired_engine(tmp_path)
    order = engine.store.orders()[0]
    ids = order["payload"]["leg_ids"]
    engine.observe(
        {
            "type": "execution",
            "execution_id": "partial.01",
            "broker_id": ids["short_entry"],
            "client_id": engine.broker.client_id,
            "own_account": True,
            "conid": 1,
            "symbol": "BTC",
            "side": "SLD",
            "quantity": "0.5",
            "price": "98.80",
        }
    )
    engine._oca_sync(order)
    assert engine.owned()["run"]["quantity"] == Decimal("-0.5")
    repairs = []
    monkeypatch.setattr(engine.broker, "submit_protection", lambda intent: repairs.append(intent))
    group = engine.store.get("oca_group", order["id"])
    engine._oca_update_protection(engine.owned()["run"], order, group)
    assert not repairs
    for broker_id in ids.values():
        engine.broker_orders[broker_id] = {**engine._oca_observed(broker_id), "status": "Cancelled"}
    engine.position_agreement = True
    engine._oca_update_protection(engine.owned()["run"], order, group)
    assert len(repairs) == 1
    assert repairs[0]["action"] == "BUY"
    assert repairs[0]["quantity"] == "0.5"
    assert repairs[0]["stop"] == "99.78"
    engine._oca_update_protection(engine.owned()["run"], order, group)
    assert len(repairs) == 1  # An uncertain repair is never resent.


@pytest.mark.parametrize("early_event", [None, "fill", "rejection"])
def test_paper_pair_staging_preview_and_live_account_guards(tmp_path, early_event):
    import queue
    from types import SimpleNamespace

    from trading_oms_backend.workspace.broker import PaperGateway

    engine = paired_engine(tmp_path)
    intent = engine._pair_intent(engine.store.orders()[0])
    gateway = PaperGateway(queue.Queue())
    sent = []
    cancelled = []

    def submit(key, contract, order):
        sent.append(order)
        if early_event == "fill" and order.transmit and not order.whatIf:
            gateway._oca_filled[intent["id"]].add("long_entry")
        if early_event == "rejection" and not order.whatIf:
            gateway._oca_terminal.add(intent["leg_ids"]["long_entry"])

    gateway.client = SimpleNamespace(
        isConnected=lambda: True,
        placeOrder=submit,
        cancelOrder=lambda key, cancel: cancelled.append(key),
    )
    gateway._next_id = 100
    gateway._accounts = ("DU000000",)  # Synthetic paper-only fixture.
    gateway._contracts[1] = SimpleNamespace(conId=1, secType="STK", currency="USD")
    gateway.attest()
    with pytest.raises(ValueError, match="preview"):
        gateway.submit_pair(intent)
    preview = {"broker_id": 200, "conid": 1, "quantity": "1", "price": "99", "epoch": gateway.epoch}
    gateway.preview_short(preview)
    assert sent[-1].whatIf is True
    preview_state = SimpleNamespace(
        initMarginChange="100",
        maintMarginAfter="100",
        equityWithLoanAfter="10000",
        warningText="",
        status="PreSubmitted",
    )
    # Credit evidence must be bound to the exact account, instrument and short branch.
    preview_order = sent[-1]
    preview_order.action = "BUY"
    gateway._preview_observation(200, gateway._contracts[1], preview_order, preview_state)
    assert gateway._short_previews[200]["status"] == "rejected"
    preview_order.action = "SELL"
    gateway._preview_observation(200, gateway._contracts[1], preview_order, preview_state)
    assert gateway._short_previews[200]["status"] == "accepted"
    gateway._shortable[1] = {"quantity": "100", "at": now()}
    sent.clear()
    gateway.submit_pair(intent)
    expected_count = {None: 6, "fill": 5, "rejection": 4}[early_event]
    assert len(sent) == expected_count
    if early_event == "fill":
        assert cancelled == [intent["leg_ids"]["short_entry"]]
    if early_event == "rejection":
        assert cancelled == [intent["leg_ids"][side + "_entry"] for side in ("long", "short")]
        assert all(not order.transmit for order in sent)

    assert all(not order.transmit for order in sent[:4])
    assert [order.action for order in sent[:4]] == ["BUY", "SELL", "SELL", "BUY"]
    assert all(order.ocaType == 1 for order in (sent[0], sent[2]))
    assert sent[0].ocaGroup == sent[2].ocaGroup
    assert sent[1].ocaGroup != sent[0].ocaGroup != sent[3].ocaGroup
    assert sent[1].parentId == sent[0].orderId
    assert sent[3].parentId == sent[2].orderId
    assert all(not order.outsideRth and order.triggerMethod == 2 for order in sent)
    gateway._accounts = ("U000000",)
    for action in (gateway.submit_pair, gateway.preview_short):
        with pytest.raises(ValueError):
            action(intent)
    assert len(sent) == expected_count


def test_legacy_template_hashes_are_unchanged():
    assert [compile_graph(t["document"]).digest for t in templates()[:2]] == [
        "6d3b57ea51d653e938392d460678ef904e2e1ee271110c65bf4fec4efc6659dc",
        "5429444fc46299f6cab5f902183697174674ce29642eaba79dbfe9bf7fa6f4ff",
    ]


def test_pending_stop_amendment_keeps_prior_protection_and_never_resends(
    tmp_path, monkeypatch, deterministic_weekend
):
    engine = paired_engine(tmp_path)
    market(engine, side="bid", price="100")
    market(engine, "tick", price="101", size="1")
    market(engine, side="ask", price="101.20")
    order = engine.store.orders()[0]
    stop_id = order["payload"]["leg_ids"]["long_stop"]
    engine.broker.state["orders"][str(stop_id)]["stop"] = order["payload"]["prices"]["long_stop"]
    calls = []
    monkeypatch.setattr(
        engine.broker, "amend_protection", lambda intent, amendment: calls.append(amendment)
    )
    reconcile(engine)
    assert len(calls) == 1 and calls[0]["stop"] == "100.19"
    assert not engine.reconciled
    assert not engine.store.get("incident", "missing_protection")
    assert engine.broker.state["orders"][str(stop_id)]["status"] == "Submitted"
    deterministic_weekend.stamp += timedelta(seconds=11)
    engine._oca_maintain()
    assert len(calls) == 1
    assert engine.store.get("incident", "oca_protection_uncertain")


def test_rejected_leg_cancels_whole_pair_and_blocks_replacement(tmp_path):
    engine = paired_engine(tmp_path)
    order = engine.store.orders()[0]
    engine.observe(
        {"type": "broker_error", "code": 201, "request": order["payload"]["leg_ids"]["short_entry"]}
    )
    engine._oca_maintain()
    drain(engine)
    assert engine.store.get("incident", "oca_structure_rejected")
    assert engine.broker.state["orders"][str(order["broker_id"])]["status"] == "Cancelled"
    assert len(engine.store.orders()) == 1


def test_pair_trade_bust_cannot_authorize_a_second_trade(tmp_path):
    engine = paired_engine(tmp_path)
    market(engine, side="bid", price="100")
    market(engine, "tick", price="101", size="1")
    market(engine, side="ask", price="101.10")
    execution = engine.broker.state["executions"][0]
    corrected = {
        **execution,
        "execution_id": execution["execution_id"].rsplit(".", 1)[0] + ".02",
        "quantity": "0",
    }
    engine.observe({"type": "execution", **corrected})
    engine._oca_maintain()
    assert engine.owned()["run"]["quantity"] == 0
    assert engine.store.get("run", "run")["entries"] == 1
    assert len(engine.store.orders()) == 1


def test_fill_during_cancel_wins_over_replacement(tmp_path, monkeypatch):
    engine = paired_engine(tmp_path)
    order = engine.store.orders()[0]
    cancellations = []
    monkeypatch.setattr(engine.broker, "cancel", cancellations.append)
    engine.cancel_entry(order["id"])
    market(engine, side="bid", price="100")
    market(engine, "tick", price="101", size="1")
    market(engine, side="ask", price="101")
    assert engine.store.get("oca_group", order["id"])["winner"] == "long"
    assert engine.owned()["run"]["quantity"] == 1
    assert len(engine.store.orders()) == 1


def test_both_entry_executions_block_new_risk(tmp_path):
    engine = paired_engine(tmp_path)
    order = engine.store.orders()[0]
    for side, action, price in (("long", "BOT", "101"), ("short", "SLD", "99")):
        engine.observe(
            {
                "type": "execution",
                "execution_id": side + ".01",
                "broker_id": order["payload"]["leg_ids"][side + "_entry"],
                "client_id": engine.broker.client_id,
                "own_account": True,
                "conid": 1,
                "symbol": "BTC",
                "quantity": "1",
                "price": price,
                "side": action,
            }
        )
    engine._oca_maintain()
    assert engine.store.get("incident", "oca_multiple_entries")
    assert not engine.store.get("run", "run")["armed"]
    assert engine.store.get("oca_group", order["id"])["state"] == "uncertain"
    assert len(engine.store.orders()) == 1


@pytest.mark.parametrize("pnl", [None, "NaN", "-100000", "Infinity"])
def test_optional_pnl_never_blocks_otherwise_ready_paired_entry(tmp_path, pnl):
    engine = paired_engine(tmp_path)
    engine.cancel_entry(engine.store.orders()[0]["id"])
    drain(engine)
    reconcile(engine)
    engine.daily_pnl, engine.pnl_at = pnl, 0
    candidate = {
        "candle": now(),
        "high": "101",
        "low": "99",
        "expires_at": (datetime.now(UTC) + timedelta(seconds=45)).isoformat(),
        "capture": "new-candle",
        "authorization_id": "authorization",
    }
    engine._oca_submit(engine.store.get("run", "run"), candidate)
    assert len(engine.store.orders()) == 2


def test_crypto_data_layer_has_no_new_execution_capabilities():
    import queue

    from trading_oms_backend.workspace.broker import PaxosDataGateway

    adapter = PaxosDataGateway(queue.Queue())
    assert not adapter.execution_enabled
    for method in ("submit_pair", "amend_protection", "preview_short", "cancel", "submit_exit"):
        assert not hasattr(adapter, method)


def test_paired_recorded_replay_is_explicitly_unavailable():
    from trading_oms_backend.workspace.market import replay

    with pytest.raises(GraphError, match="single-entry"):
        replay(compile_graph(template(True)), [])


def test_failed_local_commit_cannot_publish_an_uncommitted_fill(tmp_path, monkeypatch):
    engine = paired_engine(tmp_path)
    market(engine, side="bid", price="100")
    market(engine, "tick", price="101", size="1")
    original_write = engine.store.write

    def fail_ledger(db, kind, key, payload, revision=1):
        if kind == "simulator" and payload["executions"]:
            raise OSError("synthetic storage failure")
        original_write(db, kind, key, payload, revision)

    monkeypatch.setattr(engine.store, "write", fail_ledger)
    with pytest.raises(OSError):
        market(engine, side="ask", price="101.10")
    assert not engine.broker.state["executions"]
    assert not engine.store.get("simulator", "ledger")["executions"]
    assert engine.broker.state["cash"] == "10000"
    assert not engine.owned()


def test_local_gap_below_valid_stop_increment_is_cancelled_before_fill(tmp_path):
    engine = paired_engine(tmp_path)
    market(engine, side="ask", price="0.011")
    market(engine, "tick", price="0.01", size="1")
    market(engine, side="bid", price="0.01")
    assert not engine.broker.state["executions"]
    assert engine.broker.state["cash"] == "10000"
    assert all(o["status"] == "Cancelled" for o in engine.broker.state["orders"].values())


def test_local_gap_exceeding_cash_cancels_both_entry_branches(tmp_path):
    engine = paired_engine(tmp_path)
    market(engine, side="bid", price="100")
    market(engine, "tick", price="101", size="1")
    market(engine, side="ask", price="20000")
    assert not engine.broker.state["executions"]
    assert all(o["status"] == "Cancelled" for o in engine.broker.state["orders"].values())
    reconcile(engine)
    assert engine.reconciled


def test_recovery_of_cover_not_accepted_by_local_adapter_preserves_action(tmp_path, monkeypatch):
    engine = paired_engine(tmp_path)
    market(engine, side="ask", price="100")
    market(engine, "tick", price="99", size="1")
    market(engine, side="bid", price="99")
    reconcile(engine)
    monkeypatch.setattr(engine.broker, "submit_exit", lambda intent: None)
    engine.close_position("run")
    cover = next(o for o in engine.store.orders() if o["payload"].get("purpose") == "exit")
    reconcile(engine)
    observed = engine.broker.state["orders"][str(cover["broker_id"])]
    assert observed["action"] == "BUY" and observed["status"] == "Cancelled"
    assert engine.reconciled, engine.last_fault
    assert engine.owned()["run"]["protected"]
