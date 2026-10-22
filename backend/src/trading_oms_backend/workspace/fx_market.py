"""Live-only FX minute latch; history can warm displays but can never trigger entries."""

from datetime import timedelta


class FXSignal:
    def __init__(self, live_after):
        self.live_after = live_after
        self.last_at = self.interval = self.minute = self.high = None
        self.previous = None
        self.complete = False
        self.triggered = False
        self.last_entry = None

    def observe(self, stamp, price, interval):
        if self.last_at and stamp < self.last_at:
            return None
        if self.triggered:
            if not self.previous or stamp.isoformat() < self.previous["expires_at"]:
                if self.last_at and (
                    (stamp - self.last_at).total_seconds() > 15 or interval != self.interval
                ):
                    self.previous = None
                    self.triggered = False
                else:
                    self.last_at = max(stamp, self.last_at) if self.last_at else stamp
                    self.high = max(self.high, price)
                    return None
            self.triggered = False
            self.previous = None
        if stamp < self.live_after or not interval:
            return None
        if self.last_at and stamp < self.last_at:
            return None
        minute = stamp.replace(second=0, microsecond=0)
        continuity = bool(
            self.last_at
            and (stamp - self.last_at).total_seconds() <= 15
            and interval == self.interval
        )
        if not continuity:
            self.previous = None
            self.complete = stamp == minute and minute > self.live_after
            self.minute, self.high = minute, price
        elif minute != self.minute:
            self.previous = {
                "candle": self.minute.isoformat(),
                "high": str(self.high),
                "expires_at": (minute + timedelta(minutes=1)).isoformat(),
            }
            if not self.complete or minute != self.minute + timedelta(minutes=1):
                self.previous = None
            self.minute, self.high = minute, price
            self.complete = minute > self.live_after
        else:
            self.high = max(self.high, price)
        self.last_at, self.interval = stamp, interval
        if self.previous and stamp.isoformat() < self.previous["expires_at"]:
            from decimal import Decimal

            if price > Decimal(self.previous["high"]):
                self.triggered = True
                return {**self.previous, "price": str(price), "triggered_at": stamp.isoformat()}
        return None
