# ExecPlan: Slice 007 First Replay-Only Strategy

## 1. Goal

Implement the first deterministic replay-only strategy over locally built bars.

## 2. Non-goals

- Live market-data ingestion.
- Broker integration.
- Order intents or order submission.
- Position tracking.
- Risk engine behavior.
- Approval tickets.
- OMS integration.
- Alerts.
- UI.
- Strategy DSL or visual workflow builder.

## 3. Safety constraints

- No live trading.
- No secrets.
- No network access or live market-data source.
- No broker connectivity.
- No code path that can transmit orders.
- The strategy must run only on already built local bars.
- Generated signals must be journaled.
- Signals must not include order quantity, broker routing, account identifiers, or submission instructions.
- This slice must not make risk decisions or approve execution.

## 4. Current state

The backend has:

- deterministic local market-data replay records and JSONL reader;
- deterministic local OHLCV bar building from replay events;
- append-only local JSONL event journal.

No strategy module exists yet.

## 5. Proposed design

Add a backend replay strategy module with:

- `ReplayStrategyConfig` for a hard-coded close-vs-simple-moving-average strategy;
- `ReplayStrategySignal` for JSON-compatible bias signals;
- `run_close_above_sma_strategy` to evaluate bars in deterministic order and append every generated signal to `JsonlEventJournal`.

The strategy emits:

- `long_bias` when bar close is above the trailing simple moving average;
- `risk_off_bias` when bar close is at or below the trailing simple moving average.

It does not emit buy/sell orders, order intents, risk decisions, approvals, or broker instructions.

## 6. Data model changes

Add in-memory backend dataclasses only:

- `ReplayStrategyConfig`
- `ReplayStrategySignal`

Journal records use the existing JSONL event journal with event type `strategy.signal.generated`.

No database tables, migrations, persistent order records, or state machines.

## 7. API changes

None. This slice adds a Python module interface only.

## 8. Test plan

- Unit tests for deterministic signal generation from bars.
- Unit tests proving every generated signal is appended to the journal.
- Unit tests proving no signal payload contains order-submission fields.
- Unit tests for insufficient bars producing no signals and no journal entries.
- Unit tests for validation failures on invalid config, mixed symbols, mixed timeframes, decreasing timestamps, invalid prices, and invalid signal payloads.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 007 branch changes. Existing replay, bar builder, journal, configuration, and application skeleton remain independent.

## 11. Implementation steps

1. Mark Slice 007 in progress and create the slice branch.
2. Add focused replay-strategy tests.
3. Implement the smallest replay-only strategy module needed to satisfy the tests.
4. Document strategy behavior and limitations.
5. Run verification.
6. Self-review and red-team trading safety implications.
7. Mark Slice 007 ready for human review only after verification passes.

## 12. Completion criteria

- Replay-only strategy module exists.
- Strategy consumes local bars only.
- Strategy emits deterministic bias signals, not order intents.
- Every generated signal is journaled.
- Signal payloads contain no broker, account, order routing, quantity, or submission fields.
- Invalid strategy inputs fail validation.
- Tests cover deterministic signal generation, journaling, and validation failures.
- Verification passes.
- No live market-data source is added.
- No code path can transmit broker orders.
- No secrets are introduced.

## 13. Risks and assumptions

- The initial strategy is intentionally hard-coded and simple; the full DSL is deferred.
- Signals use Python floats because bars currently use Python floats.
- `risk_off_bias` is only a replay signal label, not an execution instruction.
- Event journal storage remains local JSONL only.
