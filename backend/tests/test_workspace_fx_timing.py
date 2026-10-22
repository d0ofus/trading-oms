from datetime import UTC, datetime, timedelta

import pytest
from test_workspace_fx_data import streams
from test_workspace_fx_execution import arm, fixture

from trading_oms_backend.workspace import fx_data
from trading_oms_backend.workspace.fx_sessions import FXSession


def clock(monkeypatch, at):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    monkeypatch.setattr(fx_data, "datetime", Frozen)
    return at


def tick(engine, run, at, receipt, kind="fx_bidask", **changes):
    return {
        "type": kind,
        "conid": run["conid"],
        "request": 500 if kind == "fx_bidask" else 501,
        "epoch": engine.broker.epoch,
        "timestamp": at.timestamp(),
        "received_at": receipt.isoformat(),
        "bid": "0.65",
        "ask": "0.6501",
        "price": "0.65005",
        "valid": True,
        **changes,
    }


def test_ahead_arrival_matures_once_without_permanent_invalidity(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    cache.pop("fx_bidask")
    cache.pop("fx_midpoint")
    arrival = clock(monkeypatch, datetime.now(UTC))
    source = arrival + timedelta(seconds=0.25)
    for kind in ("fx_bidask", "fx_midpoint"):
        engine._fx_data_observation(tick(engine, run, source, arrival, kind))
    health = engine._fx_feed_health(run["conid"], run)
    assert health["structural_valid"] and not health["execution_fresh"]
    assert health["freshness_reason"] == "clock_alignment"
    assert health["ages"]["signal source"] == -0.25
    assert not cache.get("observations")
    clock(monkeypatch, arrival + timedelta(seconds=0.5))
    engine._fx_drain_observations()
    health = engine._fx_feed_health(run["conid"], run)
    assert health["execution_fresh"] and health["feed_health"] == "healthy"
    assert health["ages"]["signal source"] == 0.25
    assert health["ages"]["signal receipt"] == 0.5
    assert len(cache["observations"]) == 2
    engine._fx_drain_observations()
    assert len(cache["observations"]) == 2
    assert not engine.broker.submitted


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"bid": "0.66"}, "invalid"),
        ({"price": "nan"}, "invalid"),
        ({"valid": False}, "invalid"),
    ],
)
def test_structural_invalidity_remains_a_real_fault(tmp_path, monkeypatch, change, reason):
    engine, run = fixture(tmp_path, monkeypatch)
    streams(engine, run["conid"])
    at = clock(monkeypatch, datetime.now(UTC))
    kind = "fx_midpoint" if "price" in change else "fx_bidask"
    engine._fx_data_observation(tick(engine, run, at, at, kind, **change))
    health = engine._fx_feed_health(run["conid"], run)
    assert not health["structural_valid"]
    assert health["freshness_reason"] == reason
    assert health["feed_health"] == "blocked"
    assert not engine.broker.submitted


def test_future_buffer_is_fenced_and_expired_receipts_never_replayed(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    at = clock(monkeypatch, datetime.now(UTC))
    engine._fx_data_observation(tick(engine, run, at + timedelta(seconds=1), at))
    clock(monkeypatch, at + timedelta(seconds=16))
    engine._fx_drain_observations()
    assert not cache.get("observations")
    at += timedelta(seconds=16)
    engine._fx_data_observation(tick(engine, run, at + timedelta(seconds=1), at))
    engine.broker.epoch += 1
    clock(monkeypatch, at + timedelta(seconds=2))
    engine._fx_drain_observations()
    assert not cache.get("observations") and not cache.get("pending_observations")
    assert not engine.broker.submitted


def test_reference_minute_cannot_overlap_authorization_clock_uncertainty(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    at = datetime.now(UTC).replace(second=58, microsecond=0)
    run["live_after"] = at.isoformat()
    market = engine._fx_runtime(run)["market"]
    assert market.live_after == at + timedelta(seconds=5)


def test_future_crossing_is_processed_once_only_after_alignment(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    cache.pop("fx_bidask")
    cache.pop("fx_midpoint")
    start = datetime.now(UTC).replace(second=0, microsecond=0)
    run.update(armed=True, live_after=(start - timedelta(seconds=6)).isoformat())
    engine.store.put("run", run["id"], run)
    monkeypatch.setattr(FXSession, "interval_start", lambda *a: start - timedelta(hours=1))
    signals = []
    monkeypatch.setattr(engine, "_fx_enter", lambda r, signal, capture: signals.append(signal))
    for second in range(0, 61, 5):
        source = start + timedelta(seconds=second)
        arrival = source - timedelta(seconds=0.25)
        clock(monkeypatch, arrival)
        for kind in ("fx_bidask", "fx_midpoint"):
            event = tick(
                engine, run, source, arrival, kind, price="0.65006" if second == 60 else "0.65005"
            )
            engine._fx_data_observation(event)
        assert not signals
        clock(monkeypatch, source + timedelta(seconds=0.1))
        engine._fx_drain_observations()
    assert len(signals) == 1
    assert signals[0]["triggered_at"] == (start + timedelta(minutes=1)).isoformat()
    engine._fx_data_observation(event)  # duplicate callback after drain
    engine._fx_drain_observations()
    assert len(signals) == 1 and len(cache["observations"]) == 26
    assert not engine.broker.submitted


def test_future_quote_cannot_trigger_local_protection_early(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    cache.pop("fx_bidask")
    engine.store.put("fx_protection", run["id"], {"quantity": "1", "stop": "0.66"})
    exits = []
    monkeypatch.setattr(engine, "_fx_request_exit", lambda *args: exits.append(args))
    at = clock(monkeypatch, datetime.now(UTC))
    event = tick(engine, run, at + timedelta(seconds=0.5), at)
    engine._fx_data_observation(event)
    assert not exits and not engine._fx_quote_evaluation(run["conid"])["fresh"]
    clock(monkeypatch, at + timedelta(seconds=0.6))
    # A status read must not process a pending observation or make it executable.
    assert not engine._fx_quote_evaluation(run["conid"])["fresh"]
    engine._fx_drain_observations()
    assert len(exits) == 1
    engine._fx_data_observation(event)
    assert len(exits) == 1


@pytest.mark.parametrize(
    "failure", ["overflow", "clock_bound", "receipt_bound", "malformed_receipt"]
)
def test_alignment_faults_block_visibly_and_never_process(tmp_path, monkeypatch, failure):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    at = clock(monkeypatch, datetime.now(UTC))
    event = tick(engine, run, at + timedelta(seconds=1), at)
    if failure == "overflow":
        monkeypatch.setattr("trading_oms_backend.workspace.fx_observations.PENDING_LIMIT", 1)
        engine._fx_data_observation(event)
        event = {**event, "timestamp": event["timestamp"] + 0.1}
    elif failure == "clock_bound":
        event["timestamp"] = (at + timedelta(seconds=5.01)).timestamp()
    elif failure == "receipt_bound":
        event["received_at"] = (at + timedelta(seconds=5.01)).isoformat()
    else:
        event["received_at"] = "not-a-timestamp"
    engine._fx_data_observation(event)
    assert engine._fx_feed_health(run["conid"], run)["feed_health"] == "blocked"
    clock(monkeypatch, at + timedelta(seconds=6))
    engine._fx_drain_observations()
    assert not cache.get("observations")
    assert engine.incidents.applicable([run])
    assert not engine.broker.submitted


def test_retirement_discards_buffer_without_qualifying_reuse(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    at = clock(monkeypatch, datetime.now(UTC))
    engine._fx_data_observation(tick(engine, run, at + timedelta(seconds=1), at))
    assert cache["pending_observations"]
    engine._retire_data_jobs({"contracts": set(), "premarket": set()})
    assert not cache.get("pending_observations")
    assert not engine._fx_quote_evaluation(run["conid"])["fresh"]
    clock(monkeypatch, at + timedelta(seconds=2))
    engine._fx_drain_observations()
    assert not cache.get("observations")


def test_independent_stream_timing_uses_one_instant_for_ages_and_funding(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    at = clock(monkeypatch, datetime.now(UTC))
    for kind in ("fx_bidask", "fx_midpoint"):
        cache.pop(kind)
        engine._fx_data_observation(tick(engine, run, at, at, kind))
    clock(monkeypatch, at + timedelta(seconds=15))
    health = engine._fx_feed_health(run["conid"], run)
    assert health["execution_fresh"] and set(health["ages"].values()) == {15}
    assert engine._fx_quote_evaluation(run["conid"])["fresh"]
    clock(monkeypatch, at + timedelta(seconds=15.001))
    health = engine._fx_feed_health(run["conid"], run)
    assert not health["execution_fresh"] and health["feed_health"] == "healthy"
    assert health["freshness_reason"] == "stale"
    assert not engine._fx_quote_evaluation(run["conid"])["fresh"]
    assert not engine.broker.submitted


def test_out_of_order_and_superseded_observations_are_discarded(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    cache.pop("fx_bidask")
    at = clock(monkeypatch, datetime.now(UTC))
    engine._fx_data_observation(tick(engine, run, at + timedelta(seconds=1), at))
    engine._fx_data_observation(tick(engine, run, at + timedelta(seconds=0.5), at))
    assert len(cache["pending_observations"]) == 1
    clock(monkeypatch, at + timedelta(seconds=2))
    engine._fx_drain_observations()
    engine._fx_data_observation(tick(engine, run, at, at))
    assert len(cache["observations"]) == 1
    assert cache["timing_diagnostics"]["streams"]["fx_bidask"]["counts"]["out_of_order"] == 2


@pytest.mark.parametrize("source", ["BID", "ASK", "MIDPOINT"])
def test_stale_unused_midpoint_does_not_reset_bid_or_ask_reference(tmp_path, monkeypatch, source):
    engine, run = fixture(tmp_path, monkeypatch)
    streams(engine, run["conid"])
    run["binding"]["execution_plan"]["signal_source"] = source
    engine.store.put("run", run["id"], run)
    runtime = engine._fx_runtime(run)
    stamp = datetime.now(UTC) + timedelta(seconds=1)
    clock(monkeypatch, stamp + timedelta(seconds=16))
    engine._fx_data_observation(tick(engine, run, stamp, stamp, "fx_midpoint"))
    if source == "MIDPOINT":
        assert run["id"] not in engine.runtime
    else:
        assert engine.runtime[run["id"]] is runtime


@pytest.mark.parametrize("boundary", ["expired", "future", "dispatch_expiry"])
def test_signal_window_rechecked_before_reservation_and_dispatch(tmp_path, monkeypatch, boundary):
    engine, run = fixture(tmp_path, monkeypatch)
    run = arm(engine, run)
    at = datetime.now(UTC)
    signal = {
        "candle": (at - timedelta(minutes=1)).isoformat(),
        "price": "0.65005",
        "high": "0.65",
        "triggered_at": at.isoformat(),
        "expires_at": (at + timedelta(seconds=1)).isoformat(),
    }
    if boundary == "expired":
        signal["expires_at"] = (at - timedelta(microseconds=1)).isoformat()
    elif boundary == "future":
        signal["triggered_at"] = (at + timedelta(seconds=0.25)).isoformat()
    else:
        original = engine.guard_entry_dispatch

        def expire(key):
            clock(monkeypatch, at + timedelta(seconds=1.01))
            return original(key)

        monkeypatch.setattr(engine, "guard_entry_dispatch", expire)
    engine._fx_enter(run, signal, "synthetic")
    assert not engine.broker.submitted
    if boundary != "dispatch_expiry":
        assert not engine.store.orders()
    else:
        assert engine.store.orders()[0]["state"] == "cancelled"
        assert not any(r.get("active") for r in engine.store.list("reservation"))


def test_buffered_crossing_after_its_minute_expires_never_reaches_entry(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = streams(engine, run["conid"])
    cache.pop("fx_bidask")
    cache.pop("fx_midpoint")
    start = datetime.now(UTC).replace(second=0, microsecond=0)
    run.update(armed=True, live_after=(start - timedelta(seconds=6)).isoformat())
    engine.store.put("run", run["id"], run)
    monkeypatch.setattr(FXSession, "interval_start", lambda *a: start - timedelta(hours=1))
    signals = []
    monkeypatch.setattr(engine, "_fx_enter", lambda *a: signals.append(a))
    for second in range(0, 116, 5):
        at = clock(monkeypatch, start + timedelta(seconds=second))
        for kind in ("fx_bidask", "fx_midpoint"):
            engine._fx_data_observation(tick(engine, run, at, at, kind))
    source = start + timedelta(seconds=119.5)
    receipt = clock(monkeypatch, source - timedelta(seconds=0.25))
    for kind in ("fx_bidask", "fx_midpoint"):
        engine._fx_data_observation(tick(engine, run, source, receipt, kind, price="0.65006"))
    clock(monkeypatch, start + timedelta(seconds=120.5))
    engine._fx_drain_observations()
    assert not signals and not engine.store.orders() and not engine.broker.submitted


@pytest.mark.parametrize("malformed", ["not-a-timestamp", None, float("inf"), "far_future"])
def test_corrected_stream_can_recover_after_a_bad_timestamp(tmp_path, monkeypatch, malformed):
    engine, run = fixture(tmp_path, monkeypatch)
    streams(engine, run["conid"])
    at = clock(monkeypatch, datetime.now(UTC))
    engine._fx_data_observation(tick(engine, run, at, at))
    timestamp = (at + timedelta(days=1)).timestamp() if malformed == "far_future" else malformed
    engine._fx_data_observation(tick(engine, run, at, at, timestamp=timestamp))
    assert engine._fx_feed_health(run["conid"], run)["feed_health"] == "blocked"
    # A valid correction is usable evidence without replaying the old accepted tick.
    engine._fx_data_observation(tick(engine, run, at, at))
    assert engine._fx_quote_evaluation(run["conid"])["fresh"]
    assert len(engine._fx_cache(run["conid"])["observations"]) == 1
    assert not engine.broker.submitted
