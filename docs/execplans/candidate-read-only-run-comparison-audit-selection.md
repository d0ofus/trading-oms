# ExecPlan: Read-only simulation run comparison and audit selection

## 1. Goal

Let an operator select two committed saved-workflow simulation runs, inspect a deterministic
evidence comparison, and prepare the existing local audit review bundle for one exact run and
journal scope. The workflow must preserve exact workflow/version/run, lifecycle, manifest,
journal, digest, and provenance attribution without inventing, repairing, retrying, or mutating
simulation evidence.

## 2. Non-goals

- No simulation start, approval, rejection, execution, retry, repair, deletion, or journal rewrite.
- No database schema or persistence mutation.
- No automatic comparison-triggered action.
- No arbitrary journal query, filesystem path, URL, script, expression, or code input.
- No Candidate 063 implementation or approval-gate relaxation.
- No IBKR dependency, broker connection, transport, account, credential, host, or port field.
- No external alert delivery, upload, deployment, production rollout, or live trading.

## 3. Safety constraints

- Every compared or exported run must come from
  `WorkflowSimulationRunner.list_projection_sources()`, which reconstructs committed SQLite
  evidence and verifies the SHA-256-bound manifest against the append-only JSONL journal.
- Comparison must reuse the lifecycle projector's typed signal, order-intent, risk, approval,
  execution, position, protection, alert, and journal validation rather than parse untrusted
  records independently.
- Two explicit selector slots are always present. Selecting the same exact run in both slots is
  allowed only to produce the deliberate identical-run state.
- Any missing, pending, malformed, corrupt, mixed-source, duplicate, contradictory, cross-run, or
  stale evidence must fail closed with a generic response and no partial comparison or export.
- Durable mode must never fall back to representative records.
- Audit selection must be bound to the exact workflow ID, workflow version, run ID, run status,
  complete manifest references, complete manifest SHA-256, selected journal references, selected
  record SHA-256 values, and fixed local-simulation provenance.
- Audit scope is either the complete committed run manifest or one exact event selected from that
  manifest. No sequence outside the committed source manifest is accepted.
- Backend behavior remains GET-only. The existing local JSON bundle response is the only export
  operation; there is no upload, delivery, server-side file write, or external sink.
- Upstream provenance remains `simulated`, `local_only`, and `externally_unverified`. Actual local
  execution evidence may additionally be `fake_broker_derived`; `broker_derived` and
  `externally_verified` remain false.
- Live trading remains disabled. Existing risk, manual approval, OMS, emergency-stop, audit,
  provenance, and readiness controls remain authoritative and unchanged.
- No secrets or private values may enter source, logs, docs, tests, screenshots, API responses, or
  bundle payloads.

## 4. Current state

- PR #53 is squash-merged as `e4a30a6de5f65b677833eda626becf355fd1ed56`.
- The untouched merged baseline passes 676 backend tests, 158 frontend tests, and the four-test
  resilience rerun.
- `WorkflowSimulationRunner.list_projection_sources()` exposes only fully reconstructed committed
  runs with their complete verified journal manifests.
- `project_simulation_executions()` projects all supported lifecycle states atomically and already
  rejects duplicate identities, journal sequences, source mismatches, incomplete evidence, and
  contradictory execution lineage.
- The frontend inspector lists actual saved runs and renders exact run and node-status evidence,
  but it can inspect only one run at a time and has no comparison workflow.
- `GET /api/audit-export-bundle` currently builds one global in-process review bundle. It does not
  support exact durable-run or journal-scope selection and uses the representative operations
  assembler.

## 5. Proposed design

Add `trading_oms_backend.simulation_run_comparison` with frozen typed records for selectors,
validated run evidence snapshots, comparison sections, deterministic summaries, and audit
selection metadata.

Expose the lifecycle projector's validated evidence boundary as a public typed helper. A comparison
snapshot will preserve:

- workflow ID and expected workflow version;
- run ID, lifecycle status, timestamps, and replay reference;
- full typed signal and order-intent evidence;
- full risk decision, approval ticket, and optional approval decision;
- optional execution, OMS/fake-broker, position, protection, and local-alert evidence;
- complete manifest references, event types, sequences, per-record SHA-256 values, and complete
  manifest SHA-256;
- fixed local-simulation provenance.

Comparison uses eleven stable sections: workflow, run, signal, order intent, risk decision,
approval ticket, approval decision, execution, protection, alerts, and journal provenance. Each
section is classified as `added`, `removed`, `changed`, or `unchanged` from left to right and
contains deterministic field-level differences. JSON objects are traversed by sorted key and
lists by stable index. A deterministic comparison SHA-256 binds both ordered selectors and both
manifest digests.

The frontend adds a compact unframed comparison workspace beside the saved-run inspector:

- two run selectors populated only from validated saved-run history;
- an explicit Compare command with loading, empty, unavailable, partial-unavailable, identical,
  and differing states;
- summary counts plus section and field differences;
- exact run, lifecycle, digest, journal, and provenance facts;
- an audit target selector for left or right;
- scope controls for complete manifest or one exact manifest event;
- an explicit local Prepare bundle command and validated JSON download after success.

Changing either selected run, target, or scope invalidates the prior comparison/export result.
No comparison or export is automatic.

## 6. Data model changes

No database migration.

Add frozen in-memory/API records:

- `SimulationRunSelector`
- `SimulationRunEvidenceSnapshot`
- `SimulationRunComparisonField`
- `SimulationRunComparisonSection`
- `SimulationRunComparison`
- `AuditExportSelection`

The selected audit bundle keeps the existing top-level bundle shape and adds a strict `selection`
manifest containing selector, lifecycle, source-manifest digest, scope, selected references,
selected record digests, provenance, and a deterministic selection SHA-256.

## 7. API changes

Add one read-only endpoint:

```text
GET /api/simulation-run-comparison
    ?left_workflow_id=...
    &left_run_id=...
    &right_workflow_id=...
    &right_run_id=...
```

Extend the existing read-only endpoint with an all-or-none selected-run mode:

```text
GET /api/audit-export-bundle
    ?workflow_id=...
    &run_id=...
    &expected_manifest_sha256=...
    &journal_scope=complete_run_manifest
```

or:

```text
GET /api/audit-export-bundle
    ?workflow_id=...
    &run_id=...
    &expected_manifest_sha256=...
    &journal_scope=single_journal_event
    &journal_sequence=...
```

The parameterless legacy local bundle remains available for compatibility. Selected mode never
uses representative evidence. Invalid request shapes return generic 400, unknown selectors return
generic 404, stale manifest binding returns generic 409, and unavailable or contradictory durable
evidence returns generic 503.

No `POST`, `PUT`, `PATCH`, or `DELETE` route is added.

## 8. Test plan

Backend:

- deterministic identical and differing comparisons;
- all eleven evidence sections and all four comparison classifications;
- pending, rejected, approved-not-executed, protected execution, and missing-protection runs;
- exact order-intent, decision, execution, protection, alert, journal, digest, and provenance
  binding;
- reversed selector ordering and stable field ordering;
- same-run selection;
- missing selector, malformed query, pending persistence, corrupt manifest, duplicate identity,
  duplicate journal sequence, mixed source, cross-run contradiction, and stale digest rejection;
- restart reconstruction and repeated-read equality with no database or journal mutation;
- complete-manifest and single-event selected bundles;
- selected bundle safety scan and parameterless compatibility;
- route inventory proving no new mutation surface.

Frontend:

- strict comparison and selected-bundle response validation;
- no request before two deliberate selections and Compare;
- loading, empty, failure, partial-unavailable, identical, and differing rendering;
- deterministic added/removed/changed/unchanged summaries and exact evidence details;
- target/scope selection, stale-result invalidation, single-event selection, bundle preparation,
  and local JSON download eligibility;
- rejection of wrong selector, digest, reference, provenance, partial section, unsafe boolean, or
  mixed-source payloads;
- absence of approval, execution, broker, account, credential, transport, deployment, rollout, and
  live-mode controls.

Runtime:

- seed multiple durable lifecycle runs through the real Vite proxy;
- compare identical and differing runs;
- prepare complete-manifest and single-event bundles;
- restart the backend and prove responses are byte-stable;
- corrupt one persisted manifest and prove comparison/export return generic failure without repair;
- confirm safety remains simulation-only with live trading disabled and no broker connectivity.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider backend/tests/test_simulation_run_comparison.py backend/tests/test_audit_export.py
npm.cmd test --prefix frontend -- --run src/simulationRunComparison.test.ts src/SimulationRunComparisonPanel.test.tsx src/App.test.tsx
npm.cmd run lint --prefix frontend
npm.cmd run typecheck --prefix frontend
npm.cmd run build --prefix frontend
.\scripts\verify.ps1
```

Use the in-app browser tooling against `http://localhost:5173`. If no browser instance is
available after the required setup and troubleshooting retry, record that limitation and rely on
rendered component tests without claiming visual inspection.

## 10. Rollback plan

Revert the candidate commits. This removes the comparison module and GET route, selected audit
bundle metadata and query mode, frontend comparison workspace, tests, and docs. No database,
journal, workflow, run, decision, execution, or external state migration is required.

## 11. Implementation steps

1. Add failing backend comparison and selected-export tests.
2. Expose the existing strict lifecycle validation boundary without weakening it.
3. Implement frozen comparison snapshots, deterministic section/field comparison, hashes, and
   selected audit metadata.
4. Add the comparison GET route and selected mode to the existing audit GET route with generic
   fail-closed errors.
5. Add failing frontend client/state/component tests.
6. Implement strict clients, local selection state, comparison rendering, selected bundle
   preparation, and safe local download eligibility.
7. Integrate the workspace with the existing saved-run inspector and preserve all actionability
   boundaries.
8. Update read-model, API, audit, UI, roadmap, slice, product-gap, and README documentation.
9. Run focused checks, full verification, production build, real proxy/restart/corruption checks,
   and available browser inspection.
10. Self-review for safety, determinism, audit integrity, false attribution, mutation surfaces, and
    scope creep; fix all P0/P1 findings.
11. Commit, push, open an unmerged PR against `main`, and wait for green CI on the exact remote
    head.

## 12. Completion criteria

- Exactly two explicit committed-run selectors produce a deterministic comparison.
- Every required evidence category and all four change classifications are present and exact.
- Identical, differing, empty, loading, failure, and partial-unavailable states are explicit.
- Comparison and export reject unavailable, corrupt, mixed, duplicate, stale, or contradictory
  evidence without partial payloads, repair, or writes.
- Selected audit bundles are bound to one exact run, complete source manifest digest, explicit
  deterministic scope, selected journal references, selected record digests, and honest
  provenance.
- The workflow is read-only except for the existing deliberate local audit JSON response/download.
- Focused tests, complete verification, frontend production build, runtime proxy/restart/corruption
  checks, and available browser inspection pass.
- P0/P1 self-review is clear.
- The candidate branch is pushed and an unmerged PR has green CI on its exact final remote head.
- No Candidate 063, broker transport, secret/private field, deployment, production rollout,
  live-order path, or live-trading capability is added.

## 13. Risks and assumptions

- The comparison endpoint intentionally validates all committed projection sources before
  selecting two. One corrupt committed source quarantines comparison/export availability rather
  than allowing a misleading partial view.
- Selecting the same run twice is the only intentional identical-run state. Distinct run IDs make
  the run section differ even when all trading evidence is otherwise equivalent.
- Per-record SHA-256 values are evidence bindings, not signatures or external verification.
- Single-event scope includes full source-manifest references and digest in selection metadata but
  includes only the chosen journal record in `journal_records` and scoped audit events.
- Historical workflow documents are not versioned separately. Selected bundles therefore bind the
  exact expected workflow version from committed run evidence and do not claim that a newer
  workflow definition is the historical document.
- Client-side JSON download is local convenience only. It is not an external delivery mechanism
  and adds no server-side file write.

### Implementation evidence

- Focused comparison, audit-export, and execution-projection tests pass with 32 backend tests.
- Full repository verification passes with 691 backend tests, 171 frontend tests, four resilience
  tests, Ruff format/lint, TypeScript, ESLint, repository security checks, and the production
  frontend build. The build retains the pre-existing advisory chunk-size warning.
- The real Vite proxy served one pre-existing pending run plus two candidate test runs: one pending
  and one executed through the local fake broker.
- Same-run comparison returned eleven unchanged sections. Different-run comparison exposed
  deterministic lifecycle differences. Exact audit export returned 38 complete-manifest records
  and one record for the selected single-event scope.
- Backend restart reproduced identical raw comparison, complete-manifest export, and single-event
  export SHA-256 values.
- Controlled digest corruption returned generic HTTP 503 from comparison and selected export,
  left the corrupt value untouched, kept the safety endpoint available with live trading false,
  and recovered after the test restored the original digest.
- Browser discovery and its required troubleshooting retry returned no available browser. Rendered
  App and component tests cover all visible states and unsafe-control absence; no screenshot or
  visual browser inspection is claimed.
- P0/P1 self-review is clear for trading safety, secrets/private values, false attribution,
  determinism, audit integrity, mutation surfaces, and scope creep.
- Unmerged PR [#54](https://github.com/d0ofus/trading-oms/pull/54) targets `main`; GitHub CI passed
  on implementation head `f360715da497ed9ddf766d0db410c52ef1dbde6a` before the documentation-only
  closeout record.
