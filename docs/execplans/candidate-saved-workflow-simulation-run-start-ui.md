# ExecPlan: Saved workflow simulation run-start UI

## 1. Goal

Allow a local admin operator to deliberately start the currently loaded, persisted, unchanged,
backend-validated visual workflow through the existing saved-workflow simulation endpoint, then
refresh and select the resulting approval-wait record in the API-backed run inspector.

## 2. Non-goals

- Approval or rejection controls in the visual builder.
- Automatic approval, automatic retry, autosave, or automatic execution.
- Changes to risk, OMS, fake-broker, position, alert, or approval orchestration semantics.
- Workflow delete, arbitrary replay paths, URLs, filesystem browsing, import/export, scripts,
  expressions, or custom code.
- IBKR dependencies, broker contact, credentials, account identifiers, deployment, rollout,
  production operation, Candidate 063, or live trading.

## 3. Safety constraints

- Live trading remains disabled and no live-order or broker-transport path may be added.
- Only a loaded saved definition with an unchanged valid local draft may be considered eligible.
- The backend must revalidate the saved DSL and atomically reject a stale expected workflow version
  before orchestration or run journaling.
- Start requires local `administer_system`; approvers cannot start runs.
- An active emergency stop must return a blocked result before risk-increasing work advances.
- The run stops at manual approval wait. Downstream fake-broker, position, and alert nodes remain
  blocked until the existing separate approval path is used.
- Every accepted run and node transition continues to use the append-only journal.
- Run IDs and timestamps are created once per deliberate attempt and retained for exact explicit
  retry. There is no automatic retry.
- The UI offers only a fixed typed local replay fixture reference and renders no backend exception
  details or private values.
- No secret, broker, account, socket, route, submit, transmit, deployment, or live-mode field may be
  added to requests, responses, controls, docs, logs, or tests.

## 4. Current state

Authoritative `origin/main` is squash commit `a042881edb82b797de06d42f79d0bc41af226b02`
from PR #47, with tree `9ef557ae98933b9885c5df226a6ffc9052a67aca`. The visual editor can
create, load, and update strictly validated local definitions with optimistic version checks and
dirty-draft protection. The existing `POST /api/workflows/{workflow_id}/simulation-runs` route
requires `administer_system`, reloads and validates the saved DSL, enforces emergency stop, is
idempotent for an identical run payload, journals the deterministic replay-to-risk-to-approval
path, and stops at manual approval. The UI has a read-only API-backed run inspector but no run-start
control. Baseline verification passes with 598 backend and 88 frontend tests.

## 5. Proposed design

Add a small typed frontend run-start module and panel beside workflow persistence controls.

The module will:

- expose the one approved local replay fixture reference;
- derive eligibility from the loaded record, selected record, clean fingerprint, compiled graph,
  persistence/list state, local operator permission, and emergency-stop/read availability;
- create a retry-stable request once when the operator enters confirmation;
- validate the exact request and untrusted response shapes;
- map HTTP 400, 401/403, 409, 423, and other failures to generic validation, authorization,
  conflict, emergency-stop, and unavailable states;
- retain the exact request after failure so only an explicit retry can reuse it.

The panel will show idle or blocked posture, then a two-step confirmation containing `SIMULATION
ONLY`, workflow ID, saved version, and replay reference. A checkbox and explicit start command are
required. Starting and retry controls remain disabled whenever the request is in flight.

`App` will own the attempt state. Success will reload the complete run-inspection view through the
existing read helper and select the exact new `workflow_id::run_id` item. A refresh failure will
keep the created-run evidence and exact retry request visible without fabricating inspector data.

The existing backend request will gain a required positive `expected_workflow_version`. The runner
will compare it with the freshly loaded saved record and raise a typed conflict before constructing
the orchestrator. The route will map that conflict to HTTP 409. Existing DSL validation,
authorization, emergency-stop, idempotency, risk, approval, and journaling remain authoritative.
The saved-workflow adapter will also bind the only approved replay reference to its deterministic
risk-evaluation clock while retaining request wall-clock timestamps for run lifecycle and approval
expiry. This preserves stale-data enforcement in the replay time domain.

## 6. Data model changes

Add `expected_workflow_version` to `WorkflowSimulationRunRequest` and its exact idempotency payload.
No persisted table, workflow definition, run record, OMS state, approval state, or journal schema is
changed.

Frontend-only state adds explicit `idle`, `confirming`, `starting`, `success`,
`validation_blocked`, `authorization_blocked`, `emergency_stop_blocked`, `conflict`, and
`unavailable` variants. Failure variants retain the exact attempt where an explicit idempotent retry
is meaningful.

## 7. API changes

The existing endpoint remains:

```text
POST /api/workflows/{workflow_id}/simulation-runs
```

Its request adds required positive integer `expected_workflow_version`. Unknown fields and loose
types are rejected. A stale version returns HTTP 409 without starting or journaling a run. No new
endpoint, action URL, broker field, account field, credential field, or live-mode field is added.

## 8. Test plan

- Backend failing-first tests for required/positive expected version, stale 409 with zero run
  journal mutation, exact idempotent retry, strict request shape, authorization, emergency stop,
  and unchanged approval-wait behavior.
- Frontend module tests for all eligibility blocks, fixed local replay input, retry-stable IDs and
  timestamps, exact request shape, strict response validation, status mapping, and no second request
  without explicit action.
- Component tests for idle, confirmation, starting, success, every blocked/error state, disabled
  unsafe paths, explicit confirmation facts, and absent broker/live/secret/approval affordances.
- App tests for loaded-clean eligibility and successful inspector refresh/selection where practical.
- Existing workflow persistence, run-inspection, auth, emergency-stop, simulation, and safety suites
  remain green.

## 9. Verification commands

```powershell
Push-Location backend
python -m pytest tests/test_workflow_simulation_runs.py tests/test_workflow_simulation_api.py
Pop-Location

Push-Location frontend
npm.cmd test -- --run workflowSimulationRunStart.test.ts WorkflowSimulationRunStartPanel.test.tsx App.test.tsx
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
Pop-Location

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Start the backend and Vite frontend on localhost, exercise create/load/start/list through the actual
frontend proxy, and inspect `http://localhost:5173` with browser tooling when available.

## 10. Rollback plan

Revert the bounded commit or close the candidate PR. This removes the panel, frontend state module,
expected-version hardening, tests, and docs together. No migration or external cleanup is required;
existing local workflow definitions and run records are unchanged.

## 11. Implementation steps

1. Add failing backend tests for expected-version enforcement and conflict behavior.
2. Add failing frontend state-machine, strict-validation, panel, and App integration tests.
3. Harden the existing request and runner with authoritative workflow-version comparison.
4. Implement the typed frontend attempt builder, response validator, and error mapping.
5. Implement the two-step panel and wire it to clean persisted workflow state in `App`.
6. Refresh and select the successful run in the read-only inspector.
7. Run focused checks, fix failures, and perform a trading-safety and secret-leak self-review.
8. Update roadmap, slice, workflow, simulation-run, and setup docs.
9. Run full verification, exercise localhost, commit, push, open the PR, and confirm CI on the exact
   head commit without merging it.

## 12. Completion criteria

- A local admin can explicitly confirm and start only a loaded, saved, unchanged, valid workflow.
- New, dirty, invalid, stale, loading, conflicting, unavailable, unauthorized, or emergency-stopped
  state cannot start a run.
- Confirmation shows workflow ID, saved version, fixed local replay reference, and `SIMULATION ONLY`.
- The exact request is stable across explicit retry and never runs or retries automatically.
- The backend rejects stale expected versions with HTTP 409 before orchestration or run journaling.
- Success refreshes and selects the real approval-wait run in the inspector.
- Failures preserve the workflow draft, loaded record, and generic non-secret operator feedback.
- Focused checks and full repository verification pass.
- Local runtime remains paper/simulation, live trading disabled, and broker connectivity absent.
- The branch is committed, pushed, represented by an open PR against main, and green in CI.

Completion evidence on 2026-07-16: full verification passed with 610 backend and 122 frontend
tests plus formatting, lint, type checking, production build, and resilience checks. Localhost
returned UI 200, manual-approval wait for a current-time run, 400 for an unapproved replay, 409 for
a stale saved version, and 423 under active emergency stop. Runtime remained paper mode with live
trading disabled and broker connectivity not configured. Required browser discovery and
troubleshooting found no attached in-app browser, so no visual-inspection claim is made. Commit,
PR, and exact-head CI evidence remain the final delivery steps.

## 13. Risks and assumptions

- Workflow run records remain process-local and disappear on backend restart.
- The deterministic runner currently uses an internal replay fixture while recording the validated
  local reference supplied by the request; this slice does not add filesystem replay ingestion.
- Browser automation may be unavailable; component tests and direct localhost API checks are the
  fallback, and no visual-inspection claim will be made without a browser.
- The local auth model is development-only and is not production identity evidence.
- A later slice may add durable run retention or richer replay selection, but neither belongs here.
