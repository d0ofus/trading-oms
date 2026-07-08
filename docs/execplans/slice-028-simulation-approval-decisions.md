# ExecPlan: Slice 028 simulation approval decisions

## 1. Goal

Add explicit approve/reject decisions for simulation-only approval tickets.

## 2. Non-goals

- No broker order transmission.
- No real account actions.
- No OMS advancement after approval.
- No fake broker execution.
- No IBKR transport.
- No live trading.

## 3. Safety constraints

- Approval decisions may advance simulation approval-ticket state only.
- Approval does not submit, transmit, route, cancel, or modify orders.
- Actor, reason, decision reference, decision ID, and timestamp must be captured.
- Decision IDs must be idempotent when payloads match and rejected when conflicting.
- Responses must not expose broker routes, account IDs, credentials, submit, or transmit fields.
- No network client, broker SDK, or live-trading path is added.

## 4. Current state

The repo can orchestrate deterministic simulation runs through pending approval tickets. Approval
ticket domain logic already supports approve/reject decisions locally, but the backend API exposes
only read endpoints.

## 5. Proposed design

Add a narrow simulation approval service seeded with the demo pending ticket and backed by a local
temporary JSONL journal. Add two FastAPI endpoints:

- `POST /api/approval-tickets/{ticket_id}/approve`
- `POST /api/approval-tickets/{ticket_id}/reject`

Each endpoint accepts decision metadata, applies the local approval-ticket decision, and returns the
journaled approval decision record.

## 6. Data model changes

New in-memory Python record:

- `SimulationApprovalDecisionInput`

No database schema or persistence layer is added.

## 7. API changes

New simulation-only mutation endpoints:

- `POST /api/approval-tickets/{ticket_id}/approve`
- `POST /api/approval-tickets/{ticket_id}/reject`

No order, broker, cancel, connect, transmit, or live-trading endpoints are added.

## 8. Test plan

- API tests for approve and reject.
- API test for idempotent repeated decision payloads.
- API test rejecting a second different decision after a ticket is no longer pending.
- API test rejecting unknown ticket IDs.
- Response safety test proving no broker, network, submission, credential, or live-trading
  affordances are returned.
- Existing read endpoint tests updated to allow only the two approved simulation mutation routes.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\trading-oms-pytest-slice028" backend\tests\test_simulation_approval_api.py backend\tests\test_read_api.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 028 commit to remove the simulation approval service, API routes, tests, docs, and
slice status updates.

## 11. Implementation steps

1. Add focused simulation approval API tests.
2. Add the simulation approval service.
3. Wire approve/reject FastAPI routes.
4. Update docs and slice queue.
5. Run focused and full verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Simulation-only approve and reject endpoints exist.
- Actor and reason metadata are captured.
- Decision idempotency is preserved.
- Approval decisions do not advance OMS or fake broker state.
- Verification passes.
- No broker transport, order transmission, real account action, credentials, or live-trading path
  is added.

## 13. Risks and assumptions

- The service is intentionally in-memory and demo-seeded until persistence and real run APIs are
  added.
- Slice 029 will explicitly orchestrate approved simulation orders through OMS and fake broker.
