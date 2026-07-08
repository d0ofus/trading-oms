# Product Strategy

Slice 025 adds the first product-requirements strategy in replay mode.

This slice does not add live market data, order intents, approval endpoints, fake broker
orchestration, broker connectivity, IBKR transport, order submission, or live trading.

## Strategy

The strategy is:

```text
first_5_minute_breakout_volume_filter
```

It consumes local 5-minute `Bar` records for the current session and exactly 10 historical sessions
of local 5-minute bars.

A replay-only signal is generated when:

- a post-opening-range bar's high is greater than the first 5-minute bar high; and
- cumulative current-session volume through that bar is at least 1.5x the 10-session average
  cumulative volume at the same bar index.

The runner returns at most one signal for the first qualifying breakout.

## Signal Shape

Generated signals are JSON-compatible and intentionally not order-shaped:

```json
{
  "schema_version": 1,
  "strategy_id": "first-bar-breakout-demo",
  "strategy_type": "first_5_minute_breakout_volume_filter",
  "symbol": "AAPL",
  "trigger_bar_start_timestamp": "2026-07-08T13:40:00Z",
  "trigger_bar_end_timestamp": "2026-07-08T13:45:00Z",
  "signal": "long_entry_candidate",
  "first_bar_high": 101.5,
  "breakout_bar_high": 102.2,
  "cumulative_volume": 380.0,
  "average_cumulative_volume": 200.0,
  "volume_threshold": 300.0,
  "volume_multiplier": 1.5,
  "historical_session_count": 10,
  "reason": "first_5_minute_high_breakout_with_volume_filter"
}
```

The signal payload does not include quantity, side, order type, order ID, client order ID, broker
route, account ID, credentials, submit, or transmit fields.

## Journal Requirement

Every generated product strategy signal is appended to the event journal with event type:

```text
strategy.signal.generated
```

The journal timestamp is the triggering bar's end timestamp.

## Guarantees

- Strategy execution is local and deterministic.
- The strategy consumes local `Bar` records only.
- The historical volume baseline must contain exactly 10 local sessions.
- All current and historical bars must match the configured symbol and 300-second timeframe.
- Invalid config, invalid bars, missing same-session-time baseline bars, duplicate historical
  session IDs, mixed symbols, mixed timeframes, decreasing timestamps, invalid prices, and invalid
  volumes fail validation.
- No network, live feed, broker, account, order-routing, order-submission, or credential path is
  used.

## Current Limitations

- Historical same-session-time volume is represented by matching 5-minute bar indexes.
- The strategy emits replay-only signals, not order intents.
- Quantity and side are intentionally deferred to Slice 026's non-executable order-intent proposal
  model.
- No Strategy DSL or visual workflow integration exists for this product strategy yet.
