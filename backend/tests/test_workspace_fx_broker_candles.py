"""Independent broker references never turn historical callbacks into live ticks."""

import sys
from datetime import UTC, datetime, timedelta

import pytest
from test_workspace_buying_power import authorize, setup
from test_workspace_fx_data import streams
from test_workspace_fx_execution import signal
from test_workspace_fx_timing import tick
from test_workspace_health import healthy_watchdog

from trading_oms_backend.workspace.fx_sessions import FXSession
from trading_oms_backend.workspace.store import now

POLICY = "idealpro_broker_candles_v2"


def prepared(tmp_path, monkeypatch, source="MIDPOINT"):
    start = datetime.now(UTC).replace(second=0, microsecond=0)

    class Clock(datetime):
        current = start + timedelta(seconds=2)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    for name, module in list(sys.modules.items()):
        if (
            name.startswith("trading_oms_backend.workspace.")
            and getattr(module, "datetime", None) is datetime
        ):
            monkeypatch.setattr(module, "datetime", Clock)
    engine, old = setup(tmp_path, monkeypatch, "1000")
    if source != "MIDPOINT":
        document = engine.store.version(old["strategy_id"], 1)["document"]
        document["settings"]["signal_source"] = source
        draft = engine.store.save_draft(None, "Source fixture", document, 0)
        engine.store.publish(draft["id"], 1)
        old["strategy_id"] = draft["id"]
    compatible = engine.fx_compatibility(
        old["strategy_id"],
        1,
        old["conid"],
        funding_policy="paper_buying_power_v1",
        execution_policy=POLICY,
    )
    run = engine.create_run(
        old["strategy_id"],
        1,
        old["conid"],
        {"quantity": "1000"},
        "broker_held",
        compatible["plan"]["hash"],
        "fx",
        "paper_buying_power_v1",
        POLICY,
    )
    streams(engine, run["conid"])
    engine._fx_source(run["conid"], source).update(
        persistent=True, request=600, epoch=engine.broker.epoch, status="pending", bars={}
    )
    monkeypatch.setattr(FXSession, "interval_start", lambda *args: start - timedelta(hours=1))
    return engine, run, Clock, start


def bar(engine, run, minute, high="0.700865", end=False):
    engine._fx_data_observation(
        {
            "type": "history_end" if end else "historical_bar",
            "conid": run["conid"],
            "request": 600,
            "epoch": engine.broker.epoch,
            "signal_source": run["binding"]["execution_plan"]["signal_source"],
            "persistent": True,
            "timestamp": str(int(minute.timestamp())),
            "open": "0.700855",
            "high": high,
            "low": "0.700845",
            "close": "0.700855",
        }
    )


def quote(engine, run, clock, price="0.700875"):
    healthy_watchdog(engine)
    for item in engine.currency_facts.values():
        item["received_at"] = now()
    for kind in ("fx_bidask", "fx_midpoint"):
        engine._fx_data_observation(
            tick(
                engine,
                run,
                clock.current,
                clock.current,
                kind,
                bid="0.70086",
                ask="0.70089",
                price=price,
            )
        )


def test_completed_reference_survives_quiet_ticks_and_submits_once(tmp_path, monkeypatch):
    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    bar(engine, run, start - timedelta(minutes=1))
    bar(engine, run, start, end=True)
    run = authorize(engine, run)
    clock.current += timedelta(seconds=1)
    quote(engine, run, clock, "0.700865")
    assert not engine.broker.submitted
    clock.current += timedelta(seconds=17)
    quote(engine, run, clock)
    assert len(engine.broker.submitted) == 1
    entry = engine.broker.submitted[0]
    assert entry["quantity"] == "1000" and entry["signal"]["high"] == "0.700865"
    assert entry["signal"]["reference_revision"]
    quote(engine, run, clock)
    assert len(engine.broker.submitted) == 1


@pytest.mark.parametrize("stale", [False, True])
def test_tick_before_reference_requires_unexpired_live_evidence(tmp_path, monkeypatch, stale):
    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    bar(engine, run, start, end=True)
    run = authorize(engine, run)
    clock.current += timedelta(seconds=1)
    quote(engine, run, clock)
    assert not engine.broker.submitted
    if stale:
        clock.current += timedelta(seconds=16)
    bar(engine, run, start - timedelta(minutes=1))
    assert len(engine.broker.submitted) == (0 if stale else 1)


def test_history_and_pre_authorization_ticks_never_submit(tmp_path, monkeypatch):
    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    quote(engine, run, clock)
    bar(engine, run, start, end=True)
    run = authorize(engine, run)
    bar(engine, run, start - timedelta(minutes=1))
    bar(engine, run, start, end=True)
    assert not engine.broker.submitted


def test_completed_reference_does_not_label_unarmed_run_as_armed(tmp_path, monkeypatch):
    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    bar(engine, run, start - timedelta(minutes=1))
    bar(engine, run, start, end=True)
    quote(engine, run, clock)
    health = engine._fx_feed_health(run["conid"], run)
    assert engine._fx_execution_status(health, run) == (
        "ready",
        "Completed broker candle ready; authorization required.",
    )
    run = authorize(engine, run)
    assert engine._fx_execution_status(health, run) == (
        "ready",
        "Armed - waiting for breakout above the completed broker candle.",
    )


def test_fractional_rejection_is_terminal_and_not_overwritten(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    engine._fx_enter(run, signal(), "captured")
    order = engine.store.orders()[0]
    engine.observe({"type": "broker_error", "request": order["broker_id"], "code": 10318})
    assert engine.store.orders()[0]["state"] == "rejected"
    engine.observe({"type": "broker_error", "request": order["broker_id"], "code": 10147})
    assert engine.store.orders()[0]["state"] == "rejected"
    assert engine.store.get("broker_order", str(order["broker_id"]))["rejection"]["code"] == 10318
    assert not [e for e in engine.store.events(limit=1000) if e["type"] == "order.cancel.requested"]
    with pytest.raises(ValueError, match="10318"):
        engine._fx_funding(run["binding"]["execution_plan"], run["binding"]["sizing"])


@pytest.mark.parametrize("case", ["missing", "partial", "old_generation", "expired", "disarmed"])
def test_reference_or_authorization_failure_never_submits(tmp_path, monkeypatch, case):
    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    bar(engine, run, start - timedelta(minutes=2))
    bar(engine, run, start, end=True)
    run = authorize(engine, run)
    clock.current += timedelta(seconds=1)
    if case != "missing":
        bar(engine, run, start - timedelta(minutes=1))
    state = engine._fx_source(run["conid"], "MIDPOINT")
    if case == "partial":
        state["bars"][str(int(start.timestamp()) - 60)]["complete"] = False
    elif case == "old_generation":
        state["epoch"] -= 1
    elif case == "expired":
        clock.current += timedelta(minutes=1)
    elif case == "disarmed":
        engine.disarm(run["id"], "test operator disarm")
    quote(engine, run, clock)
    assert not engine.broker.submitted


def test_rollover_confirms_bar_without_tick_continuity(tmp_path, monkeypatch):
    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    bar(engine, run, start)
    bar(engine, run, start, end=True)
    state = engine._fx_source(run["conid"], "MIDPOINT")
    assert not state["bars"][str(int(start.timestamp()))]["complete"]
    clock.current = start + timedelta(minutes=1, seconds=2)
    bar(engine, run, clock.current.replace(second=0))
    assert state["bars"][str(int(start.timestamp()))]["complete"]
    assert engine._history_pending_count() == 0
    rows = engine.candles(run["conid"])["items"]
    assert rows[-2]["complete"] and not rows[-1]["complete"]
    assert rows[-2]["source"] == "IBKR MIDPOINT"
    engine._fx_reset_data()
    assert not engine._fx_broker_reference(run, clock.current)


def test_changed_reference_and_new_lower_tick_cancel_pending_crossing(tmp_path, monkeypatch):
    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    bar(engine, run, start, end=True)
    run = authorize(engine, run)
    clock.current += timedelta(seconds=1)
    quote(engine, run, clock)
    clock.current += timedelta(seconds=1)
    quote(engine, run, clock, "0.70085")
    bar(engine, run, start - timedelta(minutes=1))
    assert not engine.broker.submitted


@pytest.mark.parametrize("conflict", [False, True])
def test_historical_10318_repair_requires_complete_snapshot_and_no_acceptance(
    tmp_path, monkeypatch, conflict
):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    engine._fx_enter(run, signal(), "captured")
    order = engine.store.orders()[0]
    engine.store.event("broker.message", {"code": 10318, "request": order["broker_id"]})
    engine.store.transition(order["id"], "unknown", {"reason": "legacy_unclassified"})
    if conflict:
        engine.store.event(
            "broker.order.observed", {"broker_id": order["broker_id"], "status": "Submitted"}
        )
    engine._reconciliation_started = {
        "id": "fixture-reconcile",
        "epoch": engine.broker.epoch,
        "started_at": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
    }
    engine.reconcile_parts = {"orders_end"}
    engine._reconcile_quantity_rejections()
    assert engine.store.orders()[0]["state"] == "unknown"
    engine.reconcile_parts.update(
        {"positions_end", "completed_orders_end", "executions_end", "account_end"}
    )
    engine._reconcile_quantity_rejections()
    assert engine.store.orders()[0]["state"] == ("unknown" if conflict else "rejected")
    if not conflict:
        engine._reconcile_quantity_rejections()
        assert (
            len(
                [
                    e
                    for e in engine.store.events(limit=1000)
                    if e["type"] == "order.validation_rejection.reconciled"
                ]
            )
            == 1
        )
        assert not engine.store.get("run", run["id"])["armed"]
        assert engine.store.get("run", run["id"])["entries"] == 1
        assert engine.store.get("fx_protection", run["id"])["state"] == "closed"
        engine._finish_reconcile()
        assert engine.reconciled, engine.last_fault
        assert not engine.store.get("reservation", order["id"])["active"]
        from test_workspace_fx_execution import fill

        fill(engine, order, "0.01")
        assert engine.broker.submitted[-1]["purpose"] == "protection"
        assert engine.store.get("fx_protection", run["id"])["quantity"] == "0.01"


def test_10318_for_already_accepted_order_is_not_initial_rejection(tmp_path, monkeypatch):
    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    engine._fx_enter(run, signal(), "captured")
    order = engine.store.orders()[0]
    engine._order_observation(
        {"broker_id": order["broker_id"], "status": "Submitted", "permanent_id": 1234}
    )
    engine.observe({"type": "broker_error", "code": 10318, "request": order["broker_id"]})
    assert engine.store.orders()[0]["state"] != "rejected"
    assert not engine.store.get("quantity_restriction", str(run["conid"]) + ":IDEALPRO:MKT:IOC")


def test_streaming_request_has_bounded_bootstrap_and_cancellation():
    from types import SimpleNamespace

    from test_workspace_feed_recovery import gateway

    broker = gateway()
    broker._contracts[14433401] = SimpleNamespace(secType="CASH")
    request = broker.history(14433401, signal_source="MIDPOINT", keep_up_to_date=True)
    args = broker.client.reqHistoricalData.call_args.args
    assert args[2:6] == ("", "1800 S", "1 min", "MIDPOINT")
    assert args[7:9] == (2, True)
    assert broker._history_requests[request]["persistent"]
    broker.cancel_feed(request)
    broker.client.cancelHistoricalData.assert_called_once_with(request)
    assert request not in broker._history_requests
    assert not broker.feed_event_current({"request": request, "generation": request})


@pytest.mark.parametrize("source", ["BID", "ASK"])
def test_selected_broker_source_and_live_source_match(tmp_path, monkeypatch, source):
    engine, run, clock, start = prepared(tmp_path, monkeypatch, source)
    bar(engine, run, start - timedelta(minutes=1))
    bar(engine, run, start, end=True)
    run = authorize(engine, run)
    clock.current += timedelta(seconds=1)
    for fact in engine.currency_facts.values():
        fact["received_at"] = now()
    healthy_watchdog(engine)
    price = "0.700875"
    engine._fx_data_observation(
        tick(engine, run, clock.current, clock.current, bid=price, ask=price)
    )
    assert len(engine.broker.submitted) == 1
    assert engine.broker.submitted[0]["fx_plan"]["signal_source"] == source
    assert engine.broker.submitted[0]["signal"]["price"] == price


def test_late_cancel_cannot_replace_rejection_but_late_fill_is_protected(tmp_path, monkeypatch):
    from test_workspace_fx_execution import fill

    engine, run = setup(tmp_path, monkeypatch)
    run = authorize(engine, run)
    engine._fx_enter(run, signal(), "captured")
    order = engine.store.orders()[0]
    engine.observe({"type": "broker_error", "code": 10318, "request": order["broker_id"]})
    engine._order_observation({"broker_id": order["broker_id"], "status": "Cancelled"})
    assert engine.store.orders()[0]["state"] == "rejected"
    fill(engine, order, "0.01")
    assert engine.store.get("fx_protection", run["id"])["quantity"] == "0.01"
    assert engine.broker.submitted[-1]["purpose"] == "protection"


def test_new_policy_adapter_requires_fresh_reference_evidence(tmp_path, monkeypatch):
    from test_workspace_fx_broker import adapter

    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    bar(engine, run, start - timedelta(minutes=1))
    bar(engine, run, start, end=True)
    run = authorize(engine, run)
    clock.current += timedelta(seconds=1)
    quote(engine, run, clock)
    intent = engine.broker.submitted[0]
    gateway = adapter()
    gateway.epoch = engine.broker.epoch
    gateway.submit_fx(intent)
    assert len(gateway.sent) == 1
    clock.current += timedelta(seconds=16)
    with pytest.raises(ValueError, match="fresh|Fresh|current|Current"):
        gateway.submit_fx(intent)
    assert len(gateway.sent) == 1


def test_bootstrap_end_keeps_updates_active_and_late_callbacks_are_fenced(monkeypatch):
    import queue
    import threading
    from types import SimpleNamespace

    from ibapi.client import EClient

    from trading_oms_backend.workspace.broker import GatewayData

    monkeypatch.setattr(EClient, "connect", lambda *args: None)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    gateway = GatewayData(queue.Queue())
    gateway.connect()
    gateway._contracts[14433401] = SimpleNamespace(secType="CASH")
    monkeypatch.setattr(gateway.client, "reqHistoricalData", lambda *args: None)
    monkeypatch.setattr(gateway.client, "cancelHistoricalData", lambda *args: None)
    request = gateway.history(14433401, signal_source="MIDPOINT", keep_up_to_date=True)
    candle = SimpleNamespace(
        date="1790292480", open=0.700855, high=0.700865, low=0.700845, close=0.700855, volume=-1
    )
    gateway.client.historicalData(request, candle)
    gateway.client.historicalDataEnd(request, "", "")
    gateway.client.historicalDataUpdate(request, candle)
    events = [gateway.observations.get_nowait() for _ in range(3)]
    assert [e["type"] for e in events] == ["historical_bar", "history_end", "historical_bar"]
    assert request in gateway._history_requests
    assert gateway.feed_context(request)["state"] == "active"
    assert events[-1]["persistent"]
    gateway.cancel_feed(request)
    gateway.client.historicalDataUpdate(request, candle)
    gateway.client.historicalDataEnd(request, "", "")
    assert gateway.observations.empty()


def test_slightly_ahead_broker_bar_stays_partial_without_fault_or_future_entry(
    tmp_path, monkeypatch
):
    engine, run, clock, start = prepared(tmp_path, monkeypatch)
    bar(engine, run, start - timedelta(minutes=1))
    bar(engine, run, start, end=True)
    run = authorize(engine, run)
    clock.current = start + timedelta(seconds=59, milliseconds=750)
    bar(engine, run, start + timedelta(minutes=1))
    state = engine._fx_source(run["conid"], "MIDPOINT")
    assert state["status"] == "completed"
    assert not state["bars"][str(int(start.timestamp()) + 60)]["complete"]
    assert (
        engine._fx_broker_reference(run, clock.current)["candle"]
        == (start - timedelta(minutes=1)).isoformat()
    )
    assert not engine.broker.submitted
