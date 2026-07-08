# ExecPlan: Slice 033 editable graph layout

## 1. Goal

Allow local React Flow node layout edits for the simulation workflow canvas without changing
execution behavior.

## 2. Non-goals

- No workflow persistence.
- No workflow execution.
- No save or load API.
- No arbitrary nodes.
- No edge creation or connection editing.
- No broker connectivity.
- No IBKR transport.
- No live trading.

## 3. Safety constraints

- Node movement changes frontend-local canvas positions only.
- Nodes remain the fixed simulation scaffold from Slice 032.
- Connections remain non-editable and non-connectable.
- No save, run, submit, transmit, connect, credential, route, live-mode, JavaScript, script, import,
  or eval controls are added.
- No backend mutation or external network behavior is introduced.

## 4. Current state

Slice 032 adds a static React Flow scaffold with replay source, bar builder, strategy trigger, risk
check, manual approval, fake broker, and audit sink nodes.

## 5. Proposed design

Use React Flow local node state to allow node dragging. Keep the graph frontend-local, keep edge
definitions fixed, and expose a small layout policy constant so tests can assert that execution and
persistence remain disabled.

## 6. Data model changes

None.

## 7. API changes

None.

## 8. Test plan

- Frontend tests prove the layout policy allows draggable nodes.
- Frontend tests prove connections, persistence, and execution remain disabled.
- Existing UI safety tests continue proving no live-action controls render.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 033 commit to return the canvas to the Slice 032 static scaffold.

## 11. Implementation steps

1. Add React Flow local node state.
2. Enable node dragging only.
3. Keep edge connections disabled.
4. Add tests for the layout policy.
5. Update docs and slice status.
6. Run verification.

## 12. Completion criteria

- Nodes can be moved locally on the canvas.
- Edge connection editing remains disabled.
- Persistence and execution remain disabled.
- Verification passes.

## 13. Risks and assumptions

- Layout changes are not durable until a later persistence slice.
- React Flow's built-in accessibility descriptions mention deletion/selection behavior, but no
  application delete, save, or run control is added in this slice.
