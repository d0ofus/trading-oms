# Bar Builder

Slice 006 introduces deterministic local OHLCV bar construction from validated replay events.

It does not add live market-data ingestion, broker connectivity, order submission, strategy execution, risk checks, OMS integration, event journal integration, UI, or live trading.

## Bar Shape

Bars are in-memory Python records with this JSON-compatible shape:

```json
{
  "schema_version": 1,
  "symbol": "AAPL",
  "timeframe_seconds": 60,
  "start_timestamp": "2026-07-06T00:00:00Z",
  "end_timestamp": "2026-07-06T00:01:00Z",
  "open": 100.0,
  "high": 101.0,
  "low": 99.0,
  "close": 100.5,
  "volume": 14.0,
  "event_count": 4
}
```

Fields:

- `schema_version`: currently `1`.
- `symbol`: configured uppercase symbol for the bar stream.
- `timeframe_seconds`: positive whole-second bar duration.
- `start_timestamp`: UTC inclusive bucket start.
- `end_timestamp`: UTC exclusive bucket end.
- `open`, `high`, `low`, `close`: derived from replay event prices.
- `volume`: sum of trade `size` or `volume` values. Missing trade size contributes `0.0`.
- `event_count`: number of replay events included in the bar.

## Supported Events

The builder accepts already validated `MarketDataReplayEvent` records.

Supported event types:

- `trade`: requires a positive numeric `price`; optional `size` or `volume` must be nonnegative.
- `quote`: requires an explicit `quote_price_source` of `bid`, `ask`, or `mid`. Quote bars contribute zero volume.

Unsupported event types fail validation.

## Guarantees

- Bar building is local and deterministic.
- No network or live-feed source is used.
- No broker or order path is introduced.
- Output bar order follows replay event order and timeframe buckets.
- Timestamps must be nondecreasing.
- Event symbols must match the configured symbol.
- Timeframes must be positive whole-second durations.
- Invalid prices, sizes, quote payloads, quote price sources, symbols, and timestamps fail closed.

## Current Limitations

- Local in-memory output only.
- One configured symbol per build call.
- No empty bars are emitted for gaps.
- No event journal integration yet.
- No strategy, risk, OMS, approval, alert, broker, or UI integration yet.
- Numeric values currently use Python floats because replay payloads are JSON numbers.
