# ExecPlan: Slice 004 append-only event journal

## 1. Goal

Add a backend append-only event journal foundation that can persist and replay validated audit records in deterministic order.

## 2. Non-goals

- Database migrations.
- Broker integration.
- Order submission.
- Live trading.
- Full OMS integration.
- Alerts.
- UI.

## 3. Safety constraints

- No live trading.
- No secrets.
- Default paper/simulation mode remains unchanged.
- No broker connectivity.
- No order path.
- Journal writes must append only and must not rewrite prior records.
- Invalid or unordered journal records must fail validation.

## 4. Current state

The backend has a minimal FastAPI app, strict safe configuration, and verification checks. No event journal module exists yet.

## 5. Proposed design

- Add a `JournalRecord` dataclass with `schema_version`, `sequence`, `type`, `timestamp`, and `payload`.
- Add a JSONL-backed `JsonlEventJournal` that reads existing records to determine the next sequence and appends exactly one new line per event.
- Validate required fields, payload object shape, JSON serializability, timestamp parseability, and sequence ordering.
- Keep the journal local-only and broker-agnostic.
- Document current guarantees and limitations.

## 6. Data model changes

No database changes. The file format is newline-delimited JSON with one validated event record per line.

## 7. API changes

Add a backend Python module API:
- `JournalRecord`
- `JsonlEventJournal`
- `JournalError`
- `JournalValidationError`

## 8. Test plan

- Unit tests for appending and deterministic readback order.
- Unit test proving a second append preserves the exact previous file bytes.
- Unit tests rejecting missing fields, invalid payload type, invalid JSON, and out-of-order sequences.
- Existing full verification.

## 9. Verification commands

- `make verify`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1`

## 10. Rollback plan

Revert the Slice 004 branch changes. No migrations, external services, broker connections, or trading behavior are introduced.

## 11. Implementation steps

1. Add journal tests.
2. Implement the JSONL journal module.
3. Add event journal docs.
4. Mark Slice 004 ready for human review when verification passes.

## 12. Completion criteria

- Event journal module exists.
- Journal records include type, timestamp, payload, and sequence metadata.
- Appending preserves existing records and never rewrites prior entries.
- Journal readback is deterministic and ordered.
- Invalid journal records fail validation.
- Verification passes.
- No broker order transmission or secrets are introduced.

## 13. Risks and assumptions

- This slice uses local JSONL only; production database-backed journaling is out of scope.
- File locking and concurrent writer coordination are out of scope for this first foundation.
- Callers remain responsible for not placing secrets in payloads.
