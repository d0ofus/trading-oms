from datetime import UTC, datetime, timedelta

import pytest
from test_workspace_fx_execution import fixture

from trading_oms_backend.workspace.fx_sessions import FXSession
from trading_oms_backend.workspace.store import now


def streams(engine, conid):
    cache = engine._fx_cache(conid)
    for kind, state in cache["feeds"].items():
        state.update(request=500 if kind == "fx_bidask" else 501, epoch=engine.broker.epoch)
    return cache


@pytest.mark.parametrize("source", ["MIDPOINT", "BID", "ASK"])
def test_source_specific_live_boundary_signal_and_display(tmp_path, monkeypatch, source):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    start = datetime.now(UTC).replace(second=0, microsecond=0)
    run["binding"]["execution_plan"]["signal_source"] = source
    run.update(armed=True, live_after=(start - timedelta(seconds=6)).isoformat())
    engine.store.put("run", run["id"], run)
    engine._fx_source(run["conid"], source).update(status="completed", epoch=engine.broker.epoch)
    cache.pop("fx_bidask", None)
    cache.pop("fx_midpoint", None)
    monkeypatch.setattr(FXSession, "interval_start", lambda *args: start - timedelta(hours=1))
    triggers = []
    monkeypatch.setattr(engine, "_fx_enter", lambda r, signal, capture: triggers.append(signal))
    for second in range(0, 61, 5):
        at = start + timedelta(seconds=second)
        monkeypatch.setattr(engine, "_fx_now", lambda at=at: at)
        value = "0.650001" if second == 60 else "0.650000"
        event = {
            "type": "fx_midpoint" if source == "MIDPOINT" else "fx_bidask",
            "conid": run["conid"],
            "epoch": engine.broker.epoch,
            "request": 501 if source == "MIDPOINT" else 500,
            "timestamp": int((start + timedelta(seconds=second)).timestamp()),
            "received_at": at.isoformat(),
            "price": value,
            "bid": value,
            "ask": value,
        }
        if source == "MIDPOINT":
            engine._fx_data_observation({**event, "type": "fx_bidask", "request": 500})
        engine._fx_data_observation(event)
    assert len(triggers) == 1 and triggers[0]["high"] == "0.650000"
    rows = engine.candles(run["conid"], signal_source=source)["items"]
    assert rows[-2]["source"] == source + " live"
    assert rows[-2]["volume"] is None
    assert cache["observations"].maxlen == 30000


def test_history_and_old_generation_never_emit_live_signals(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    history = cache["sources"]["MIDPOINT"]
    history.update(status="pending", request=600, epoch=engine.broker.epoch)
    event = {
        "type": "historical_bar",
        "conid": run["conid"],
        "signal_source": "MIDPOINT",
        "request": 600,
        "epoch": engine.broker.epoch,
        "timestamp": "1699999980",
        "open": "0.65",
        "high": "0.99",
        "low": "0.65",
        "close": "0.99",
    }
    engine._fx_data_observation({**event, "request": 599})
    assert not history["bars"]
    engine._fx_data_observation(event)
    engine._fx_data_observation({**event, "type": "history_end"})
    assert history["status"] == "completed"
    assert run["id"] not in engine.runtime and not engine.broker.submitted
    engine._fx_data_observation(
        {
            "type": "fx_midpoint",
            "conid": run["conid"],
            "request": 501,
            "epoch": engine.broker.epoch - 1,
            "price": "99",
        }
    )
    assert cache["fx_midpoint"]["price"] == "0.65005"


def test_bid_run_does_not_depend_on_midpoint_failure(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    run["binding"]["execution_plan"]["signal_source"] = "BID"
    engine.store.put("run", run["id"], run)
    engine._fx_prepare_data(run["conid"], "BID")
    engine._fx_source(run["conid"], "BID").update(status="completed", epoch=engine.broker.epoch)
    state = engine._fx_cache(run["conid"])["feeds"]["fx_midpoint"]
    engine._fx_data_failure(
        run["conid"], state, "quote", "permissions", "Unavailable", "fx_midpoint"
    )
    assert engine._fx_feed_health(run["conid"], run)["execution_fresh"]
    assert not engine.incidents.applicable([run])
    assert engine._dependency_history_ready(run["conid"])


def test_retry_is_paced_idempotent_and_preserves_completed_history(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    cache["sources"]["BID"] = {"status": "failed", "attempts": 3, "bars": {}}
    result = engine._fx_retry_feeds(run["conid"], ["history"], "a" * 32, "operator")
    assert result["queued"] == ["history"] and not result["armed"]
    assert cache["sources"]["MIDPOINT"]["status"] == "completed"
    assert engine._fx_retry_feeds(run["conid"], ["history"], "a" * 32, "operator") == result
    calls = []
    monkeypatch.setattr(engine.broker, "start_feed", lambda *a: calls.append(a) or 900)
    for value in cache["feeds"].values():
        value["status"] = "queued"
    engine._fx_data_maintain()
    engine._fx_data_maintain()
    assert len(calls) == 1  # Same-instrument tick requests are separated by 15 seconds.


def test_invalid_crossed_quotes_cannot_trigger_or_protect(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    engine._fx_data_observation(
        {
            "type": "fx_bidask",
            "conid": run["conid"],
            "request": 500,
            "epoch": engine.broker.epoch,
            "timestamp": datetime.now(UTC).timestamp(),
            "bid": "0.66",
            "ask": "0.65",
            "received_at": now(),
        }
    )
    assert not cache["fx_bidask"]["valid"]
    assert not engine._fx_feed_health(run["conid"], run)["execution_fresh"]
    assert not engine.broker.submitted
