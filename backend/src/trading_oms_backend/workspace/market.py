from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache

from .graph import Compiled, GraphError, number


@lru_cache(maxsize=1)
def calendar():
    import exchange_calendars

    return exchange_calendars.get_calendar("XNYS", start="2000-01-01", end="2040-12-31")


def session_bounds(timestamp: datetime):
    from zoneinfo import ZoneInfo

    day = timestamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    return _session_day(day)


@lru_cache(maxsize=4096)
def _session_day(day):
    cal = calendar()
    if not cal.is_session(day):
        return None
    return cal.session_open(day).to_pydatetime(), cal.session_close(day).to_pydatetime()


def parse_tick(raw: dict):
    if not isinstance(raw, dict) or set(raw) != {"timestamp", "price", "size"}:
        raise GraphError("Ticks require timestamp, price and size only.")
    try:
        stamp = datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise GraphError("Use timezone-aware ISO timestamps in the tick dataset.") from exc
    if stamp.tzinfo is None:
        raise GraphError("Tick timestamps must include a timezone.")
    price, size = number(raw["price"]), number(raw["size"])
    if price <= 0 or size < 0:
        raise GraphError("Trade prices must be positive and sizes non-negative.")
    return stamp.astimezone(UTC), price, size


@dataclass
class Candle:
    start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def update(self, price, size):
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += size


class Market:
    def __init__(self, graph: Compiled):
        self.graph = graph
        self.current: Candle | None = None
        self.closed: list[Candle] = []
        self.previous_time: datetime | None = None
        self.day = None
        self.volume = Decimal(0)
        self.low = self.range_high = self.range_low = None
        self.day_complete = False
        self.minute_volumes: dict[int, Decimal] = {}
        self.history_volumes: list[dict[int, Decimal]] = []
        self.last_minute = -1
        self.last_entry: datetime | None = None
        self.session_seed_until: datetime | None = None
        self.bar_seed_until: datetime | None = None
        self.last_price: Decimal | None = None
        self.closed_until: datetime | None = None
        self.opening_ranges = {
            n["params"]["period"]: [None, None]
            for n in graph.ordered
            if n["kind"] == "field" and n["params"]["field"] in {"opening_high", "opening_low"}
        }
        self.completed_emas = {
            n["params"]["period"]: None
            for n in graph.ordered
            if n["kind"] == "field" and n["params"]["field"] == "ema"
        }

    def _finish_candle(self, candle):
        self.closed_until = candle.start + timedelta(
            seconds=self.graph.document["settings"]["timeframe"]
        )
        self.closed.append(candle)
        for period, previous in self.completed_emas.items():
            if previous is None:
                if len(self.closed) >= period:
                    self.completed_emas[period] = (
                        sum(b.close for b in self.closed[-period:]) / period
                    )
            else:
                alpha = Decimal(2) / (period + 1)
                self.completed_emas[period] = alpha * candle.close + (1 - alpha) * previous
        self.closed = self.closed[-1000:]

    def seed(self, minute_bars: list[dict], fine_bars: list[dict], stamp: datetime):
        """Warm indicators without evaluating signals or inventing historical ticks."""
        timeframe = self.graph.document["settings"]["timeframe"]
        bounds = session_bounds(stamp)
        if not bounds:
            return
        opened, _ = bounds
        stamp = stamp.replace(second=0, microsecond=0)
        self.session_seed_until = stamp
        by_day: dict[str, dict[int, dict]] = {}
        for bar in minute_bars:
            time = datetime.fromtimestamp(int(bar["timestamp"]), UTC)
            window = session_bounds(time)
            if window and window[0] <= time < window[1] and time + timedelta(minutes=1) <= stamp:
                by_day.setdefault(window[0].date().isoformat(), {})[
                    int((time - window[0]).total_seconds() // 60)
                ] = bar
        self.history_volumes = []
        for day, items in sorted(by_day.items()):
            if day >= opened.date().isoformat():
                continue
            window = session_bounds(datetime.fromisoformat(day + "T16:00:00+00:00"))
            expected = int((window[1] - window[0]).total_seconds() // 60)
            if set(items) != set(range(expected)):
                continue
            total, cumulative = Decimal(0), {}
            for minute, bar in sorted(items.items()):
                cumulative[minute] = total
                total += number(bar["volume"])
            self.history_volumes.append(cumulative)
        self.history_volumes = self.history_volumes[-10:]
        today = by_day.get(opened.date().isoformat(), {})
        elapsed = max(0, int((stamp - opened).total_seconds() // 60))
        self.day = opened.date()
        self.day_complete = set(today) == set(range(elapsed))
        self.volume = sum((number(b["volume"]) for b in today.values()), Decimal(0))
        self.low = min((number(b["low"]) for b in today.values()), default=None)
        opening = [b for i, b in today.items() if i < 5]
        self.range_high = max((number(b["high"]) for b in opening), default=None)
        self.range_low = min((number(b["low"]) for b in opening), default=None)
        for period in self.opening_ranges:
            window = [b for i, b in today.items() if i < period]
            self.opening_ranges[period] = [
                max((number(b["high"]) for b in window), default=None),
                min((number(b["low"]) for b in window), default=None),
            ]
        self.minute_volumes, self.last_minute = {}, elapsed - 1
        accumulated = Decimal(0)
        for minute, bar in sorted(today.items()):
            self.minute_volumes[minute] = accumulated
            accumulated += number(bar["volume"])
        grouped: dict[datetime, Candle] = {}
        for bar in sorted(
            fine_bars if timeframe == 5 else minute_bars, key=lambda b: int(b["timestamp"])
        ):
            time = datetime.fromtimestamp(int(bar["timestamp"]), UTC)
            window = session_bounds(time)
            if not window or not window[0] <= time < window[1]:
                continue
            start = window[0] + timedelta(
                seconds=int((time - window[0]).total_seconds()) // timeframe * timeframe
            )
            source_seconds = 5 if timeframe == 5 else 60
            if time + timedelta(seconds=source_seconds) > stamp:
                continue
            self.bar_seed_until = time + timedelta(seconds=source_seconds)
            if start not in grouped:
                grouped[start] = Candle(
                    start,
                    number(bar["open"]),
                    number(bar["high"]),
                    number(bar["low"]),
                    number(bar["close"]),
                    number(bar["volume"]),
                )
            else:
                candle = grouped[start]
                candle.high, candle.low = (
                    max(candle.high, number(bar["high"])),
                    min(candle.low, number(bar["low"])),
                )
                candle.close, candle.volume = (
                    number(bar["close"]),
                    candle.volume + number(bar["volume"]),
                )
        self.closed = []
        self.current = None
        for candle in grouped.values():
            if candle.start + timedelta(seconds=timeframe) <= stamp:
                self._finish_candle(candle)
            else:
                self.current = candle
        self.previous_time = None

    def accept(self, stamp, price, size):
        if price <= 0 or size < 0:
            raise GraphError("Invalid trade observation. Repair data before evaluating strategies.")
        if self.previous_time is not None and stamp < self.previous_time:
            raise GraphError("Out-of-order observations require data recovery.")
        if self.closed_until is not None and stamp < self.closed_until:
            raise GraphError("A late trade belongs to an already completed candle. Repair history.")
        bounds = session_bounds(stamp)
        if not bounds or not bounds[0] <= stamp < bounds[1]:
            return None
        opened, closed = bounds
        seconds = int((stamp - opened).total_seconds())
        new_day = opened.date() != self.day
        if new_day:
            if self.day_complete and self.minute_volumes:
                self.history_volumes.append(dict(self.minute_volumes))
                self.history_volumes = self.history_volumes[-10:]
            self.day = opened.date()
            self.day_complete = seconds < 1
            self.volume = Decimal(0)
            self.low = self.range_high = self.range_low = None
            self.minute_volumes = {}
            self.last_minute = -1
            self.current = None
            self.opening_ranges = {period: [None, None] for period in self.opening_ranges}
            self.session_seed_until = None
            self.bar_seed_until = None
        minute = seconds // 60
        if minute > self.last_minute:
            self.minute_volumes[minute] = self.volume
            self.last_minute = minute
        if self.session_seed_until is None or stamp >= self.session_seed_until:
            self.volume += size
            self.low = price if self.low is None else min(price, self.low)
            if seconds < 300:
                self.range_high = price if self.range_high is None else max(price, self.range_high)
                self.range_low = price if self.range_low is None else min(price, self.range_low)
            for period, window in self.opening_ranges.items():
                if seconds < period * 60:
                    window[0] = price if window[0] is None else max(price, window[0])
                    window[1] = price if window[1] is None else min(price, window[1])
        timeframe = self.graph.document["settings"]["timeframe"]
        start = opened + timedelta(seconds=seconds // timeframe * timeframe)
        transitioned = self.current is not None and self.current.start != start
        if transitioned:
            self._finish_candle(self.current)
        if self.current is None or transitioned:
            self.current = Candle(start, price, price, price, price, size)
        else:
            self.current.update(price, size)
        self.previous_time = stamp
        self.last_price = price
        return self.context(stamp, transitioned)

    def close_clock(self, stamp):
        if self.current is None or self.last_price is None:
            return None
        end = self.current.start + timedelta(seconds=self.graph.document["settings"]["timeframe"])
        if stamp < end:
            return None
        self._finish_candle(self.current)
        self.current = None
        return self.context(end, True)

    def context(self, stamp, transitioned=False):
        bounds = session_bounds(stamp)
        if not bounds:
            return None
        opened, closed = bounds
        seconds = int((stamp - opened).total_seconds())
        minute = seconds // 60
        timeframe = self.graph.document["settings"]["timeframe"]
        start = opened + timedelta(seconds=seconds // timeframe * timeframe)
        history = self.history_volumes
        relative = None
        if self.day_complete and len(history) == 10 and all(minute in h for h in history):
            average = sum(h[minute] for h in history) / 10
            relative = (
                self.minute_volumes.get(minute, self.volume) / average if average > 0 else None
            )
        context = {
            "last": self.last_price,
            "session_volume": self.volume if self.day_complete else None,
            "relative_volume": relative,
            "opening_high": self.range_high if self.day_complete and seconds >= 300 else None,
            "opening_low": self.range_low if self.day_complete and seconds >= 300 else None,
            "session_low": self.low if self.day_complete else None,
            "minutes_from_open": seconds / 60,
            "minutes_to_close": (closed - stamp).total_seconds() / 60,
            "since_entry": (stamp - self.last_entry).total_seconds() if self.last_entry else 1e12,
            "bar_closed": transitioned,
            "bar_start": start.isoformat(),
        }
        for node in self.graph.ordered:
            if node["kind"] != "field":
                continue
            params = node["params"]
            # In completed-candle mode, the first next-bar tick is only a clock:
            # the strategy sees the candle that just closed, not that next tick.
            forming = (
                params["source"] == "current"
                and self.graph.document["settings"]["evaluation"] == "intrabar"
            )
            bars = self.closed + ([self.current] if forming and self.current else [])
            period, field = params["period"], params["field"]
            value = context.get(field)
            if field in {"open", "high", "low", "close", "volume"}:
                value = getattr(bars[-1], field) if bars else None
            elif field == "prior_close":
                value = bars[-2].close if len(bars) >= 2 else None
            elif field in {"opening_high", "opening_low"}:
                value = (
                    self.opening_ranges[period][0 if field == "opening_high" else 1]
                    if self.day_complete and seconds >= period * 60
                    else None
                )
            elif field == "ema":
                value = self.completed_emas[period]
                if forming and self.current:
                    if value is not None:
                        alpha = Decimal(2) / (period + 1)
                        value = alpha * self.current.close + (1 - alpha) * value
                    elif len(bars) >= period:
                        value = sum(b.close for b in bars[-period:]) / period
            elif field in {"sma", "ema", "rolling_high", "rolling_low"}:
                value = None
                if len(bars) >= period:
                    window = bars[-period:]
                    if field == "sma":
                        value = sum(b.close for b in window) / period
                    elif field == "rolling_high":
                        value = max(b.high for b in window)
                    elif field == "rolling_low":
                        value = min(b.low for b in window)
                    else:
                        value = sum(b.close for b in bars[:period]) / period
                        alpha = Decimal(2) / (period + 1)
                        for bar in bars[period:]:
                            value = alpha * bar.close + (1 - alpha) * value
            context[node["id"]] = value
        return context


def replay(graph: Compiled, ticks: list[dict], directory=None) -> dict:
    from pathlib import Path
    from tempfile import TemporaryDirectory

    if directory is None:
        with TemporaryDirectory(prefix="oms-replay-") as temporary:
            return replay(graph, ticks, Path(temporary))
    from .replay_oms import ReplayOMS
    from .runtime import evaluate_step, size_entry
    from .store import Conflict

    if not 2 <= len(ticks) <= 250_000:
        raise GraphError("Select a tick dataset containing 2?250,000 observations.")
    market = Market(graph)
    state = {"graph": graph, "previous": {}, "entry": False, "seeded": False, "last_bar": None}
    settings = graph.document["settings"]
    profile = {"shares": 10, "planned_stop_risk": "10", "notional": "1000"}
    oms = ReplayOMS(directory, graph, ticks)
    trades, signals = [], []
    position = pending = None
    entry_count = 0
    current_day = previous_stamp = None
    realized = daily_realized = Decimal(0)
    target_required = any(n["kind"] == "target" for n in graph.ordered)
    for sequence, raw in enumerate(ticks):
        stamp, price, size = parse_tick(raw)
        bounds = session_bounds(stamp)
        if (
            previous_stamp
            and bounds
            and bounds[0] <= previous_stamp < stamp < bounds[1]
            and (stamp - previous_stamp).total_seconds() > 15
        ):
            raise GraphError(
                "Tick dataset has a gap longer than 15 seconds. Repair the capture before replay."
            )
        previous_stamp = stamp
        completed = market.close_clock(stamp)
        current = market.accept(stamp, price, size)
        if current is None:
            continue
        if market.day != current_day:
            entry_count, current_day, daily_realized = 0, market.day, Decimal(0)
        if pending:
            if (stamp - pending["at"]).total_seconds() > settings["entry_timeout"] or current[
                "minutes_to_close"
            ] <= 15:
                oms.cancel(pending)
                pending = None
            elif price <= pending["limit"]:
                oms.fill(pending, price)
                position = {**pending, "entry": price, "entered_at": stamp.isoformat()}
                pending = None
                market.last_entry = stamp
                entry_count += 1
        contexts = [completed] if completed is not None else []
        if settings["evaluation"] == "intrabar" or current["bar_closed"]:
            contexts.append(current)
        evaluated = [(context, *evaluate_step(state, context)) for context in contexts]
        if position:
            reason = (
                "protective_stop"
                if price <= position["stop"]
                else "target"
                if position["target"] is not None and price >= position["target"]
                else "session_exit"
                if current["minutes_to_close"] <= settings["exit_before_close"]
                else "condition"
                if any(r["exit"] is True for _, r, _ in evaluated)
                else None
            )
            if reason:
                oms.fill(position, price, exit=True)
                pnl = (price - position["entry"]) * position["quantity"]
                realized += pnl
                daily_realized += pnl
                trades.append(
                    {
                        "entered_at": position["entered_at"],
                        "exited_at": stamp.isoformat(),
                        "entry": str(position["entry"]),
                        "exit": str(price),
                        "quantity": position["quantity"],
                        "pnl": str(pnl),
                        "reason": reason,
                    }
                )
                position = None
        for context, result, signal in evaluated:
            if not (
                signal
                and not position
                and not pending
                and context["minutes_to_close"] > 15
                and entry_count < settings["max_entries"]
                and daily_realized > -100
            ):
                continue
            limit = (price * Decimal("1.001")).quantize(Decimal("0.01"))
            stop, target = result["stop"], result["target"]
            if target_required and target is None or target is not None and target <= limit:
                continue
            try:
                quantity = size_entry(settings, profile, limit, stop, Decimal(5000))
            except Conflict:
                continue
            intent = {"quantity": quantity, "limit": limit, "stop": stop, "target": target}
            durable = oms.entry(intent)
            pending = {**intent, **durable, "at": stamp}
            signals.append(
                {
                    "sequence": sequence,
                    "timestamp": stamp.isoformat(),
                    "quantity": quantity,
                    "limit": str(limit),
                    "stop": str(stop),
                }
            )
    oms.store.event("replay.finished", {"signals": len(signals), "trades": len(trades)})
    oms.store.verify()
    return {
        "mode": "replay",
        "evidence": "recorded_ticks_simulated_fills",
        "strategy_hash": graph.digest,
        "ticks": len(ticks),
        "signals": signals,
        "trades": trades,
        "realized_pnl": str(realized),
        "open_position": {
            "quantity": position["quantity"],
            "entry": str(position["entry"]),
            "stop": str(position["stop"]),
        }
        if position
        else None,
        "working_entry": pending is not None,
        "limitations": [
            "Simulated fills use the next eligible trade; fees and liquidity are not modeled.",
            "Open positions at dataset end remain open; no fill is invented.",
            "Quotes use a fixed simulated spread. "
            "Broker protection and network faults need separate trials.",
        ],
    }
