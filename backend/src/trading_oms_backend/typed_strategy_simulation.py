from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any


class BreakoutSimulationError(ValueError):
    """Raised when a typed strategy simulation cannot proceed safely."""

    def __init__(
        self,
        message: str,
        *,
        audit_events: tuple[dict[str, Any], ...] = (),
    ) -> None:
        super().__init__(message)
        self.audit_events = audit_events


@dataclass(frozen=True)
class NormalizedTrade:
    timestamp: str
    price: str
    sequence: int
    source: str = "last_trade"

    def __post_init__(self) -> None:
        _parse_timestamp(self.timestamp, "trade.timestamp")
        _positive_decimal(self.price, "trade.price")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise BreakoutSimulationError("trade.sequence must be a positive integer")
        if self.source != "last_trade":
            raise BreakoutSimulationError("trade.source must be last_trade")


@dataclass(frozen=True)
class RiskPolicy:
    version_id: str
    max_dollar_risk: str
    max_shares: int
    max_notional: str
    max_concurrent_positions: int
    max_symbol_exposure: str
    max_daily_loss: str
    admin_slippage_allowance: str
    chase_threshold: str
    max_data_age_seconds: int = 5

    def __post_init__(self) -> None:
        _identifier(self.version_id, "risk policy version_id")
        for field_name in (
            "max_dollar_risk",
            "max_notional",
            "max_symbol_exposure",
            "max_daily_loss",
            "chase_threshold",
        ):
            _positive_decimal(getattr(self, field_name), f"risk policy {field_name}")
        _non_negative_decimal(
            self.admin_slippage_allowance,
            "risk policy admin_slippage_allowance",
        )
        for field_name in ("max_shares", "max_concurrent_positions", "max_data_age_seconds"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise BreakoutSimulationError(f"risk policy {field_name} must be positive")


@dataclass(frozen=True)
class RiskContext:
    buying_power: str
    concurrent_positions: int
    current_symbol_exposure: str
    daily_realized_loss: str

    def __post_init__(self) -> None:
        _non_negative_decimal(self.buying_power, "buying_power")
        _non_negative_decimal(self.current_symbol_exposure, "current_symbol_exposure")
        _non_negative_decimal(self.daily_realized_loss, "daily_realized_loss")
        if (
            isinstance(self.concurrent_positions, bool)
            or not isinstance(self.concurrent_positions, int)
            or self.concurrent_positions < 0
        ):
            raise BreakoutSimulationError("concurrent_positions must be a non-negative integer")


@dataclass(frozen=True)
class RunEnvelope:
    run_id: str
    workflow_id: str
    workflow_version: int
    workflow_checksum: str
    symbol: str
    contract_id: str
    primary_exchange: str
    currency: str
    routing: str
    min_tick: str
    maximum_dollar_loss: str
    runtime_mode: str
    dataset_id: str
    session_date: str
    session_timezone: str
    rth_open: str
    rth_close: str
    entry_lifetime: str
    position_lifetime: Mapping[str, Any]
    risk_policy_version: str
    expires_at: str
    opening_range_minutes: int = 5
    dataset_resolution: str = "trade_ticks"

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "workflow_id",
            "contract_id",
            "primary_exchange",
            "dataset_id",
            "risk_policy_version",
        ):
            _identifier(getattr(self, field_name), field_name)
        if (
            isinstance(self.workflow_version, bool)
            or not isinstance(self.workflow_version, int)
            or self.workflow_version < 1
        ):
            raise BreakoutSimulationError("workflow_version must be a positive integer")
        if (
            not isinstance(self.workflow_checksum, str)
            or len(self.workflow_checksum) != 64
            or any(character not in "0123456789abcdef" for character in self.workflow_checksum)
        ):
            raise BreakoutSimulationError("workflow_checksum must be lowercase sha256 hex")
        if (
            not isinstance(self.symbol, str)
            or not self.symbol
            or self.symbol != self.symbol.upper()
        ):
            raise BreakoutSimulationError("symbol must be a non-empty uppercase value")
        if self.currency != "USD" or self.routing != "SMART":
            raise BreakoutSimulationError("only SMART-routed USD contracts are supported")
        _positive_decimal(self.min_tick, "min_tick")
        _positive_decimal(self.maximum_dollar_loss, "maximum_dollar_loss")
        if self.runtime_mode not in {"historical_simulation", "live_simulation"}:
            raise BreakoutSimulationError("runtime_mode must be a supported simulation mode")
        _parse_date(self.session_date, "session_date")
        _timezone(self.session_timezone)
        open_time = _parse_time(self.rth_open, "rth_open")
        close_time = _parse_time(self.rth_close, "rth_close")
        if close_time <= open_time:
            raise BreakoutSimulationError("rth_close must be after rth_open")
        if self.entry_lifetime not in {"DAY", "GTC"}:
            raise BreakoutSimulationError("entry_lifetime must be DAY or GTC")
        if (
            isinstance(self.opening_range_minutes, bool)
            or not isinstance(self.opening_range_minutes, int)
            or not 1 <= self.opening_range_minutes <= 60
        ):
            raise BreakoutSimulationError("opening_range_minutes must be between 1 and 60")
        _validate_position_lifetime(self.position_lifetime)
        _parse_timestamp(self.expires_at, "expires_at")
        if self.dataset_resolution not in {"trade_ticks", "five_second_bars"}:
            raise BreakoutSimulationError("dataset_resolution is unsupported")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RunEnvelope:
        values = dict(payload)
        values.setdefault("opening_range_minutes", 5)
        return cls(**values)

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_version": self.workflow_version,
            "workflow_checksum": self.workflow_checksum,
            "symbol": self.symbol,
            "contract_id": self.contract_id,
            "primary_exchange": self.primary_exchange,
            "currency": self.currency,
            "routing": self.routing,
            "min_tick": self.min_tick,
            "maximum_dollar_loss": self.maximum_dollar_loss,
            "runtime_mode": self.runtime_mode,
            "dataset_id": self.dataset_id,
            "session_date": self.session_date,
            "session_timezone": self.session_timezone,
            "rth_open": self.rth_open,
            "rth_close": self.rth_close,
            "entry_lifetime": self.entry_lifetime,
            "position_lifetime": _json_copy(self.position_lifetime),
            "risk_policy_version": self.risk_policy_version,
            "expires_at": self.expires_at,
            "opening_range_minutes": self.opening_range_minutes,
            "dataset_resolution": self.dataset_resolution,
        }


@dataclass(frozen=True)
class ArmAuthorization:
    run_id: str
    fingerprint: str
    authorized_at: str
    expires_at: str
    authorized_by: str

    def __post_init__(self) -> None:
        _identifier(self.run_id, "authorization run_id")
        _identifier(self.authorized_by, "authorization authorized_by")
        if (
            not isinstance(self.fingerprint, str)
            or len(self.fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in self.fingerprint)
        ):
            raise BreakoutSimulationError("authorization fingerprint must be lowercase sha256 hex")
        authorized_at = _parse_timestamp(self.authorized_at, "authorization authorized_at")
        expires_at = _parse_timestamp(self.expires_at, "authorization expires_at")
        if expires_at <= authorized_at:
            raise BreakoutSimulationError("authorization expires_at must be after authorized_at")


@dataclass(frozen=True)
class BreakoutSimulationResult:
    run_id: str
    status: str
    data_resolution: str
    opening_range_high: str | None
    trigger_threshold: str | None
    trigger_price: str | None
    frozen_day_low: str | None
    conservative_entry: str | None
    per_share_risk: str | None
    shares: str | None
    entry_fill_price: str | None
    protective_stop_price: str | None
    exit_fill_price: str | None
    realized_pnl: str | None
    protection_state: str
    idempotency_key: str | None
    critical_alert: str | None
    audit_events: tuple[dict[str, Any], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "run_id": self.run_id,
            "status": self.status,
            "data_resolution": self.data_resolution,
            "opening_range_high": self.opening_range_high,
            "trigger_threshold": self.trigger_threshold,
            "trigger_price": self.trigger_price,
            "frozen_day_low": self.frozen_day_low,
            "conservative_entry": self.conservative_entry,
            "per_share_risk": self.per_share_risk,
            "shares": self.shares,
            "entry_fill_price": self.entry_fill_price,
            "protective_stop_price": self.protective_stop_price,
            "exit_fill_price": self.exit_fill_price,
            "realized_pnl": self.realized_pnl,
            "protection_state": self.protection_state,
            "idempotency_key": self.idempotency_key,
            "critical_alert": self.critical_alert,
            "audit_events": [_json_copy(event) for event in self.audit_events],
            "simulated": True,
        }


def fingerprint_run_envelope(envelope: RunEnvelope) -> str:
    if not isinstance(envelope, RunEnvelope):
        raise BreakoutSimulationError("envelope must be RunEnvelope")
    encoded = json.dumps(
        envelope.to_payload(),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def simulate_first_five_minute_breakout(
    *,
    trades: Iterable[NormalizedTrade],
    envelope: RunEnvelope,
    authorization: ArmAuthorization,
    policy: RiskPolicy,
    risk_context: RiskContext,
    data_complete: bool = True,
    data_quality: str = "complete",
    reconciled: bool = True,
    emergency_stop_active: bool = False,
    evaluated_at: str | None = None,
) -> BreakoutSimulationResult:
    _validate_runtime_inputs(
        envelope=envelope,
        authorization=authorization,
        policy=policy,
        risk_context=risk_context,
        data_complete=data_complete,
        data_quality=data_quality,
        reconciled=reconciled,
        emergency_stop_active=emergency_stop_active,
    )
    ordered_trades = _validated_trade_sequence(trades)
    if not ordered_trades:
        raise BreakoutSimulationError("trade dataset must not be empty")
    if envelope.runtime_mode == "live_simulation":
        _validate_fresh_live_data(ordered_trades, policy, evaluated_at)

    timezone = _timezone(envelope.session_timezone)
    target_date = _parse_date(envelope.session_date, "session_date")
    sessions = _select_session_trades(ordered_trades, envelope, timezone, target_date)
    if not sessions:
        raise BreakoutSimulationError("dataset is missing the requested RTH session")

    opening_end = _opening_end(envelope)
    min_tick = _positive_decimal(envelope.min_tick, "min_tick")
    opening_high: Decimal | None = None
    threshold: Decimal | None = None
    day_low: Decimal | None = None
    after_opening: list[tuple[NormalizedTrade, datetime, Decimal]] = []
    trigger_item: tuple[NormalizedTrade, datetime, Decimal] | None = None
    trigger_index = -1
    for session_trades in sessions:
        opening_trades = [
            item for item in session_trades if _local_time(item[1], timezone) < opening_end
        ]
        after_opening = [
            item for item in session_trades if _local_time(item[1], timezone) >= opening_end
        ]
        if not opening_trades or not after_opening:
            raise BreakoutSimulationError("opening range is incomplete")

        opening_high = max(item[2] for item in opening_trades)
        threshold = opening_high + min_tick
        previous_price = opening_trades[-1][2]
        day_low = min(item[2] for item in opening_trades)
        for index, item in enumerate(after_opening):
            day_low = min(day_low, item[2])
            if previous_price < threshold <= item[2]:
                trigger_item = item
                trigger_index = index
                break
            previous_price = item[2]
        if trigger_item is not None:
            break

    quantum = _decimal_quantum(min_tick)
    if opening_high is None or threshold is None or day_low is None:
        raise BreakoutSimulationError("dataset is missing an eligible RTH session")
    if trigger_item is None:
        _verify_authorization(
            envelope,
            authorization,
            _parse_timestamp(evaluated_at or authorization.authorized_at, "evaluated_at"),
        )
        return _empty_result(
            envelope,
            status="expired_day" if envelope.entry_lifetime == "DAY" else "completed_no_trigger",
            opening_range_high=_format_decimal(opening_high, quantum),
            trigger_threshold=_format_decimal(threshold, quantum),
            event_type="workflow.entry.expired" if envelope.entry_lifetime == "DAY" else None,
        )

    trigger_trade, trigger_at, trigger_price = trigger_item
    signal_event = _event(
        "workflow.signal.detected",
        trigger_trade.timestamp,
        opening_range_high=_format_decimal(opening_high, quantum),
        trigger_threshold=_format_decimal(threshold, quantum),
        trigger_price=_format_decimal(trigger_price, quantum),
        frozen_day_low=_format_decimal(day_low, quantum),
    )
    authorization_check_at = (
        trigger_at
        if envelope.runtime_mode == "live_simulation"
        else _parse_timestamp(
            evaluated_at or authorization.authorized_at,
            "historical simulation evaluated_at",
        )
    )
    try:
        _verify_authorization(
            envelope,
            authorization,
            _parse_timestamp(evaluated_at or authorization.authorized_at, "evaluated_at"),
        )
        _verify_authorization(envelope, authorization, authorization_check_at)
    except BreakoutSimulationError as exc:
        raise BreakoutSimulationError(
            str(exc),
            audit_events=(
                signal_event,
                _event(
                    "workflow.authorization.blocked",
                    trigger_trade.timestamp,
                    reason=str(exc),
                ),
            ),
        ) from exc
    slippage = _non_negative_decimal(
        policy.admin_slippage_allowance,
        "risk policy admin_slippage_allowance",
    )
    conservative_entry = trigger_price + slippage
    per_share_risk = conservative_entry - day_low
    if per_share_risk <= 0:
        reason = "risk distance must be positive"
        raise BreakoutSimulationError(
            reason,
            audit_events=(
                signal_event,
                _event("workflow.risk.blocked", trigger_trade.timestamp, reason=reason),
            ),
        )
    maximum_loss = _positive_decimal(envelope.maximum_dollar_loss, "maximum_dollar_loss")
    shares = int((maximum_loss / per_share_risk).to_integral_value(rounding=ROUND_FLOOR))
    if shares < 1:
        reason = "calculated shares must be greater than zero"
        raise BreakoutSimulationError(
            reason,
            audit_events=(
                signal_event,
                _event("workflow.risk.blocked", trigger_trade.timestamp, reason=reason),
            ),
        )
    notional = conservative_entry * shares
    sizing_event = _event(
        "workflow.sizing.calculated",
        trigger_trade.timestamp,
        maximum_dollar_loss=_format_decimal(maximum_loss, _money_quantum()),
        conservative_entry=_format_decimal(conservative_entry, quantum),
        per_share_risk=_format_decimal(per_share_risk, quantum),
        shares=str(shares),
    )
    try:
        _apply_policy(
            maximum_loss=maximum_loss,
            shares=shares,
            notional=notional,
            policy=policy,
            context=risk_context,
        )
    except BreakoutSimulationError as exc:
        raise BreakoutSimulationError(
            str(exc),
            audit_events=(
                signal_event,
                sizing_event,
                _event("workflow.risk.blocked", trigger_trade.timestamp, reason=str(exc)),
            ),
        ) from exc

    events: list[dict[str, Any]] = [
        signal_event,
        sizing_event,
        _event("workflow.risk.passed", trigger_trade.timestamp, policy_version=policy.version_id),
        _event(
            "workflow.authorization.verified",
            trigger_trade.timestamp,
            fingerprint=authorization.fingerprint,
        ),
    ]
    idempotency_key = _idempotency_key(envelope, authorization, trigger_trade)
    events.append(
        _event(
            "workflow.order_plan.created",
            trigger_trade.timestamp,
            idempotency_key=idempotency_key,
            entry_type="stop_market",
            protective_stop=_format_decimal(day_low, quantum),
        )
    )
    events.append(
        _event(
            "workflow.order.activated",
            trigger_trade.timestamp,
            idempotency_key=idempotency_key,
            entry_type="stop_market",
            simulated=True,
        )
    )

    eligible_fills = after_opening[trigger_index + 1 :]
    if not eligible_fills:
        return _result(
            envelope,
            status="triggered_unfilled_expired",
            opening_high=opening_high,
            threshold=threshold,
            trigger_price=trigger_price,
            day_low=day_low,
            conservative_entry=conservative_entry,
            per_share_risk=per_share_risk,
            shares=shares,
            idempotency_key=idempotency_key,
            events=events
            + [_event("workflow.entry.expired", trigger_trade.timestamp, reason="no_next_trade")],
            quantum=quantum,
        )

    fill_trade, fill_at, fill_reference = eligible_fills[0]
    chase_threshold = _positive_decimal(policy.chase_threshold, "risk policy chase_threshold")
    if fill_reference - trigger_price > chase_threshold:
        return _result(
            envelope,
            status="expired_chase",
            opening_high=opening_high,
            threshold=threshold,
            trigger_price=trigger_price,
            day_low=day_low,
            conservative_entry=conservative_entry,
            per_share_risk=per_share_risk,
            shares=shares,
            idempotency_key=idempotency_key,
            events=events
            + [
                _event(
                    "workflow.trigger.expired",
                    fill_trade.timestamp,
                    reason="chase_threshold_exceeded",
                )
            ],
            quantum=quantum,
        )

    entry_fill = fill_reference + slippage
    try:
        if _position_exit_due(envelope.position_lifetime, fill_at, timezone, entered_at=fill_at):
            raise BreakoutSimulationError("configured position exit is already due")
        actual_risk_distance = entry_fill - day_low
        if actual_risk_distance <= 0:
            raise BreakoutSimulationError("entry price must remain above the protective stop")
        executable_shares = min(
            shares,
            int((maximum_loss / actual_risk_distance).to_integral_value(rounding=ROUND_FLOOR)),
        )
        if executable_shares < 1:
            raise BreakoutSimulationError("actual entry risk permits zero shares")
        if executable_shares != shares:
            events.append(
                _event(
                    "workflow.order_plan.resized",
                    fill_trade.timestamp,
                    previous_shares=str(shares),
                    shares=str(executable_shares),
                    actual_per_share_risk=_format_decimal(actual_risk_distance, quantum),
                )
            )
        shares = executable_shares
        _apply_policy(
            maximum_loss=maximum_loss,
            shares=shares,
            notional=entry_fill * shares,
            policy=policy,
            context=risk_context,
        )
    except BreakoutSimulationError as exc:
        raise BreakoutSimulationError(
            str(exc),
            audit_events=tuple(events)
            + (
                _event(
                    "workflow.risk.blocked",
                    fill_trade.timestamp,
                    reason=str(exc),
                    phase="execution_recheck",
                ),
            ),
        ) from exc
    events.append(
        _event(
            "workflow.risk.passed",
            fill_trade.timestamp,
            policy_version=policy.version_id,
            phase="execution_recheck",
        )
    )
    events.extend(
        [
            _event(
                "workflow.order.filled",
                fill_trade.timestamp,
                side="buy",
                price=_format_decimal(entry_fill, quantum),
                shares=str(shares),
                simulated=True,
            ),
            _event(
                "workflow.protection.activated",
                fill_trade.timestamp,
                stop_price=_format_decimal(day_low, quantum),
                time_in_force="GTC",
            ),
            _event(
                "workflow.position.updated",
                fill_trade.timestamp,
                state="open_protected",
                shares=str(shares),
            ),
        ]
    )

    exit_fill: Decimal | None = None
    exit_timestamp: str | None = None
    exit_reason: str | None = None
    # Entry lifetime limits entries; existing protection follows every remaining
    # supplied tick, including later sessions and ticks after authorization expiry.
    remaining_ticks = (
        item
        for item in ordered_trades
        if (item[1], item[0].sequence) > (fill_at, fill_trade.sequence)
    )
    for later_trade, later_at, later_price in remaining_ticks:
        if later_price <= day_low:
            exit_fill = min(day_low, later_price - slippage)
            exit_timestamp = later_trade.timestamp
            exit_reason = "protective_stop"
            break
        if _position_exit_due(envelope.position_lifetime, later_at, timezone, entered_at=fill_at):
            exit_fill = later_price - slippage
            exit_timestamp = later_trade.timestamp
            exit_reason = "position_lifetime"
            break

    if exit_fill is None:
        return _result(
            envelope,
            status="position_open_protected",
            opening_high=opening_high,
            threshold=threshold,
            trigger_price=trigger_price,
            day_low=day_low,
            conservative_entry=conservative_entry,
            per_share_risk=per_share_risk,
            shares=shares,
            entry_fill=entry_fill,
            idempotency_key=idempotency_key,
            events=events,
            quantum=quantum,
        )

    realized_pnl = (exit_fill - entry_fill) * shares
    events.extend(
        [
            _event(
                "workflow.order.filled",
                exit_timestamp or fill_trade.timestamp,
                side="sell",
                price=_format_decimal(exit_fill, quantum),
                shares=str(shares),
                reason=exit_reason,
                simulated=True,
            ),
            _event(
                "workflow.position.updated",
                exit_timestamp or fill_trade.timestamp,
                state="closed",
                realized_pnl=_format_decimal(realized_pnl, _money_quantum()),
            ),
        ]
    )
    critical_alert = None
    if -realized_pnl > maximum_loss:
        critical_alert = "realized_loss_exceeded_authorized_dollar_risk"
        events.append(
            _event(
                "workflow.alert.critical",
                exit_timestamp or fill_trade.timestamp,
                reason=critical_alert,
                realized_loss=_format_decimal(-realized_pnl, _money_quantum()),
            )
        )
    return _result(
        envelope,
        status="position_closed",
        opening_high=opening_high,
        threshold=threshold,
        trigger_price=trigger_price,
        day_low=day_low,
        conservative_entry=conservative_entry,
        per_share_risk=per_share_risk,
        shares=shares,
        entry_fill=entry_fill,
        exit_fill=exit_fill,
        realized_pnl=realized_pnl,
        idempotency_key=idempotency_key,
        critical_alert=critical_alert,
        events=events,
        quantum=quantum,
    )


def _validate_runtime_inputs(
    *,
    envelope: RunEnvelope,
    authorization: ArmAuthorization,
    policy: RiskPolicy,
    risk_context: RiskContext,
    data_complete: bool,
    data_quality: str,
    reconciled: bool,
    emergency_stop_active: bool,
) -> None:
    if not isinstance(envelope, RunEnvelope):
        raise BreakoutSimulationError("envelope must be RunEnvelope")
    if not isinstance(authorization, ArmAuthorization):
        raise BreakoutSimulationError("authorization must be ArmAuthorization")
    if not isinstance(policy, RiskPolicy):
        raise BreakoutSimulationError("policy must be RiskPolicy")
    if not isinstance(risk_context, RiskContext):
        raise BreakoutSimulationError("risk_context must be RiskContext")
    if not data_complete:
        raise BreakoutSimulationError("market data is incomplete")
    if data_quality != "complete":
        raise BreakoutSimulationError("market data quality must be complete")
    if not reconciled:
        raise BreakoutSimulationError("reconciliation state must be known and reconciled")
    if emergency_stop_active:
        raise BreakoutSimulationError("emergency stop is active")
    if policy.version_id != envelope.risk_policy_version:
        raise BreakoutSimulationError("risk policy version does not match the run envelope")
    if authorization.run_id != envelope.run_id:
        raise BreakoutSimulationError("authorization run_id does not match")
    if authorization.fingerprint != fingerprint_run_envelope(envelope):
        raise BreakoutSimulationError("authorization fingerprint does not match the run envelope")


def _verify_authorization(
    envelope: RunEnvelope, authorization: ArmAuthorization, evaluated_at: datetime
) -> None:
    authorized_at = _parse_timestamp(authorization.authorized_at, "authorization authorized_at")
    authorization_expiry = _parse_timestamp(authorization.expires_at, "authorization expires_at")
    envelope_expiry = _parse_timestamp(envelope.expires_at, "expires_at")
    if evaluated_at < authorized_at:
        raise BreakoutSimulationError("authorization is not active yet")
    if evaluated_at >= authorization_expiry or evaluated_at >= envelope_expiry:
        raise BreakoutSimulationError("armed authorization expired")


def _apply_policy(
    *,
    maximum_loss: Decimal,
    shares: int,
    notional: Decimal,
    policy: RiskPolicy,
    context: RiskContext,
) -> None:
    if maximum_loss > _positive_decimal(policy.max_dollar_risk, "max_dollar_risk"):
        raise BreakoutSimulationError("maximum dollar risk exceeds administrator cap")
    if shares > policy.max_shares:
        raise BreakoutSimulationError("calculated shares exceed administrator share cap")
    if notional > _positive_decimal(policy.max_notional, "max_notional"):
        raise BreakoutSimulationError("calculated notional exceeds administrator notional cap")
    if notional > _non_negative_decimal(context.buying_power, "buying_power"):
        raise BreakoutSimulationError("calculated notional exceeds buying power")
    if context.concurrent_positions >= policy.max_concurrent_positions:
        raise BreakoutSimulationError("concurrent position cap is already reached")
    exposure = _non_negative_decimal(context.current_symbol_exposure, "current_symbol_exposure")
    if exposure + notional > _positive_decimal(policy.max_symbol_exposure, "max_symbol_exposure"):
        raise BreakoutSimulationError("calculated notional exceeds symbol exposure cap")
    daily_loss = _non_negative_decimal(context.daily_realized_loss, "daily_realized_loss")
    if daily_loss + maximum_loss > _positive_decimal(policy.max_daily_loss, "max_daily_loss"):
        raise BreakoutSimulationError("authorized risk would exceed the daily loss cap")


def _validated_trade_sequence(
    trades: Iterable[NormalizedTrade],
) -> list[tuple[NormalizedTrade, datetime, Decimal]]:
    values = list(trades)
    if any(not isinstance(trade, NormalizedTrade) for trade in values):
        raise BreakoutSimulationError("trades must contain NormalizedTrade values")
    result: list[tuple[NormalizedTrade, datetime, Decimal]] = []
    seen_keys: set[tuple[datetime, int]] = set()
    seen_sequences: set[int] = set()
    previous_key: tuple[datetime, int] | None = None
    for trade in values:
        timestamp = _parse_timestamp(trade.timestamp, "trade.timestamp")
        price = _positive_decimal(trade.price, "trade.price")
        key = (timestamp, trade.sequence)
        if key in seen_keys or trade.sequence in seen_sequences:
            raise BreakoutSimulationError("duplicate trade callback detected")
        if previous_key is not None and key < previous_key:
            raise BreakoutSimulationError("trade callbacks are out of order")
        seen_keys.add(key)
        seen_sequences.add(trade.sequence)
        previous_key = key
        result.append((trade, timestamp, price))
    return result


def _validate_fresh_live_data(
    trades: list[tuple[NormalizedTrade, datetime, Decimal]],
    policy: RiskPolicy,
    evaluated_at: str | None,
) -> None:
    if evaluated_at is None:
        raise BreakoutSimulationError("live_simulation requires evaluated_at for stale-data checks")
    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    age_seconds = (evaluated - trades[-1][1]).total_seconds()
    if age_seconds < 0 or age_seconds > policy.max_data_age_seconds:
        raise BreakoutSimulationError("live market data is stale or clock-invalid")


def _select_session_trades(
    trades: list[tuple[NormalizedTrade, datetime, Decimal]],
    envelope: RunEnvelope,
    timezone: str,
    target_date: date,
) -> tuple[list[tuple[NormalizedTrade, datetime, Decimal]], ...]:
    rth_open = _parse_time(envelope.rth_open, "rth_open")
    rth_close = _parse_time(envelope.rth_close, "rth_close")
    expiry_date = _local_datetime(
        _parse_timestamp(envelope.expires_at, "expires_at"), timezone
    ).date()
    session_dates = sorted(
        {
            _local_datetime(item[1], timezone).date()
            for item in trades
            if target_date <= _local_datetime(item[1], timezone).date() <= expiry_date
        }
    )
    if envelope.entry_lifetime == "DAY":
        session_dates = [target_date] if target_date in session_dates else []
    return tuple(
        [
            item
            for item in trades
            if _local_datetime(item[1], timezone).date() == session_date
            and rth_open <= _local_time(item[1], timezone) <= rth_close
        ]
        for session_date in session_dates
    )


def _opening_end(envelope: RunEnvelope) -> time:
    rth_open = _parse_time(envelope.rth_open, "rth_open")
    if rth_open != time(9, 30):
        raise BreakoutSimulationError("opening-range strategy requires a 09:30 RTH open")
    return (
        datetime.combine(date.min, rth_open) + timedelta(minutes=envelope.opening_range_minutes)
    ).time()


def _position_exit_due(
    position_lifetime: Mapping[str, Any],
    timestamp: datetime,
    timezone: str,
    *,
    entered_at: datetime,
) -> bool:
    if position_lifetime.get("kind") != "exit_at_time":
        return False
    exit_time = _parse_time(position_lifetime.get("time"), "position_lifetime.time")
    entry_date = _local_datetime(entered_at, timezone).date()
    return _local_datetime(timestamp, timezone) >= datetime.combine(entry_date, exit_time)


def _idempotency_key(
    envelope: RunEnvelope, authorization: ArmAuthorization, trigger: NormalizedTrade
) -> str:
    raw = f"{envelope.run_id}|{authorization.fingerprint}|{trigger.timestamp}|{trigger.sequence}"
    return f"sim-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _event(event_type: str, timestamp: str, **payload: Any) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "timestamp": timestamp,
        "payload": _json_copy(payload),
    }


def _empty_result(
    envelope: RunEnvelope,
    *,
    status: str,
    opening_range_high: str | None,
    trigger_threshold: str | None,
    event_type: str | None,
) -> BreakoutSimulationResult:
    events: tuple[dict[str, Any], ...] = ()
    if event_type is not None:
        events = (_event(event_type, envelope.expires_at, reason="entry_lifetime"),)
    return BreakoutSimulationResult(
        run_id=envelope.run_id,
        status=status,
        data_resolution=envelope.dataset_resolution,
        opening_range_high=opening_range_high,
        trigger_threshold=trigger_threshold,
        trigger_price=None,
        frozen_day_low=None,
        conservative_entry=None,
        per_share_risk=None,
        shares=None,
        entry_fill_price=None,
        protective_stop_price=None,
        exit_fill_price=None,
        realized_pnl=None,
        protection_state="not_applicable",
        idempotency_key=None,
        critical_alert=None,
        audit_events=events,
    )


def _result(
    envelope: RunEnvelope,
    *,
    status: str,
    opening_high: Decimal,
    threshold: Decimal,
    trigger_price: Decimal,
    day_low: Decimal,
    conservative_entry: Decimal,
    per_share_risk: Decimal,
    shares: int,
    idempotency_key: str,
    events: list[dict[str, Any]],
    quantum: Decimal,
    entry_fill: Decimal | None = None,
    exit_fill: Decimal | None = None,
    realized_pnl: Decimal | None = None,
    critical_alert: str | None = None,
) -> BreakoutSimulationResult:
    if entry_fill is None:
        protection_state = "planned"
    elif exit_fill is None:
        protection_state = "active"
    else:
        protection_state = "completed"
    return BreakoutSimulationResult(
        run_id=envelope.run_id,
        status=status,
        data_resolution=envelope.dataset_resolution,
        opening_range_high=_format_decimal(opening_high, quantum),
        trigger_threshold=_format_decimal(threshold, quantum),
        trigger_price=_format_decimal(trigger_price, quantum),
        frozen_day_low=_format_decimal(day_low, quantum),
        conservative_entry=_format_decimal(conservative_entry, quantum),
        per_share_risk=_format_decimal(per_share_risk, quantum),
        shares=str(shares),
        entry_fill_price=None if entry_fill is None else _format_decimal(entry_fill, quantum),
        protective_stop_price=_format_decimal(day_low, quantum),
        exit_fill_price=None if exit_fill is None else _format_decimal(exit_fill, quantum),
        realized_pnl=(
            None if realized_pnl is None else _format_decimal(realized_pnl, _money_quantum())
        ),
        protection_state=protection_state,
        idempotency_key=idempotency_key,
        critical_alert=critical_alert,
        audit_events=tuple(events),
    )


def _validate_position_lifetime(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise BreakoutSimulationError("position_lifetime must be an object")
    kind = value.get("kind")
    if kind in {"hold_with_protective_stop", "exit_on_typed_condition"}:
        if set(value) != {"kind"}:
            raise BreakoutSimulationError("position_lifetime contains unsupported fields")
        return
    if kind == "exit_at_time":
        if set(value) != {"kind", "time"}:
            raise BreakoutSimulationError("exit_at_time requires exactly kind and time")
        _parse_time(value.get("time"), "position_lifetime.time")
        return
    raise BreakoutSimulationError("position_lifetime kind is unsupported")


def _positive_decimal(value: Any, field_name: str) -> Decimal:
    decimal_value = _decimal(value, field_name)
    if decimal_value <= 0:
        raise BreakoutSimulationError(f"{field_name} must be positive")
    return decimal_value


def _non_negative_decimal(value: Any, field_name: str) -> Decimal:
    decimal_value = _decimal(value, field_name)
    if decimal_value < 0:
        raise BreakoutSimulationError(f"{field_name} must be non-negative")
    return decimal_value


def _decimal(value: Any, field_name: str) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BreakoutSimulationError(f"{field_name} must be a decimal string")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as exc:
        raise BreakoutSimulationError(f"{field_name} must be a decimal string") from exc
    if not decimal_value.is_finite():
        raise BreakoutSimulationError(f"{field_name} must be finite")
    return decimal_value


def _decimal_quantum(min_tick: Decimal) -> Decimal:
    return Decimal(1).scaleb(min_tick.as_tuple().exponent)


def _money_quantum() -> Decimal:
    return Decimal("0.01")


def _format_decimal(value: Decimal, quantum: Decimal) -> str:
    return format(value.quantize(quantum), "f")


def _identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BreakoutSimulationError(f"{field_name} must be a non-empty identifier")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(character not in allowed for character in value):
        raise BreakoutSimulationError(f"{field_name} contains unsupported characters")
    return value


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BreakoutSimulationError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BreakoutSimulationError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BreakoutSimulationError(f"{field_name} must include a timezone")
    return parsed


def _parse_date(value: Any, field_name: str) -> date:
    if not isinstance(value, str):
        raise BreakoutSimulationError(f"{field_name} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BreakoutSimulationError(f"{field_name} must be YYYY-MM-DD") from exc


def _parse_time(value: Any, field_name: str) -> time:
    if not isinstance(value, str):
        raise BreakoutSimulationError(f"{field_name} must be HH:MM:SS")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise BreakoutSimulationError(f"{field_name} must be HH:MM:SS") from exc
    if parsed.tzinfo is not None:
        raise BreakoutSimulationError(f"{field_name} must be exchange-local without timezone")
    return parsed


def _timezone(value: str) -> str:
    if value != "America/New_York":
        raise BreakoutSimulationError("session_timezone is unknown")
    return value


def _local_time(timestamp: datetime, timezone: str) -> time:
    return _local_datetime(timestamp, timezone).time()


def _local_datetime(timestamp: datetime, timezone: str) -> datetime:
    _timezone(timezone)
    utc_timestamp = timestamp.astimezone(UTC)
    year = utc_timestamp.year
    dst_start_day = _nth_weekday_of_month(year, 3, weekday=6, occurrence=2)
    dst_end_day = _nth_weekday_of_month(year, 11, weekday=6, occurrence=1)
    dst_start_utc = datetime(year, 3, dst_start_day, 7, tzinfo=UTC)
    dst_end_utc = datetime(year, 11, dst_end_day, 6, tzinfo=UTC)
    offset = timedelta(hours=-4 if dst_start_utc <= utc_timestamp < dst_end_utc else -5)
    return (utc_timestamp + offset).replace(tzinfo=None)


def _nth_weekday_of_month(year: int, month: int, *, weekday: int, occurrence: int) -> int:
    first = date(year, month, 1)
    days_until_weekday = (weekday - first.weekday()) % 7
    return 1 + days_until_weekday + (occurrence - 1) * 7


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise BreakoutSimulationError("payload must be JSON-serializable") from exc
