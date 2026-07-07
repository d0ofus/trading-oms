from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.event_journal import JsonlEventJournal

SIGNAL_EVENT_TYPE = "strategy.signal.generated"
STRATEGY_TYPE = "close_above_sma"
VALID_SIGNALS = {"long_bias", "risk_off_bias"}


class ReplayStrategyError(ValueError):
    """Raised when replay-only strategy inputs or outputs are invalid."""


@dataclass(frozen=True)
class ReplayStrategyConfig:
    strategy_id: str
    symbol: str
    lookback_bars: int = 3
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ReplayStrategyError("schema_version must be 1")
        _validated_identifier(self.strategy_id, "strategy_id")
        _validated_symbol(self.symbol)
        if not isinstance(self.lookback_bars, int) or self.lookback_bars < 2:
            raise ReplayStrategyError("lookback_bars must be an integer greater than or equal to 2")


@dataclass(frozen=True)
class ReplayStrategySignal:
    strategy_id: str
    symbol: str
    bar_start_timestamp: str
    bar_end_timestamp: str
    signal: str
    close: float
    moving_average: float
    lookback_bars: int
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "strategy_type": STRATEGY_TYPE,
            "symbol": self.symbol,
            "bar_start_timestamp": self.bar_start_timestamp,
            "bar_end_timestamp": self.bar_end_timestamp,
            "signal": self.signal,
            "close": self.close,
            "moving_average": self.moving_average,
            "lookback_bars": self.lookback_bars,
            "reason": self.reason,
        }

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ReplayStrategyError("schema_version must be 1")
        _validated_identifier(self.strategy_id, "strategy_id")
        _validated_symbol(self.symbol)
        _parse_timestamp(self.bar_start_timestamp, "bar_start_timestamp")
        _parse_timestamp(self.bar_end_timestamp, "bar_end_timestamp")
        if self.signal not in VALID_SIGNALS:
            raise ReplayStrategyError("signal must be one of long_bias or risk_off_bias")
        _positive_finite_number(self.close, "close")
        _positive_finite_number(self.moving_average, "moving_average")
        if not isinstance(self.lookback_bars, int) or self.lookback_bars < 2:
            raise ReplayStrategyError("lookback_bars must be an integer greater than or equal to 2")
        _validated_identifier(self.reason, "reason")
        try:
            json.dumps(self.to_json_dict(), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ReplayStrategyError("signal payload must be JSON-serializable") from exc


def run_close_above_sma_strategy(
    bars: Iterable[Bar],
    config: ReplayStrategyConfig,
    journal: JsonlEventJournal,
) -> list[ReplayStrategySignal]:
    bar_list = list(bars)
    _validate_bars(bar_list, config)

    signals: list[ReplayStrategySignal] = []
    for index in range(config.lookback_bars - 1, len(bar_list)):
        window = bar_list[index - config.lookback_bars + 1 : index + 1]
        close = bar_list[index].close
        moving_average = sum(bar.close for bar in window) / config.lookback_bars
        signal_name = "long_bias" if close > moving_average else "risk_off_bias"
        reason = "close_above_sma" if signal_name == "long_bias" else "close_at_or_below_sma"

        signal = ReplayStrategySignal(
            strategy_id=config.strategy_id,
            symbol=config.symbol,
            bar_start_timestamp=bar_list[index].start_timestamp,
            bar_end_timestamp=bar_list[index].end_timestamp,
            signal=signal_name,
            close=close,
            moving_average=moving_average,
            lookback_bars=config.lookback_bars,
            reason=reason,
        )
        journal.append(
            event_type=SIGNAL_EVENT_TYPE,
            payload=signal.to_json_dict(),
            timestamp=signal.bar_end_timestamp,
        )
        signals.append(signal)

    return signals


def _validate_bars(bars: list[Bar], config: ReplayStrategyConfig) -> None:
    previous_start: datetime | None = None
    timeframe_seconds: int | None = None

    for bar in bars:
        if bar.symbol != config.symbol:
            raise ReplayStrategyError(
                f"bar symbol {bar.symbol} does not match configured symbol {config.symbol}"
            )
        if timeframe_seconds is None:
            timeframe_seconds = bar.timeframe_seconds
        elif bar.timeframe_seconds != timeframe_seconds:
            raise ReplayStrategyError("all bars must use the same timeframe")

        start = _parse_timestamp(bar.start_timestamp, "bar_start_timestamp")
        end = _parse_timestamp(bar.end_timestamp, "bar_end_timestamp")
        if end <= start:
            raise ReplayStrategyError("bar end_timestamp must be after start_timestamp")
        if previous_start is not None and start < previous_start:
            raise ReplayStrategyError("bar timestamps must be nondecreasing")
        previous_start = start

        if not isinstance(bar.timeframe_seconds, int) or bar.timeframe_seconds <= 0:
            raise ReplayStrategyError("bar timeframe_seconds must be a positive integer")
        _positive_finite_number(bar.close, "close")


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayStrategyError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ReplayStrategyError(f"{field_name} must not contain leading or trailing whitespace")
    return value


def _validated_symbol(symbol: str) -> str:
    _validated_identifier(symbol, "symbol")
    if symbol != symbol.upper():
        raise ReplayStrategyError("symbol must be uppercase")
    return symbol


def _positive_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ReplayStrategyError(f"{field_name} must be a finite number")

    number = float(value)
    if not math.isfinite(number):
        raise ReplayStrategyError(f"{field_name} must be a finite number")
    if number <= 0:
        raise ReplayStrategyError(f"{field_name} must be greater than zero")
    return number


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ReplayStrategyError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayStrategyError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReplayStrategyError(f"{field_name} must include a timezone")
    return parsed
