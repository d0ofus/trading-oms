# ExecPlan: Automatic recovery, stable FX readiness and broker credit

## 1. Goal

Implement the approved 24 September 2026 plan: retire unused feed restrictions,
automatically recover narrowly classified corrected data-request faults, authorize
healthy quiet FX runs without permitting stale-data execution, and share broker-aware
cash/margin funding across supported stock strategies and the existing FX strategy.
Keep one final authorization and the current navigation, layout and canvas.

## 2. Non-goals

Live trading, new asset families/templates, account setting changes, automatic currency
conversion/rerouting/resizing, removing ownership/protection checks, or placing a trade
as part of implementation. Existing published hashes and run policies remain intact.

## 3. Safety constraints

Paper adapter guards apply to every executable and What-If request. What-If requests
are isolated, immutable nonexecution requests. Entries need explicit authorization,
fresh source/receipt observations, legal quantity, current reconciled credit evidence,
serialized reservations and a protection plan. No secrets/raw broker warnings in logs.
No restart resumption, signal replay, overlapping exits or outage-driven liquidation.

## 4. Current state

Retirement differs from data scheduling: it retains paused flat unarchived runs and
all CASH pair positions. FX readiness duplicates stale quotes under funding, and the
review moves changing rows between visible and collapsed groups. Existing execution
policies require native settled cash; What-If exists only for short OCA credit checks.
The audit baseline is 70 passing focused tests, not acceptance of this change.

## 5. Proposed design

Share component dependencies across scheduling/recovery. Retire unused components on
current complete no-exposure proof without a feed-health countdown. Genuine recovery
keeps 30 healthy seconds. Only complete episodes matching the known fixed request
fault fingerprints qualify for automatic engine recovery; ambiguous episodes do not.

Pin successor funding and quiet-authorization policies in new execution bindings.
Separate can_authorize from can_dispatch; healthy accepted FX streams/history can
wait while quiet, but entries require fresh quotes and a new complete live minute.
Stable review rows show waiting/checking instead of Resolve. Add bounded transition
diagnostics. Existing bindings keep their prior funding/arming contract.

Use cash when sufficient and automatic broker What-If credit evidence when borrowing
is required. One account queue, at most one preview per minute, coalesced by exact
order terms/account revision; UI reads never send previews. Exact credit evidence
must be current at dispatch, concurrent reservations deducted without double counting
broker-reflected orders. Preview delay cannot extend an expired signal. Expected
approved currency debits are reconciled through the real currency ledger.

## 6. Data model changes

Additive execution-plan funding/authorization policy fields, structured readiness,
credit request/evidence/reservation records and recovery classification metadata.
Use the existing document store and append-only journal. Back up before first policy
write; no rewrite of existing bindings, approvals, episodes or strategy versions.

## 7. API changes

Extend compatibility/preparation/review with funding mode, credit evidence/status,
can_authorize/can_dispatch and waiting dependencies. Extend incident summaries with
current relevance and automatic classification. Preserve existing response fields.
Rollback flags disable new broker-credit arming and classified-fault autorecovery.

## 8. Test plan

Regression-first tests for saved paused META/USD.JPY restrictions, virtual versus real
FX ownership, component dependencies, retirement/recovery races, unknown faults,
quiet authorization and freshness transitions. Funding tests cover cash, cross-currency
margin, insufficient/unknown credit, exact identities, pacing, stale callbacks,
concurrent reservations, partial fills/debits/restart and nonexecuting What-If.
Browser fixtures cover stable rows and unchanged controls. Retain legacy and paper
guard suites. Data-only broker observation must not authorize or submit an order.

## 9. Verification commands

Focused pytest/frontend tests after each slice, then `./scripts/verify.ps1` including
isolated browser regressions. Record commands and results below as work progresses.

## 10. Rollback plan

Disable new credit-policy arming and classified-engine autorecovery independently.
Continue reconciliation, existing protection and requested exits. Never restore state
over a running engine or unreconciled broker exposure.

## 11. Implementation steps

1. Add failing dependency/recovery and quiet-readiness regressions.
2. Implement shared dependency retirement and narrow fault recovery.
3. Add credit adapter/service/reservations with regression tests and policy backup.
4. Integrate stock/FX funding and stage-aware readiness, preserving old policies.
5. Stabilize UI, add browser coverage, update operator documentation.
6. Full verification, safety self-review and data-only observation when available.

## 12. Completion criteria

Approved behavior implemented; full gate passes; old hashes/policies and paper guards
preserved; no trade forced. Record any unavailable external qualification explicitly.
Margin execution qualification remains a separately operator-armed natural signal.

## 13. Risks and assumptions

Broker margin previews are estimates, not acceptance guarantees. Missing essential
credit evidence blocks execution. Virtual FX positions cannot establish real ownership.
Sparse quotes can remain stale despite a healthy subscription; never fabricate data.
Pre-existing workspace changes are retained. No production state is altered by tests.

## Progress

- Plan created before implementation. Repository guidance and current paths reviewed.
- Dependency regressions failed before the change, then passed for paused runs,
  virtual versus real ownership, post-failure reconciliation and narrow fault recovery.
- Implemented shared account credit, nonexecuting adapter requests, additive bindings,
  transactional reservations, approved-debit reconciliation and stable FX review rows.
- Broad intermediate backend run passed 1,349 tests; focused funding tests cover all
  four stock templates with synthetic qualified HKD and AUD/ASX contracts and USD credit.
- Browser FX publication/preparation/review regression passed, including stable DOM rows
  across fresh/quiet transitions, no extra checkbox and polling cleanup.
- Safety review found and fixed credit queue starvation and incorrect minute highs while
  a triggered entry waits for credit. Added regressions before those corrections.
- Design detail: single-entry evidence lives 30s; two exact OCA branch estimates may
  live 180s to allow sequential 60s-paced previews. Account revision and economic terms
  must match. GTD absolute timestamps are validated afresh by the existing signal/session
  guard and are excluded from credit reuse identity; TIF and order prices remain pinned.
- Data-only 90-second observation received 557 MIDPOINT historical bars, both timestamped
  streams and completed reconciliations, without incidents or orders. Ordinary freshness
  waiting still occurred between quotes; this does not revoke healthy quiet authorization.
- Implementation and final safety review are complete.
- The first full gate passed 1,357 backend and 190 frontend tests, then PowerShell log
  redirection treated Vite's non-failing chunk-size warning as a terminating native error.
  Rerunning the unchanged gate with OS-level log capture. Final review also removed an
  unnecessary margin-field requirement for fully settled-cash purchases; regressions
  cover missing fields and broker unset values while preserving margin-entry blocking.
- Final safety review checked exact credit terms at the paper adapter boundary,
  stale-generation fencing, transactional capacity, authorization acknowledgments,
  protection/exit independence, fault classification and audit-data redaction. No
  remaining P0/P1 finding was identified. The data observation had seven successful
  reconciliations, zero failed reconciliations, 120 candles in the bounded viewer page,
  and zero orders. No executable margin trial was performed.
- Final `./scripts/verify.ps1` completed with exit 0 and `verify: ok`: 1,360 backend
  tests, 190 frontend tests and all 24 isolated browser tests passed. Formatting,
  linting, compilation, TypeScript, production build and secret scanning passed;
  Python and npm dependency audits reported no known vulnerabilities. The exact
  source/build verification stamp was written by the gate. Non-failing third-party
  deprecation, Vite chunk-size and audit-tool guidance warnings remain.
- Operator acceptance: data-only AUD.USD observation completed; actual margin-funded
  execution remains separately operator-armed on a natural paper signal. Deployment
  requires the normal workspace restart and preparation of a new run to adopt the
  new binding policies. No production run was armed, no broker setting was changed,
  and no production incident was manually released during implementation.
