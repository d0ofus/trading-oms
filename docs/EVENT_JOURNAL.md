# Event Journal

The event journal is the audit foundation for safety-critical trading workflow events.

Slice 004 introduces a local JSONL journal only. It does not add broker connectivity, order submission, OMS integration, database migrations, or live trading.

## Record Shape

Each line is one JSON object:

```json
{
  "schema_version": 1,
  "sequence": 1,
  "type": "system.started",
  "timestamp": "2026-07-06T00:00:00Z",
  "payload": {}
}
```

Fields:

- `schema_version`: currently `1`.
- `sequence`: contiguous positive integer assigned by the journal.
- `type`: non-empty event type string.
- `timestamp`: ISO-8601 timestamp string.
- `payload`: JSON object with event-specific data.

## Guarantees

- Appends add one new line and preserve existing file bytes.
- Readback validates every line before returning records.
- Readback order is deterministic and sequence-ordered.
- Invalid JSON, blank lines, missing fields, invalid timestamps, non-object payloads, non-standard JSON values, and non-contiguous sequences fail validation.

## Current Limitations

- Local JSONL storage only.
- No concurrent writer coordination yet.
- No database-backed journal yet.
- No event producers are wired into trading behavior yet.
- Callers must not put secrets in payloads.
