# ExecPlan: Slice 038 run saved simulation workflows

## 1. Goal

Run a saved visual workflow definition against deterministic local replay in simulation mode only.

## 2. Non-goals

- No automatic approval.
- No fake broker execution from the workflow run endpoint.
- No position update or alert dispatch from the workflow run endpoint.
- No IBKR transport.
- No real broker connectivity.
- No live trading.
- No arbitrary code, scripts, imports, eval, credentials, account IDs, route, submit, or transmit
  fields.

## 3. Safety constraints

- A workflow must be saved and validated before it can be run.
- Runs must use the existing deterministic replay, strategy, risk, OMS, approval-ticket, and audit
  path.
- The run endpoint must stop at manual approval wait.
- Fake broker, position, and alert nodes must be marked blocked/waiting rather than executed.
- Every node status must be journaled.
- Unknown workflow IDs, unsafe workflow documents, stale market data, duplicate risk IDs, and
  unknown broker state must block risk-increasing progression.

## 4. Current state

Slice 037 persists validated simulation workflow definitions. Existing simulation orchestration can
turn deterministic replay into an order intent, risk decision, OMS pending-approval state, and manual
approval ticket without broker execution.

## 5. Proposed design

Add a workflow simulation runner service that loads a saved workflow definition, re-validates its DSL
document, executes the existing replay-to-approval orchestration with deterministic local fixtures,
and appends node status records to the event journal. Add a `POST
/api/workflows/{workflow_id}/simulation-runs` endpoint that returns the simulation run record and
node statuses.

## 6. Data model changes

Add workflow simulation run records:

- `schema_version: 1`
- `workflow_id`
- `run_id`
- `status`
- `created_at`
- `updated_at`
- `simulation_run`
- `node_statuses`
- `journal_references`

## 7. API changes

Add simulation-only endpoint:

- `POST /api/workflows/{workflow_id}/simulation-runs`

## 8. Test plan

- Backend service tests for successful deterministic run to approval wait, journaled node statuses,
  idempotency, unknown workflow rejection, invalid saved workflow rejection, and no fake broker
  execution.
- Backend API tests for endpoint payloads and forbidden broker/live/secret/action affordances.
- Frontend client tests for the simulation-run endpoint and absence of broker/run-to-live fields.
- UI tests for visible simulation-only run availability without execution/broker controls.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 038 commit to remove the runner service, endpoint, tests, docs, and frontend client
surface.

## 11. Implementation steps

1. Add backend tests for workflow simulation run behavior and API boundaries.
2. Implement the workflow simulation runner with deterministic local fixtures.
3. Wire the FastAPI endpoint and reset helper.
4. Add frontend client support and safe UI status.
5. Update docs and run verification.

## 12. Completion criteria

- A saved workflow can start a deterministic local simulation run.
- The run validates the saved DSL and reaches manual approval wait only.
- Node status records are journaled for replay, bar, strategy, risk, approval, blocked downstream
  execution nodes, and audit.
- No fake broker execution, broker transport, live trading, secrets, or production rollout are
  added.
- Verification passes.

## 13. Risks and assumptions

- The first workflow-run endpoint intentionally uses a deterministic built-in fixture. Later slices
  can add controlled replay-file selection while preserving local-only validation.
