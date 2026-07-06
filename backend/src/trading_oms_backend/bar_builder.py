from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from trading_oms_backend.market_data_replay import MarketDataReplayEvent


class BarBuildError(ValueError):
    """Raised when replay events cannot be converted into deterministic bars."""


@dataclass(frozen=True)
class BarBuilderConfig:
    symbol: str
    timeframe: timedelta
    quote_price_source: str | None = None


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe_seconds: int
    start_timestamp: str
    end_timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    event_count: int
    schema_version: int = 1

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "timeframe_seconds": self.timeframe_seconds,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "event_count": self.event_count,
        }


@dataclass
class _OpenBar:
    symbol: str
    timeframe_seconds: int
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    event_count: int

    def update(self, price: float, volume: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume
        self.event_count += 1

    def close_bar(self) -> Bar:
        end = self.start + timedelta(seconds=self.timeframe_seconds)
        return Bar(
            symbol=self.symbol,
            timeframe_seconds=self.timeframe_seconds,
            start_timestamp=_format_timestamp(self.start),
            end_timestamp=_format_timestamp(end),
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            event_count=self.event_count,
        )


def build_time_bars(
    events: Iterable[MarketDataReplayEvent],
    config: BarBuilderConfig,
) -> list[Bar]:
    timeframe_seconds = _validated_timeframe_seconds(config.timeframe)
    symbol = _validated_symbol(config.symbol)
    _validate_quote_price_source(config.quote_price_source)

    bars: list[Bar] = []
    open_bar: _OpenBar | None = None
    previous_timestamp: datetime | None = None

    for event in events:
        if event.symbol != symbol:
            raise BarBuildError(
                f"event symbol {event.symbol} does not match configured symbol {symbol}"
            )

        event_timestamp = event.parsed_timestamp().astimezone(UTC)
        if previous_timestamp is not None and event_timestamp < previous_timestamp:
            raise BarBuildError("event timestamps must be nondecreasing")
        previous_timestamp = event_timestamp

        price, volume = _price_and_volume(event, config.quote_price_source)
        bucket_start = _bucket_start(event_timestamp, timeframe_seconds)

        if open_bar is None:
            open_bar = _new_open_bar(symbol, timeframe_seconds, bucket_start, price, volume)
            continue

        if bucket_start != open_bar.start:
            bars.append(open_bar.close_bar())
            open_bar = _new_open_bar(symbol, timeframe_seconds, bucket_start, price, volume)
            continue

        open_bar.update(price, volume)

    if open_bar is not None:
        bars.append(open_bar.close_bar())

    return bars


def _new_open_bar(
    symbol: str,
    timeframe_seconds: int,
    start: datetime,
    price: float,
    volume: float,
) -> _OpenBar:
    return _OpenBar(
        symbol=symbol,
        timeframe_seconds=timeframe_seconds,
        start=start,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=volume,
        event_count=1,
    )


def _validated_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise BarBuildError("symbol must be a non-empty string")
    if symbol != symbol.strip():
        raise BarBuildError("symbol must not contain leading or trailing whitespace")
    if symbol != symbol.upper():
        raise BarBuildError("symbol must be uppercase")
    return symbol


def _validated_timeframe_seconds(timeframe: timedelta) -> int:
    if not isinstance(timeframe, timedelta):
        raise BarBuildError("timeframe must be a datetime.timedelta")

    timeframe_seconds = timeframe.total_seconds()
    if not timeframe_seconds.is_integer() or timeframe_seconds <= 0:
        raise BarBuildError("timeframe must be a positive whole-second duration")
    return int(timeframe_seconds)


def _validate_quote_price_source(quote_price_source: str | None) -> None:
    if quote_price_source is None:
        return
    if quote_price_source not in {"bid", "ask", "mid"}:
        raise BarBuildError("quote_price_source must be one of bid, ask, or mid")


def _price_and_volume(
    event: MarketDataReplayEvent,
    quote_price_source: str | None,
) -> tuple[float, float]:
    if event.event_type == "trade":
        price = _positive_number(event.payload.get("price"), "price")
        volume = _event_volume(event.payload)
        return price, volume

    if event.event_type == "quote":
        if quote_price_source is None:
            raise BarBuildError("quote events require an explicit quote_price_source")
        return _quote_price(event.payload, quote_price_source), 0.0

    raise BarBuildError(f"unsupported market-data event type for bar building: {event.event_type}")


def _quote_price(payload: dict[str, Any], quote_price_source: str) -> float:
    if quote_price_source == "bid":
        return _positive_number(payload.get("bid"), "bid")
    if quote_price_source == "ask":
        return _positive_number(payload.get("ask"), "ask")

    bid = _positive_number(payload.get("bid"), "bid")
    ask = _positive_number(payload.get("ask"), "ask")
    if ask < bid:
        raise BarBuildError("ask must be greater than or equal to bid")
    return (bid + ask) / 2


def _event_volume(payload: dict[str, Any]) -> float:
    if "size" in payload:
        return _nonnegative_number(payload["size"], "size")
    if "volume" in payload:
        return _nonnegative_number(payload["volume"], "volume")
    return 0.0


def _positive_number(value: Any, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if number <= 0:
        raise BarBuildError(f"{field_name} must be greater than zero")
    return number


def _nonnegative_number(value: Any, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if number < 0:
        raise BarBuildError(f"{field_name} must be nonnegative")
    return number


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise BarBuildError(f"{field_name} must be a finite number")

    number = float(value)
    if not math.isfinite(number):
        raise BarBuildError(f"{field_name} must be a finite number")
    return number


def _bucket_start(timestamp: datetime, timeframe_seconds: int) -> datetime:
    epoch_seconds = int(timestamp.timestamp())
    bucket_epoch_seconds = epoch_seconds - (epoch_seconds % timeframe_seconds)
    return datetime.fromtimestamp(bucket_epoch_seconds, tz=UTC)


def _format_timestamp(timestamp: datetime) -> str:
    return timestamp.isoformat().replace("+00:00", "Z")
