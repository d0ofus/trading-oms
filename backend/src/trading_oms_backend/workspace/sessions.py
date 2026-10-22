"""Exchange dates and broker-bounded paper execution windows."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

NY = ZoneInfo("America/New_York")


def next_session_day(stamp, hours="regular"):
    from .market import calendar

    cal = calendar()
    day = stamp.astimezone(NY).date()
    for offset in range(8):
        candidate = day + timedelta(days=offset)
        if not cal.is_session(candidate.isoformat()):
            continue
        end = (
            datetime.combine(candidate, time(20), NY).astimezone(UTC)
            if hours == "extended"
            else cal.session_close(candidate.isoformat()).to_pydatetime()
        )
        if stamp < end - timedelta(minutes=15):
            return candidate.isoformat()
    raise ValueError("No eligible exchange session in the next seven days.")


def execution_bounds(day, hours="regular", contract=None):
    from .market import calendar

    cal = calendar()
    if not cal.is_session(day):
        return None
    if hours == "regular":
        return cal.session_open(day).to_pydatetime(), cal.session_close(day).to_pydatetime()
    if hours != "extended" or not contract:
        return None
    try:
        zone = ZoneInfo(
            {"EST": "America/New_York"}.get(
                contract.get("time_zone"), contract.get("time_zone", "")
            )
        )
        windows = []
        for section in contract.get("trading_hours", "").split(";"):
            if not section or "CLOSED" in section:
                continue
            prefix, periods = section.split(":", 1)
            for period in periods.split(","):
                left, right = period.split("-")
                left = left if ":" in left else prefix + ":" + left
                right = right if ":" in right else prefix + ":" + right
                start = datetime.strptime(left, "%Y%m%d:%H%M").replace(tzinfo=zone).astimezone(UTC)
                end = datetime.strptime(right, "%Y%m%d:%H%M").replace(tzinfo=zone).astimezone(UTC)
                earliest = datetime.combine(
                    datetime.fromisoformat(day).date(), time(4), NY
                ).astimezone(UTC)
                latest = datetime.combine(
                    datetime.fromisoformat(day).date(), time(20), NY
                ).astimezone(UTC)
                start, end = max(start, earliest), min(end, latest)
                if end > start:
                    windows.append((start, end))
        # A disconnected schedule must not be flattened into an executable gap.
        windows.sort()
        if not windows:
            return None
        start, end = windows[0]
        for following, finish in windows[1:]:
            if following > end:
                return None
            end = max(end, finish)
        return start, end
    except (ValueError, KeyError, ZoneInfoNotFoundError):
        return None


def candle_bounds(stamp, extended=False):
    """Data can be captured in the envelope; dispatch separately checks broker hours."""
    from .market import session_bounds

    bounds = session_bounds(stamp)
    if not bounds or not extended:
        return bounds
    day = stamp.astimezone(NY).date()
    return (
        datetime.combine(day, time(4), NY).astimezone(UTC),
        datetime.combine(day, time(20), NY).astimezone(UTC),
    )
