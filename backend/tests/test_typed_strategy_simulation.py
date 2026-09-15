from __future__ import annotations

from copy import deepcopy

import pytest

from trading_oms_backend.typed_strategy_simulation import (
    ArmAuthorization,
    BreakoutSimulationError,
    NormalizedTrade,
    RiskContext,
    RiskPolicy,
    RunEnvelope,
    fingerprint_run_envelope,
    simulate_first_five_minute_breakout,
)


def test_first_five_minute_breakout_freezes_day_low_and_sizes_with_decimals() -> None:
    envelope = run_envelope()
    result = simulate_first_five_minute_breakout(
        trades=trade_ticks(),
        envelope=envelope,
        authorization=authorization(envelope),
        policy=risk_policy(),
        risk_context=risk_context(),
    )

    assert result.status == "position_open_protected"
    assert result.opening_range_high == "101.00"
    assert result.trigger_threshold == "101.01"
    assert result.trigger_price == "101.01"
    assert result.frozen_day_low == "99.50"
    assert result.conservative_entry == "101.03"
    assert result.per_share_risk == "1.53"
    assert result.shares == "64"
    assert result.entry_fill_price == "101.05"
    assert result.protective_stop_price == "99.50"
    assert result.protection_state == "active"
    assert result.idempotency_key.startswith("sim-")
    assert [event["event_type"] for event in result.audit_events] == [
        "workflow.signal.detected",
        "workflow.sizing.calculated",
        "workflow.risk.passed",
        "workflow.authorization.verified",
        "workflow.order_plan.created",
        "workflow.order.activated",
        "workflow.order_plan.resized",
        "workflow.risk.passed",
        "workflow.order.filled",
        "workflow.protection.activated",
        "workflow.position.updated",
    ]


def test_cross_requires_transition_and_uses_opening_range_only_after_0935() -> None:
    ticks = trade_ticks()[:2] + [
        NormalizedTrade("2026-07-08T13:35:00Z", "101.00", 3),
        NormalizedTrade("2026-07-08T13:35:01Z", "101.01", 4),
        NormalizedTrade("2026-07-08T13:35:02Z", "101.03", 5),
        NormalizedTrade("2026-07-08T13:35:03Z", "101.04", 6),
    ]

    result = simulate_first_five_minute_breakout(
        trades=ticks,
        envelope=run_envelope(),
        authorization=authorization(run_envelope()),
        policy=risk_policy(),
        risk_context=risk_context(),
    )

    assert result.trigger_price == "101.01"
    assert result.entry_fill_price == "101.05"


def test_configurable_one_minute_range_is_part_of_runtime_behavior() -> None:
    envelope = run_envelope(opening_range_minutes=1)
    ticks = [
        NormalizedTrade("2026-07-08T13:30:00Z", "99.50", 1),
        NormalizedTrade("2026-07-08T13:30:59Z", "100.00", 2),
        NormalizedTrade("2026-07-08T13:31:00Z", "100.01", 3),
        NormalizedTrade("2026-07-08T13:31:01Z", "100.03", 4),
    ]

    result = simulate_first_five_minute_breakout(
        trades=ticks,
        envelope=envelope,
        authorization=authorization(envelope),
        policy=risk_policy(),
        risk_context=risk_context(),
    )

    assert result.opening_range_high == "100.00"
    assert result.trigger_price == "100.01"


def test_gap_through_fill_and_stop_are_deterministic_and_alert_on_budget_breach() -> None:
    ticks = trade_ticks() + [
        NormalizedTrade("2026-07-08T13:36:00Z", "99.20", 6),
    ]
    ticks[3] = NormalizedTrade("2026-07-08T13:35:02Z", "101.80", 4)
    policy = risk_policy(chase_threshold="1.00")

    result = simulate_first_five_minute_breakout(
        trades=ticks,
        envelope=run_envelope(),
        authorization=authorization(run_envelope()),
        policy=policy,
        risk_context=risk_context(),
    )

    assert result.status == "position_closed"
    assert result.entry_fill_price == "101.82"
    assert result.exit_fill_price == "99.18"
    assert result.realized_pnl == "-113.52"
    assert result.critical_alert == "realized_loss_exceeded_authorized_dollar_risk"
    assert result.audit_events[-1]["event_type"] == "workflow.alert.critical"


def test_chase_threshold_expires_instead_of_chasing() -> None:
    ticks = trade_ticks()
    ticks[3] = NormalizedTrade("2026-07-08T13:35:02Z", "101.30", 4)

    result = simulate_first_five_minute_breakout(
        trades=ticks,
        envelope=run_envelope(),
        authorization=authorization(run_envelope()),
        policy=risk_policy(chase_threshold="0.10"),
        risk_context=risk_context(),
    )

    assert result.status == "expired_chase"
    assert result.shares == "65"
    assert result.entry_fill_price is None
    assert result.audit_events[-1]["event_type"] == "workflow.trigger.expired"


@pytest.mark.parametrize(
    ("policy_overrides", "context_overrides", "message"),
    [
        ({"max_dollar_risk": "50.00"}, {}, "maximum dollar risk"),
        ({"max_shares": 50}, {}, "share cap"),
        ({"max_notional": "5000.00"}, {}, "notional cap"),
        ({}, {"buying_power": "1000.00"}, "buying power"),
        ({}, {"daily_realized_loss": "500.00"}, "daily loss cap"),
        ({}, {"daily_realized_loss": "450.00"}, "daily loss cap"),
        ({}, {"concurrent_positions": 2}, "concurrent position cap"),
    ],
)
def test_risk_policy_caps_block_before_fill(
    policy_overrides: dict[str, object],
    context_overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(BreakoutSimulationError, match=message):
        simulate_first_five_minute_breakout(
            trades=trade_ticks(),
            envelope=run_envelope(),
            authorization=authorization(run_envelope()),
            policy=risk_policy(**policy_overrides),
            risk_context=risk_context(**context_overrides),
        )


def test_authorization_fingerprint_covers_behavior_and_expiry() -> None:
    envelope = run_envelope()
    changed = deepcopy(envelope.to_payload())
    changed["maximum_dollar_loss"] = "125.00"
    changed_envelope = RunEnvelope.from_payload(changed)

    assert fingerprint_run_envelope(envelope) != fingerprint_run_envelope(changed_envelope)

    changed_range = RunEnvelope.from_payload({**envelope.to_payload(), "opening_range_minutes": 1})
    assert fingerprint_run_envelope(envelope) != fingerprint_run_envelope(changed_range)

    with pytest.raises(BreakoutSimulationError, match="fingerprint"):
        simulate_first_five_minute_breakout(
            trades=trade_ticks(),
            envelope=changed_envelope,
            authorization=authorization(envelope),
            policy=risk_policy(),
            risk_context=risk_context(),
        )

    expired = ArmAuthorization(
        run_id=envelope.run_id,
        fingerprint=fingerprint_run_envelope(envelope),
        authorized_at="2026-07-08T13:00:00Z",
        expires_at="2026-07-08T13:34:00Z",
        authorized_by="strategy-operator-001",
    )
    with pytest.raises(BreakoutSimulationError, match="expired"):
        simulate_first_five_minute_breakout(
            trades=trade_ticks(),
            envelope=envelope,
            authorization=expired,
            policy=risk_policy(),
            risk_context=risk_context(),
            evaluated_at="2026-07-08T13:35:00Z",
        )


def test_historical_replay_may_be_armed_after_the_recorded_market_session() -> None:
    envelope = run_envelope(expires_at="2026-08-26T00:00:00Z")
    armed = ArmAuthorization(
        run_id=envelope.run_id,
        fingerprint=fingerprint_run_envelope(envelope),
        authorized_at="2026-08-25T00:00:00Z",
        expires_at="2026-08-26T00:00:00Z",
        authorized_by="strategy-operator-001",
    )

    result = simulate_first_five_minute_breakout(
        trades=trade_ticks(),
        envelope=envelope,
        authorization=armed,
        policy=risk_policy(),
        risk_context=risk_context(),
        evaluated_at="2026-08-25T00:01:00Z",
    )

    assert result.status == "position_open_protected"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"data_complete": False}, "incomplete"),
        ({"data_quality": "gap_detected"}, "quality"),
        ({"reconciled": False}, "reconciliation"),
        ({"emergency_stop_active": True}, "emergency stop"),
    ],
)
def test_data_and_safety_gates_fail_closed(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(BreakoutSimulationError, match=message):
        simulate_first_five_minute_breakout(
            trades=trade_ticks(),
            envelope=run_envelope(),
            authorization=authorization(run_envelope()),
            policy=risk_policy(),
            risk_context=risk_context(),
            **kwargs,
        )


def test_out_of_order_and_duplicate_ticks_are_rejected() -> None:
    duplicate = trade_ticks()
    duplicate.insert(2, duplicate[1])
    with pytest.raises(BreakoutSimulationError, match="duplicate"):
        _simulate(duplicate)

    out_of_order = trade_ticks()
    out_of_order[2] = NormalizedTrade("2026-07-08T13:29:59Z", "100.50", 3)
    with pytest.raises(BreakoutSimulationError, match="out of order"):
        _simulate(out_of_order)


def test_day_entry_lifetime_does_not_use_a_later_session() -> None:
    next_day = [
        NormalizedTrade("2026-07-09T13:30:00Z", "100.00", 20),
        NormalizedTrade("2026-07-09T13:34:59Z", "101.00", 21),
        NormalizedTrade("2026-07-09T13:35:01Z", "101.01", 22),
        NormalizedTrade("2026-07-09T13:35:02Z", "101.03", 23),
    ]
    no_trigger_first_day = trade_ticks()[:2] + [
        NormalizedTrade("2026-07-08T13:35:01Z", "101.00", 3)
    ]

    result = _simulate(no_trigger_first_day + next_day)

    assert result.status == "expired_day"
    assert result.trigger_price is None


def test_gtc_entry_lifetime_resets_opening_range_for_the_next_session() -> None:
    first_day = [
        NormalizedTrade("2026-07-08T13:30:00Z", "99.00", 1),
        NormalizedTrade("2026-07-08T13:34:59Z", "100.00", 2),
        NormalizedTrade("2026-07-08T13:35:01Z", "100.00", 3),
    ]
    second_day = [
        NormalizedTrade("2026-07-09T13:30:00Z", "109.00", 4),
        NormalizedTrade("2026-07-09T13:34:59Z", "110.00", 5),
        NormalizedTrade("2026-07-09T13:35:01Z", "110.01", 6),
        NormalizedTrade("2026-07-09T13:35:02Z", "110.03", 7),
    ]
    envelope = run_envelope(
        entry_lifetime="GTC",
        expires_at="2026-07-09T20:00:00Z",
    )
    armed = ArmAuthorization(
        run_id=envelope.run_id,
        fingerprint=fingerprint_run_envelope(envelope),
        authorized_at="2026-07-08T13:00:00Z",
        expires_at="2026-07-09T20:00:00Z",
        authorized_by="strategy-operator-001",
    )

    result = simulate_first_five_minute_breakout(
        trades=first_day + second_day,
        envelope=envelope,
        authorization=armed,
        policy=risk_policy(max_notional="100000.00"),
        risk_context=risk_context(buying_power="100000.00"),
    )

    assert result.opening_range_high == "110.00"
    assert result.trigger_price == "110.01"


def _simulate(trades: list[NormalizedTrade]):
    envelope = run_envelope()
    return simulate_first_five_minute_breakout(
        trades=trades,
        envelope=envelope,
        authorization=authorization(envelope),
        policy=risk_policy(),
        risk_context=risk_context(),
    )


def trade_ticks() -> list[NormalizedTrade]:
    return [
        NormalizedTrade("2026-07-08T13:30:00Z", "99.50", 1),
        NormalizedTrade("2026-07-08T13:34:59Z", "101.00", 2),
        NormalizedTrade("2026-07-08T13:35:01Z", "101.01", 3),
        NormalizedTrade("2026-07-08T13:35:02Z", "101.03", 4),
        NormalizedTrade("2026-07-08T13:35:03Z", "101.04", 5),
    ]


def run_envelope(**overrides: object) -> RunEnvelope:
    values: dict[str, object] = {
        "run_id": "strategy-run-001",
        "workflow_id": "first-five-minute-breakout",
        "workflow_version": 2,
        "workflow_checksum": "a" * 64,
        "symbol": "AAPL",
        "contract_id": "fixture-contract-aapl",
        "primary_exchange": "NASDAQ",
        "currency": "USD",
        "routing": "SMART",
        "min_tick": "0.01",
        "maximum_dollar_loss": "100.00",
        "runtime_mode": "historical_simulation",
        "dataset_id": "dataset-aapl-2026-07-08",
        "session_date": "2026-07-08",
        "session_timezone": "America/New_York",
        "rth_open": "09:30:00",
        "rth_close": "16:00:00",
        "opening_range_minutes": 5,
        "entry_lifetime": "DAY",
        "position_lifetime": {"kind": "hold_with_protective_stop"},
        "risk_policy_version": "policy-001",
        "expires_at": "2026-07-08T20:00:00Z",
    }
    values.update(overrides)
    return RunEnvelope(**values)


def authorization(envelope: RunEnvelope) -> ArmAuthorization:
    return ArmAuthorization(
        run_id=envelope.run_id,
        fingerprint=fingerprint_run_envelope(envelope),
        authorized_at="2026-07-08T13:00:00Z",
        expires_at="2026-07-08T20:00:00Z",
        authorized_by="strategy-operator-001",
    )


def risk_policy(**overrides: object) -> RiskPolicy:
    values: dict[str, object] = {
        "version_id": "policy-001",
        "max_dollar_risk": "250.00",
        "max_shares": 1000,
        "max_notional": "50000.00",
        "max_concurrent_positions": 2,
        "max_symbol_exposure": "50000.00",
        "max_daily_loss": "500.00",
        "admin_slippage_allowance": "0.02",
        "chase_threshold": "0.50",
    }
    values.update(overrides)
    return RiskPolicy(**values)


def risk_context(**overrides: object) -> RiskContext:
    values: dict[str, object] = {
        "buying_power": "50000.00",
        "concurrent_positions": 0,
        "current_symbol_exposure": "0.00",
        "daily_realized_loss": "0.00",
    }
    values.update(overrides)
    return RiskContext(**values)


def test_execution_recheck_applies_buying_power_to_actual_fill_price() -> None:
    envelope = run_envelope(maximum_dollar_loss="10.00")
    with pytest.raises(BreakoutSimulationError, match="buying power"):
        simulate_first_five_minute_breakout(
            trades=trade_ticks(),
            envelope=envelope,
            authorization=authorization(envelope),
            policy=risk_policy(),
            risk_context=risk_context(buying_power="606.20"),
        )


def test_protective_stop_monitors_later_ticks_after_entry_session_and_expiry() -> None:
    result = _simulate(trade_ticks() + [NormalizedTrade("2026-07-09T13:30:00Z", "99.00", 6)])
    assert result.status == "position_closed"
    assert result.exit_fill_price == "98.98"
    assert result.critical_alert == "realized_loss_exceeded_authorized_dollar_risk"


def test_configured_exit_remains_due_when_next_tick_arrives_the_following_day() -> None:
    envelope = run_envelope(position_lifetime={"kind": "exit_at_time", "time": "15:55:00"})
    result = simulate_first_five_minute_breakout(
        trades=trade_ticks() + [NormalizedTrade("2026-07-09T13:30:00Z", "102.00", 6)],
        envelope=envelope,
        authorization=authorization(envelope),
        policy=risk_policy(),
        risk_context=risk_context(),
    )
    assert result.status == "position_closed"
    assert result.exit_fill_price == "101.98"


def test_entry_is_blocked_when_its_configured_exit_is_already_due() -> None:
    envelope = run_envelope(position_lifetime={"kind": "exit_at_time", "time": "09:35:02"})
    with pytest.raises(BreakoutSimulationError, match="position exit is already due") as error:
        simulate_first_five_minute_breakout(
            trades=trade_ticks(),
            envelope=envelope,
            authorization=authorization(envelope),
            policy=risk_policy(),
            risk_context=risk_context(),
        )
    assert not any(e["event_type"] == "workflow.order.filled" for e in error.value.audit_events)
