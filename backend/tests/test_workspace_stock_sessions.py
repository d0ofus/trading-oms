from datetime import UTC, datetime, timedelta
from decimal import Decimal

from test_workspace_stock_policy import contract

from trading_oms_backend.workspace.graph import compile_graph
from trading_oms_backend.workspace.stock_market import StockMarket
from trading_oms_backend.workspace.stock_sessions import StockSession
from trading_oms_backend.workspace.stock_strategies import stock_templates


def test_hk_holiday_half_day_and_us_dst():
    hk = StockSession(contract())
    assert not hk.intervals(datetime(2026, 10, 1, 3, tzinfo=UTC))
    assert hk.bounds(datetime(2026, 12, 24, 3, tzinfo=UTC))[1].hour == 4
    us = contract()
    us["stock_rules"]["calendar"] = "XNYS"
    market = StockSession(us)
    assert market.bounds(datetime(2026, 3, 6, 16, tzinfo=UTC))[0].hour == 14
    assert market.bounds(datetime(2026, 3, 9, 16, tzinfo=UTC))[0].hour == 13


def test_broker_liquid_hours_can_narrow_calendar_and_lunch_never_creates_bars():
    c = contract()
    c["liquid_hours"] = "20260922:0930-20260922:1200,1300-20260922:1500"
    graph = compile_graph(stock_templates()[-1]["document"])
    market = StockMarket(graph, c)
    before = datetime(2026, 9, 22, 3, 59, tzinfo=UTC)
    market.accept(before, Decimal(30), Decimal(1))
    market.close_clock(before + timedelta(minutes=1))
    assert len(market.closed) == 1
    assert market.accept(datetime(2026, 9, 22, 4, 30, tzinfo=UTC), Decimal(31), Decimal(2)) is None
    reopened = datetime(2026, 9, 22, 5, tzinfo=UTC)
    assert not market.live_candle_eligible(market.closed[-1], reopened)
    context = market.accept(reopened, Decimal(31), Decimal(2))
    assert context["minutes_from_open"] == 150
    assert len(market.closed) == 1
    assert market.schedule.bounds(reopened)[1].hour == 7


def test_unknown_volume_does_not_become_zero_or_break_price_only_warmup():
    graph = compile_graph(stock_templates()[1]["document"])
    market = StockMarket(graph, contract())
    stamp = datetime(2026, 9, 22, 2, tzinfo=UTC)
    bars = [
        {
            "timestamp": str(int((stamp - timedelta(minutes=i)).timestamp())),
            "open": "30",
            "high": "31",
            "low": "29",
            "close": "30",
            "volume": None,
        }
        for i in range(1, 26)
    ]
    market.seed(bars, [], stamp)
    assert market.closed and market.closed[-1].volume is None
    assert market.volume is None
    assert market.closed[-1].close == Decimal(30)
    assert not market.history_volumes


def test_missing_history_minute_cannot_be_fabricated_as_complete_five_minute_bar():
    document = stock_templates()[1]["document"]
    document["settings"]["timeframe"] = 300
    market = StockMarket(compile_graph(document), contract())
    opened = datetime(2026, 9, 22, 1, 30, tzinfo=UTC)
    bars = [
        {
            "timestamp": str(int((opened + timedelta(minutes=i)).timestamp())),
            "open": "30",
            "high": "31",
            "low": "29",
            "close": "30",
            "volume": "1",
        }
        for i in (0, 1, 3, 4)
    ]
    market.seed(bars, [], opened + timedelta(minutes=5))
    assert not market.closed


def test_premarket_dst_holidays_half_days_and_current_broker_evidence():
    from test_workspace_preparation_policy import meta

    from trading_oms_backend.workspace.stock_rules import resolve_rules

    c = meta()
    c["stock_rules"], _ = resolve_rules(c, {"amount": "1", "revision": 1})
    for day, utc_open, utc_close in (("20260306", 9, 21), ("20260309", 8, 20), ("20261127", 9, 18)):
        c["trading_hours"] = f"{day}:0400-{day}:2000"
        c["liquid_hours"] = f"{day}:0930-{day}:1600"
        stamp = datetime.strptime(day, "%Y%m%d").replace(tzinfo=UTC, hour=16)
        s = StockSession(c, "premarket_regular")
        assert s.bounds(stamp)[0].hour == utc_open
        assert s.bounds(stamp)[1].hour == utc_close
        assert len(s.intervals(stamp)) == 2
        assert not s.tradable(s.bounds(stamp)[1])
    assert not StockSession(c, "premarket_regular").intervals(
        datetime(2026, 11, 26, 16, tzinfo=UTC)
    )
    c["trading_hours"] = "20260922:0800-20260922:2000"
    c["liquid_hours"] = "20260922:0930-20260922:1600"
    stamp = datetime(2026, 9, 22, 14, tzinfo=UTC)
    assert StockSession(c, "premarket_regular").bounds(stamp)[0].hour == 12
    c["liquid_hours"] = "20260921:0930-20260921:1600"
    assert not StockSession(c, "premarket_regular").intervals(stamp)
