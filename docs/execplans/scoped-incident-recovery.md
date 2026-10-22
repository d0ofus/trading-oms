# ExecPlan: Activity performance and scoped incident recovery

## 1. Goal

Gate new entries on applicable current restrictions, preserve all incident evidence,
and let the operator acknowledge verified routine recovery during arming. Keep
Activity reads and rendering bounded as the incident ledger grows.

## 2. Non-goals

No live execution, automatic arming, broker trials, production incident clearance,
infrastructure deployment, or retrospective reconstruction of missing exceptions.

## 3. Safety constraints

Unknown scope/state blocks new risk. Recovery never bypasses market freshness,
paper context, reconciliation, protection, risk, emergency stop or human approval.
Release and authorization are atomic, idempotent and checked against episode
revisions/current engine ownership. Independent watchdog alerts remain fenced.
Protection and risk-reducing operations remain available under their own checks.
No account identifiers, credentials, raw exception values or local variables enter
diagnostics. Existing journal records, strategy hashes and approvals are immutable.

## 4. Current state

Engine readiness treats every unresolved legacy incident as a global blocker.
Incidents have code identities rather than episode identities; exception causes are
discarded. Arming already uses a serialized engine command and a SQLite transaction.
Activity has bounded audit pages but rerenders with the root clock, and does not
distinguish recovered restrictions from active failures or historical investigations.

## 5. Proposed design

Add indexed SQLite incident episodes with separate condition, restriction and
investigation states. Policy determines trusted scopes; unknown failures are global.
Journal transitions and mirror legacy code documents for compatibility. Migrate
legacy incidents conservatively after a SQLite backup. Recovery uses current-owner
watchdog health, complete post-failure reconciliation and a monotonic 30-second
healthy interval. Operator rationale is required for dedicated recovery reviews.
Routine watchdog/connectivity recoveries can be explicitly acknowledged in arming;
revalidate episode revisions, ownership and evidence in the authorization transaction.
Keep emergency stop separate. Final entry dispatch also checks applicable holds.

Activity separates current holds and paged history, with lazy incident details.
Move the footer clock into its own component, memoize audit rendering and expose
build identities with a manual reload notice. Fault diagnostics are bounded/redacted.

## 6. Data model changes

Incident episode projection, partial unique open-episode index, scope/restriction
indexes, migration metadata and backup. Episode payloads include timestamps,
revisions, recurrence, policy, source instance, evidence, release actor and rationale.
Reconciliation evidence includes start/completion identity and engine/connection
generation. New authorization records pin reviewed recovery revisions and actor.

## 7. API changes

Paged incident list/detail endpoints; enriched overview and health/build status.
Arming preview adds recoveries and conditional eligibility; arm accepts explicit
episode/revision acknowledgments and review engine identity. Dedicated review accepts
rationale/revision. Missing acknowledgment never grants permission. Legacy code
reviews require an unambiguous current episode.

## 8. Test plan

Regression tests first for scope, migration, recurrence, recovery evidence, dedicated
reviews, atomic acknowledgment/arming, stale previews and dispatch gates. Verify
watchdog races and that exits still work. Browser coverage for recovery checkboxes,
separate history, rationale, build mismatch and bounded audit navigation. Extend
large-history fixtures and memory/CPU probes; run 30-minute isolated streaming soak.

## 9. Verification commands

`./scripts/verify.ps1`

`node scripts/activity_memory_probe.cjs 1800`

`python scripts/workspace_load_probe.py`

## 10. Rollback plan

Stop the application and watchdog before changing versions. Preserve the new journal
and state; do not delete restrictions. Use the pre-migration backup only in a separate
recovery directory, reconcile broker reality and obtain fresh authorization. Never
restore an old authorization or overwrite new broker evidence with a stale backup.

## 11. Implementation steps

1. Add failing lifecycle/recovery tests and implement incident projections/migration.
2. Integrate scoped gates, recovery evaluation, watchdog writer and redacted faults.
3. Add atomic recovery/arming and authenticated API projections.
4. Implement Activity/review UI, clock isolation and build identity.
5. Run focused checks, full verification, browser/load probes and self-review.
6. Document operation, migration, results and unavailable external checks.

## 12. Completion criteria

Requested regression and verification checks pass, memory stays bounded, history is
preserved, no live path or automatic authorization is introduced, and any unavailable
real-browser/operator checks are explicitly reported.

## 13. Risks and assumptions

Single-operator paper application. The active user workspace is not modified or
restarted by implementation/testing. Authenticated actor IDs are opaque session audit
identities, not login tokens. Legacy missing evidence stays unknown until current
recovery is proven; old generic exceptions remain unexplained investigations.

## Implementation record

- Added regression tests before the incident implementation. Initial lifecycle
  tests failed because the new module did not exist. The final focused recovery,
  authenticated API and watchdog suite passed 38 tests.
- Added `incidents.py` for policy-scoped episodes, indexed projections, constant-size
  counts, conservative backed-up migration, audited recurrence/release/investigation
  transitions and bounded diagnostics. Added `incident_recovery.py` for current-owner
  evidence, post-failure reconciliation and a monotonic stability window.
- Integrated the independent watchdog writer, scoped readiness, transactional
  release/authorization, idempotent acknowledgments, opaque authenticated actors and
  the final dispatch gate. Invalid never-submitted intents release their reservation;
  a stale quote alone does not revoke otherwise-valid quiet-market authorization.
- Added incident pages/details, explicit dedicated review rationale, separate
  investigation closure and recovery checkboxes in arming. Legacy code-based review
  rejects ambiguity. Added build identity/reload notice, isolated footer clock and
  memoized audit rendering with stable table definitions. Existing bounded audit,
  candle and order/run interfaces remain in use.
- Preserved current-user state. No running user workspace was restarted or migrated,
  no real incident was released, and no broker order was submitted/cancelled by this
  implementation work. All recovery mutations in tests used isolated state.

## Verification evidence

- `python -m pytest backend/tests/test_workspace_incidents.py
  backend/tests/test_workspace_incident_api.py backend/tests/test_workspace_health.py
  -q`: 38 passed, one existing Starlette/httpx deprecation warning.
- `python scripts/workspace_load_probe.py`: passed with one million journal events,
  100,000 released incident projections, 50 subscribed contract fixtures, 1,000 saved
  strategies/runs and five active runs. 883 combined audit/incident read cycles,
  78 ms p95, 1,406 ms maximum overview latency, 1,422 ms maximum engine-loop age,
  84,188-byte compact overview. No callback overflow, watchdog fault, engine fault
  or orders. This uses an adapter without submission/cancellation capabilities.
- `node scripts/activity_memory_probe.cjs 0` against the final frontend build:
  5,000 synthetic events and five Activity navigations passed; 5.06 MiB retained
  JavaScript heap, 22 mounted rows, 686 DOM nodes. Browser-process private allocation
  was approximately 105 MiB and summed working sets 438 MiB. Working sets include
  mapped/shared pages and are distinct from retained JavaScript heap.
- `./scripts/verify.ps1`: passed (1,006 backend tests, 190 frontend tests, eight
  browser workflows, formatting/lint/type checks, secret scan, dependency audits
  and paper verification). Non-blocking warnings remain for Starlette/httpx,
  frontend bundle size and dependency-audit hashing guidance.
- Final reconciliation-journal evidence links were additionally verified with
  `pytest backend/tests/test_workspace_incidents.py backend/tests/test_workspace_readiness.py
  backend/tests/test_workspace_health.py backend/tests/test_workspace_unified.py -q`:
  67 passed. Final backend formatting and lint checks passed. `git diff --check`
  passed (Git reported existing LF/CRLF conversion notices).
- Browser screenshots of the new incident list and recovery review were visually
  inspected; accessibility and explicit unselected consent checks passed. The
  30-minute stream also passed: 357,400 synthetic events, 6.00 MiB final retained
  heap, 22 mounted table rows (20 audit and two incident rows), 686 DOM nodes.
  Final summed process working sets were 252.17 MiB and private allocations
  113.91 MiB. Steady streaming used approximately 3% of one CPU core. The last
  half of the run stayed around 5.8–6.0 MiB retained heap. The soak preceded the
  final stable-column and detail-display refinements; the final-build 5,000-event/
  navigation repeat above passed after those refinements.

## Self-review and limits

Reviewed trading safety first: active/unknown restrictions cannot be acknowledged
away, new runs inherit holds, watchdog ownership is fenced, restoration does not
arm runs or clear emergency stop, and protection/owned exits keep their existing
controls. Final dispatch rechecks health, scoped restrictions, current readiness,
authorization and market freshness. Confirmed release and authorization share one
transaction and record evidence rechecked at confirmation.

Review found and corrected duplicated outage notifications, repeated full-history
incident counts, an unnecessary history sort in compatibility projection updates,
and cancellation queue writes for inactive saved runs. Restriction activation now
updates armed runs or runs with pending entries. Historical journal/strategy records
are never rewritten. The existing whole-session qualification review remains
conservative and separate from per-run execution readiness.

The original generic engine fault has no recoverable exception details. New diagnostics
do not reconstruct that history. Tests establish operational recovery behavior,
not a known fix for its missing root cause. The user browser/profile was unavailable
for direct profiling; isolated Chromium measurements do not prove its total RAM/lag
is fixed. No operator-armed BTC paper observation/recovery trial was performed.
Live trading remains disabled; this is neither broker qualification nor institutional
certification. Saved-run scans/shutdown and actual broker pacing remain capacity
constraints despite bounded history reads.
