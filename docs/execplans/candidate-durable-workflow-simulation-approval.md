# ExecPlan: Durable saved-workflow simulation approval

## 1. Goal

Allow a separately authorized approver to deliberately approve or reject one persisted
saved-workflow simulation run that is waiting for manual approval. The exact decision, updated
workflow-run status, updated node statuses, and append-only journal evidence must survive backend
reconstruction and restart without duplicate decisions or journal records.

Approval in this slice stops at an explicit `approved_not_executed` state. It does not advance the
OMS, call the fake broker, create a fill or position, deliver an alert, contact IBKR, or transmit an
order.

## 2. Non-goals

- Automatic approval, automatic retry, automatic recovery, or automatic execution.
- OMS advancement, fake-broker acknowledgement, fill, cancel, reject, position, protection, or
  alert orchestration.
- Changes to replay data, strategy evaluation, risk policy, or order-intent creation.
- Repair, deletion, or silent completion of pending or corrupt durable evidence.
- Arbitrary replay paths, URLs, imports, scripts, expressions, or custom code.
- IBKR dependencies, sockets, TWS or Gateway contact, broker transport, credentials, account
  identifiers, deployment, production rollout, or live trading.
- Candidate 063 implementation or any relaxation of its external-review gates.

## 3. Safety constraints

- Live trading remains disabled and no broker-order transmission path may be added.
- Default operation remains local deterministic simulation using the one approved replay fixture.
- The persisted run must already contain a passed risk decision and a pending manual approval
  ticket before a decision can be reserved.
- The decision must bind unambiguously to the persisted workflow ID, saved workflow version, run
  ID, order-intent ID, risk-decision ID, order ID, and approval-ticket ID.
- The dedicated `approve_simulation` permission remains mandatory. The decision actor must equal
  the authenticated approver identity, and administrator/approver role separation remains intact.
- Approval and rejection are distinct deliberate commands with explicit decision ID, timestamp,
  actor, reference, and reason.
- Active emergency stop blocks approval. Rejection remains available as a risk-reducing action.
- Expired, unknown, stale, already-decided, mismatched, ambiguous, pending, partial, malformed,
  missing, corrupt, digest-invalid, or contradictory evidence fails closed.
- The JSONL journal remains the append-only source of truth. SQLite stores canonical identity,
  state, and digest-bound evidence for strict reconstruction.
- A decision reservation must be durable before its first decision journal append. Finalization
  must atomically mark the SQLite decision evidence committed only after complete typed evidence
  exists.
- An interrupted pending decision is retained and unavailable for automatic retry or display as a
  completed decision.
- Exact committed retries remain idempotent across restart. Conflicting retries are rejected.
- Every accepted decision and changed workflow-node status is journaled.
- API and UI errors must not expose paths, SQL, raw exception details, secrets, credentials,
  account identifiers, broker routes, or private values.
- No secret, broker, account, submit, transmit, deployment, or live-mode field may be introduced in
  persistence, APIs, logs, docs, screenshots, or tests.

## 4. Current state

Authoritative `origin/main` is squash commit
`071a37e21d468249bc0a2a0cb836e413e1efa550` from PR #49. Its exact branch head passed CI before
merge. The working branch was created from that commit in a healthy isolated clone because the
original root checkout has missing Git objects and invalid refs.

`WorkflowSimulationRunner` currently:

- validates and starts one saved workflow against the fixed local replay;
- journals replay, strategy, order intent, risk, OMS pending approval, and approval-ticket creation;
- stops at `waiting_for_approval`;
- stores the exact request, typed run record, node statuses, and a digest-bound JSONL manifest in
  schema-v2 SQLite evidence; and
- strictly reconstructs list/get and exact retry results after restart.

The existing generic approval endpoints use `SimulationApprovalService`, which seeds a separate
in-memory demo ticket and clears its temporary journal when rebuilt. They cannot safely decide the
approval ticket embedded in a persisted saved-workflow run.

The run inspector shows the persisted approval ticket ID and node evidence, but it has no deliberate
decision controls. Downstream fake-broker, position, and alert nodes remain
`blocked_waiting_for_approval`.

Implementation update: the bounded decision path, schema-v3 evidence, scoped API routes, deliberate
UI, and local Admin/Approver session switch are implemented. Focused and full verification pass.
Real localhost approval, rejection, role separation, restart recovery, and exact-retry journal
deduplication have been exercised. Browser discovery returned no available browser instance, so no
visual-inspection claim is made; component/render tests and direct Vite-proxy checks are the
recorded fallback.

## 5. Proposed design

Add workflow/run-scoped simulation decision endpoints. The request includes the expected saved
workflow version and approval-ticket ID in addition to the existing explicit decision fields. The
path supplies workflow ID and run ID. All four identities must match the committed persisted run.

`WorkflowSimulationRunner.apply_decision` will serialize decision attempts under its existing
runner lock and:

1. load and fully validate the committed run and its JSONL manifest;
2. require `waiting_for_approval`, the expected workflow version, and the exact approval ticket;
3. locate exactly one persisted `approval.ticket.created` event and validate its typed ticket,
   order, client-order, risk-decision, OMS, and order-intent attribution against the run-derived
   identifiers;
4. enforce emergency stop for approval but not rejection;
5. atomically reserve the canonical decision request as `pending` in SQLite before journal append;
6. restore the typed pending ticket into `ApprovalTicketBook` and apply the existing
   `ApprovalDecisionRequest`, preserving existing timing and ticket-state validation;
7. append updated workflow-node status events for the approval and downstream blocked nodes;
8. build a new typed workflow-run record whose status is `approved_not_executed` or `rejected`,
   whose approval decision is explicit, and whose node references point to the new status records;
9. extend the run's manifest with only the attributable decision records and verify every entry
   against the JSONL source; and
10. atomically commit the decision record, updated run record, expanded manifest, and digest in
    SQLite.

The original initial-run request identity remains unchanged. Schema-v3 decision columns on the same
evidence row make one decision per run representable and allow reads to fail closed while a decision
is pending. A unique partial index prevents one decision ID from being attached to different runs.

Manifest sequence validation changes from one contiguous segment to strictly increasing unique
sequences. Initial run creation is contiguous, but a later manual decision may occur after unrelated
runs have appended events. Every manifest entry must still exactly match the source JSONL record and
must be attributable to this run.

The frontend adds a compact decision panel beside the selected run inspector. It is available only
for a strictly validated `waiting_for_approval` run to an operator with approver permission. Review
and confirmation are separate steps. Approval and rejection have separate controls, show
`SIMULATION ONLY`, and display workflow, version, run, and ticket identity. The form captures a
reason; actor and deterministic retry-stable decision identity are bound to the current operator and
attempt. Success reloads the run and selects its durable updated record.

## 6. Data model changes

Add SQLite migration version 3 with nullable decision columns on
`workflow_simulation_run_evidence`:

- `decision_id`;
- `decision_request_sha256`;
- `decision_request_json`;
- `decision_evidence_state`, limited by application validation to `pending` or `committed`;
- `decision_record_json`; and
- `decision_updated_at`.

Add a unique partial index on non-null `decision_id`.

No-decision rows require all decision columns to be null. Pending rows require canonical request
identity and no decision record. Committed rows require a typed decision record whose identities
match the request and updated run record.

Extend `WorkflowSimulationRunRecord` with nullable typed `approval_decision` evidence. Existing
schema-v1 records without that field remain readable as undecided records. New serialized records
include the field. State invariants are:

- `waiting_for_approval` requires a ticket and no decision;
- `approved_not_executed` requires an approved decision;
- `rejected` requires a rejected decision; and
- downstream nodes cannot have execution-complete statuses in either decided state.

The nested original simulation run remains non-terminal in this slice because no OMS/fake-broker
execution or simulation-run completion transition occurs. The outer workflow-run decision status is
the authoritative state for this bounded continuation.

## 7. API changes

Add:

```text
POST /api/workflows/{workflow_id}/simulation-runs/{run_id}/approve
POST /api/workflows/{workflow_id}/simulation-runs/{run_id}/reject
```

Strict request body:

```json
{
  "schema_version": 1,
  "expected_workflow_version": 1,
  "approval_ticket_id": "workflow-run-001-approval-ticket",
  "decision_id": "workflow-run-001-approve-decision",
  "decided_at": "2026-07-17T06:00:00Z",
  "actor": "approver-operator-001",
  "decision_reference": "workflow-run-001-approve-manual-review",
  "reason": "operator_reviewed_simulation_evidence"
}
```

Success returns the updated `WorkflowSimulationRunRecord`. Existing generic demo approval endpoints
remain unchanged for compatibility, but the saved-workflow UI uses only the scoped endpoints.

Expected failures:

- 400 for invalid input, expired tickets, or actor mismatch;
- 403 for missing approver permission;
- 404 for unknown workflow/run;
- 409 for stale version, identity conflict, or conflicting decided state;
- 423 when emergency stop blocks approval; and
- 503 with generic detail for pending or invalid durable evidence.

No endpoint submits, routes, transmits, executes, fills, cancels, contacts a broker, or enables live
trading.

## 8. Test plan

- Add failing-first SQLite tests for schema-v3 initialization and migration from schema v2.
- Test exact decision reservation, global decision-ID uniqueness, conflicting reservation, pending
  shape, atomic finalization, and committed reconstruction.
- Add typed approval ticket and decision reconstruction tests.
- Add runner tests for exact workflow/version/run/ticket/order-intent/risk/order attribution.
- Test approval to `approved_not_executed` and rejection to terminal `rejected`.
- Test approval expiry, unknown run, stale workflow version, ticket mismatch, duplicate or missing
  attribution, already-decided state, and ambiguous evidence.
- Test emergency-stop approval block and rejection allowance.
- Test same-runner and cross-runner concurrent decisions.
- Test exact committed retry after restart with unchanged journal count and conflicting retry
  rejection.
- Test pending, partial, malformed, missing, corrupt, digest-invalid, and contradictory decision
  evidence.
- Test non-contiguous but strictly ordered attributable manifests and reject duplicate,
  out-of-order, foreign, or source-mismatched records.
- Assert that approval and rejection emit no OMS post-approval transition, fake-broker transition,
  fill, position, external alert, broker request, network action, or live-order event.
- Add API tests for role separation, actor binding, emergency stop, status mapping, restart recovery,
  idempotency, and generic unavailable responses.
- Add frontend API/client/component tests for loaded, review, confirmation, deciding, approved,
  rejected, conflict, forbidden, expired, emergency-stop, unavailable, and recovered states.
- Assert absence of broker, account, credential, live-mode, submit, transmit, automatic approval,
  automatic retry, and automatic execution affordances.
- Exercise a real localhost create/load/start/decision/restart/recover sequence.

## 9. Verification commands

```powershell
Push-Location backend
python -m pytest tests/test_approval_tickets.py tests/test_local_persistence.py tests/test_workflow_simulation_runs.py tests/test_workflow_simulation_api.py tests/test_emergency_stop_api.py
ruff format --check .
ruff check .
mypy src
Pop-Location

Push-Location frontend
npm.cmd test -- --run workflowSimulationApproval.test.ts WorkflowSimulationApprovalPanel.test.tsx workflowRunInspector.test.ts App.test.tsx
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
Pop-Location

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Start the backend and Vite on localhost, exercise the decision and restart sequence through the real
API proxy, and inspect `http://localhost:5173` with the in-app browser when available.

## 10. Rollback plan

Revert the bounded candidate commit or close the PR. Migration version 3 is additive. A previous
binary ignores the added columns and index, while the schema-v2 initial-run evidence remains
present. Do not delete local evidence automatically. Preserve pending or committed decision data
for investigation before any operator-directed cleanup.

## 11. Implementation steps

1. Add failing tests for typed decision reconstruction and schema-v3 persistence.
2. Implement migration, reservation, finalization, strict reconstruction, and decision-ID
   uniqueness.
3. Add runner-level decision request/record models and fail-closed evidence validation.
4. Restore the exact persisted ticket into the existing approval domain and apply decisions under
   the existing runner and journal locks.
5. Add workflow/run-scoped endpoints with existing approver authorization, actor binding, and
   emergency-stop behavior.
6. Add the deliberate selected-run decision client, state model, and UI panel.
7. Run focused tests and fix safety, durability, idempotency, and UI-state failures.
8. Update slice, API, persistence, journal, simulation-run, visual-builder, roadmap, and gap docs.
9. Run full verification, the localhost restart matrix, browser inspection, and P0/P1 self-review.
10. Commit, push, create a PR against `main`, and require green exact-head CI without merging.

## 12. Completion criteria

- Schema version 3 initializes and migrates additively and idempotently.
- Only an authorized approver can decide the exact pending persisted ticket.
- Actor, workflow version, workflow, run, order intent, risk decision, order, and ticket identities
  are bound and validated.
- Emergency stop blocks approval and permits rejection.
- Approval ends at `approved_not_executed`; rejection terminally blocks downstream nodes.
- Exact retry after restart returns the same record with no duplicate journal entries.
- Conflicting, concurrent, pending, partial, malformed, missing, corrupt, or contradictory evidence
  fails closed.
- Every accepted decision and changed node status is present in the append-only journal and
  digest-bound durable manifest.
- No OMS post-approval transition, fake-broker event, fill, position, external alert, broker
  contact, order transmission, credential, account field, rollout, or live capability is added.
- The UI requires explicit review and confirmation and refreshes to the exact recovered result.
- Focused checks, full verification, frontend build, localhost restart flow, and safety self-review
  pass.
- The branch is committed and pushed, an unmerged PR exists against `main`, and exact-head CI is
  green.

## 13. Risks and assumptions

- SQLite and JSONL cannot share one transaction. The explicit pending decision state preserves
  interrupted work as unavailable evidence instead of fabricating success.
- A global journal may contain unrelated events between run creation and a later decision. The
  per-run manifest therefore uses strictly increasing source sequences rather than requiring one
  contiguous range.
- The existing local authentication headers are a development-only identity model and do not
  constitute production authentication. The UI exposes an explicit local Admin/Approver switch and
  sends one consistent selected role across read and workflow clients; production rejects this
  header model.
- One decision per saved-workflow run is intentional. Later execution must consume only a durable
  approved decision and requires a separately reviewed slice.
- Existing generic demo approval endpoints remain separate compatibility behavior. Saved-workflow
  decisions never fall back to the seeded demo ticket.
- Browser automation may be unavailable. Component tests and direct localhost checks are the
  fallback, and no visual-inspection claim will be made without browser evidence.
