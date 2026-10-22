"""Exchange sessions for schema-7 evaluation; legacy candle behavior stays separate."""

from datetime import datetime, timedelta

from .graph import number
from .market import Market
from .stock_sessions import StockSession


class StockMarket(Market):
    def __init__(self, graph, contract):
        super().__init__(graph)
        self.schedule = contract if isinstance(contract, StockSession) else StockSession(contract)

    def volume_value(self, value):
        if value is None:
            return None
        result = number(value)
        return result if result >= 0 else None

    def elapsed_seconds(self, stamp, opened):
        return int(self.schedule.elapsed(stamp))

    def session_bounds(self, stamp):
        return self.schedule.bounds(stamp)

    def tradable(self, stamp):
        return self.schedule.tradable(stamp)

    def expected_minutes(self, stamp, until=None):
        return set(range(len(self.schedule.minutes(stamp, until))))

    def history_day(self, day):
        return datetime.fromisoformat(day + "T09:00:00+00:00")

    def _finish_candle(self, candle):
        if self.closed:
            start = self.closed[-1].start + timedelta(
                seconds=self.graph.document["settings"]["timeframe"]
            )
            cursor = start
            gap = False
            while cursor < candle.start:
                if any(
                    max(a, start) < min(b, candle.start) for a, b in self.schedule.intervals(cursor)
                ):
                    gap = True
                    break
                cursor = cursor + timedelta(days=1)
            if gap:
                self.closed = []
                self.completed_emas = {period: None for period in self.completed_emas}
        super()._finish_candle(candle)

    def seed(self, minute_bars, fine_bars, stamp):
        super().seed(minute_bars, fine_bars, stamp)
        timeframe = self.graph.document["settings"]["timeframe"]
        if timeframe != 300:
            return
        # A five-minute history candle requires all five real source minutes.
        sources = {int(b["timestamp"]) for b in minute_bars}
        complete = [
            c
            for c in self.closed
            if all(int(c.start.timestamp()) + i * 60 in sources for i in range(5))
        ]
        self.closed = []
        self.completed_emas = {period: None for period in self.completed_emas}
        for candle in complete:
            self._finish_candle(candle)

    def accept(self, stamp, price, size):
        if not self.tradable(stamp):
            return None
        return super().accept(stamp, price, size)

    def context(self, stamp, transitioned=False):
        result = super().context(stamp, transitioned)
        if result:
            elapsed = self.schedule.elapsed(stamp) / 60
            result["minutes_from_open"] = elapsed
            # Session windows count eligible trading minutes across a scheduled break.
            for node in self.graph.ordered:
                if node["kind"] == "field" and node["params"]["field"] == "minutes_from_open":
                    result[node["id"]] = elapsed
        return result

    def live_candle_eligible(self, candle, stamp):
        interval = self.schedule.interval_start(stamp)
        return interval is not None and candle.start >= interval and self.tradable(candle.start)
