"""Regular stock sessions, including exchange breaks and current broker schedules."""

from datetime import UTC, datetime, timedelta
from functools import lru_cache

from .store import Conflict


@lru_cache(maxsize=32)
def stock_calendar(name):
    import exchange_calendars

    try:
        return exchange_calendars.get_calendar(name, start="2000-01-01", end="2040-12-31")
    except (ValueError, KeyError) as exc:
        raise Conflict("A supported, verified exchange calendar is required.") from exc


class StockSession:
    def __init__(self, contract, session_mode="regular"):
        self.contract = contract
        self.extended = session_mode == "premarket_regular"
        self.calendar = stock_calendar(contract["stock_rules"]["calendar"])
        self._interval_cache = {}

    def intervals(self, stamp):
        day = stamp.astimezone(self.calendar.tz).date().isoformat()
        if day not in self._interval_cache:
            if len(self._interval_cache) >= 65:
                self._interval_cache.pop(next(iter(self._interval_cache)))
            self._interval_cache[day] = self._day_intervals(day)
        return self._interval_cache[day]

    def _day_intervals(self, day):
        if not self.calendar.is_session(day):
            return []
        start = self.calendar.session_open(day).to_pydatetime()
        end = self.calendar.session_close(day).to_pydatetime()
        if self.calendar.session_has_break(day):
            intervals = [
                (start, self.calendar.session_break_start(day).to_pydatetime()),
                (self.calendar.session_break_end(day).to_pydatetime(), end),
            ]
        else:
            intervals = [(start, end)]
        if self.extended:
            if not any(
                s.startswith(day.replace("-", "") + ":")
                for s in self.contract.get("liquid_hours", "").split(";")
            ):
                return []
            regular = StockSession(self.contract)._day_intervals(day)
            if not regular:
                return []
            early = start.astimezone(self.calendar.tz).replace(hour=4, minute=0).astimezone(UTC)
            intervals = [(early, start), *regular]
        # Broker schedules can narrow, never broaden the qualified regular calendar.
        schedule = self.contract.get("trading_hours" if self.extended else "liquid_hours", "")
        broker_intervals = []
        known = False
        compact_day = day.replace("-", "")
        for segment in schedule.split(";"):
            if not segment.startswith(compact_day + ":"):
                continue
            known = True
            raw = segment.split(":", 1)[1]
            if raw == "CLOSED":
                return []
            try:
                for interval in raw.split(","):
                    left, right = interval.split("-")
                    left = left if ":" in left else compact_day + ":" + left
                    right = right if ":" in right else compact_day + ":" + right
                    a, b = (
                        datetime.strptime(v, "%Y%m%d:%H%M")
                        .replace(tzinfo=self.calendar.tz)
                        .astimezone(UTC)
                        for v in (left, right)
                    )
                    if b <= a:
                        b += timedelta(days=1)
                    broker_intervals.append((a, b))
            except ValueError as exc:
                raise Conflict("Broker liquid hours are malformed; refresh the contract.") from exc
        if known:
            intervals = [
                (max(a, x), min(b, y))
                for a, b in intervals
                for x, y in broker_intervals
                if max(a, x) < min(b, y)
            ]
        elif self.extended:
            return []  # No current broker evidence: do not extrapolate extended sessions.
        return intervals

    def bounds(self, stamp):
        intervals = self.intervals(stamp)
        return (intervals[0][0], intervals[-1][1]) if intervals else None

    def tradable(self, stamp):
        return any(a <= stamp < b for a, b in self.intervals(stamp))

    def interval_start(self, stamp):
        return next((a for a, b in self.intervals(stamp) if a <= stamp < b), None)

    def elapsed(self, stamp):
        return sum(max(0, (min(stamp, b) - a).total_seconds()) for a, b in self.intervals(stamp))

    def minutes(self, stamp, until=None):
        bounds = self.bounds(stamp)
        if not bounds:
            return set()
        return {
            int((t - bounds[0]).total_seconds() // 60)
            for a, b in self.intervals(stamp)
            for i in range(int((b - a).total_seconds() // 60))
            if (t := a + timedelta(minutes=i)) < (until or b)
        }
