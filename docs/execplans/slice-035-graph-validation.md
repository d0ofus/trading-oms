# ExecPlan: Slice 035 graph validation

## 1. Goal

Validate visual simulation workflow graphs before later save or run slices can use them.

## 2. Non-goals

- No graph persistence.
- No graph-to-DSL compiler.
- No workflow execution.
- No backend mutation endpoint.
- No broker connectivity.
- No IBKR transport.
- No live trading.

## 3. Safety constraints

- Validation must reject missing risk, approval, and audit nodes.
- Validation must reject unsafe action nodes and unsupported node types.
- Validation must reject cycles and unknown edge endpoints.
- No save, run, submit, transmit, connect, credential, route, live-mode, script, import, JavaScript,
  or eval controls are added.
- The default workflow remains simulation-only and non-executing.

## 4. Current state

Slice 034 defines a typed visual node catalog and renders the canvas from that catalog. The graph is
frontend-local and non-executing.

## 5. Proposed design

Add a pure TypeScript validator for visual workflow graph inputs. Surface the default graph
validation result in the visual builder and add tests for required-node, unsafe-node,
unsupported-node, cycle, and unknown-edge failures.

## 6. Data model changes

Frontend TypeScript validation types only.

## 7. API changes

None.

## 8. Test plan

- Tests accept the default catalog graph.
- Tests reject missing risk, approval, and audit nodes.
- Tests reject unsafe and unsupported nodes.
- Tests reject cycles and unknown edge endpoints.
- UI tests prove the validation result is visible without action controls.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 035 commit to remove validation and return to the typed catalog renderer.

## 11. Implementation steps

1. Add validation types and validator.
2. Add tests for valid and invalid graph shapes.
3. Render default graph validation status.
4. Update docs and slice status.
5. Run verification.

## 12. Completion criteria

- Required-node validation exists.
- Unsafe/unsupported-node validation exists.
- Cycle validation exists.
- Default graph is valid.
- Verification passes.

## 13. Risks and assumptions

- Backend validation is deferred; this slice establishes the frontend validation model for later
  backend persistence and run endpoints.
