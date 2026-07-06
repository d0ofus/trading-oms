# ExecPlan: Slice 005 deterministic market-data replay

## 1. Goal

Create a deterministic local market-data replay format and basic backend reader for simulation-only workflows.

## 2. Non-goals

- Live market-data ingestion.
- Broker integration.
- Order submission.
- Strategy execution.
- Bar building.
- Risk engine.
- UI.

## 3. Safety constraints

- No live trading.
- No secrets.
- Default paper/simulation mode remains unchanged.
- No broker connectivity.
- No order path.
- Replay is local-file only.
- Replay readback must be deterministic and validated before use.

## 4. Current state

The backend has safe configuration and a local JSONL event journal. No market-data replay reader or replay event schema exists yet.

## 5. Proposed design

- Add a `MarketDataReplayEvent` dataclass with `schema_version`, `sequence`, `timestamp`, `symbol`, `event_type`, and `payload`.
- Add a `JsonlMarketDataReplay` reader for newline-delimited JSON replay files.
- Validate JSON shape, required fields, JSON-serializable payloads, contiguous sequence order, and nondecreasing timestamps.
- Keep the format local-only and deterministic; do not add live ingestion or external data access.
- Document the replay record shape, guarantees, and limitations.

## 6. Data model changes

No database changes. Replay files are newline-delimited JSON with one validated market-data event per line.

## 7. API changes

Add a backend Python module API:
- `MarketDataReplayEvent`
- `JsonlMarketDataReplay`
- `ReplayError`
- `ReplayValidationError`

## 8. Test plan

- Unit tests for stable record shape and round trip.
- Unit tests for deterministic readback in file order.
- Unit tests rejecting missing fields, invalid payload type, invalid JSON, blank lines, duplicate/out-of-order sequences, and decreasing timestamps.
- Existing full verification.

## 9. Verification commands

- `make verify`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1`

## 10. Rollback plan

Revert the Slice 005 branch changes. No migrations, external services, broker connections, live data feeds, or trading behavior are introduced.

## 11. Implementation steps

1. Add replay reader tests.
2. Implement the JSONL replay module.
3. Add replay format docs.
4. Mark Slice 005 ready for human review when verification passes.

## 12. Completion criteria

- Replay module exists.
- Replay events include sequence, timestamp, symbol, event type, and payload.
- Replay reader returns deterministic file order.
- Invalid replay records fail validation.
- Out-of-order or duplicate sequences fail validation.
- Verification passes.
- No live data source, broker order transmission, or secrets are introduced.

## 13. Risks and assumptions

- This slice intentionally supports only local JSONL replay files.
- Live market-data adapters are out of scope.
- Bar construction and strategy consumption come in later slices.
