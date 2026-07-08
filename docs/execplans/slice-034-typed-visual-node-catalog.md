# ExecPlan: Slice 034 typed visual node catalog

## 1. Goal

Create the typed visual node catalog for the safe simulation workflow builder.

## 2. Non-goals

- No arbitrary custom nodes.
- No node palette UI.
- No graph validation.
- No DSL compilation.
- No workflow save, load, or run behavior.
- No broker connectivity.
- No IBKR transport.
- No live trading.

## 3. Safety constraints

- Catalog nodes are static and typed.
- Every catalog node has `supportsExecution: false`.
- Risk-increasing simulation paths keep risk, manual approval, fake broker, alert, and audit nodes
  visible.
- No broker host, account ID, credential, route, live-mode, JavaScript, script, import, or eval
  fields are added.

## 4. Current state

Slices 032 and 033 add a React Flow canvas with local node layout editing. The node data is still
defined in the component.

## 5. Proposed design

Move visual workflow node definitions into a standalone typed catalog module. Include the required
simulation workflow nodes: replay source, bar builder, strategy trigger, risk check, approval
ticket, fake broker, position update, alert, and audit sink. Render the existing canvas from that
catalog.

## 6. Data model changes

Frontend TypeScript catalog types only.

## 7. API changes

None.

## 8. Test plan

- Frontend tests prove expected node types and edges.
- Frontend tests prove all catalog nodes remain non-executing.
- Frontend tests prove the catalog has no broker, credential, live-mode, route, or arbitrary-code
  affordances.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 034 commit to restore the previous component-local node definitions.

## 11. Implementation steps

1. Add typed node and edge catalog definitions.
2. Render the canvas from the catalog.
3. Add position update and alert nodes.
4. Update tests and docs.
5. Run verification.

## 12. Completion criteria

- Typed node catalog exists.
- Required simulation workflow nodes exist.
- Catalog entries are non-executing.
- Verification passes.

## 13. Risks and assumptions

- Validation and graph-to-DSL compilation are intentionally deferred to later Gate C slices.
