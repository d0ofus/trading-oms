from datetime import UTC, datetime, timedelta

from test_workspace_credit_funding import new_run
from test_workspace_fx_execution import signal

from trading_oms_backend.workspace.credit_policy import POLICY


def test_healthy_quiet_fx_can_authorize_but_cannot_dispatch(tmp_path, monkeypatch):
    engine, run = new_run(tmp_path, monkeypatch)
    cache = engine._fx_cache(run["conid"])
    for feed in cache["feeds"].values():
        feed["epoch"] = engine.broker.epoch
    stale = (datetime.now(UTC) - timedelta(seconds=16)).isoformat()
    for kind in ("fx_bidask", "fx_midpoint"):
        cache[kind].update(source_at=stale, received_at=stale)
    preview = engine.arm_preview([run["id"]])
    assert preview["can_authorize"]
    assert not preview["can_dispatch"]
    data = next(c for c in preview["checks"] if c["code"].startswith("fx_data_"))
    funding = next(c for c in preview["checks"] if c["code"].startswith("fx_funding_"))
    assert data["status"] == "waiting" and data["remediation"] is None
    assert funding["status"] == "waiting" and funding["depends_on"] == data["code"]
    engine.arm(
        [run["id"]],
        "b" * 32,
        review_fingerprint=preview["review_fingerprint"],
        fx_policy_revision="idealpro_funded_fx_v1",
        resume_policy=preview["resume_policy"],
        review_instance=engine.process_identity,
        local_protection_acknowledged=True,
        execution_plan_revisions={run["id"]: run["binding"]["execution_plan"]["hash"]},
        funding_policy_acknowledged=POLICY,
    )
    armed = engine.store.get("run", run["id"])
    assert armed["armed"]
    assert not engine._fx_guard(armed)
    engine._fx_enter(armed, {**signal(), "price": "0.66"}, "fixture")
    assert not engine.broker.submitted


def test_failed_stream_cannot_be_treated_as_a_quiet_feed(tmp_path, monkeypatch):
    engine, run = new_run(tmp_path, monkeypatch)
    engine._fx_cache(run["conid"])["feeds"]["fx_midpoint"]["status"] = "failed"
    preview = engine.arm_preview([run["id"]])
    assert not preview["can_authorize"]


def test_price_age_does_not_change_material_review_fingerprint(tmp_path, monkeypatch):
    engine, run = new_run(tmp_path, monkeypatch)
    first = engine.arm_preview([run["id"]])
    engine._fx_cache(run["conid"])["fx_midpoint"]["source_at"] = (
        datetime.now(UTC) - timedelta(seconds=16)
    ).isoformat()
    second = engine.arm_preview([run["id"]])
    assert first["review_fingerprint"] == second["review_fingerprint"]


def test_fresh_cached_prices_do_not_qualify_a_different_stream_generation(tmp_path, monkeypatch):
    engine, run = new_run(tmp_path, monkeypatch)
    engine._fx_cache(run["conid"])["feeds"]["fx_midpoint"].update(
        epoch=engine.broker.epoch - 1, status="healthy"
    )
    assert not engine._fx_feed_health(run["conid"], run)["execution_fresh"]
    assert not engine.arm_preview([run["id"]])["can_authorize"]


def test_waiting_for_credit_keeps_next_live_candle_high_accurate():
    from decimal import Decimal

    from trading_oms_backend.workspace.fx_market import FXSignal

    start = datetime.now(UTC).replace(second=0, microsecond=0)
    signal = FXSignal(start - timedelta(seconds=1))
    for second in range(0, 60, 5):
        assert signal.observe(start + timedelta(seconds=second), Decimal("0.65"), start) is None
    assert signal.observe(start + timedelta(seconds=60), Decimal("0.651"), start)
    for second in range(65, 120, 5):
        assert signal.observe(start + timedelta(seconds=second), Decimal("0.66"), start) is None
    # The credit wait expired. A lower price cannot break this minute's true high.
    assert signal.observe(start + timedelta(seconds=120), Decimal("0.655"), start) is None
    assert signal.previous["high"] == "0.66"
