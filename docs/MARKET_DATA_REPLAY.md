# Market-Data Replay

Slice 005 introduces a deterministic local market-data replay format and backend reader.

It does not add live market-data ingestion, broker connectivity, order submission, strategy execution, bar building, or live trading.

## Record Shape

Each replay file is newline-delimited JSON. Each line is one market-data event:

```json
{
  "schema_version": 1,
  "sequence": 1,
  "timestamp": "2026-07-06T00:00:00Z",
  "symbol": "AAPL",
  "event_type": "trade",
  "payload": {
    "price": 100.25,
    "size": 10
  }
}
```

Fields:

- `schema_version`: currently `1`.
- `sequence`: contiguous positive integer in file order.
- `timestamp`: timezone-aware ISO-8601 timestamp string.
- `symbol`: uppercase symbol string.
- `event_type`: non-empty market-data event type, such as `trade` or `quote`.
- `payload`: JSON object with event-specific data.

## Guarantees

- Replay is local-file only.
- Readback returns events in deterministic file order.
- Every line is validated before events are returned.
- Sequence numbers must be contiguous starting at `1`.
- Timestamps must be timezone-aware and nondecreasing.
- Invalid JSON, blank lines, missing fields, invalid timestamps, non-object payloads, non-standard JSON values, duplicate sequences, and out-of-order sequences fail validation.

## Current Limitations

- No live feed integration.
- No bar building yet.
- No strategy execution yet.
- No event journal integration yet.
- No concurrent file mutation handling.
