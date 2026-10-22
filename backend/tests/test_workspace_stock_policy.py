"""Stock policies use synthetic contracts; no broker session or production state."""

import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from trading_oms_backend.workspace.graph import compile_graph
from trading_oms_backend.workspace.reusable import shared_templates
from trading_oms_backend.workspace.stock_policy import compatibility, fx_rate, size_stock
from trading_oms_backend.workspace.stock_sessions import StockSession
from trading_oms_backend.workspace.stock_strategies import stock_copy
from trading_oms_backend.workspace.store import Conflict


def contract():
    return {
        "conid": 323608988,
        "symbol": "1810",
        "sec_type": "STK",
        "currency": "HKD",
        "primary_exchange": "SEHK",
        "routing_exchange": "SEHK",
        "resolved": True,
        "order_types": ["MKT", "LMT", "STP"],
        "market_rule": 1,
        "stock_rules": {
            "revision": 1,
            "source": "operator_verified",
            "reference": "TWS contract details",
            "calendar": "XHKG",
            "quantity_increment": "200",
            "minimum_quantity": "200",
            "exit_increment": "1",
            "price_scale": "1",
            "same_day_resale": True,
            "broker_protection": True,
            "native_oca": True,
            "local_protection": True,
            "fractional_protection": False,
            "fee_reserve": "25",
            "currency": "HKD",
        },
    }


def test_stock_copy_preserves_old_hashes_and_all_canvas_nodes():
    for item in shared_templates():
        old = copy.deepcopy(item["document"])
        old_hash = compile_graph(old).digest
        converted = stock_copy(old)
        assert converted["schema_version"] == 7
        assert converted["nodes"] == old["nodes"]
        assert converted["edges"] == old["edges"]
        assert converted["settings"]["notional"] == old["settings"]["notional"]
        assert compile_graph(converted).digest != old_hash
        assert compile_graph(old).digest == old_hash
        assert item["document"] == old


@pytest.mark.parametrize("us", [False, True])
def test_all_templates_assess_stock_without_claiming_broker_acceptance(us):
    c = contract()
    if us:
        c.update(
            currency="USD",
            symbol="SPY",
            conid=100,
            routing_exchange="SMART",
            primary_exchange="ARCA",
        )
        c["stock_rules"].update(
            currency="USD",
            calendar="XNYS",
            minimum_quantity="1",
            quantity_increment="1",
            fee_reserve="1",
        )
    for item in shared_templates():
        result = compatibility(c, stock_copy(item["document"]))
        assert result["status"] == "needs_qualification"
        assert not result["blockers"]
        assert result["plan"]["currency"] == c["currency"]
        assert result["plan"]["risk_currency"] == "USD"


def test_stock_replay_is_explicitly_synthetic_and_preserves_published_hash():
    from trading_oms_backend.workspace.market import replay

    graph = compile_graph(stock_copy(shared_templates()[1]["document"]))
    original = copy.deepcopy(graph.document)
    start = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    ticks = [
        {"timestamp": (start + timedelta(seconds=i)).isoformat(), "price": "100", "size": "1"}
        for i in range(0, 180, 10)
    ]
    result = replay(graph, ticks)
    assert result["strategy_hash"] == graph.digest
    assert any("synthetic USD" in text for text in result["limitations"])
    assert graph.document == original


def test_minor_unit_prices_and_combined_oca_budget_use_conservative_usd():
    c = contract()
    c["stock_rules"].update(price_scale="0.01", minimum_quantity="1", quantity_increment="1")
    settings = {"notional": "1000", "risk": "10", "sizing": "risk"}
    profile = {"notional": "1000", "planned_stop_risk": "10", "stock_units": 1}
    quantity, reserved = size_stock(
        settings,
        profile,
        c,
        [(Decimal(3000), Decimal(2970)), (Decimal(2900), Decimal(2929))],
        Decimal("0.128"),
        Decimal(10000),
        Decimal(10000),
    )
    assert quantity == 1
    assert Decimal(reserved["notional"]) == Decimal("7.552")
    assert Decimal(reserved["risk"]) == Decimal("0.07552")
    assert reserved["native_funds"] == "109.00"


@pytest.mark.parametrize(
    "field", ["quantity_increment", "exit_increment", "price_scale", "calendar"]
)
def test_missing_evidence_is_not_replaced_by_defaults(field):
    c = contract()
    del c["stock_rules"][field]
    result = compatibility(c, stock_copy(shared_templates()[0]["document"]))
    assert result["status"] == "unknown"
    assert result["blockers"]


def test_short_structure_cannot_fall_back_to_local_cancellation():
    c = contract()
    c["stock_rules"]["native_oca"] = False
    paired = stock_copy(shared_templates()[2]["document"])
    assert compatibility(c, paired, "locally_monitored")["blockers"]
    long = stock_copy(shared_templates()[-1]["document"])
    assert not compatibility(c, long, "locally_monitored")["blockers"]


def test_currency_uses_conservative_side_and_rejects_stale_or_future_quotes():
    stamp = datetime(2026, 9, 22, 3, tzinfo=UTC)
    q = {
        "live": True,
        "base": "USD",
        "quote": "HKD",
        "bid": "7.80",
        "ask": "7.82",
        "received_at": stamp.isoformat(),
    }
    assert fx_rate("HKD", [q], stamp) == Decimal(1) / Decimal("7.80")
    for seconds in (-61, 1):
        q["received_at"] = (stamp + timedelta(seconds=seconds)).isoformat()
        with pytest.raises(Conflict):
            fx_rate("HKD", [q], stamp)


def test_board_lot_risk_is_usd_and_never_increases_a_small_budget():
    c = contract()
    settings = {"notional": "1000", "risk": "10", "sizing": "risk", "shares": "200"}
    profile = {"notional": "1000", "planned_stop_risk": "10", "stock_units": 1}
    quantity, reservation = size_stock(
        settings,
        profile,
        c,
        [(Decimal(30), Decimal("29.7"))],
        Decimal("0.13"),
        Decimal(10000),
        Decimal(10000),
    )
    assert quantity == 200
    assert reservation["notional"] == "780.00"
    assert Decimal(reservation["risk"]) == Decimal("7.8")
    assert Decimal(reservation["native_funds"]) == Decimal(6025)
    settings["notional"] = "25"
    with pytest.raises(Conflict, match="minimum"):
        size_stock(
            settings,
            profile,
            c,
            [(Decimal(30), Decimal("29.7"))],
            Decimal("0.13"),
            Decimal(10000),
            Decimal(10000),
        )


def test_lunch_is_same_session_but_not_an_entry_interval():
    session = StockSession(contract())
    morning = datetime(2026, 9, 22, 3, 59, tzinfo=UTC)
    lunch = datetime(2026, 9, 22, 4, 30, tzinfo=UTC)
    afternoon = datetime(2026, 9, 22, 5, 0, tzinfo=UTC)
    assert session.bounds(morning) == session.bounds(afternoon)
    assert session.tradable(morning)
    assert not session.tradable(lunch)
    assert session.tradable(afternoon)
    assert session.elapsed(afternoon) == 150 * 60
    assert session.interval_start(afternoon) == afternoon


def test_non_stock_and_same_day_resale_restriction_fail_closed():
    document = stock_copy(shared_templates()[0]["document"])
    c = contract()
    c["sec_type"] = "CFD"
    assert compatibility(c, document)["status"] == "incompatible"
    c = contract()
    c["stock_rules"]["same_day_resale"] = False
    assert compatibility(c, document)["blockers"]
