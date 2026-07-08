# ExecPlan: Slice 036 graph-to-DSL compiler

## 1. Goal

Compile validated visual simulation workflow graphs to a typed simulation workflow DSL preview.

## 2. Non-goals

- No workflow persistence.
- No workflow execution.
- No backend mutation endpoint.
- No broker connectivity.
- No IBKR transport.
- No live trading.
- No arbitrary code or expression language.

## 3. Safety constraints

- Compilation must run validation first.
- Invalid graphs must not produce a DSL document.
- The DSL must be simulation mode only.
- The DSL must explicitly keep broker transport, live trading, and arbitrary code disabled.
- No broker host, account ID, credential, route, JavaScript, script, import, or eval fields are
  added.

## 4. Current state

Slice 035 validates the typed visual workflow graph and renders validation state in the UI.

## 5. Proposed design

Add a pure TypeScript compiler from validated node and edge catalogs to a JSON-compatible simulation
workflow DSL document. Render a local preview in the existing visual builder panel. Add a backend
parser/validator for the generated DSL shape.

## 6. Data model changes

Frontend TypeScript DSL types and backend parser dataclasses only.

## 7. API changes

None.

## 8. Test plan

- Tests compile the default graph to simulation-mode DSL.
- Tests prove invalid graphs do not compile.
- Backend tests prove the parser accepts the safe DSL and rejects unsafe shapes.
- Tests prove the formatted preview contains no credential, route, live, broker host, or
  arbitrary-code affordances.
- UI tests prove the workflow DSL preview renders.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 036 commit to remove the compiler and workflow DSL preview.

## 11. Implementation steps

1. Add DSL types and compiler.
2. Reuse graph validation before compilation.
3. Add backend parser/validator.
4. Render the workflow DSL preview.
5. Add tests and docs.
6. Run verification.

## 12. Completion criteria

- Default graph compiles to simulation workflow DSL.
- Invalid graph compilation is blocked.
- UI preview renders the generated DSL.
- Verification passes.

## 13. Risks and assumptions

- The frontend compiler and backend parser are still preview/persistence foundations; no workflow
  execution is added.
