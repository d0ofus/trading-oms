import time
from datetime import UTC, datetime, timedelta

import pytest
from test_workspace_unified import crypto_engine

from trading_oms_backend.workspace.store import now


def test_quiet_trade_return_does_not_invalidate_history_or_authorization(tmp_path):
    engine = crypto_engine(tmp_path)[0]
    old = (datetime.now(UTC) - timedelta(seconds=19)).isoformat()
    engine.data[456].update(received_at=old, source_at=old, history_loaded=True)
    # No run evaluation needed to reproduce the old pre-tick gap detector.
    engine.store.put(
        "run",
        "quiet",
        {
            "id": "quiet",
            "conid": 456,
            "armed": True,
            "position": "0",
            "capability_error": "fixture",
        },
    )
    assert not engine.feed_health(456)["execution_fresh"]
    engine._tick(
        {"type": "tick", "conid": 456, "timestamp": time.time(), "price": "100", "size": "1"}
    )
    assert engine.data[456]["warm"]
    assert engine.store.get("run", "quiet")["armed"]
    assert not any(e["type"] == "market.gap" for e in engine.store.events())
    assert engine.feed_health(456)["execution_fresh"]


def test_delayed_callback_cannot_refresh_quote_age(tmp_path):
    engine = crypto_engine(tmp_path)[0]
    old = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    engine.observe(
        {"type": "quote", "conid": 456, "side": "ask", "price": "100", "received_at": old}
    )
    assert engine.quotes[456]["ask"]["received_at"] == old
    assert not engine._crypto_fresh(456)


def test_stale_quote_crossing_skips_generation_without_delayed_entry(tmp_path):
    engine = crypto_engine(tmp_path)[0]
    engine.connected = engine.attested = engine.position_agreement = True
    run = {
        "id": "r",
        "conid": 456,
        "execution": "crypto_breakout",
        "armed": True,
        "entries": 0,
        "authorization_id": "a",
        "position": "0",
    }
    engine.store.put("run", "r", run)
    engine.store.put(
        "crypto_trigger",
        "r",
        {
            "run_id": "r",
            "state": "monitoring",
            "authorization_id": "a",
            "high": "101",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "started_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
    )
    engine.quotes[456]["ask"]["received_at"] = (
        datetime.now(UTC) - timedelta(seconds=20)
    ).isoformat()
    tick = {"conid": 456, "timestamp": time.time(), "price": "102"}
    engine._crypto_trade(tick)
    assert engine.store.get("crypto_trigger", "r")["state"] == "skipped"
    assert engine.store.get("run", "r")["armed"]
    engine.quotes[456]["ask"]["received_at"] = now()
    engine._crypto_trade(tick)
    assert not engine.broker.submitted


@pytest.mark.parametrize("fault", ["price", "volume", "order", "closed_candle"])
def test_invalid_trade_never_reaches_local_triggers(tmp_path, fault):
    engine, run = crypto_engine(tmp_path)
    engine._crypto_trade = lambda _: pytest.fail("Invalid trade reached local trigger processing")
    tick = {"type": "tick", "conid": 456, "timestamp": time.time(), "price": "101", "size": "1"}
    if fault == "price":
        tick["price"] = "-1"
    elif fault == "volume":
        tick["size"] = "-1"
    elif fault == "order":
        engine.data[456]["last_valid_trade_at"] = (
            datetime.now(UTC) + timedelta(seconds=1)
        ).isoformat()
    else:
        from types import SimpleNamespace

        engine.runtime[run["id"]] = {
            "market": SimpleNamespace(closed_until=datetime.now(UTC) + timedelta(seconds=1))
        }
    engine._tick(tick)
    assert not engine.data[456]["warm"]
    assert not engine.store.get("run", run["id"])["armed"]
    assert not engine.broker.submitted
