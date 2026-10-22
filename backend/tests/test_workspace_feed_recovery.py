"""Offline regressions: data retries never invoke broker execution."""

import json
import queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_workspace_unified import confirm, crypto_engine, crypto_entry

from trading_oms_backend.workspace.broker import GatewayData
from trading_oms_backend.workspace.broker_feeds import classify_data_error
from trading_oms_backend.workspace.store import Conflict


@pytest.mark.parametrize(
    ("code", "message", "reason"),
    [
        (10189, "No market data permissions", "permissions"),
        (10189, "TWS session is connected from a different IP", "session_conflict"),
        (162, "Historical data request pacing violation", "pacing"),
        (162, "HMDS query returned no data", "unavailable_data"),
        (162, "unsupported request", "unsupported_request"),
        (162, "service temporarily unavailable", "transient"),
        (162, "unrecognized confidential broker detail", "unknown"),
    ],
)
def test_error_classification_is_bounded_and_never_retains_message(code, message, reason):
    result = classify_data_error(code, message + " private-fixture-value")
    assert result["reason"] == reason
    assert "private-fixture-value" not in json.dumps(result)


def gateway():
    broker = GatewayData(queue.Queue())
    broker.client = Mock()
    broker._contracts[456] = SimpleNamespace(secType="CRYPTO")
    return broker


def test_targeted_retry_preserves_quotes_and_fences_retired_trade_callbacks(monkeypatch):
    broker = gateway()
    clock = [100.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])
    assert broker.subscribe(456)
    quote_id, trade_id = list(broker._requests)
    broker.data_error(trade_id, 10189, "No market data permissions")
    error = broker.observations.get_nowait()
    assert error["request_kind"] == "trade" and error["reason"] == "permissions"
    assert not broker.retry_feed(456, "trade")  # same-contract pacing
    clock[0] += 15
    assert broker.retry_feed(456, "trade")
    assert quote_id in broker._requests
    assert broker.client.reqMktData.call_count == 1
    assert broker.client.reqTickByTickData.call_count == 2
    assert not broker.feed_event_current({"request": trade_id, "generation": trade_id})
    broker.emit_feed("tick", trade_id, timestamp=1, price="1", size="1")
    assert broker.observations.empty()
    broker.client.placeOrder.assert_not_called()
    broker.client.cancelOrder.assert_not_called()


def test_expected_cancel_requires_retired_context_and_is_bounded():
    broker = gateway()
    broker.subscribe(456)
    retired = next(iter(broker._requests))
    broker.unsubscribe(456)
    broker.data_error(retired, 300, "arbitrary private broker text")
    event = broker.observations.get_nowait()
    assert event["reason"] == "expected_cancellation"
    assert event["context"] == "retired_data"
    broker.data_error(987654, 300, "unknown identifier")
    assert broker.observations.get_nowait()["context"] == "broker"
    for request in range(2000, 4200):
        broker.register_feed(request, 456, "history", seconds=60, end="")
        broker.retire_feed(request, "completed")
    assert len(broker._terminal_feeds) <= 1024


def test_unsubscribe_fences_queued_history_completion_and_errors():
    broker = gateway()
    broker.register_feed(11, 456, "history", seconds=60, end="")
    broker.retire_feed(11, "completed")
    broker.register_feed(12, 456, "trade")
    broker.data_error(12, 10189, "unknown")
    queued_error = broker.observations.get_nowait()
    broker.unsubscribe(456)
    assert not broker.feed_event_current({"request": 11, "generation": 11})
    assert not broker.feed_error_current(queued_error)


def test_stream_reset_preserves_independent_history_and_fences_old_epoch():
    broker = gateway()
    broker.subscribe(456)
    broker.register_feed(20, 456, "history", seconds=60, end="")
    broker._history_requests[20] = {"conid": 456, "seconds": 60}
    broker.reset_subscriptions()
    assert broker.feed_event_current({"request": 20, "generation": 20})
    assert not broker.feed_event_current({"request": 20, "generation": 20, "epoch": -1})
    assert not broker.feed_error_current({"request": 20, "generation": 19})
    broker.client.cancelHistoricalData.assert_not_called()


def test_callback_error_racing_cancellation_cannot_revive_old_request():
    import threading

    broker = gateway()
    broker.subscribe(456)
    request = next(iter(broker._requests))
    emitting, finish = threading.Event(), threading.Event()
    original_emit = broker.emit

    def delayed_emit(*args, **kwargs):
        original_emit(*args, **kwargs)
        emitting.set()
        assert finish.wait(5)

    broker.emit = delayed_emit
    callback = threading.Thread(target=broker.data_error, args=(request, 10189, "unknown"))
    callback.start()
    assert emitting.wait(5)
    cancel = threading.Thread(target=broker.cancel_feed, args=(request,))
    cancel.start()
    finish.set()
    callback.join(5)
    cancel.join(5)
    assert not callback.is_alive() and not cancel.is_alive()
    assert not broker.feed_error_current(broker.observations.get_nowait())
    assert broker.feed_context(request)["state"] == "cancelled"


def test_history_retry_completion_keeps_successful_ranges_and_waits_for_live_continuity(tmp_path):
    engine, run = crypto_engine(tmp_path)
    conid = run["conid"]
    jobs = [(conid, "first", 60), (conid, "second", 60)]
    engine.register_history_jobs(jobs)
    engine.history_bars[conid] = {60: {"100": {"close": "100"}}, 5: {}}
    engine.history_started(10, jobs[0])
    engine.history_finished(10)
    engine.history_started(11, jobs[1])
    engine.fail_feed({"conid": conid, "request": 11, "request_kind": "history", "code": 162})
    engine.retry_feeds(conid, ["history"], "c" * 32)
    engine.maintain_feed_retries(__import__("time").monotonic())
    assert engine.history_jobs == [jobs[1]]
    engine.history_jobs.clear()
    engine.history_started(12, jobs[1])
    engine.history_pending[12] = (0, conid)
    engine._history_summary = Mock()
    engine.observe({"type": "history_end", "request": 12, "conid": conid})
    assert engine.data[conid]["history_loaded"] and not engine.data[conid]["warm"]
    assert engine.feed_projection(conid)["history"]["status"] == "healthy"
    assert engine.history_bars[conid][60]["100"]["close"] == "100"
    assert not engine.store.get("run", run["id"])["armed"]
    assert not engine.broker.submitted


def test_retry_endpoint_requires_authentication_and_is_idempotent(tmp_path):
    from fastapi.testclient import TestClient

    from trading_oms_backend.workspace.api import create_app

    token = "synthetic-feed-recovery-test-pairing"
    app = create_app(tmp_path, token, start_engine=False)
    engine = app.state.engine
    engine.connected = True
    engine.data[456] = {"conid": 456}
    engine.components_for(456)["trade"]["status"] = "failed"
    origin = "http://127.0.0.1:8000"
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        payload = {"components": ["trade"], "mutation_id": "b" * 32}
        assert client.post("/api/market-data/456/retry", json=payload).status_code == 401
        assert client.post("/api/auth/pair", json={"token": token}).status_code == 200
        first = client.post("/api/market-data/456/retry", json=payload)
        assert first.status_code == 200
        assert client.post("/api/market-data/456/retry", json=payload).json() == first.json()
        events = [e for e in engine.store.events() if e["type"] == "market.retry.requested"]
        assert len(events) == 1 and events[0]["payload"]["actor"].startswith("operator-")
        assert (
            client.post(
                "/api/market-data/456/retry", json={**payload, "components": ["history"]}
            ).status_code
            == 409
        )


def test_delayed_or_invalid_observation_cannot_prove_feed_recovery(tmp_path):
    engine, run = crypto_engine(tmp_path)
    state = engine.components_for(run["conid"])["trade"]
    for tick in [
        {"price": "-1", "received_at": "2026-01-01T00:00:00+00:00"},
        {"price": "100", "received_at": "2026-01-01T00:00:00+00:00"},
    ]:
        engine.observe(
            {
                "type": "tick",
                "conid": run["conid"],
                "timestamp": __import__("time").time(),
                "size": "1",
                **tick,
            }
        )
        assert state["status"] == "pending"
    assert not engine.broker.submitted


def test_history_failure_does_not_liquidate_but_fresh_stop_still_protects(tmp_path):
    import time

    engine, run = crypto_engine(tmp_path)
    entry = crypto_entry(engine, run)
    confirm(engine, entry, "0.1", "100.123", "Cancelled")
    engine.fail_feed({"conid": 456, "request": 20, "request_kind": "history", "code": 162})
    assert len(engine.broker.submitted) == 1  # The outage alone cannot sell.
    engine.observe(
        {"type": "tick", "conid": 456, "timestamp": time.time(), "price": "99", "size": "1"}
    )
    assert len(engine.broker.submitted) == 2
    assert engine.broker.submitted[-1]["purpose"] == "exit"
    assert engine.incidents.open()


def test_retired_cancel_and_unassociated_read_error_are_diagnostics(tmp_path):
    engine, _ = crypto_engine(tmp_path)
    engine.observe(
        {
            "type": "broker_error",
            "request": 12,
            "code": 300,
            "context": "retired_data",
            "reason": "expected_cancellation",
        }
    )
    assert not engine.incidents.open()
    engine.observe({"type": "broker_error", "request": 99, "code": 300, "context": "broker"})
    assert engine.incidents.open()[0]["code"] == "broker_notice"
    assert not engine.incidents.page()["items"]


def test_combined_legacy_incident_requires_all_components(tmp_path):
    engine, _ = crypto_engine(tmp_path)
    states = engine.components_for(456)
    for state in states.values():
        state["status"] = "healthy"
    states["trade"]["status"] = "failed"
    item = engine.incident("market_data_failure", "Legacy mixed failure", conid=456)
    checks = {c["code"]: c for c in engine._recovery_checks(item)}
    assert checks["feed_quote"]["passed"] and checks["feed_history"]["passed"]
    assert not checks["feed_trade"]["passed"]


def test_independent_failures_targeted_idempotent_retry_and_partial_history(tmp_path, monkeypatch):
    engine, run = crypto_engine(tmp_path)
    conid = run["conid"]
    engine.components_for(conid)["quote"]["status"] = "healthy"
    jobs = [(conid, "completed", 60), (conid, "failed", 60), (conid, "next", 60)]
    engine.register_history_jobs(jobs)
    engine.history_started(10, jobs[0])
    engine.history_finished(10)
    engine.history_started(11, jobs[1])
    engine.history_jobs = [jobs[2]]
    engine.history_bars[conid] = {60: {"1": {"close": "100"}}, 5: {}}
    for request, kind, code in [(8, "trade", 10189), (11, "history", 162)]:
        engine.observe(
            {
                "type": "broker_error",
                "request": request,
                "code": code,
                "context": "market_data",
                "conid": conid,
                "request_kind": kind,
            }
        )
    states = engine.feed_projection(conid)
    assert states["quote"]["status"] == "healthy"
    assert states["trade"]["diagnostic"]["code"] == 10189
    assert states["history"]["diagnostic"]["code"] == 162
    assert {i["code"] for i in engine.incidents.open()} >= {
        "trade_feed_failure",
        "history_feed_failure",
    }
    assert engine.history_jobs == [jobs[2]]
    result = engine.retry_feeds(conid, ["history"], "a" * 32)
    assert engine.retry_feeds(conid, ["history"], "a" * 32) == result
    with pytest.raises(Conflict):
        engine.retry_feeds(conid, ["trade"], "a" * 32)
    engine.maintain_feed_retries(__import__("time").monotonic())
    assert jobs[1] in engine.history_jobs and jobs[0] not in engine.history_jobs
    assert engine.history_bars[conid][60]["1"] == {"close": "100"}
    assert engine.feed_projection(conid)["trade"]["status"] == "failed"
    assert not engine.store.get("run", run["id"])["armed"]
    assert not engine.broker.submitted


@pytest.mark.parametrize(
    ("reason", "delays"), [("transient", [15, 30, 60]), ("pacing", [60, 120, 240])]
)
def test_automatic_retry_backoff_stops_after_three_attempts(tmp_path, monkeypatch, reason, delays):
    engine, run = crypto_engine(tmp_path)
    clock = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])
    engine.broker.retry_feed = Mock(return_value=True)
    for index in range(4):
        engine.fail_feed(
            {
                "conid": run["conid"],
                "request": 12 + index,
                "code": 162,
                "request_kind": "trade",
                "reason": reason,
            }
        )
        state = engine.feed_projection(run["conid"])["trade"]
        if index == 3:
            assert not state["retry_pending"] and state["retry_available"]
            break
        assert state["retry_in_seconds"] == delays[index]
        engine.maintain_feed_retries(clock[0] + delays[index] - 1)
        assert engine.broker.retry_feed.call_count == index
        clock[0] += delays[index]
        engine.maintain_feed_retries(clock[0])
        assert engine.broker.retry_feed.call_count == index + 1
