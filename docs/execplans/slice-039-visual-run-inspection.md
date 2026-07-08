# ExecPlan: Slice 039 visual run inspection

## 1. Goal

Show saved workflow simulation run status, node outcomes, and journal references on the visual graph.

## 2. Non-goals

- No automatic approval.
- No broker transport.
- No IBKR integration.
- No live trading.
- No real alert delivery.
- No order submission.
- No secrets or credential fields.

## 3. Safety constraints

- Inspection must be read-only.
- Inspection endpoints must return only simulation run records already created by the simulation-only
  runner.
- The visual canvas may show blocked fake broker, position, and alert nodes but must not execute
  them.
- Journal references must be visible so operators can trace status evidence.
- No UI buttons, forms, broker controls, credential inputs, route fields, script/import/eval fields,
  or live-mode controls may be added.

## 4. Current state

Slice 038 can start a saved workflow run against deterministic replay and journal per-node statuses.
The frontend shows only status pills for run availability, not per-node inspection.

## 5. Proposed design

Add read-only workflow simulation run listing/detail methods to the backend runner and FastAPI app.
Add frontend client methods for those read endpoints. Extend the React Flow canvas with a default
simulation run inspection overlay that shows status and journal references for each node, including
approval wait and blocked downstream nodes.

## 6. Data model changes

No new persisted model. Reuse `WorkflowSimulationRunRecord` and `WorkflowNodeRunStatus`.

## 7. API changes

Add read-only endpoints:

- `GET /api/workflows/{workflow_id}/simulation-runs`
- `GET /api/workflows/{workflow_id}/simulation-runs/{run_id}`

## 8. Test plan

- Backend tests for list/detail run inspection and unknown run handling.
- API tests for read-only run inspection and forbidden affordance absence.
- Frontend client tests for list/detail methods.
- Visual canvas tests for node statuses, journal references, approval waits, blocked downstream
  nodes, and support for risk-block/fill/alert status vocabulary.
- App tests proving no live-action controls render.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 039 commit to remove inspection endpoints, frontend inspection overlay, tests, and
docs.

## 11. Implementation steps

1. Add backend tests and read-only runner accessors.
2. Wire read-only FastAPI endpoints.
3. Add frontend client methods and visual inspection data/types.
4. Render node status and journal references on the canvas.
5. Update docs and run verification.

## 12. Completion criteria

- Saved workflow run records can be inspected via read-only backend endpoints.
- The visual canvas shows node status and journal references.
- Approval waits and blocked downstream nodes are visible.
- The status model can represent risk blocks, fills, and alerts for future completed simulation
  paths without enabling execution.
- Verification passes.

## 13. Risks and assumptions

- The first visual inspection uses the deterministic Slice 038 approval-wait run shape. Future
  approval/fill UI slices can feed completed fake-broker/position/alert outcomes into the same
  status model.
