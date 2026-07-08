# ExecPlan: Slice 015 Visual Workflow Builder

## 1. Goal

Add the first frontend visual workflow builder foundation for the existing replay-only
`close_above_sma` Strategy DSL.

## 2. Non-goals

- Live trading.
- Broker integration.
- Order intents or order submission.
- Risk checks.
- Approval execution workflow.
- OMS or fake broker orchestration.
- Real market-data ingestion.
- Backend API mutation or persistence.
- Adding React Flow or other new dependencies.
- Arbitrary expressions, custom scripts, or code execution.
- Drag-and-drop graph editing.
- Importing or exporting files.
- Real credentials, tokens, or secrets.

## 3. Safety constraints

- Do not enable live trading.
- Do not add broker connectivity or order-transmission paths.
- Do not add credentials, tokens, account IDs, passwords, certificates, private keys, or secrets.
- Keep the builder local and replay-only.
- Generated DSL must use `mode: replay`, `strategy_type: close_above_sma`, and safe fields only.
- The UI must not include submit/place/transmit order, connect broker, live trading, Telegram send,
  credential, import/export, or code execution controls.

## 4. Current state

The frontend has a static read-only operations shell with safety posture, workflow sections, and
tests that render the app to static markup. Slice 014 added a backend Strategy DSL that accepts a
JSON-compatible replay-only document for `close_above_sma`.

## 5. Proposed design

Extend the existing React/Vite frontend with a local visual builder section:

- static node graph representing replay bars, SMA calculation, signal generation, and DSL output;
- controlled safe inputs for symbol, lookback bars, and bar timeframe seconds;
- generated JSON DSL preview from local state;
- explicit replay-only/no-broker/no-order/no-credentials safety labels.

Use existing React and CSS only. Do not add dependencies.

## 6. Data model changes

None. The visual builder uses local frontend state only.

## 7. API changes

None. No backend API, CLI command, config key, network call, persistence, import, or export is added.

## 8. Test plan

- Frontend render tests for visual builder section and expected node labels.
- Frontend render tests for generated DSL preview fields.
- Frontend render tests for safe local controls.
- Frontend safety test updates proving forbidden live-action, broker, secret, import/export, and
  code-execution affordances are absent.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the slice branch changes to remove the visual builder UI, tests, docs, ExecPlan, and Slice
015 status updates. No persistent data or external state is introduced.

## 11. Implementation steps

1. Add frontend tests for the visual builder and generated safe DSL preview.
2. Add local visual builder state, node graph, controls, and DSL preview to the frontend shell.
3. Add CSS for the builder layout using the existing visual language.
4. Update docs and slice acceptance status.
5. Run verification and repair failures.
6. Self-review and red-team the UI safety boundary.

## 12. Completion criteria

- Visual workflow builder section exists in the frontend shell.
- Builder represents the replay-only `close_above_sma` flow as visual nodes.
- Builder can update safe local DSL fields for symbol, lookback bars, and timeframe.
- Builder renders generated DSL preview with `schema_version: 1`, `mode: replay`, and
  `strategy_type: close_above_sma`.
- UI clearly states no broker connectivity, no order actions, and no credential fields.
- UI contains no enabled order submission, broker, live trading, Telegram, credential,
  import/export, or code-execution controls.
- Tests cover node rendering, DSL preview behavior, safe editable controls, and forbidden
  live-action affordances.
- Verification passes.
- No live broker connectivity or order submission path is added.
- No real credentials, tokens, or secrets are introduced.

## 13. Risks and assumptions

- React Flow is deferred because dependency installs require an explicit gate.
- The first builder is a deterministic local foundation, not a full graph editor.
- Future visual builder work should map graph editing into the same typed DSL shape rather than
  introducing arbitrary expressions.
