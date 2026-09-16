from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trading_oms_backend.workspace.graph import compile_graph, templates
from trading_oms_backend.workspace.market import Market, replay, session_bounds


def test_exchange_holidays_and_early_close():
    assert session_bounds(datetime(2026, 12, 25, 15, tzinfo=UTC)) is None
    bounds = session_bounds(datetime(2026, 11, 27, 15, tzinfo=UTC))
    assert bounds[1].hour == 18  # 13:00 New York, not a hard-coded 16:00.


def test_completed_candle_evaluation_does_not_read_next_candle():
    document = templates()[1]["document"]
    document["settings"]["evaluation"] = "bar_close"
    market = Market(compile_graph(document))
    start = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    market.accept(start, Decimal(100), Decimal(10))
    value = market.accept(start + timedelta(seconds=60), Decimal(200), Decimal(1))
    assert value["bar_closed"]
    assert value["price"] == Decimal(100)
    assert value["last"] == Decimal(200)


def test_forming_ema_does_not_accumulate_intrabar_updates():
    document = templates()[1]["document"]
    node = next(n for n in document["nodes"] if n["id"] == "sma_fast")
    node["params"].update(field="ema", period=2)
    graph = compile_graph(document)
    noisy, sparse = Market(graph), Market(graph)
    start = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    for market in (noisy, sparse):
        market.accept(start, Decimal(100), Decimal(1))
        market.accept(start + timedelta(seconds=60), Decimal(110), Decimal(1))
    noisy.accept(start + timedelta(seconds=65), Decimal(900), Decimal(1))
    final = start + timedelta(seconds=70)
    assert (
        noisy.accept(final, Decimal(120), Decimal(1))["sma_fast"]
        == sparse.accept(final, Decimal(120), Decimal(1))["sma_fast"]
    )


def test_tick_replay_is_deterministic_and_does_not_invent_terminal_fills():
    document = templates()[1]["document"]
    for node in document["nodes"]:
        if node["id"] == "sma_fast":
            node["params"]["period"] = 2
        if node["id"] == "sma_slow":
            node["params"]["period"] = 3
    start = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    ticks = [
        {
            "timestamp": (start + timedelta(seconds=i)).isoformat(),
            "price": str([105, 103, 100, 101, 108][i // 60]),
            "size": "10",
        }
        for i in range(0, 241, 10)
    ]
    ticks.append(
        {
            "timestamp": (start + timedelta(minutes=4, seconds=10)).isoformat(),
            "price": "108",
            "size": "10",
        }
    )
    graph = compile_graph(document)
    result = replay(graph, ticks)
    assert result == replay(graph, ticks)
    assert result["signals"]
    assert result["open_position"]
    assert result["trades"] == []


def test_opening_range_length_changes_the_executable_value():
    document = templates()[0]["document"]
    next(n for n in document["nodes"] if n["id"] == "range")["params"]["period"] = 1
    market = Market(compile_graph(document))
    start = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    market.accept(start, Decimal(100), Decimal(1))
    market.accept(start + timedelta(seconds=30), Decimal(105), Decimal(1))
    value = market.accept(start + timedelta(seconds=61), Decimal(110), Decimal(1))
    assert value["range"] == 105


def test_history_seed_preserves_partial_five_minute_candle():
    document = templates()[1]["document"]
    document["settings"]["timeframe"] = 300
    market = Market(compile_graph(document))
    start = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    bars = [
        {
            "timestamp": str(int((start + timedelta(minutes=i)).timestamp())),
            "open": str(100 + i),
            "high": str(101 + i),
            "low": "99",
            "close": str(100 + i),
            "volume": "10",
        }
        for i in range(2)
    ]
    market.seed(bars, [], start + timedelta(minutes=2))
    market.accept(start + timedelta(minutes=2, seconds=1), Decimal(105), Decimal(2))
    assert market.current.open == 100
    assert market.current.low == 99
    assert market.current.high == 105
    assert market.current.volume == 22
    assert market.volume == 22


def test_clock_closes_a_candle_once_without_inventing_another_trade():
    document = templates()[1]["document"]
    document["settings"]["evaluation"] = "bar_close"
    market = Market(compile_graph(document))
    start = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    market.accept(start, Decimal(100), Decimal(10))
    result = market.close_clock(start + timedelta(seconds=60))
    assert result["price"] == 100
    assert result["bar_closed"]
    assert market.current is None
    assert market.close_clock(start + timedelta(seconds=60)) is None
    market.accept(start + timedelta(seconds=61), Decimal(200), Decimal(3))
    assert market.closed[-1].volume == 10
    assert market.current.volume == 3


def test_opening_range_volume_template_executes_after_ten_reference_sessions(tmp_path):
    from trading_oms_backend.workspace.market import calendar
    from trading_oms_backend.workspace.store import Store

    cal = calendar()
    sessions = cal.sessions_in_range("2026-08-31", "2026-09-16")[:11]
    ticks = []
    for index, day in enumerate(sessions):
        opened = cal.session_open(day).to_pydatetime()
        duration = int((cal.session_close(day).to_pydatetime() - opened).total_seconds())
        for second in range(0, duration, 10):
            ticks.append(
                {
                    "timestamp": (opened + timedelta(seconds=second)).isoformat(),
                    "price": "101" if index == 10 and second >= 300 else "100",
                    "size": "30" if index == 10 else "10",
                }
            )
    result = replay(compile_graph(templates()[0]["document"]), ticks, tmp_path)
    assert result["signals"]
    assert len(result["trades"]) == 1
    assert result["trades"][0]["reason"] == "session_exit"
    assert result["open_position"] is None
    store = Store(tmp_path)
    assert store.orders()[0]["state"] == "filled"
    assert any(e["type"] == "execution.received" for e in store.events())


def test_replay_rejects_unrepaired_intrabar_gaps():
    import pytest

    from trading_oms_backend.workspace.graph import GraphError

    ticks = [
        {"timestamp": f"2026-09-15T13:{minute}:00+00:00", "price": "100", "size": "1"}
        for minute in ["30", "32"]
    ]
    with pytest.raises(GraphError, match="gap"):
        replay(compile_graph(templates()[1]["document"]), ticks)
