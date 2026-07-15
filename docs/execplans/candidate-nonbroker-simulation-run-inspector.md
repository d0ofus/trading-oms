# ExecPlan: non-broker simulation run inspector

## 1. Goal

Replace the frontend's static representative simulation-run panel with a read-only inspector backed
by the existing saved-workflow and workflow-simulation-run APIs.

## 2. Non-goals

- No workflow save, update, validate, or run-start controls.
- No approval decision changes.
- No fake-broker execution changes.
- No IBKR dependency, connector, socket, session, callback, contract lookup, or broker contact.
- No credentials, account identifiers, private values, deployment, rollout, or live trading.
- No Candidate 063 implementation.

## 3. Safety constraints

- The inspector may call only existing `GET` workflow and simulation-run endpoints.
- An empty or failed API response must not fall back to a representative completed execution.
- Run status, node status, replay reference, approval ticket, and journal references must remain
  visibly simulation-only and read-only.
- The UI must not add submit, transmit, connect, authenticate, credential, account, or live-mode
  fields or actions.
- Candidate 063 IBKR connector work remains deferred.

## 4. Current state

The backend already exposes read-only workflow-run list and detail endpoints with typed node-status
and journal-reference records. The frontend client already supports those endpoints, but `App.tsx`
does not use it. Instead, the simulation-run section always renders a hard-coded `sim-run-001` that
claims approval, fake-broker fill, position, and protection-alert outcomes. Saved visual workflow
runs actually stop at manual approval, so that panel is not an inspection of current application
state and can mislead an operator.

The merged `main` baseline passes full verification with 587 backend tests and 60 frontend tests.

## 5. Proposed design

Add a small frontend run-inspection state module that:

- loads saved workflow definitions through `GET /api/workflows`;
- loads each workflow's run history through `GET /api/workflows/{workflow_id}/simulation-runs`;
- produces deterministic newest-first run rows;
- reports explicit loading, loaded, empty, and failed states without fabricated fallback data.

Update the operations shell to load that state independently from the existing operations snapshot.
The simulation-run section will provide a compact run selector/history table and render the selected
record's metadata, node-status timeline, approval wait, replay input reference, and journal
references. Selection is local display state only.

## 6. Data model changes

Frontend-only view state is added for:

- workflow identity and display name;
- the existing `WorkflowSimulationRunApiView` record;
- `loading`, `loaded`, and `error` load states;
- a stable workflow/run selection key.

No backend, persistence, journal, order, position, risk, approval, or broker data model changes are
made.

## 7. API changes

None. The slice consumes only these existing read endpoints:

- `GET /api/workflows`
- `GET /api/workflows/{workflow_id}/simulation-runs`

No mutation endpoint or transport interface is added or changed.

## 8. Test plan

- Add unit tests for deterministic multi-workflow loading and newest-first ordering.
- Add unit tests for explicit empty history and fail-closed API errors.
- Update frontend rendering tests to use API-shaped workflow-run records.
- Prove the selected run renders workflow, replay, approval-wait, node-status, and journal evidence.
- Prove the static completed fake-broker and protection-alert record is absent.
- Prove loading, error, and no-run states expose no fabricated run.
- Preserve existing safety tests for absent broker, credential, transmit, and live affordances.

## 9. Verification commands

```powershell
npm run test --prefix frontend
npm run lint --prefix frontend
npm run typecheck --prefix frontend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Run the local frontend at `http://localhost:5173` and inspect the simulation-run section at desktop
and mobile widths where browser tooling is available.

## 10. Rollback plan

Revert this slice's commit. The existing backend APIs and all simulation, approval, OMS, journal,
and safety behavior remain unchanged.

## 11. Implementation steps

1. Add failing frontend tests for run-inspection loading, sorting, empty/error handling, and render
   behavior.
2. Implement the frontend run-inspection loader and typed state.
3. Replace the static simulation-run records with API-backed history and selected-run detail.
4. Add restrained responsive styling for the selector, history table, metadata, and timeline.
5. Update slice documentation and the product gap record.
6. Run focused tests, full verification, and local UI inspection.
7. Self-review for trading safety, secret leakage, misleading evidence, and scope creep.

## 12. Completion criteria

- The UI shows only workflow simulation runs returned by the backend.
- Multiple runs are ordered deterministically and can be selected for read-only inspection.
- Empty, loading, and failed reads never show a fabricated successful run.
- The selected run exposes its actual node statuses and journal references.
- Candidate 063 remains deferred and no broker, transport, order, approval, deployment, rollout, or
  live behavior changes.
- Focused and full verification pass.

## 13. Risks and assumptions

- Workflow-run records are currently process-local in the runner; this slice accurately displays
  that current source and does not claim restart durability.
- Loading one run list per saved workflow is acceptable for the current local operator scale.
- The existing backend validators and fixed node-status vocabulary are the source of displayed run
  evidence; the frontend does not infer execution outcomes.
- A later separately approved slice can add durable run persistence or richer comparison without
  broadening this slice.
