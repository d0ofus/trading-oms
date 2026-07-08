# ExecPlan: Slice 014 Strategy DSL

## 1. Goal

Add the first typed Strategy DSL foundation for deterministic replay-only strategy configuration,
validation, and execution through the existing `close_above_sma` strategy path.

## 2. Non-goals

- Live trading.
- Broker integration.
- Order intents or order submission.
- Risk checks.
- Approval tickets.
- OMS integration.
- Fake broker orchestration.
- Real market-data ingestion.
- Arbitrary expressions or code execution.
- YAML parser dependency.
- Visual workflow builder.
- UI editing.

## 3. Safety constraints

- Do not enable live trading.
- Do not add any broker connectivity or order-transmission path.
- Do not add credentials, tokens, account IDs, passwords, certificates, private keys, or secrets.
- The DSL must be validated before execution.
- The DSL must be deterministic and replay-compatible.
- The DSL must not support arbitrary code, expressions, scripts, imports, or functions.
- The DSL must not support action/order/broker fields.
- Generated signals must continue to be journaled through the existing event journal path.

## 4. Current state

The backend has one hard-coded replay-only `close_above_sma` strategy in
`replay_strategy.py`. It consumes local `Bar` records, emits deterministic bias signals, and
journals every generated signal. `docs/STRATEGY_DSL.md` says the DSL is not implemented.

## 5. Proposed design

Add `trading_oms_backend.strategy_dsl` with:

- typed dataclasses for DSL documents and parameters;
- parser functions for JSON-compatible dictionaries and JSON strings;
- strict schema validation and unknown-field rejection;
- recursive rejection of broker/order/action/secret/code-shaped keys and credential-shaped text;
- compiler to the existing `ReplayStrategyConfig`;
- replay runner that dispatches only to `run_close_above_sma_strategy`.

The initial DSL supports only:

- `schema_version: 1`
- `strategy_type: close_above_sma`
- `mode: replay`
- uppercase `symbol`
- positive whole-second `bar_timeframe_seconds`
- `parameters.lookback_bars`
- `parameters.price_source: close`

## 6. Data model changes

Add Python dataclasses only:

- `StrategyDslParameters`
- `StrategyDslDocument`

No database tables or migrations.

## 7. API changes

No HTTP API, CLI command, config key, dependency, or external integration changes.

The new backend module exposes local Python parser/compiler/runner functions.

## 8. Test plan

- Unit tests for parsing from dict and JSON string.
- Unit tests for stable JSON shape.
- Unit tests for compiling DSL to `ReplayStrategyConfig`.
- Unit tests for deterministic replay execution and signal journaling through the existing path.
- Unit tests for validation failures: invalid schema, unsupported mode/type/source, invalid symbol,
  invalid timeframe, invalid lookback, unknown fields, broker/order/action fields, secrets, and
  arbitrary-code-shaped fields.
- Unit tests proving DSL documents and generated signals do not contain order/broker/secret-shaped
  payload fields.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the slice branch changes to remove the DSL module, tests, docs, ExecPlan, and Slice 014
status updates. No persistent data or external state is introduced.

## 11. Implementation steps

1. Add focused Strategy DSL tests.
2. Implement `trading_oms_backend.strategy_dsl`.
3. Update Strategy DSL and replay strategy docs.
4. Update README and slice status.
5. Run verification and repair failures.
6. Self-review and red-team the DSL safety boundary.

## 12. Completion criteria

- Strategy DSL module exists.
- DSL documents are versioned and validated before execution.
- DSL supports the existing `close_above_sma` replay strategy.
- DSL can compile to the existing replay strategy config.
- DSL replay runner journals generated signals through the existing strategy path.
- DSL rejects live mode, broker/order/action fields, secrets, unsupported strategy types, and
  arbitrary-code-shaped fields.
- Tests cover parsing, validation failures, deterministic replay execution, journal coverage, and
  no order/broker/secret-shaped payloads.
- Verification passes.
- No live broker connectivity or order submission path is added.
- No real credentials, tokens, or secrets are introduced.

## 13. Risks and assumptions

- YAML is intentionally deferred to avoid adding a dependency in this safety slice.
- The DSL is intentionally narrow; future visual-builder work should compile into this typed shape
  rather than adding arbitrary expressions.
- Future strategy types must be added explicitly with their own validation and replay tests.
