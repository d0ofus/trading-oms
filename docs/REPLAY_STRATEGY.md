# Replay Strategy

Slice 007 introduces the first deterministic replay-only strategy.

It does not add live market-data ingestion, broker connectivity, order intents, order submission, risk checks, approvals, OMS integration, alerts, UI, Strategy DSL execution, or live trading.

## Strategy

The initial strategy is hard-coded:

```text
close_above_sma
```

For each bar with enough trailing history, it compares the bar close against the trailing simple moving average.

Signals:

- `long_bias`: bar close is above the trailing simple moving average.
- `risk_off_bias`: bar close is at or below the trailing simple moving average.

These are replay signals only. They are not buy or sell orders, order intents, approvals, risk decisions, or broker instructions.

## Signal Shape

Each generated signal is JSON-compatible:

```json
{
  "schema_version": 1,
  "strategy_id": "close-above-sma-demo",
  "strategy_type": "close_above_sma",
  "symbol": "AAPL",
  "bar_start_timestamp": "2026-07-06T00:02:00Z",
  "bar_end_timestamp": "2026-07-06T00:03:00Z",
  "signal": "long_bias",
  "close": 103.0,
  "moving_average": 101.33333333333333,
  "lookback_bars": 3,
  "reason": "close_above_sma"
}
```

## Journal Requirement

Every generated strategy signal is appended to the existing event journal with event type:

```text
strategy.signal.generated
```

The journal timestamp is the signal bar's `bar_end_timestamp`.

## Guarantees

- Strategy execution is local and deterministic.
- The strategy consumes local `Bar` records only.
- No network, live feed, broker, account, order-routing, order-submission, or credential path is used.
- Signal payloads exclude order-shaped fields such as account, broker, side, quantity, order type, submit, and transmit.
- Invalid config, invalid bars, mixed symbols, mixed timeframes, decreasing timestamps, invalid prices, and invalid signal payloads fail validation.

## Current Limitations

- One hard-coded strategy only.
- No Strategy DSL integration yet.
- No risk engine integration yet.
- No fake broker or OMS integration yet.
- No approval workflow yet.
- No UI yet.
- Numeric values currently use Python floats because bars currently use Python floats.
