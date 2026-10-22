import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from trading_oms_backend.workspace.fx_market import FXSignal
from trading_oms_backend.workspace.fx_policy import compatibility, size_fx
from trading_oms_backend.workspace.fx_sessions import FXSession
from trading_oms_backend.workspace.fx_strategies import fx_copy
from trading_oms_backend.workspace.graph import compile_graph
from trading_oms_backend.workspace.stock_strategies import stock_templates


def fx_contract(base="AUD", quote="USD", conid=14433401):
    return {
        "conid": conid,
        "symbol": base,
        "currency": quote,
        "sec_type": "CASH",
        "exchange": "IDEALPRO",
        "routing_exchange": "IDEALPRO",
        "resolved": True,
        "min_size": "1",
        "size_increment": "1",
        "order_types": ["MKT", "LMT", "STP"],
        "market_rule": 1,
        "min_tick": "0.00005",
        "time_zone": "US/Eastern",
        "trading_hours": "20260923:1715-20260924:1700;20260924:1715-20260925:1700",
        "liquid_hours": "20260923:1715-20260924:1700;20260924:1715-20260925:1700",
    }


def fx_document():
    return fx_copy(stock_templates(8)[-1]["document"])


def test_fx_copy_is_explicit_and_preserves_legacy_canvas_and_hash():
    source = stock_templates(8)[-1]["document"]
    original = copy.deepcopy(source)
    before = compile_graph(source).digest
    copied = fx_copy(source)
    assert copied["schema_version"] == 9
    assert copied["settings"]["signal_source"] == "MIDPOINT"
    assert copied["settings"]["breakout_comparison"] == "gt"
    assert copied["nodes"] == original["nodes"] and copied["edges"] == original["edges"]
    assert source == original and compile_graph(source).digest == before
    alternative = copy.deepcopy(copied)
    alternative["settings"]["signal_source"] = "ASK"
    assert compile_graph(alternative).digest != compile_graph(copied).digest
    with pytest.raises(ValueError, match="long-only"):
        fx_copy(stock_templates(8)[0]["document"])


@pytest.mark.parametrize("source", ["MIDPOINT", "BID", "ASK"])
def test_fx_source_is_published_and_no_traded_last_is_inferred(source):
    document = fx_document()
    document["settings"]["signal_source"] = source
    result = compatibility(fx_contract(), document)
    assert result["can_prepare"]
    assert result["plan"]["signal_source"] == source
    assert result["plan"]["entry_type"] == "MKT"
    assert result["plan"]["entry_tif"] == "IOC"
    document["settings"]["signal_source"] = "LAST"
    with pytest.raises(ValueError, match="Midpoint, Bid or Ask"):
        compile_graph(document)


@pytest.mark.parametrize("base,quote", [("AUD", "USD"), ("USD", "JPY"), ("EUR", "GBP")])
def test_pairs_qualify_by_economics_and_not_symbol_allowlist(base, quote):
    result = compatibility(fx_contract(base, quote), fx_document())
    assert result["plan"]["base_currency"] == base
    assert result["plan"]["currency"] == quote
    assert result["rules"]["minimum_quantity"] == "1"
    assert Decimal(result["rules"]["standard_minimum"]) > 1


@pytest.mark.parametrize(
    "changes",
    [
        {"sec_type": "STK"},
        {"symbol": "XAU"},
        {"size_increment": None},
        {"routing_exchange": "FXCONV"},
    ],
)
def test_unknown_rules_and_non_currency_products_are_not_guessed(changes):
    result = compatibility({**fx_contract(), **changes}, fx_document())
    assert not result["can_prepare"] and result["blockers"]


def test_funded_exact_quantity_and_optional_ceilings():
    plan = compatibility(fx_contract(), fx_document())["plan"]
    result = size_fx(
        plan,
        {"quantity": "30000", "notional": None, "risk": None},
        Decimal("0.67"),
        Decimal("1"),
        Decimal("50000"),
        Decimal("4"),
    )
    assert result["quantity"] == "30000"
    assert Decimal(result["native_funds"]) > 20000
    with pytest.raises(ValueError, match="funds"):
        size_fx(
            plan,
            {"quantity": "30000", "notional": None, "risk": None},
            Decimal("0.67"),
            Decimal("1"),
            Decimal("10000"),
            Decimal("4"),
        )
    with pytest.raises(ValueError, match="ceiling"):
        size_fx(
            plan,
            {"quantity": "30000", "notional": "25", "risk": None},
            Decimal("0.67"),
            Decimal("1"),
            Decimal("50000"),
            Decimal("4"),
        )


def test_fx_sessions_enforce_daily_break_weekend_and_current_broker_evidence():
    session = FXSession(fx_contract())
    assert session.tradable(datetime(2026, 9, 24, 12, tzinfo=UTC))
    assert not session.tradable(datetime(2026, 9, 24, 21, 5, tzinfo=UTC))
    assert session.tradable(datetime(2026, 9, 24, 21, 15, tzinfo=UTC))
    assert not session.tradable(datetime(2026, 9, 26, 12, tzinfo=UTC))
    assert not FXSession({**fx_contract(), "trading_hours": ""}).tradable(
        datetime(2026, 9, 24, 12, tzinfo=UTC)
    )


def test_complete_flat_minute_and_boundary_crossing_use_strict_unrounded_high():
    start = datetime(2026, 9, 24, 12, tzinfo=UTC)
    signal = FXSignal(start - timedelta(seconds=1))
    for second in range(0, 60, 5):
        assert signal.observe(start + timedelta(seconds=second), Decimal("0.670025"), "day") is None
    assert signal.observe(start + timedelta(seconds=60), Decimal("0.670025"), "day") is None
    trigger = signal.observe(start + timedelta(seconds=61), Decimal("0.670026"), "day")
    assert trigger["high"] == "0.670025"
    assert signal.observe(start + timedelta(seconds=62), Decimal("0.67003"), "day") is None
    second = FXSignal(start - timedelta(seconds=1))
    for tick in range(0, 60, 5):
        second.observe(start + timedelta(seconds=tick), Decimal("0.67"), "day")
    assert second.observe(start + timedelta(seconds=60), Decimal("0.68"), "day")


def test_gap_and_session_change_never_replay_a_crossing():
    start = datetime(2026, 9, 24, 12, tzinfo=UTC)
    for next_time, interval in ((60, "new"), (90, "day")):
        signal = FXSignal(start - timedelta(seconds=1))
        for tick in range(0, 60, 5):
            signal.observe(start + timedelta(seconds=tick), Decimal("0.67"), "day")
        assert (
            signal.observe(start + timedelta(seconds=next_time), Decimal("0.68"), interval) is None
        )


def test_authorization_exactly_on_boundary_still_requires_next_complete_minute():
    start = datetime(2026, 9, 24, 12, tzinfo=UTC)
    signal = FXSignal(start)
    for second in range(0, 61, 5):
        assert signal.observe(start + timedelta(seconds=second), Decimal("0.65"), "day") is None
    assert signal.observe(start + timedelta(seconds=61), Decimal("0.66"), "day") is None


def test_trade_tick_replay_cannot_reinterpret_a_published_fx_price_source():
    from trading_oms_backend.workspace.market import replay

    with pytest.raises(ValueError, match="timestamped Midpoint/Bid/Ask"):
        replay(compile_graph(fx_document()), [])


@pytest.mark.parametrize("day,opening", [("20260308", 21), ("20261101", 22)])
def test_fx_sunday_open_observes_us_dst(day, opening):
    following = (datetime.strptime(day, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    contract = {**fx_contract(), "trading_hours": f"{day}:1715-{following}:1700"}
    session = FXSession(contract)
    stamp = datetime.strptime(day, "%Y%m%d").replace(hour=opening, minute=15, tzinfo=UTC)
    assert session.tradable(stamp)
    assert not session.tradable(stamp - timedelta(seconds=1))
    assert not FXSession({**contract, "trading_hours": day + ":CLOSED"}).tradable(stamp)
