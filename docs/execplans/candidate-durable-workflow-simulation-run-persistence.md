# ExecPlan: Durable saved-workflow simulation-run persistence

## 1. Goal

Persist accepted saved-workflow simulation-run requests and their complete validated evidence in the
existing local SQLite foundation so exact list, get, inspector, and idempotent retry behavior survives
backend reconstruction or process restart. Incomplete, corrupt, missing, or contradictory evidence
must fail closed and must never be presented as a successful simulation run.

## 2. Non-goals

- Approval or rejection controls, automatic approval, automatic retry, or downstream execution.
- Changes to replay fixtures, strategy behavior, risk policy, approval semantics, OMS, fake-broker,
  position, alert, or reconciliation behavior.
- Remote persistence, external services, cloud databases, multi-host coordination, or deployment.
- Arbitrary replay paths, URLs, file browsing, scripts, expressions, imports, or custom code.
- IBKR connectivity, broker transport, credentials, account fields, production rollout, or live
  trading.

## 3. Safety constraints

- Live trading remains disabled; no live-order, broker-transport, or credential path may be added.
- Default operation remains deterministic local simulation with the existing approved replay
  reference and replay-derived risk time domain.
- A saved workflow must still pass strict DSL validation and the expected workflow version check
  before a new run can be reserved or journaled.
- Existing authorization and emergency-stop checks remain mandatory before risk-increasing work.
- Risk must pass before an approval ticket is created, and every accepted path must stop at manual
  approval wait before any downstream execution.
- The JSONL event journal remains the append-only source of truth; SQLite evidence binds to and
  verifies journal records rather than replacing them.
- The exact accepted request, workflow attribution, run record, approval reference, node statuses,
  and journal references must be stored together under a stable run identity.
- A conflicting duplicate run ID, pending write, malformed persisted record, invalid manifest,
  missing journal record, or contradictory journal record must fail closed without rerunning.
- Database paths, SQL details, exception text, credentials, private values, and unsafe fields must
  not appear in API or UI error messages.
- No secret, broker, account, route, submit, transmit, deployment, or live-mode field may be added
  to persistence payloads, APIs, logs, docs, screenshots, or tests.

## 4. Current state

Authoritative `origin/main` is squash commit `6958c43a14f54251ae354e47e277fb21548d19e7`
from PR #48. Baseline verification passes with 610 backend and 122 frontend tests. Saved workflow
definitions use a local JSON file, but the application currently creates that file and the workflow
simulation JSONL journal in temporary directories and deletes them when rebuilding services.
`WorkflowSimulationRunner` keeps accepted payloads and results only in process-local dictionaries,
so restart loses list/get data and exact retry identity. `LocalSqlitePersistenceStore` has schema
version 1 and a basic `workflow_simulation_runs` table, but the running API does not use it and that
table does not model reservation state or journal integrity.

## 5. Proposed design

Extend the existing local SQLite store with a versioned workflow-run evidence table. A new run is
written in this order:

1. authorize, enforce emergency stop, load and validate the saved DSL, and compare the expected
   workflow version;
2. atomically reserve the canonical exact request and its SHA-256 identity as `pending` before any
   run-specific journal append;
3. run the existing deterministic replay-to-risk-to-approval orchestration and append node statuses
   to the existing JSONL journal;
4. build and validate the typed run record and a canonical manifest of every journal record appended
   for the run; and
5. atomically finalize the same SQLite row as `committed` with the typed record, manifest, and
   manifest digest.

The runner will receive persistence through a small protocol to avoid coupling core orchestration to
SQLite. On start, list, or get, committed rows are strictly reconstructed into typed records and their
manifests are compared byte-for-canonical-byte with the authoritative JSONL records. A pending row is
an explicit interrupted-write condition: it is retained, is not silently completed or deleted, and
blocks reads and retries for that identity. An exact retry of committed evidence returns the existing
record without revalidation against a later workflow revision, rerunning orchestration, or appending
journal records. A different request with the same run ID is a conflict.

The running application will use one stable local state directory for saved workflow JSON, workflow
simulation JSONL, and SQLite evidence. Test reset helpers will explicitly clear isolated test state,
while a reconstruction helper will drop only in-memory service objects so restart behavior can be
tested without deleting durable files. Runner-level locking plus SQLite immediate transactions will
serialize in-process duplicate attempts; database uniqueness prevents two runner instances from both
reserving the same run ID.

API endpoints and response shapes remain unchanged. Persistence and journal integrity failures map
to a generic service-unavailable response. Unknown runs remain not found, stale workflow versions
remain conflicts, and active emergency stop remains locked.

## 6. Data model changes

Add SQLite migration version 2 with a new `workflow_simulation_run_evidence` table:

- `run_id` primary key;
- `workflow_id` and `expected_workflow_version` attribution;
- canonical `request_json` and `request_sha256` idempotency identity;
- `evidence_state` constrained by application validation to `pending` or `committed`;
- `record_json`, `journal_manifest_json`, and `journal_manifest_sha256`, nullable only while pending;
- deterministic `created_at` and `updated_at`; and
- an index on `(workflow_id, updated_at, run_id)` for stable list ordering.

The existing schema-v1 tables remain intact for compatibility. Migration is additive and
idempotent. Persisted run and journal payloads retain schema version 1; SQLite migration version and
domain-record schema version are separate concerns.

## 7. API changes

No endpoint or successful response shape changes. Existing endpoints remain:

```text
POST /api/workflows/{workflow_id}/simulation-runs
GET  /api/workflows/{workflow_id}/simulation-runs
GET  /api/workflows/{workflow_id}/simulation-runs/{run_id}
```

Incomplete or invalid durable evidence returns HTTP 503 with a generic workflow-simulation-evidence
unavailable detail. Existing 400 validation, 401/403 authorization, 404 unknown run, 409 stale or
conflicting identity, and 423 emergency-stop behavior remains. No broker, account, secret, replay
path, approval action, deployment, or live-mode field is added.

## 8. Test plan

- Add failing-first SQLite tests for fresh schema-v2 initialization, idempotent initialization,
  migration from schema v1, exact reservation, conflicting reservation, and atomic finalization.
- Add failing-first runner tests for reconstruction list/get, exact retry after reconstruction with
  unchanged journal count, conflicting retry, deterministic ordering, and concurrent exact
  duplicates producing one journal trail.
- Add fail-closed tests for pending rows, malformed record JSON, malformed manifests, invalid
  digests, missing journal references, truncated/corrupt JSONL, and contradictory SQLite/JSONL
  evidence.
- Add API tests for service reconstruction, recovered list/get, generic 503 responses without paths
  or SQL details, and preserved authorization, emergency-stop, stale-version, replay allowlist,
  replay-time risk, and manual-approval-wait behavior.
- Preserve frontend run-inspector tests for loading, empty, success, conflict, and unavailable states
  without rendering exception details or private values.
- Exercise real localhost create/start/list, backend restart, recovered list/get, exact retry,
  conflicting retry, and corrupt-evidence failure.

## 9. Verification commands

```powershell
Push-Location backend
python -m pytest tests/test_local_persistence.py tests/test_workflow_simulation_runs.py tests/test_workflow_simulation_api.py
python -m pytest tests/test_resilience.py
ruff format --check .
ruff check .
mypy src
Pop-Location

Push-Location frontend
npm.cmd test -- --run workflowRunInspector.test.ts workflowSimulationRunStart.test.ts App.test.tsx
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
Pop-Location

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Start backend and Vite on localhost, exercise the restart matrix through the actual API proxy, and
inspect `http://localhost:5173` with browser tooling when available.

## 10. Rollback plan

Revert the bounded candidate commit or close the PR. Migration version 2 is additive, so rollback
does not alter or delete existing schema-v1 data. A previous binary will ignore the new table. Local
candidate state can be removed only after preserving any evidence needed for review; no automatic
destructive downgrade is performed.

## 11. Implementation steps

1. Add failing tests for migration, reservation/finalization, reconstruction, idempotency,
   concurrency, and fail-closed evidence integrity.
2. Add strict typed reconstruction for simulation run, node status, and workflow run records.
3. Implement SQLite migration v2 and exact pending/committed evidence operations.
4. Inject persistence into the runner, enforce safe write ordering, lock duplicate attempts, and
   validate canonical journal manifests on every recovered read.
5. Wire stable local state and non-destructive service reconstruction into the FastAPI application;
   map evidence failures to generic HTTP 503 responses.
6. Run focused checks, fix failures, and inspect persistence and API behavior for P0/P1 safety issues.
7. Update local-persistence, journal, simulation-run, roadmap, slice, and setup documentation.
8. Run full verification and the complete localhost restart/corruption matrix.
9. Start the finalized app on port 5173 and visually inspect it with available browser tooling.
10. Commit, push, create a PR against main, and confirm CI on the exact head commit without merging.

## 12. Completion criteria

- New and migrated local databases report schema version 2 and initialize idempotently.
- A run reservation exists before its first run-specific journal append and finalization is atomic.
- Restarted services return the same strictly validated list/get records in deterministic order.
- Exact retry after restart returns the same record with no duplicate journal entries.
- Conflicting retry and concurrent duplicate attempts fail safely or share the one committed result.
- Pending, partial, malformed, missing, corrupt, or contradictory evidence cannot appear successful.
- Existing auth, emergency stop, workflow version, replay allowlist, replay-time risk, journaling, and
  manual-approval wait controls remain enforced.
- The UI preserves generic loading, empty, success, conflict, and unavailable behavior without
  exposing private persistence details.
- Focused and full verification pass, and the localhost restart matrix is demonstrated.
- Local runtime remains simulation/paper only with live trading disabled and broker contact absent.
- The candidate branch is committed, pushed, represented by an open PR, and green in exact-head CI.

Implementation evidence on 2026-07-17: focused durability tests pass across migration, atomic
reservation/finalization, restart reconstruction, exact retry, conflict, deterministic ordering,
same-runner and cross-runner concurrency, pending/partial records, invalid digests, malformed JSON,
missing references, contradictory evidence, and generic API failures. Full repository verification
passes with 627 backend and 122 frontend tests plus formatting, lint, type checking, compilation,
and resilience checks; the production frontend build also passes. Through the real Vite proxy, a
saved workflow reached manual approval wait, survived an actual backend process restart, recovered
list/get, returned an exact retry without changing the 18-line journal, rejected a conflicting retry
with HTTP 400, and returned generic HTTP 503 for deliberately corrupt evidence before restoration.
Backend and frontend returned HTTP 200 on localhost. Browser runtime discovery and the required
troubleshooting pass found no available browser, so no visual screenshot claim is made. The bounded
branch is pushed and PR #49 is open against `main`; exact-head CI is required after every update and
the PR remains unmerged pending separate human approval.

## 13. Risks and assumptions

- SQLite and JSONL cannot share one atomic transaction. The explicit pending state preserves an
  interruption rather than fabricating completion; recovery of a pending row is intentionally a
  later, separately reviewed capability.
- The JSONL journal remains authoritative. The SQLite manifest is an integrity binding and lookup
  record, not an alternate event source.
- Runner and path-scoped journal locking cover one application process. Cross-host and shared-filesystem
  writers are out of scope because this remains a self-hosted local simulation slice.
- The stable local state directory is development/local state, not a production deployment or backup
  design.
- Browser automation may be unavailable; component tests and direct localhost checks are the fallback,
  and no visual-inspection claim will be made without browser evidence.
- The local authentication model is development-only and does not constitute production identity
  assurance.
