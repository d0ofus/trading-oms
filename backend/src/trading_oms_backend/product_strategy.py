from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_oms_backend.bar_builder import Bar
from trading_oms_backend.event_journal import JsonlEventJournal

SIGNAL_EVENT_TYPE = "strategy.signal.generated"
STRATEGY_TYPE = "first_5_minute_breakout_volume_filter"
VALID_SIGNALS = {"long_entry_candidate"}


class ProductBreakoutStrategyError(ValueError):
    """Raised when product strategy inputs or outputs are invalid."""


@dataclass(frozen=True)
class ProductBreakoutStrategyConfig:
    strategy_id: str
    symbol: str
    opening_range_seconds: int = 300
    volume_multiplier: float = 1.5
    historical_session_count: int = 10
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ProductBreakoutStrategyError("schema_version must be 1")
        _validated_identifier(self.strategy_id, "strategy_id")
        _validated_symbol(self.symbol)
        if self.opening_range_seconds != 300:
            raise ProductBreakoutStrategyError("opening_range_seconds must be 300")
        _positive_finite_number(self.volume_multiplier, "volume_multiplier")
        if self.volume_multiplier <= 1.0:
            raise ProductBreakoutStrategyError("volume_multiplier must be greater than 1.0")
        if self.historical_session_count != 10:
            raise ProductBreakoutStrategyError("historical_session_count must be 10")


@dataclass(frozen=True)
class HistoricalVolumeSession:
    session_id: str
    bars: tuple[Bar, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ProductBreakoutStrategyError("schema_version must be 1")
        _validated_identifier(self.session_id, "session_id")
        if not isinstance(self.bars, tuple):
            raise ProductBreakoutStrategyError("historical session bars must be a tuple")
        if not self.bars:
            raise ProductBreakoutStrategyError("historical session bars must not be empty")


@dataclass(frozen=True)
class ProductBreakoutSignal:
    strategy_id: str
    symbol: str
    trigger_bar_start_timestamp: str
    trigger_bar_end_timestamp: str
    signal: str
    first_bar_high: float
    breakout_bar_high: float
    cumulative_volume: float
    average_cumulative_volume: float
    volume_threshold: float
    volume_multiplier: float
    historical_session_count: int
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ProductBreakoutStrategyError("schema_version must be 1")
        _validated_identifier(self.strategy_id, "strategy_id")
        _validated_symbol(self.symbol)
        _parse_timestamp(self.trigger_bar_start_timestamp, "trigger_bar_start_timestamp")
        _parse_timestamp(self.trigger_bar_end_timestamp, "trigger_bar_end_timestamp")
        if self.signal not in VALID_SIGNALS:
            raise ProductBreakoutStrategyError("signal must be long_entry_candidate")
        _positive_finite_number(self.first_bar_high, "first_bar_high")
        _positive_finite_number(self.breakout_bar_high, "breakout_bar_high")
        _nonnegative_finite_number(self.cumulative_volume, "cumulative_volume")
        _positive_finite_number(self.average_cumulative_volume, "average_cumulative_volume")
        _positive_finite_number(self.volume_threshold, "volume_threshold")
        _positive_finite_number(self.volume_multiplier, "volume_multiplier")
        if self.historical_session_count != 10:
            raise ProductBreakoutStrategyError("historical_session_count must be 10")
        _validated_identifier(self.reason, "reason")
        _assert_json_serializable(self.to_json_dict(), "product strategy signal")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "strategy_type": STRATEGY_TYPE,
            "symbol": self.symbol,
            "trigger_bar_start_timestamp": self.trigger_bar_start_timestamp,
            "trigger_bar_end_timestamp": self.trigger_bar_end_timestamp,
            "signal": self.signal,
            "first_bar_high": self.first_bar_high,
            "breakout_bar_high": self.breakout_bar_high,
            "cumulative_volume": self.cumulative_volume,
            "average_cumulative_volume": self.average_cumulative_volume,
            "volume_threshold": self.volume_threshold,
            "volume_multiplier": self.volume_multiplier,
            "historical_session_count": self.historical_session_count,
            "reason": self.reason,
        }

    @classmethod
    def from_json_dict(cls, raw_signal: Mapping[str, Any]) -> ProductBreakoutSignal:
        expected_keys = {
            "schema_version",
            "strategy_id",
            "strategy_type",
            "symbol",
            "trigger_bar_start_timestamp",
            "trigger_bar_end_timestamp",
            "signal",
            "first_bar_high",
            "breakout_bar_high",
            "cumulative_volume",
            "average_cumulative_volume",
            "volume_threshold",
            "volume_multiplier",
            "historical_session_count",
            "reason",
        }
        if not isinstance(raw_signal, Mapping) or set(raw_signal) != expected_keys:
            raise ProductBreakoutStrategyError("product strategy signal fields are invalid")
        if raw_signal["strategy_type"] != STRATEGY_TYPE:
            raise ProductBreakoutStrategyError("strategy_type is invalid")
        return cls(
            schema_version=raw_signal["schema_version"],
            strategy_id=raw_signal["strategy_id"],
            symbol=raw_signal["symbol"],
            trigger_bar_start_timestamp=raw_signal["trigger_bar_start_timestamp"],
            trigger_bar_end_timestamp=raw_signal["trigger_bar_end_timestamp"],
            signal=raw_signal["signal"],
            first_bar_high=raw_signal["first_bar_high"],
            breakout_bar_high=raw_signal["breakout_bar_high"],
            cumulative_volume=raw_signal["cumulative_volume"],
            average_cumulative_volume=raw_signal["average_cumulative_volume"],
            volume_threshold=raw_signal["volume_threshold"],
            volume_multiplier=raw_signal["volume_multiplier"],
            historical_session_count=raw_signal["historical_session_count"],
            reason=raw_signal["reason"],
        )


def run_first_bar_breakout_volume_strategy(
    current_session_bars: Iterable[Bar],
    historical_sessions: Iterable[HistoricalVolumeSession],
    config: ProductBreakoutStrategyConfig,
    journal: JsonlEventJournal,
) -> list[ProductBreakoutSignal]:
    if not isinstance(config, ProductBreakoutStrategyConfig):
        raise ProductBreakoutStrategyError("config must be ProductBreakoutStrategyConfig")
    if not isinstance(journal, JsonlEventJournal):
        raise ProductBreakoutStrategyError("journal must be JsonlEventJournal")

    current_bars = list(current_session_bars)
    if not current_bars:
        return []

    historical_session_list = list(historical_sessions)
    _validate_historical_sessions(historical_session_list, current_bars, config)
    _validate_bar_list(current_bars, config, "current session bars")

    if len(current_bars) < 2:
        return []

    first_bar_high = current_bars[0].high
    cumulative_volume = current_bars[0].volume

    for index, current_bar in enumerate(current_bars[1:], start=1):
        cumulative_volume += current_bar.volume
        if current_bar.high <= first_bar_high:
            continue

        average_cumulative_volume = _average_historical_cumulative_volume(
            historical_session_list,
            index,
        )
        volume_threshold = average_cumulative_volume * config.volume_multiplier
        if cumulative_volume < volume_threshold:
            return []

        signal = ProductBreakoutSignal(
            strategy_id=config.strategy_id,
            symbol=config.symbol,
            trigger_bar_start_timestamp=current_bar.start_timestamp,
            trigger_bar_end_timestamp=current_bar.end_timestamp,
            signal="long_entry_candidate",
            first_bar_high=first_bar_high,
            breakout_bar_high=current_bar.high,
            cumulative_volume=cumulative_volume,
            average_cumulative_volume=average_cumulative_volume,
            volume_threshold=volume_threshold,
            volume_multiplier=config.volume_multiplier,
            historical_session_count=config.historical_session_count,
            reason="first_5_minute_high_breakout_with_volume_filter",
        )
        journal.append(
            event_type=SIGNAL_EVENT_TYPE,
            payload=signal.to_json_dict(),
            timestamp=signal.trigger_bar_end_timestamp,
        )
        return [signal]

    return []


def _validate_historical_sessions(
    historical_sessions: list[HistoricalVolumeSession],
    current_bars: list[Bar],
    config: ProductBreakoutStrategyConfig,
) -> None:
    if len(historical_sessions) != config.historical_session_count:
        raise ProductBreakoutStrategyError("historical sessions must contain exactly 10 sessions")

    seen_session_ids: set[str] = set()
    for historical_session in historical_sessions:
        if not isinstance(historical_session, HistoricalVolumeSession):
            raise ProductBreakoutStrategyError(
                "historical sessions must be HistoricalVolumeSession records"
            )
        if historical_session.session_id in seen_session_ids:
            raise ProductBreakoutStrategyError("historical session IDs must be unique")
        seen_session_ids.add(historical_session.session_id)

        _validate_bar_list(
            list(historical_session.bars),
            config,
            f"historical session {historical_session.session_id} bars",
        )
        if len(historical_session.bars) < len(current_bars):
            raise ProductBreakoutStrategyError(
                "historical sessions must include the same session time as every current bar"
            )


def _validate_bar_list(
    bars: list[Bar],
    config: ProductBreakoutStrategyConfig,
    context: str,
) -> None:
    previous_start: datetime | None = None
    for bar in bars:
        if not isinstance(bar, Bar):
            raise ProductBreakoutStrategyError(f"{context} must contain Bar records")
        if bar.symbol != config.symbol:
            raise ProductBreakoutStrategyError(
                f"{context} symbol {bar.symbol} does not match configured symbol {config.symbol}"
            )
        if bar.timeframe_seconds != config.opening_range_seconds:
            raise ProductBreakoutStrategyError(
                f"{context} timeframe must be {config.opening_range_seconds} seconds"
            )

        start = _parse_timestamp(bar.start_timestamp, "bar_start_timestamp")
        end = _parse_timestamp(bar.end_timestamp, "bar_end_timestamp")
        if end <= start:
            raise ProductBreakoutStrategyError("bar end_timestamp must be after start_timestamp")
        if previous_start is not None and start < previous_start:
            raise ProductBreakoutStrategyError(f"{context} timestamps must be nondecreasing")
        previous_start = start

        _positive_finite_number(bar.open, "open")
        _positive_finite_number(bar.high, "high")
        _positive_finite_number(bar.low, "low")
        _positive_finite_number(bar.close, "close")
        _nonnegative_finite_number(bar.volume, "volume")
        if not isinstance(bar.event_count, int) or bar.event_count < 1:
            raise ProductBreakoutStrategyError("event_count must be a positive integer")
        if bar.low > min(bar.open, bar.high, bar.close):
            raise ProductBreakoutStrategyError("low must not exceed open, high, or close")
        if bar.high < max(bar.open, bar.low, bar.close):
            raise ProductBreakoutStrategyError("high must not be below open, low, or close")


def _average_historical_cumulative_volume(
    historical_sessions: list[HistoricalVolumeSession],
    bar_index: int,
) -> float:
    cumulative_volumes = []
    for session in historical_sessions:
        try:
            session_bars = session.bars[: bar_index + 1]
        except IndexError as exc:
            raise ProductBreakoutStrategyError(
                "historical sessions must include the same session time as the breakout bar"
            ) from exc
        if len(session_bars) < bar_index + 1:
            raise ProductBreakoutStrategyError(
                "historical sessions must include the same session time as the breakout bar"
            )
        cumulative_volumes.append(sum(bar.volume for bar in session_bars))
    return sum(cumulative_volumes) / len(cumulative_volumes)


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductBreakoutStrategyError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ProductBreakoutStrategyError(f"{field_name} must not contain whitespace padding")
    return value


def _validated_symbol(symbol: str) -> str:
    _validated_identifier(symbol, "symbol")
    if symbol != symbol.upper():
        raise ProductBreakoutStrategyError("symbol must be uppercase")
    return symbol


def _positive_finite_number(value: Any, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if number <= 0:
        raise ProductBreakoutStrategyError(f"{field_name} must be greater than zero")
    return number


def _nonnegative_finite_number(value: Any, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if number < 0:
        raise ProductBreakoutStrategyError(f"{field_name} must be nonnegative")
    return number


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProductBreakoutStrategyError(f"{field_name} must be a finite number")

    number = float(value)
    if not math.isfinite(number):
        raise ProductBreakoutStrategyError(f"{field_name} must be a finite number")
    return number


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ProductBreakoutStrategyError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProductBreakoutStrategyError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProductBreakoutStrategyError(f"{field_name} must include a timezone")
    return parsed


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProductBreakoutStrategyError(f"{payload_name} must be JSON-serializable") from exc
