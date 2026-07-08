# ExecPlan: Slice 032 React Flow visual canvas scaffold

## 1. Goal

Add the first React Flow canvas scaffold for the Gate C visual simulation workflow builder.

## 2. Non-goals

- No graph editing.
- No workflow persistence.
- No workflow execution.
- No backend mutation.
- No broker connectivity.
- No IBKR transport.
- No live trading.
- No credentials, account IDs, host fields, routes, scripts, imports, or arbitrary code fields.

## 3. Safety constraints

- The canvas is static and frontend-only.
- The graph describes simulation-only workflow stages.
- Risk check, manual approval, fake broker, and audit sink remain visible in the scaffold.
- The UI must not render submit, transmit, connect, save, run, import, export, credential,
  live-mode, account, broker-host, JavaScript, script, or eval controls.
- No live trading, broker transport, secrets, or production rollout are introduced.

## 4. Current state

The existing Slice 015 visual builder is a static local Strategy DSL surface with no React Flow
dependency. Gate B has added deterministic simulation orchestration and a read-only simulation run
detail UI.

## 5. Proposed design

Add `@xyflow/react`, create an isolated `VisualSimulationWorkflowCanvas` component, and render a
static React Flow graph inside the existing visual builder section. The graph is locked:
non-draggable, non-connectable, non-selectable, and without Controls, buttons, save actions, or run
actions.

## 6. Data model changes

None.

## 7. API changes

None.

## 8. Test plan

- Frontend tests prove the React Flow scaffold renders expected simulation nodes.
- Frontend tests prove the scaffold contains no execution, broker, credential, live-mode, route, or
  arbitrary-code affordances.
- Existing safety tests continue proving no live-action controls render.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 032 commit to remove the dependency, component, tests, and docs.

## 11. Implementation steps

1. Add the React Flow dependency.
2. Add a static React Flow scaffold component.
3. Wire the component into the visual builder section.
4. Add focused frontend tests.
5. Update docs and slice status.
6. Run verification.

## 12. Completion criteria

- React Flow dependency is installed.
- Static simulation workflow canvas renders.
- No graph editing, save, run, broker, credential, live-mode, route, script, import, or eval control
  exists.
- Verification passes.

## 13. Risks and assumptions

- NPM reported audit findings after installing the dependency; no forced audit fix is applied in
  this slice because that would broaden dependency changes beyond the scaffold.
- Browser visual verification is deferred until Gate C has a usable builder milestone unless needed
  earlier for layout defects.
