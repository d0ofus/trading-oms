# ExecPlan: Durable upstream simulation read-model projections

## 1. Goal

Project every fully validated committed saved-workflow simulation run into one coherent operations
read snapshot. The signal, risk-decision, approval-ticket, and audit views must reflect exact local
simulation evidence for pending-approval, rejected, approved-not-executed, and executed runs. When
durable runs exist, representative records must disappear from every lifecycle resource; stages
that a run has not reached must be represented by empty durable resources rather than demo rows.

The operator UI will show exact workflow/run lineage for signals, risk decisions, and approval
tickets. Terminal decisions will be visibly read-only. A pending durable ticket will direct the
operator to the existing saved-run approval panel instead of broadening the generic approval
mutation path.

## 2. Non-goals

- Adding or changing approval, execution, OMS, fake-broker, journal, or recovery mutations.
- Automatically approving, executing, retrying, repairing, deleting, or rewriting evidence.
- Adding a database migration or another persistence source.
- Candidate 063, an IBKR dependency, a socket, a connectivity probe, contract lookup, broker
  host/port/account/credential fields, or any broker transport.
- External alert delivery, deployment, production rollout, readiness-gate relaxation, or live
  trading.

## 3. Safety constraints

- Live trading remains disabled and no live-order path may exist.
- No secrets, private values, broker account identifiers, credentials, tokens, hosts, or ports may
  be introduced or exposed.
- Only committed SQLite evidence whose manifest digest matches the append-only JSONL source may be
  read. Reads must perform no writes or repairs.
- Every projected record must be reconstructed through the existing typed domain parsers and
  linked to exact persisted identities. Missing or contradictory identities fail closed; they are
  never inferred from a neighboring run.
- The exact persisted order-intent `source_signal_reference` is the signal identity. It must match
  the unique signal journal record in the same manifest.
- Durable and representative records must never be mixed. Any unavailable, pending, malformed,
  digest-invalid, source-mismatched, duplicate, or contradictory evidence makes the complete
  affected operations snapshot unavailable through a generic HTTP 503 response.
- Pre-execution evidence is classified `simulated`, `local_only`, and `externally_unverified`, with
  `broker_derived=false` and `externally_verified=false`. It must not claim fake-broker derivation.
- Existing execution records retain their exact fake-broker attribution. Empty downstream stages
  must not claim that a fake-broker action occurred.
- Terminal approval tickets are non-actionable. Pending durable tickets use only the existing
  workflow/run-scoped, separately authorized approval flow with its authorization, expiry,
  idempotency, emergency-stop, and concurrency checks unchanged.

## 4. Current state

- `WorkflowSimulationRunner.list_projection_sources()` atomically enumerates all committed local
  simulation evidence, reconstructs each run, verifies its canonical manifest against the JSONL
  source, and rejects pending or corrupt evidence.
- Each source manifest already contains typed `strategy.signal.generated`,
  `order_intent.proposed`, `risk.decision.evaluated`, `approval.ticket.created`, and optional
  `approval.ticket.decided` records. Executed runs additionally contain the OMS, fake-broker,
  position, protection, alert, and execution-completion evidence projected by PR #52.
- `project_simulation_executions()` currently ignores non-executed sources and replaces only audit,
  orders, positions, and alerts when at least one execution exists. Signals, risk decisions, and
  approval tickets remain representative.
- The signal read model currently accepts only the older representative strategy values and has no
  durable lineage. Risk decisions and approval tickets likewise have no workflow/run attribution.
- The frontend verifies the four execution resources as one fake-broker-derived group. The approval
  inbox renders forms for every pending read-model ticket, which would be unsafe for a durable
  saved-run ticket because the authoritative mutation is workflow/run scoped.

## 5. Proposed design

1. Add a frozen `SimulationDecisionAttributionReadModel` carrying workflow/version/run status,
   signal reference, order-intent ID, risk-decision ID, approval-ticket ID, optional exact approval
   decision/actor/reason/timestamp, event-specific journal references, the complete run manifest,
   and fixed pre-execution provenance.
2. Add optional decision attribution to signal, risk-decision, approval-ticket, and audit records.
   Extend the signal enum to the exact persisted product signal `long_entry_candidate`; do not map
   it to the older demo strategy vocabulary.
3. Refactor the existing projection module into one deterministic lifecycle projection. For every
   source, locate exactly one signal, order-intent, risk-decision, and ticket-created event and zero
   or one decision event as required by run status. Reconstruct them with existing domain
   `from_json_dict` APIs and cross-check all IDs, timestamps, status, source references, and run
   records before emitting anything.
4. Claim signal, intent, risk, ticket, decision, execution, order, fill/position/alert, and journal
   identities globally across the snapshot. Duplicate identities or duplicate audit sequences fail
   the whole projection.
5. If there are no durable sources, return the existing representative model unchanged. If at
   least one durable source exists, replace signals, risk decisions, approval tickets, and audit
   events with durable records. Preserve the PR #52 order/position/alert projection for executed
   sources; use empty non-representative downstream resources when there are no executions.
6. Give every durable resource explicit source metadata. Upstream and lifecycle-wide audit
   resources use non-broker simulation provenance. Downstream records use fake-broker provenance
   only when actual execution evidence is present.
7. Extend frontend validation to enforce complete decision attribution, event/record identity
   agreement, exact lifecycle-dependent optional fields, coherent durable resource provenance, and
   absence of representative data in durable mode.
8. Add workflow/run drill-down controls to signal, risk, ticket, and audit views. Durable pending
   tickets render a read-only route to the saved-run inspector; terminal tickets render exact
   decision facts with no form or action buttons. Representative pending tickets retain their
   existing bounded generic behavior.

## 6. Data model changes

- Add `SimulationDecisionAttributionReadModel` and its JSON API view.
- Add optional `decision_attribution` to `SignalReadModel`, `RiskDecisionReadModel`,
  `ApprovalTicketReadModel`, and `AuditEventReadModel`.
- Permit `long_entry_candidate` as an exact signal value.
- No SQLite schema, append-only journal schema, persisted workflow-run schema, or state transition
  changes.

## 7. API changes

The existing read-only endpoints gain additive durable attribution fields and durable records:

- `GET /api/signals`
- `GET /api/risk-decisions`
- `GET /api/approval-tickets`
- `GET /api/audit-events`

The existing orders, positions, alerts, protection, workflow-run, approval, and execution endpoints
remain behaviorally unchanged. No endpoint is added and no mutation contract is broadened.

## 8. Test plan

- Backend projection tests for pending approval, rejected, approved-not-executed, protected
  execution, and missing-protection execution.
- Exact typed lineage checks for signal, intent, risk, ticket, decision, actor, reason, timestamps,
  and journal references.
- Deterministic multi-workflow ordering, restart recovery, repeated read, and representative-only
  fallback tests.
- Empty downstream resources for non-executed durable runs and mixed-lifecycle snapshots without
  representative records.
- Fail-closed tests for pending evidence, malformed payloads, bad manifest digests, duplicate
  identities/sequences, source mismatches, missing events, contradictory status/decision evidence,
  and generic API errors with no private diagnostics.
- Existing execution projection regression tests for order, position, protection, alert, and audit
  evidence.
- Frontend client tests for exact attribution/provenance validation and rejection of partial,
  contradictory, broker-claimed upstream, or mixed representative/durable snapshots.
- Frontend rendering tests for workflow/run drill-down, pending routing, terminal status and
  decision facts, and absence of terminal approval actions or unsafe broker/live controls.

## 9. Verification commands

```powershell
Push-Location backend
python -m pytest tests/test_simulation_execution_projections.py tests/test_read_api.py -q
Pop-Location

Push-Location frontend
npm test -- --run src/readApiClient.test.ts src/App.test.tsx
npm run lint
npm run typecheck
npm run build
Pop-Location

.\scripts\verify.ps1
```

Run the backend and Vite development server, inspect `http://localhost:5173`, and exercise loaded,
empty, pending, rejected, approved-not-executed, executed, and generic-unavailable states through
the real Vite proxy. Use the in-app browser when available and retain test/runtime evidence for
states that require deterministic fixtures.

## 10. Rollback plan

Revert this candidate commit. The change is read-only and additive, so rollback requires no data
migration, journal rewrite, cleanup, or compensating trading action. Existing schema-v4 evidence
remains intact and can still be inspected through the saved-run inspector.

## 11. Implementation steps

1. Add failing backend tests for all lifecycle states, identity checks, atomic failure, fallback,
   and execution-projection regression.
2. Add the decision-attribution read model and implement typed lifecycle projection.
3. Wire all affected read endpoints through the one projected operations snapshot.
4. Add failing frontend client and rendering tests for provenance, drill-down, and actionability.
5. Implement frontend types, validation, durable lifecycle views, and inspector selection.
6. Run focused checks, fix failures, and run full verification.
7. Perform localhost browser/runtime checks and a P0/P1 safety review.
8. Update this ExecPlan, `docs/SLICES.md`, and `docs/PRODUCT_GAP_ANALYSIS.md` with exact evidence.
9. Commit, push, open a PR against `main`, and verify CI on the exact remote head without merging.

## 12. Completion criteria

- All four committed run lifecycle states project exact upstream evidence.
- Every required identity, decision fact, timestamp, and journal reference is preserved and
  cross-validated.
- Durable mode contains no representative records; unreached stages are empty and explicitly
  attributed.
- No durable evidence retains a generic approval action that bypasses the workflow/run-scoped
  approval path; all terminal evidence is visibly non-actionable.
- Corruption and contradiction fail the affected operations APIs closed with generic errors and no
  partial payloads.
- PR #52 execution projections remain correct for protected and missing-protection outcomes.
- Focused tests, complete `verify.ps1`, frontend build, localhost inspection, and P0/P1 review pass.
- The branch is pushed and an unmerged PR has green CI on its exact remote head.
- No broker transport, secret/private field, production rollout, live-order path, or live-trading
  capability is added.

## 13. Risks and assumptions

- The durable run-start path currently creates exactly one product signal, order intent, passed
  risk decision, and approval ticket. The projector will reject any different multiplicity rather
  than silently choose one.
- The canonical signal has no independent domain `signal_id`; its exact persisted
  `source_signal_reference` is the only durable unique identity and is already bound into the
  order-intent record. The projector will expose that value unchanged as `signal_id`.
- A resource can be durably empty because its lifecycle stage was not reached. Frontend validation
  must distinguish that safe state from a partial execution projection.
- Lifecycle-wide audit evidence includes both pre-execution and fake-broker events. Event-level
  attribution remains exact; resource-level audit provenance must not overstate every event as
  fake-broker-derived.
- A stale or corrupt record in any enumerated committed source intentionally quarantines the whole
  projected operations snapshot. This favors operator safety and provenance coherence over partial
  availability.

Implementation evidence:

- Focused checks pass with 46 backend and 32 frontend tests. Ruff formatting/lint, TypeScript type
  checking, and frontend lint pass.
- Complete Windows verification passes with 676 backend and 158 frontend tests plus the dedicated
  resilience rerun. A fresh-clone CRLF checkout initially changed two unchanged Candidate 062
  review inputs at the byte level; preserving their canonical LF bytes restored the deterministic
  packet checks without changing repository content.
- The real Vite proxy returned `waiting_for_approval`, `rejected`, `approved_not_executed`, and
  `executed` runs, four durable signal/risk/ticket chains, one downstream execution, and 102 audit
  rows. Upstream and downstream provenance remained correctly distinct.
- Corrupting one local manifest digest made all seven lifecycle endpoints return the same generic
  HTTP 503 while `/api/safety` remained available. Reads performed no repair or rewrite.
- Browser setup and the required discovery retry reported no available browser instance. Static
  rendered-component tests cover loaded, empty, pending, terminal, executed, fallback, drill-down,
  and forbidden-control states; this plan makes no visual-browser or screenshot claim.
- P0/P1 review found and fixed two issues before completion: manifest audit coverage is now exact in
  the client, and representative terminal tickets are visible but non-actionable. No remaining
  P0/P1 finding is known.
- Unmerged PR [#53](https://github.com/d0ofus/trading-oms/pull/53) is open against `main`. GitHub CI
  passed on implementation head `3f2a3f6b8b46fcd5daeb6ded4b94e2eedccd1a1c`; the documentation-only
  closeout commit is rechecked separately so delivery evidence is bound to the final remote head.
