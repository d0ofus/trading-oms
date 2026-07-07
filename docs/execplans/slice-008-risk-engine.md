# ExecPlan: Slice 008 Risk Engine

## 1. Goal

Implement structured risk checks that can evaluate proposed risk decisions before any future approval or execution workflow.

## 2. Non-goals

- Broker integration.
- Order submission.
- Live trading.
- Approval tickets.
- OMS state machine.
- Position tracking.
- Fake broker execution.
- Alerts.
- UI.
- Database migrations.

## 3. Safety constraints

- No live trading.
- No secrets.
- No broker connectivity.
- No code path that can transmit orders.
- Every risk decision must be journaled.
- Stale market data must block risk decisions.
- Unknown broker state must block new risk-increasing decisions.
- Duplicate request IDs must be blocked.
- Risk-increasing entry requests must include a protective-order plan or an explicitly approved exception.
- A passed risk decision is not human approval and not permission to execute.

## 4. Current state

The backend has deterministic replay events, local bar building, replay-only strategy signals, and an append-only JSONL event journal. There is no risk engine yet.

## 5. Proposed design

Add a backend `risk_engine` module with:

- `RiskPolicy` for limits and freshness settings;
- `ProtectiveOrderPlan` for minimal protective-stop validation;
- `RiskEvaluationRequest` for a proposed risk decision;
- `RiskCheckResult` and `RiskDecision` for structured results;
- `evaluate_risk` to run deterministic checks and append every decision to the event journal with event type `risk.decision.evaluated`.

The checks will cover:

- allowed symbol;
- duplicate request ID;
- market-data freshness;
- unknown broker state for risk-increasing requests;
- maximum quantity;
- maximum notional;
- protective plan or approved exception for risk-increasing requests.

## 6. Data model changes

Add in-memory backend dataclasses only:

- `RiskPolicy`
- `ProtectiveOrderPlan`
- `RiskEvaluationRequest`
- `RiskCheckResult`
- `RiskDecision`

No database tables, migrations, persistent order records, or state machines.

## 7. API changes

None. This slice adds a Python module interface only.

## 8. Test plan

- Unit tests for passed risk decisions with protective plans.
- Unit tests proving every decision is journaled.
- Unit tests for stale market data, unknown broker state, duplicate request IDs, missing protection, invalid protective stops, quantity limit, and notional limit.
- Unit tests proving risk-reducing requests can pass unknown broker state when market data is fresh.
- Unit tests for request and policy validation.
- Unit tests proving journal payloads contain no broker routing, account, submit, transmit, or live-order fields.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 008 branch changes. Existing replay, bar builder, strategy, journal, configuration, and application skeleton remain independent.

## 11. Implementation steps

1. Mark Slice 008 in progress and create the slice branch.
2. Add focused risk-engine tests.
3. Implement the smallest deterministic risk-engine module needed to satisfy the tests.
4. Document risk-engine behavior and limitations.
5. Run verification.
6. Self-review and red-team trading safety implications.
7. Mark Slice 008 ready for human review only after verification passes.

## 12. Completion criteria

- Risk engine module exists.
- Risk decisions include structured check results.
- Every risk decision is journaled.
- Stale market data blocks decisions.
- Unknown broker state blocks risk-increasing decisions.
- Duplicate request IDs are blocked.
- Risk-increasing requests require a protective plan or explicitly approved exception.
- Quantity and notional limits are enforced.
- Tests cover passed decisions, blocked decisions, journaling, and validation failures.
- Verification passes.
- No broker connectivity or order submission path is added.
- No secrets are introduced.

## 13. Risks and assumptions

- The initial request model is a risk-evaluation input, not an OMS order intent.
- Passed risk decisions are explicitly not approvals and not execution permission.
- Position-aware risk reduction is deferred until position tracking exists.
- Numeric values currently use Python floats because earlier slices use Python floats.
