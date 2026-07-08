# ExecPlan: Slice 027 replay to risk to approval orchestration

## 1. Goal

Wire deterministic replay, local bars, the product strategy, non-routable order-intent proposals,
risk decisions, OMS pending-approval context, and approval-ticket creation into one simulation
orchestration path.

## 2. Non-goals

- No approval decision endpoints.
- No automatic approval.
- No fake broker execution.
- No simulated fills.
- No position tracking.
- No broker connectivity.
- No IBKR transport.
- No live trading.

## 3. Safety constraints

- Risk must pass before approval-ticket creation.
- Approval tickets must not be created when stale market data, duplicate request IDs, or unknown
  broker state block risk.
- Order intents remain non-routable proposals.
- OMS is used only to create a local `PENDING_APPROVAL` context.
- No broker adapter or fake broker execution is invoked.
- Every generated signal, proposal, risk decision, OMS transition, approval ticket, and simulation
  run transition must be journaled by the existing domain modules.
- No network client, broker SDK, HTTP mutation endpoint, or live-trading path is added.

## 4. Current state

The repo has simulation run records, the product replay strategy, non-routable order-intent
proposals, risk checks, OMS transitions, and approval tickets as separate domain modules. They are
not yet orchestrated into a deterministic simulation path.

## 5. Proposed design

Add `trading_oms_backend.simulation_orchestration` with `ReplayToApprovalOrchestrator`. The
orchestrator owns in-memory run, proposal, OMS, and approval-ticket books for deterministic local
execution. A run loads replay events into 5-minute bars, generates at most one product-strategy
signal, creates a non-routable order-intent proposal, evaluates risk, creates OMS `CREATED` and
`PENDING_APPROVAL` transitions only when risk passes, and then creates a pending approval ticket.

## 6. Data model changes

New in-memory Python records only:

- `ReplayToApprovalConfig`
- `ReplayToApprovalResult`

No database schema or persistence layer is added.

## 7. API changes

None. No HTTP, CLI, config, broker, or frontend API is added in this slice.

## 8. Test plan

- Integration-style unit test for replay to pending approval-ticket creation.
- Tests proving stale market data, unknown broker state, and duplicate risk request IDs block
  before approval-ticket creation.
- Test proving no breakout creates no proposal, risk decision, or approval ticket.
- Test proving duplicate order-intent proposal IDs are blocked and the simulation run fails safely.
- Source safety test proving no broker, network, order-submission, credential, or live-trading
  affordances are added.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\trading-oms-pytest-slice027" backend\tests\test_simulation_orchestration.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 027 commit to remove the simulation orchestration module, tests, docs, and slice
status updates.

## 11. Implementation steps

1. Add focused orchestration tests.
2. Implement the replay-to-approval orchestrator.
3. Add orchestration documentation.
4. Update README and `docs/SLICES.md`.
5. Run focused and full verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Replay events are deterministically converted to local bars.
- Product strategy signals can create non-routable order-intent proposals.
- Proposals are evaluated by the risk engine.
- Approval tickets are created only after passed risk and local OMS pending-approval context.
- Stale data, duplicate risk request IDs, and unknown broker state block approval-ticket creation.
- Duplicate order-intent proposal IDs are blocked.
- Verification passes.
- No approval decision endpoint, fake broker execution, simulated fill, broker transport, order
  submission, credentials, or live-trading path is added.

## 13. Risks and assumptions

- The orchestrator remains in-memory until later persistence work.
- Product strategy signals currently create buy/increase market proposals with protective stops at
  the first 5-minute bar high.
- Slice 028 will add explicit simulation-only approval decisions.
- Slice 029 will advance approved simulation orders through OMS and fake broker.
