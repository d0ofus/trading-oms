"""Current broker FX intervals intersected with the versioned IDEALPRO week."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .store import Conflict

POLICY = "idealpro_fx_week_v1"
EASTERN = ZoneInfo("America/New_York")


class FXSession:
    def __init__(self, contract):
        self.contract = contract
        name = contract.get("time_zone", "")
        if name in {"US/Eastern", "EST", "EST5EDT"}:
            name = "America/New_York"
        try:
            self.zone = ZoneInfo(name)
        except (ValueError, KeyError) as exc:
            raise Conflict("Current broker FX time-zone evidence is required.") from exc
        self.broker_intervals = []
        try:
            for segment in contract.get("trading_hours", "").split(";"):
                if not segment:
                    continue
                day, raw = segment.split(":", 1)
                if raw == "CLOSED":
                    continue
                for interval in raw.split(","):
                    left, right = interval.split("-")
                    a, b = (
                        datetime.strptime(v if ":" in v else day + ":" + v, "%Y%m%d:%H%M")
                        .replace(tzinfo=self.zone)
                        .astimezone(UTC)
                        for v in (left, right)
                    )
                    if b <= a:
                        b += timedelta(days=1)
                    self.broker_intervals.append((a, b))
        except ValueError as exc:
            raise Conflict("Broker FX trading hours are malformed; refresh the contract.") from exc

    def intervals(self, stamp):
        local = stamp.astimezone(EASTERN)
        result = []
        for offset in (-1, 0):
            day = local.date() + timedelta(days=offset)
            if day.weekday() in (4, 5):
                continue  # No Friday/Saturday evening session.
            a = datetime.combine(day, datetime.min.time(), EASTERN).replace(hour=17, minute=15)
            b = (a + timedelta(days=1)).replace(hour=17, minute=0)
            for x, y in self.broker_intervals:
                start, end = max(a.astimezone(UTC), x), min(b.astimezone(UTC), y)
                if start < end and start <= stamp < end:
                    result.append((start, end))
        return result

    def tradable(self, stamp):
        return bool(self.intervals(stamp))

    def bounds(self, stamp):
        intervals = self.intervals(stamp)
        return intervals[0] if intervals else None

    def interval_start(self, stamp):
        bounds = self.bounds(stamp)
        return bounds[0] if bounds else None
