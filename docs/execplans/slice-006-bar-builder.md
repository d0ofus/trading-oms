# ExecPlan: Slice 006 Bar Builder

## 1. Goal

Build deterministic local OHLCV bars from validated market-data replay events.

## 2. Non-goals

- Live market-data ingestion.
- Broker integration.
- Order submission.
- Strategy execution.
- Risk engine behavior.
- OMS integration.
- UI.
- Event journal integration.

## 3. Safety constraints

- No live trading.
- No secrets.
- No network access or live market-data source.
- No broker connectivity.
- No code path that can transmit orders.
- Bar building must operate only on local replay events.
- Invalid or unsupported replay payloads must fail closed instead of producing misleading bars.
- Stale market-data blocking remains a future trading-decision concern; this slice does not make trading decisions.

## 4. Current state

`backend/src/trading_oms_backend/market_data_replay.py` defines validated local replay events and a JSONL reader. Replay events are deterministic, sequence-ordered, timezone-aware, and local-file only. No bar builder exists yet.

## 5. Proposed design

Add a backend `bar_builder` module with:

- a frozen `Bar` dataclass for one OHLCV bar;
- a `BarBuilderConfig` dataclass for symbol, timeframe, and optional price source;
- a `build_time_bars` function that consumes validated `MarketDataReplayEvent` objects and returns deterministic bars in event order;
- validation that accepts `trade` events with numeric `price` and optional numeric `size` or `volume`;
- validation that accepts `quote` events only when configured to derive price from `bid`, `ask`, or `mid`;
- hard failures for mixed symbols, unsupported event types, invalid prices, invalid sizes, nonpositive timeframes, and decreasing timestamps.

## 6. Data model changes

Add in-memory backend dataclasses only:

- `BarBuilderConfig`
- `Bar`

No database tables, migrations, persistent records, or order state changes.

## 7. API changes

None. This slice adds a Python module interface only.

## 8. Test plan

- Unit tests for deterministic OHLCV bars from trade replay events.
- Unit tests for timeframe bucketing across minute boundaries.
- Unit tests for stable handling of quote-derived mid prices.
- Unit tests for validation failures on unsupported event types, mixed symbols, missing prices, invalid sizes, nonpositive timeframes, and decreasing timestamps.
- No integration, replay-engine, chaos, or e2e behavior beyond existing placeholders.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 006 branch changes. The existing replay reader, event journal, configuration, and application skeleton remain independent.

## 11. Implementation steps

1. Mark Slice 006 in progress and create the slice branch.
2. Add focused bar-builder tests.
3. Implement the smallest deterministic bar-builder module needed to satisfy the tests.
4. Document bar-builder behavior and limitations.
5. Run verification.
6. Self-review and red-team safety implications.
7. Mark Slice 006 ready for human review only after verification passes.

## 12. Completion criteria

- Bar builder module exists.
- Bars include symbol, timeframe, start/end timestamps, open, high, low, close, and volume.
- Trade replay events build deterministic OHLCV bars.
- Quote replay events can build deterministic bars only through an explicit configured price source.
- Invalid or unsupported events fail validation.
- Tests cover readback-to-bar behavior and validation failures.
- Verification passes.
- No live market-data source is added.
- No code path can transmit broker orders.
- No secrets are introduced.

## 13. Risks and assumptions

- The initial bar model uses Python floats because replay payloads currently carry JSON numbers. Decimal precision may be revisited before production trading decisions depend on bars.
- Empty input returns an empty bar list.
- Timeframe alignment is based on Unix epoch bucket boundaries using timezone-aware timestamps.
- Journal integration is intentionally deferred.
