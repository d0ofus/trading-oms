# ExecPlan: Slice 029 OMS and fake broker simulation orchestration

## 1. Goal

Advance approved simulation orders through local OMS transitions and the simulation-only fake broker.

## 2. Non-goals

- No IBKR transport.
- No paper account orders.
- No live broker connectivity.
- No real account actions.
- No HTTP order-execution endpoint.
- No live trading.

## 3. Safety constraints

- Execution requires an existing local `PENDING_APPROVAL` OMS order.
- Execution applies a local approved approval-ticket decision before OMS `APPROVED`.
- Fake broker requests are built only from already risk-passed, pending-approval simulation context.
- Every approval decision, OMS transition, and fake broker transition must be journaled.
- Duplicate execution IDs must be idempotent only when payloads match.
- A terminal order state must block new execution attempts.
- No network client, broker SDK, IBKR transport, HTTP execution endpoint, or live-trading path is
  added.

## 4. Current state

The repo can orchestrate replay through a pending approval ticket and can apply simulation-only
approval decisions. Approved orders are not yet advanced through OMS and fake broker execution.

## 5. Proposed design

Extend `ReplayToApprovalOrchestrator` with `execute_approved_order()`. The method validates an
`ApprovedOrderExecutionRequest`, applies the local approval decision, advances OMS through
`APPROVED` and `SUBMITTED`, sends a local `BrokerOrderRequest` to the fake broker, and mirrors fake
broker acknowledgement, fill, cancel, or reject outcomes back into OMS.

## 6. Data model changes

New in-memory Python records only:

- `ApprovedOrderExecutionRequest`
- `ApprovedOrderExecutionResult`

No database schema or persistence layer is added.

## 7. API changes

None. No HTTP, CLI, config, broker, or frontend API is added in this slice.

## 8. Test plan

- Unit/integration-style test for approved order fill through OMS and fake broker.
- Test for fake broker reject path mirrored to OMS `REJECTED`.
- Test for fake broker cancel path with OMS `CANCEL_REQUESTED` before `CANCELLED`.
- Test for execution ID idempotency.
- Test that terminal order state blocks a second execution attempt.
- Source safety test proving no broker, network, order-submission, credential, or live-trading
  affordances are added.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\trading-oms-pytest-slice029" backend\tests\test_simulation_execution.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 029 commit to remove approved-order execution orchestration, tests, docs, and
slice status updates.

## 11. Implementation steps

1. Add focused simulation execution tests.
2. Extend the simulation orchestrator with approved-order execution.
3. Add execution documentation.
4. Update README and `docs/SLICES.md`.
5. Run focused and full verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Approved simulation orders advance through OMS `APPROVED` and `SUBMITTED`.
- Fake broker acknowledgement, fill, cancel, and reject paths are supported locally.
- OMS mirrors fake broker outcomes.
- Duplicate execution IDs are idempotent and terminal states block repeat execution.
- Verification passes.
- No IBKR transport, real broker connectivity, HTTP order-execution endpoint, credentials, or
  live-trading path is added.

## 13. Risks and assumptions

- Execution remains in-memory until later persistence work.
- Fake broker execution is local simulation only.
- Slice 030 will add simulated positions, protection monitoring, and alerts from fills.
