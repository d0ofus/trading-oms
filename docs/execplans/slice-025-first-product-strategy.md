# ExecPlan: Slice 025 first product strategy

## 1. Goal

Implement the product requirements strategy in replay mode: detect a first 5-minute bar high
breakout only when cumulative volume is at least 1.5x the 10-session average cumulative volume at
the same session time.

## 2. Non-goals

- No live market data.
- No order intents.
- No approval mutation endpoints.
- No fake broker orchestration.
- No broker connectivity.
- No IBKR transport.
- No live trading.

## 3. Safety constraints

- The strategy emits replay-only signals, not orders.
- Every generated signal must be journaled.
- Signal payloads must not contain quantity, side, broker routing, account, credential, submit, or
  transmit fields.
- Inputs must be deterministic local `Bar` records.
- The 10-session volume baseline must be explicit and local.
- No network client, broker SDK, HTTP mutation endpoint, or live-trading path is added.

## 4. Current state

The repo already has deterministic bars, append-only journaling, and a demo `close_above_sma`
replay strategy. The product requirements strategy does not exist yet.

## 5. Proposed design

Add `trading_oms_backend.product_strategy` with typed config, historical volume sessions, and
signal records. The runner consumes current-session 5-minute bars plus exactly 10 historical
sessions, detects the first post-opening-range high breakout, applies the cumulative-volume filter,
journals the resulting signal, and returns at most one signal.

## 6. Data model changes

New in-memory Python records only:

- `ProductBreakoutStrategyConfig`
- `HistoricalVolumeSession`
- `ProductBreakoutSignal`

No database schema or persistence layer is added.

## 7. API changes

None. No HTTP, CLI, config, broker, or frontend API is added in this slice.

## 8. Test plan

- Unit tests for the passing breakout plus volume-filter path.
- Unit tests for blocked breakouts when cumulative volume is below threshold.
- Unit tests for no-breakout and insufficient-current-bar behavior.
- Unit tests for stable JSON signal shape and journal coverage.
- Validation tests for config, current bars, historical sessions, and missing same-session-time
  volume baselines.
- Source/payload safety tests proving no broker, network, order-submission, credential, or live
  trading affordances are added.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\trading-oms-pytest-slice025" backend\tests\test_product_strategy.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 025 commit to remove the product strategy module, tests, docs, and slice status
updates.

## 11. Implementation steps

1. Add focused product strategy tests.
2. Implement the replay-only product strategy model and runner.
3. Add product strategy documentation.
4. Update README and `docs/SLICES.md`.
5. Run focused and full verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- The product strategy detects first 5-minute bar high breakouts.
- The strategy requires cumulative volume to be at least 1.5x the 10-session average cumulative
  volume at the same session time.
- Every generated signal is journaled.
- Tests cover deterministic signal generation, validation, journaling, and safety boundaries.
- Verification passes.
- No order intent, order submission, broker transport, HTTP mutation endpoint, credentials, or
  live-trading path is added.

## 13. Risks and assumptions

- The runner returns at most one replay-only signal for the first qualifying breakout.
- Historical same-session-time volume is represented by matching 5-minute bar indexes across the
  10 historical sessions.
- Quantity and side remain intentionally out of the signal payload; Slice 026 will introduce
  non-executable order-intent proposals behind safety validation.
