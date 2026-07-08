# ExecPlan: Slice 045 audit export bundle

## 1. Goal

Create a deterministic local audit export bundle that includes read-model, workflow, run, and
journal references while refusing to export secret-shaped or live-routing-shaped content.

## 2. Non-goals

- No uploads.
- No external delivery.
- No live trading.
- No IBKR transport.
- No broker connectivity.
- No production rollout.
- No secrets or credentials.

## 3. Safety constraints

- Export must be local review data only.
- Export must recursively scan payload keys and values before returning or writing a bundle.
- Secret-shaped content, live-enabled booleans, broker host/account fields, submit/transmit/route
  affordances, and arbitrary-code-shaped text must block export.
- The endpoint must be `GET` only.
- Export must not create, approve, reject, submit, route, transmit, cancel, reconcile, upload, or
  deliver anything externally.

## 4. Current state

The repo has backend read models, workflow definitions, workflow simulation runs, local journal
records, and a local persistence foundation. It does not yet have a reviewable audit export bundle.

## 5. Proposed design

Add a backend audit export module that builds a stable JSON bundle from existing domain/read-model
records. Add a read-only FastAPI endpoint for the current in-process snapshot. Add tests for
determinism, references, scan rejection, local file writing, and endpoint behavior.

## 6. Data model changes

No database changes. New JSON bundle shape only.

## 7. API changes

Add:

- `GET /api/audit-export-bundle`

## 8. Test plan

- Backend tests for deterministic stable JSON.
- Backend tests for workflow, run, and journal references.
- Backend tests for recursive safety-scan rejection.
- Backend tests for local JSON writing.
- Backend API test proving the endpoint returns a read-only bundle with references.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 045 commit to remove the audit export module, endpoint, tests, and docs.

## 11. Implementation steps

1. Add audit export tests.
2. Implement deterministic bundle builder and scanner.
3. Add read-only API endpoint.
4. Update docs and slice queue.
5. Run full verification.

## 12. Completion criteria

- Export bundle has stable JSON output.
- Export bundle includes workflow IDs, run IDs, and journal sequence references.
- Unsafe content blocks export.
- `GET /api/audit-export-bundle` returns a safe bundle.
- Verification passes.
- No external delivery, IBKR transport, broker connectivity, live trading, secrets, or production
  rollout are added.

## 13. Risks and assumptions

- The endpoint exports current in-process data for this slice.
- SQLite-backed export orchestration, bundle signing, compression, retention, and external review
  transport remain future work.
