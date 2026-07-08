# ExecPlan: Slice 037 workflow persistence

## 1. Goal

Save and load validated simulation workflow definitions through local backend persistence.

## 2. Non-goals

- No workflow execution.
- No simulation run creation.
- No broker connectivity.
- No IBKR transport.
- No live trading.
- No arbitrary code or expression language.
- No credential, broker host, account ID, route, submit, transmit, import, script, or eval fields.

## 3. Safety constraints

- Saved workflows must parse through the safe workflow DSL validator before persistence.
- Persistence is local-only and stores simulation workflow definitions, not broker configuration.
- Mutation endpoints may save or update definitions only; they must not run workflows.
- Saved payloads must keep broker transport, live trading, and arbitrary code disabled.
- Responses must not expose action URLs, broker fields, credentials, account IDs, or secrets.

## 4. Current state

Slice 036 adds a frontend compiler for the default visual graph and a backend parser/validator for
the generated simulation workflow DSL. No workflow persistence exists yet.

## 5. Proposed design

Add a backend workflow definition domain module with versioned records and a local JSON file store.
The store validates DSL documents, keeps create/update operations idempotent for identical payloads,
increments record versions on updates, and writes records atomically. Add FastAPI endpoints for list,
detail, create, and update. Add a frontend client surface and a disabled/preview UI status for saved
workflow persistence without run controls.

## 6. Data model changes

Add workflow definition records:

- `schema_version: 1`
- `workflow_id`
- `display_name`
- `description`
- `version`
- `created_at`
- `updated_at`
- `document`

## 7. API changes

Add simulation-only workflow definition endpoints:

- `GET /api/workflows`
- `POST /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `PUT /api/workflows/{workflow_id}`

## 8. Test plan

- Backend unit tests for create, list, detail, update, versioning, idempotency, invalid DSL rejection,
  unknown workflow handling, and secret/broker/live field rejection.
- Backend API tests for endpoint payloads, mutation boundaries, and forbidden response affordances.
- Frontend tests for workflow API client methods and visible persistence status without run, broker,
  credential, route, script, import, eval, or live-mode controls.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 037 commit to remove workflow persistence files, endpoints, tests, docs, and UI
status text.

## 11. Implementation steps

1. Add backend tests for workflow definition persistence and API endpoints.
2. Add workflow definition store and record validation.
3. Wire list/detail/create/update endpoints into the FastAPI app.
4. Add frontend API client types and safe persistence status UI.
5. Update docs and run verification.

## 12. Completion criteria

- Valid simulation workflow DSL documents can be saved, listed, loaded, and updated locally.
- Invalid or unsafe workflow documents are rejected before persistence.
- Workflow updates are versioned and idempotent for identical payloads.
- Endpoints do not run workflows and expose no broker/live/secret/action affordances.
- Verification passes.

## 13. Risks and assumptions

- The JSON file store is intentionally local and small; Slice 040 can replace or extend it with
  SQLite for broader persistence.
- Runtime app persistence uses a local temp-backed default service in tests and development unless a
  future config slice introduces an explicit data directory.
