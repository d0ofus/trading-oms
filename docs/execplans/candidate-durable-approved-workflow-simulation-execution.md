# ExecPlan: Durable approved saved-workflow simulation execution

## 1. Goal

Allow a separately authorized local simulation administrator to deliberately execute one persisted
saved-workflow run only after a different approver has recorded a valid committed approval. The
command must consume the exact workflow version, run, ticket, approval decision, order intent, risk
decision, and OMS order evidence and then use the existing local OMS, fake broker, simulated
position, protection-monitoring, local alert, and append-only journal domains.

The accepted path is deterministic and simulation-only. It produces restart-recoverable execution,
fill, position, protection, local alert, node-status, and journal evidence. It cannot contact a
broker or transmit an order.

## 2. Non-goals

- Automatic execution when approval is recorded.
- Automatic retry, repair, deletion, or silent completion of interrupted execution evidence.
- IBKR SDKs, sockets, hosts, ports, probes, contract lookup, account identifiers, paper transport,
  external broker order submission, or live trading.
- Real protective-order submission, real portfolio reconciliation, or real alert delivery.
- Arbitrary broker outcomes, replay inputs, scripts, expressions, imports, or operator code.
- Deployment, production rollout, readiness-gate relaxation, Candidate 063, or changes to its
  external-review requirements.
- Production authentication or combining local administrator and approver roles.

## 3. Safety constraints

- Live trading remains disabled. Default and effective operation remain local simulation/paper.
- The command is a separate deliberate action after approval; approval itself never executes.
- `administer_system` is required to execute. `approve_simulation` is insufficient, and the local
  role policy continues to prohibit combining administrator and approver roles.
- The request actor must equal the authenticated administrator.
- The persisted run must be `approved_not_executed` with committed, digest-valid approval evidence.
- Workflow ID, saved version, run ID, approval ticket ID, approval decision ID, order-intent ID,
  risk-decision ID, order ID, and their journal attribution must all match exactly.
- The persisted risk result must be `passed`, the order must be `PENDING_APPROVAL`, and the
  risk-increasing order intent must contain a valid protective-order plan. Missing or contradictory
  protection evidence fails before execution reservation or OMS/fake-broker work.
- Active emergency stop blocks execution before reservation and journals the blocked attempt.
- Unknown simulated broker state blocks execution before reservation and is journaled as a local
  execution safety block.
- Execution reservation is durable before the first OMS or fake-broker side effect.
- SQLite and JSONL do not share a transaction. Interrupted `pending` execution evidence remains
  unavailable and requires operator investigation; it is never automatically rerun or shown as
  successful.
- Exact committed retries are idempotent across restart. Conflicting or concurrent requests fail
  without duplicate OMS transitions, fake orders, fills, positions, alerts, or journal records.
- The existing explicit OMS state machine and `FakeBroker` adapter are the only order lifecycle and
  broker-shaped components used.
- A filled simulated position whose expected protection is absent creates a critical local alert,
  records local no-op dispatch, and marks further risk-increasing work blocked in the execution
  evidence.
- All alerts remain local/no-op. No Telegram, HTTP, webhook, or other external delivery is added.
- Every accepted execution, OMS transition, fake-broker transition, fill, position update,
  protection result, alert intent/dispatch, node-status change, interrupted boundary, and safety
  block remains attributable in durable or append-only local evidence.
- API and UI errors must not expose paths, SQL, stack traces, secrets, credentials, account values,
  broker routes, or private values.
- No secret, broker-route, account, submit, transmit, deployment, or live-mode field may be added to
  persistence, APIs, logs, docs, screenshots, tests, or alerts.

## 4. Current state

Authoritative `origin/main` is squash commit
`e8ecd7318b72bd413a3a443ea4a3cea4e1986d8b` from merged PR #50. Its exact head passed CI. This
branch was created from that commit in a fresh healthy isolated clone because the original root
checkout was stale and has previously exhibited missing Git objects and invalid references.

`WorkflowSimulationRunner` currently persists one fixed saved-workflow replay through strategy,
order-intent, risk, OMS `PENDING_APPROVAL`, and approval-ticket creation. Schema-v3 SQLite evidence
stores the accepted run request, run record, decision request/record, and digest-bound JSONL
manifest. A separately authorized approver can durably approve or reject the exact ticket.
Approval ends at `approved_not_executed`; rejection permanently blocks downstream nodes.

The repository already has deterministic in-memory domains for:

- explicit OMS transitions and duplicate transition-ID handling;
- local `FakeBroker` acknowledgement and fill transitions;
- simulated position updates and expected-protection monitoring;
- critical missing-protection alert intents and local no-op dispatch; and
- append-only JSONL journaling.

Those domains are not yet reconstructed from saved-run evidence, called by a saved-run API, or
captured in the durable run record. The selected-run UI can approve/reject but has no explicit
post-approval execution control.

## 5. Proposed design

Add one workflow/run-scoped `execute` endpoint and a strict
`WorkflowSimulationExecutionRequest`. The path supplies workflow and run identity. The body binds
the expected saved version and all approval, order-intent, risk, and OMS identities. It also records
an explicit execution ID, timestamp, actor, reference, reason, known simulated-broker-state flag,
and deterministic protection observation.

`WorkflowSimulationRunner.execute_approved_run` uses a dedicated non-blocking execution gate before
the existing runner lock so simultaneous execution requests return conflict while a later exact
retry remains idempotent. The accepted path then:

1. fully load and validate the committed schema-v3 run and its JSONL source manifest;
2. require `approved_not_executed`, a committed approved decision, administrator actor binding,
   the exact version and identity tuple, and no prior execution evidence;
3. reconstruct exactly one typed order-intent proposal, passed risk decision, OMS `CREATED` and
   `PENDING_APPROVAL` history, ticket, and approval decision from attributable journal records;
4. require the risk-increasing proposal to carry a valid protective plan and reject unknown
   simulated broker state;
5. enforce the emergency stop before reservation;
6. atomically reserve the canonical execution request as `pending` in SQLite;
7. restore the validated OMS history into the existing state machine without appending duplicate
   historical records;
8. advance OMS through `APPROVED` and `SUBMITTED`, call the existing local fake broker for a fixed
   deterministic acknowledge-and-fill sequence, then advance OMS through `ACKNOWLEDGED` and
   `FILLED`;
9. pass the typed fake fill to `SimulatedPositionBook`, recording either expected protection or a
   missing-protection critical local alert; for a protected result, create one informational local
   completion alert and local no-op dispatch so the workflow alert node has explicit evidence;
10. append updated workflow-node statuses and a `workflow_simulation.execution_completed` record;
11. build a typed execution record and expanded strictly increasing manifest, validating each
    record against the JSONL source; and
12. atomically finalize the execution record, updated run record, expanded manifest, and digests in
    SQLite.

The state-machine restoration method will validate every stored transition by rebuilding its
request and expected snapshot. It populates in-memory state only and never writes historical events
again. The fake broker is always new for an unexecuted run, and its existing duplicate client-order
guard remains active during the accepted execution.

Committed execution reads reconstruct all nested typed records and verify their exact manifest
records and identity bindings. A committed exact retry returns the existing record before any
domain component is invoked. A pending or corrupt execution makes list/get/retry return only the
generic unavailable state.

The frontend adds a selected-run execution panel. Eligibility requires a strictly validated
`approved_not_executed` record and an administrator session. The panel shows the exact workflow,
version, run, ticket, approval decision, order intent, risk decision, OMS order, and protective-plan
facts. Review and second confirmation are separate. The control is labeled `SIMULATION ONLY`, and
success reloads the run inspector from backend evidence.

## 6. Data model changes

Add SQLite migration version 4 with nullable execution columns on
`workflow_simulation_run_evidence`:

- `execution_id`;
- `execution_request_sha256`;
- `execution_request_json`;
- `execution_evidence_state`, validated as `pending` or `committed`;
- `execution_record_json`; and
- `execution_updated_at`.

Add a unique partial index on non-null `execution_id`.

No-execution rows require every execution column to be null. Pending rows require canonical request
identity and no execution record. Committed rows require a typed execution record matching the
request, updated run record, manifest, and digest.

Add `WorkflowSimulationExecutionRecord` with:

- exact execution, workflow, run, version, approval, order-intent, risk, and order identities;
- execution timestamp, actor, reference, and reason;
- simulated broker-state and expected-protection observations;
- ordered typed OMS and fake-broker transitions;
- typed simulated position;
- typed local alert intents and local no-op dispatch outcomes;
- explicit protection status and `risk_increasing_actions_blocked`; and
- journal references for execution-specific evidence.

Extend `WorkflowSimulationRunRecord` with nullable execution evidence. Existing schema-v1 JSON
records without this field remain readable as unexecuted records. New run statuses are:

- `executed` for a deterministic fill with expected protection present; and
- `executed_protection_missing` for a deterministic fill followed by a critical missing-protection
  condition and a block on further risk-increasing work.

`approved_not_executed` requires no execution record. Both executed statuses require the previously
committed approved decision and one committed execution record. Rejected runs never permit
execution.

## 7. API changes

Add:

```text
POST /api/workflows/{workflow_id}/simulation-runs/{run_id}/execute
```

Strict request body:

```json
{
  "schema_version": 1,
  "expected_workflow_version": 1,
  "approval_ticket_id": "workflow-run-001-approval-ticket",
  "approval_decision_id": "workflow-run-001-approve-decision",
  "order_intent_id": "workflow-run-001-intent",
  "risk_decision_id": "workflow-run-001-risk",
  "order_id": "workflow-run-001-order",
  "execution_id": "workflow-run-001-execution",
  "executed_at": "2026-07-21T06:00:00Z",
  "actor": "human-operator-001",
  "execution_reference": "workflow-run-001-manual-simulation-execution",
  "reason": "operator_confirmed_approved_simulation_execution",
  "broker_state_known": true,
  "expected_protection_present": true
}
```

The endpoint requires `administer_system`; approver-only sessions receive 403. Success returns the
complete updated `WorkflowSimulationRunRecord`.

Expected failures:

- 400 for invalid fields, actor mismatch, missing protective plan, expired or rejected approval,
  or explicitly unknown simulated broker state;
- 403 for missing administrator permission;
- 404 for an unknown workflow/run;
- 409 for stale version, identity conflict, an unapproved/already-executed run, conflicting request,
  or concurrent execution;
- 423 when emergency stop is active; and
- 503 with generic detail for pending, partial, malformed, missing, corrupt, or contradictory
  durable evidence.

No endpoint accepts a broker route, account, host, port, credential, live mode, external alert
destination, or arbitrary broker outcome.

## 8. Test plan

- Add failing-first schema-v4 initialization and v3-to-v4 migration tests.
- Test execution reservation, global execution-ID uniqueness, exact reservation retry, conflicting
  retry, pending shape, atomic finalization, and committed reconstruction.
- Test strict JSON reconstruction for OMS requests/snapshots/transitions, fake-broker requests and
  transitions, simulated positions, alert intents, and dispatch outcomes.
- Test OMS history restoration without journal append and reject malformed, out-of-order,
  duplicate, identity-mismatched, or recomputation-inconsistent history.
- Test valid committed approval execution through OMS, fake broker, fill, position, protection,
  local alert, node statuses, and execution-completed evidence.
- Test execution before approval, after rejection, with expired approval, and after prior execution.
- Test exact workflow/version/run/ticket/decision/order-intent/risk/order attribution mismatch.
- Test missing protective plan and contradictory protection evidence fail before OMS/fake-broker
  side effects.
- Test administrator/approver role separation and body actor binding.
- Test active emergency-stop blocking and explicit unknown simulated broker-state blocking.
- Test exact retry in-process and after service reconstruction with unchanged journal counts.
- Test conflicting retry, same-runner concurrency, and independent-runner concurrency.
- Test pending, partial, missing, malformed, digest-invalid, source-mismatched, and contradictory
  execution evidence.
- Test deterministic fake fill and exact position reconstruction.
- Test duplicate order/execution prevention and unknown OMS/broker state blocking.
- Test expected protection present with informational local no-op alert.
- Test expected protection missing with critical local no-op alert and the durable
  risk-increasing-actions block.
- Test append-only source and expanded manifest integrity for every required domain event.
- Test API status mapping, generic unavailable errors, restart recovery, and idempotency.
- Add frontend client/state/component tests for eligibility, review, second confirmation, executing,
  completed, critical protection block, forbidden, conflict, emergency-stop, unavailable, and
  recovered states.
- Assert absence of broker, account, credential, live-mode, transmit, external-alert, automatic
  approval, and automatic-execution affordances.
- Exercise the real Vite-proxy start/approve/switch-role/execute/restart/recover/retry flow.

## 9. Verification commands

```powershell
Push-Location backend
python -m pytest tests/test_oms_state_machine.py tests/test_fake_broker.py tests/test_simulated_positions.py tests/test_local_persistence.py tests/test_workflow_simulation_runs.py tests/test_workflow_simulation_api.py
ruff format --check .
ruff check .
mypy src
Pop-Location

Push-Location frontend
npm.cmd test -- --run workflowSimulationExecution.test.ts WorkflowSimulationExecutionPanel.test.tsx workflowApiClient.test.ts App.test.tsx
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
Pop-Location

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Run changed-file secret scanning, `git diff --check`, `git fsck --full --no-dangling`, and a
safety-focused P0/P1 self-review. Start the backend and Vite locally, exercise the full flow through
the Vite proxy, and inspect `http://localhost:5173` with the in-app browser when available.

## 10. Rollback plan

Revert the bounded candidate commits or close the PR. Migration version 4 is additive. An older
binary ignores the new columns while schema-v3 run and decision evidence remains preserved. Never
delete pending, partial, or committed local execution evidence automatically. Preserve the SQLite
row and JSONL journal for operator investigation before any separately approved cleanup.

## 11. Implementation steps

1. Add focused failing tests for typed domain reconstruction, OMS restoration, schema-v4 execution
   persistence, and strict evidence validation.
2. Implement typed reconstruction and no-journal OMS history restoration.
3. Implement migration, execution reservation/finalization, global execution-ID uniqueness, and
   fail-closed row reconstruction.
4. Add the execution request/record models and extend saved-run state invariants.
5. Reconstruct the exact approved context and orchestrate existing OMS, fake broker, position,
   protection, alert, and journal domains under the runner lock.
6. Add the administrator-only scoped endpoint with actor binding and emergency-stop behavior.
7. Add the deliberate selected-run execution client, state model, and two-stage UI panel.
8. Run focused tests and fix durability, idempotency, role, protection, and UI-state failures.
9. Update slice, roadmap, execution, persistence, journal, run, API, authorization, protection,
   alert, and visual-builder documentation.
10. Run full verification, production build, localhost restart matrix, browser inspection, secret
    scan, Git integrity checks, and P0/P1 self-review.
11. Commit only bounded files, push the dedicated branch, create an unmerged PR against current
    `main`, and require green exact-head CI without merging.

## 12. Completion criteria

- Schema version 4 initializes and migrates additively and idempotently.
- Only a separately authorized administrator can explicitly execute an exact committed approved
  saved-workflow run; approval itself remains non-executing.
- Every workflow, version, run, ticket, approval, order-intent, risk, order, actor, and protection
  identity is strictly bound and validated.
- Emergency stop, unknown simulated broker state, missing protection plan, rejected approval,
  unapproved state, and corrupt evidence fail closed before risk-increasing side effects.
- The accepted path uses existing OMS and `FakeBroker` interfaces and produces deterministic OMS,
  fake-fill, position, protection, local alert, node-status, and completion evidence.
- Missing expected protection produces a critical local alert and durable block on further
  risk-increasing work.
- Exact committed retry after restart returns the same result without duplicate domain or journal
  records. Conflicting, concurrent, pending, partial, malformed, missing, corrupt, or contradictory
  evidence fails closed.
- Every accepted execution record is recoverable from typed SQLite evidence and an exact
  digest-bound append-only JSONL manifest.
- The UI requires explicit review and second confirmation, displays the exact consumed safety
  evidence, and refreshes from backend evidence.
- No IBKR, broker transport, account, credential, external alert delivery, deployment, rollout, or
  live-order capability is introduced.
- Focused tests, full verification, production build, localhost restart/retry checks, secret scan,
  Git integrity audit, and P0/P1 self-review pass.
- The branch is committed and pushed, an unmerged mergeable PR exists against current `main`, and
  CI is green on the exact remote head.

## 13. Risks and assumptions

- SQLite and JSONL cannot commit atomically. A durable pending execution row is the explicit crash
  boundary; automatic replay after partial OMS/fake-broker events would risk duplicates and is
  intentionally prohibited.
- The prior OMS is represented by immutable journal records. Restoration must recompute and compare
  each state rather than trusting a serialized final snapshot.
- `expected_protection_present` is a deterministic simulation observation, not a real broker claim.
  A false observation deliberately exercises the critical protection-alert path after a valid
  protective plan was required before execution.
- The fixed fake-broker path fills immediately after acknowledgement. Other outcomes remain covered
  by existing in-memory domain tests and are not exposed by this endpoint.
- Local header authentication is development-only. It demonstrates role separation but is not
  sufficient for production operation.
- Browser automation may be unavailable. Component tests and direct localhost checks are the
  fallback, and no visual-inspection claim will be made without browser evidence.

Implementation record:

- The bounded schema-v4 persistence, typed reconstruction, OMS restoration, runner orchestration,
  Admin-only endpoint, and two-stage UI were implemented on the dedicated branch.
- Safety review found and fixed the P1 issues before delivery: execution commands use the persisted
  run version rather than the latest editable workflow version; committed evidence is fully
  validated before exact/conflicting retry handling; and simultaneous execution requests are
  rejected while later exact retries remain idempotent. Complete OMS manifest attribution is
  checked as the exact approval prefix plus execution suffix. Actor mismatch now reaches the
  runner's attributable blocked-event path, and UI copy separates the persisted protection plan
  from the operator's deterministic protection observation.
- Full Windows verification passed with 663 backend and 150 frontend tests. Ruff formatting/lint,
  TypeScript, frontend lint, repository security checks, and resilience tests passed. The
  production frontend build passed with only the existing advisory chunk-size warning.
- Real Vite-proxy checks proved Admin/Approver separation, durable `approved_not_executed`, active
  emergency-stop blocking, deterministic OMS/fake fill/position/protection/local alert evidence,
  backend-restart recovery, identical exact retry, and zero duplicate journal lines.
- Browser setup and the required troubleshooting retry reported no available browser instance.
  No screenshot or visual-inspection claim is made; component and integration rendering remains
  covered by the full frontend suite.
- Candidate 063, IBKR transport, broker/account fields, external alert delivery, deployment,
  production rollout, and live trading remain unchanged and deferred.
