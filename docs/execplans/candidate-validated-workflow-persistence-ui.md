# ExecPlan: validated visual workflow persistence UI

## 1. Goal

Connect the interactive simulation workflow editor to the existing local workflow-definition APIs
so an operator can deliberately list, load, create, and update backend-validated workflows while
seeing clear draft, dirty, saving, success, conflict, validation, empty, and unavailable states.

## 2. Non-goals

- No workflow execution or simulation-run start control.
- No delete, autosave, arbitrary JSON editing, custom node type, expression, script, import, eval,
  or code execution.
- No approval, risk, OMS, fake-broker, position, alert, journal, emergency-stop, or simulation-run
  behavior change.
- No Candidate 063 implementation, IBKR dependency, broker connection, socket, paper session,
  credential, account identifier, contract lookup, market-data request, or order transport.
- No deployment, rollout, production operation, or live trading.

## 3. Safety constraints

- Frontend compilation must succeed before any create or update request is sent.
- Backend workflow parsing remains authoritative and must complete before a record is written.
- Backend and frontend validation must reject duplicate node IDs/types, unsupported nodes, unknown
  endpoints, cycles, missing risk/manual-approval/audit nodes, incomplete ordered safety paths,
  forbidden metadata, secret-shaped content, broker-routing fields, and unsafe modes.
- Updates must carry the selected record's expected version and fail with HTTP 409 if that version
  is stale; an exact successful retry may remain idempotent.
- Failed saves and conflicts must preserve all local metadata and graph edits.
- Loading or starting a new draft while dirty requires an explicit discard confirmation.
- Responses are untrusted until their structure, metadata, version, timestamps, workflow document,
  and safety posture are validated locally.
- The persisted document remains `simulation`, `preview_only`, and `fake_broker_only`, with broker
  transport, live trading, and arbitrary code disabled.
- No save path may call the existing simulation-run endpoint.
- No secret, account, broker host/port, submit, transmit, route, paper-session, or live-mode field or
  control may appear.

## 4. Current state

PR #46 was squash-merged as authoritative `origin/main` commit
`9ef557ae98933b9885c5df226a6ffc9052a67aca`, tree
`ebdd50395c1533a8732f076577672463610cae2c`. That tree exactly matches the reviewed interactive
editor commit. The clean branch `candidate-slice-validated-workflow-persistence-ui` starts at that
commit.

The baseline passes full verification with 587 backend and 72 frontend tests. One initial Windows
temp-file replacement was denied transiently; the exact failed test and a complete rerun passed
without repository edits.

The editor currently owns a page-local typed graph and continuously compiles it to preview DSL.
The frontend API client already exposes workflow list/detail/create/update methods, and the backend
already validates and stores local workflow definitions. The UI does not call those persistence
methods. Updates have no expected-version precondition, and the backend parser does not yet reject
duplicate node identities/types or require the complete ordered safety path.

## 5. Proposed design

Add a pure frontend persistence module that validates untrusted workflow records, maps a valid saved
DSL document back into typed editor state using catalog layout, creates deterministic sorted list
state, validates safe metadata, builds exact create/update requests, fingerprints saved and current
drafts, detects dirty state, classifies safe errors, and orchestrates list/create/update calls for
focused tests.

Keep `App` as the UI state owner. On mount it explicitly loads the workflow list. A compact
persistence panel provides metadata fields, saved-workflow selection, deliberate load/new/create/
update commands, a dirty-discard checkbox, and status feedback. Loading and new-draft commands are
blocked while dirty unless the discard checkbox is checked. Create/update commands are disabled
while saving or invalid; update additionally requires a loaded dirty record. Successful responses
become the new clean baseline. Failures leave the draft untouched.

Harden the existing backend parser to the editor's graph invariants. Extend the existing PUT
request with `expected_version`; require it for changed updates, return 409 for stale versions, and
preserve exact-request retry idempotency. No endpoint is added.

## 6. Data model changes

Backend:

- add optional `expected_version` to the shared workflow-definition request model;
- reject `expected_version` on create;
- require a positive matching `expected_version` for changed updates;
- retain record `version` as the authoritative concurrency token.

Frontend:

- add a typed update request carrying `expected_version`;
- add validated workflow-list, metadata-draft, selected-record, operation-status, dirty-baseline,
  and discard-confirmation state;
- reconstruct editor nodes from the safe catalog and persisted IDs/types, with catalog positions;
- reconstruct only typed `workflow` edges from saved DSL edges.

No trading, order, broker, approval, journal, position, alert, or configuration model changes.

## 7. API changes

No new endpoint.

Existing interfaces remain:

- `GET /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `POST /api/workflows`
- `PUT /api/workflows/{workflow_id}`

The PUT body adds required optimistic-concurrency field `expected_version`. A stale version returns
HTTP 409. POST rejects an `expected_version`. No delete or run endpoint is added or called.

## 8. Test plan

- Backend failing-first tests for duplicate node ID/type rejection, incomplete safety-path
  rejection, create/update validation before writes, required/matching expected versions, stale
  conflict without mutation, exact retry idempotency, unsafe metadata/documents, and HTTP 409.
- Frontend failing-first tests for deterministic sorted loading, strict response validation, safe
  DSL-to-editor mapping, exact create/update payloads, expected version, metadata/document safety,
  invalid graphs causing zero requests, backend rejection causing zero persisted success state,
  version-conflict classification, dirty detection, discard protection, and failed-save draft
  preservation.
- Rendering tests for loading, empty, ready, dirty, saving, success, validation-error, conflict,
  and unavailable states; deliberate controls; responsive-safe dimensions; and absence of run,
  broker, order, credential, account, script, import, eval, paper-session, and live controls.
- Existing workflow API, editor, compiler, run-inspector, and repository safety tests remain green.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider backend/tests/test_workflow_dsl.py backend/tests/test_workflow_definitions.py backend/tests/test_workflow_api.py
npm.cmd run test --prefix frontend -- workflowApiClient.test.ts workflowPersistence.test.ts App.test.tsx
npm.cmd run lint --prefix frontend
npm.cmd run typecheck --prefix frontend
npm.cmd run build --prefix frontend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Start the backend and frontend on localhost, exercise list/load/create/update and invalid-graph
blocking through `http://localhost:5173` where browser tooling is available, and report any browser
limitation honestly.

## 10. Rollback plan

Revert the single candidate commit. This removes the persistence controls, frontend state helpers,
expected-version precondition, parser hardening, tests, and docs while returning to the merged local
interactive editor and existing workflow API behavior. No stored production or broker state exists
in this slice.

## 11. Implementation steps

1. Add failing backend tests for authoritative graph validation and optimistic concurrency.
2. Add failing frontend tests for record validation, mapping, requests, dirty/discard behavior,
   async operations, and rendered states.
3. Harden the backend DSL parser and workflow store/API update precondition.
4. Add the pure frontend workflow-persistence module and typed client update request/error surface.
5. Integrate deliberate list/load/new/create/update controls and status states into `App`.
6. Add restrained responsive styles without adding run or broker affordances.
7. Run focused checks and full verification; exercise the localhost workflow where tooling permits.
8. Self-review for every requested safety and correctness risk, fix all P0/P1 findings, update docs,
   commit, push, create the PR, inspect CI, and audit the full objective.

## 12. Completion criteria

- Operators can list and deliberately load valid saved simulation workflows.
- Operators can create a valid new definition and update a loaded definition through existing APIs.
- Every write is blocked by frontend invalidity and remains subject to authoritative backend
  validation before persistence.
- Stale updates return a visible version conflict and do not mutate storage or local edits.
- Dirty state is accurate; failed saves preserve edits; load/new cannot overwrite dirty work without
  explicit discard confirmation; no autosave occurs.
- All requested loading, empty, saving, success, validation-error, conflict, and unavailable states
  are visible and tested.
- Exact typed payloads contain only safe metadata, DSL, timestamps, and update expected version.
- No execution, run-start, delete, broker, account, credential, transport, deployment, rollout,
  production, or live-trading capability is added.
- Focused checks, full verification, runtime inspection where available, self-review, commit/push,
  PR creation, CI inspection, and requirement-by-requirement completion audit succeed.

Implementation evidence is recorded progressively in `docs/SLICES.md`. The bounded localhost API
exercise has confirmed create version 1, list/detail load, update version 2, stale update HTTP 409,
invalid graph HTTP 400, `live_trading_enabled: false`, and `broker_transport_allowed: false`.
Browser discovery and the required troubleshooting pass found no available browser instance, so
no visual browser claim is made; component rendering and responsive layout tests remain the visual
fallback evidence. Final full verification passes with 598 backend and 86 frontend tests, plus
formatting, lint, type, repository safety, production-build, and resilience checks.

## 13. Risks and assumptions

- Existing saved records do not retain canvas coordinates; loading uses deterministic catalog
  positions while preserving persisted node IDs/types and edges.
- PUT callers must adopt `expected_version`; this intentional contract hardening prevents silent
  lost updates.
- Exact retries after a successful update are idempotent even though their expected version is now
  stale; any changed stale request fails.
- Backend parser hardening may reject previously accepted but editor-invalid records. Fail-closed
  rejection is intentional.
- Browser tooling may remain unavailable; HTTP/runtime checks and component tests are required but
  will not be misreported as visual inspection.
