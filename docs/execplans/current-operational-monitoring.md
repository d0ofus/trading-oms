# ExecPlan: Current operational monitoring

## 1. Goal

Implement the approved monitoring rebuild: complete single-account reconciliation without disrupting healthy data, permit unused subscriptions to be removed, and show only current, relevant trading concerns. Preparation and one final paper authorization remain the normal workflow.

## 2. Non-goals

No real-money execution, strategy republication, resizing, rerouting, implicit liquidation, emergency-stop release or automatic arming. Existing funding and protection contracts remain unchanged.

## 3. Safety constraints

Paper/simulation only; no secrets in artifacts. Require complete broker evidence for new risk, fresh signal and execution observations at dispatch, known ownership, legal quantity, buying power and a protection plan. Preserve durable order identity, duplicate prevention, audit records and explicit authorization. Historical absence alone never proves an uncertain order safe.

## 4. Current state

The approved audit reproduced a missing multi-position completion marker, timeout-driven reconnects, unconditional reconciliation requirements for unsubscribe, empty exit records retaining dependencies, optional FX history gating live signals, excessive incident severity and a notification variable-shadowing bug. The working tree contains earlier approved changes and must be preserved. Audit baseline: 87 focused tests; these do not cover the new behavior.

## 5. Proposed design

Use a continuous single-account position subscription with an explicit initial completion marker and connection fencing. Serialize uncorrelated snapshots and retry missing correlated components without resetting transport. Share current component dependencies across scheduling, removal and monitoring. Keep historical incident episodes as audit records; derive current attention and blocking from required evidence, classify severity/scope, and automatically resolve conclusively recovered concerns without a universal stability timer. Keep emergency stop explicit. Treat downloaded FX breakout candles as optional display input. Reuse existing Activity and review layouts with scoped, structured current conditions and neutral progress.

## 6. Data model changes

Additive metadata in existing incident/document payloads for classification, recovery reason, dependencies and evidence. Bounded preparation leases and connection-local snapshot state. Back up persisted state before any additive migration; preserve original journals, strategies, approvals and bindings.

## 7. API changes

Extend existing incident/readiness responses with current relevance, category, scope, stages and remediation. Return structured unsubscribe conflicts while retaining successful response shape. Add preparation lease release to the existing preparation interface. Preserve legacy recovery endpoints for older clients.

## 8. Test plan

Regress empty/populated/missing/late position completions, ID collisions, no timeout reconnect, paused/empty-operation dependencies, unsubscribe while unrelated reconciliation is pending, true exposure locks, prior-session retirement, unknown order/protection hazards, automatic evidence-based recovery, optional FX history versus required strategy history, notification deduplication and UI polling/navigation/canvas behavior. Use isolated broker fixtures, then a data-only broker observation if available.

## 9. Verification commands

Run focused pytest suites after each slice; frontend lint/typecheck/unit and isolated Playwright regressions. Run `.\scripts\verify.ps1` from the activated repository environment. Record results below. Broker-connected acceptance requires at least five minutes of stable data/reconciliation and unused unsubscribe/restore; actual trading requires separate operator emergency release and final authorization.

## 10. Rollback plan

Disable new entries before reverting. Retain reconciliation, owned-position protection, requested exits and audit history. Do not restore an old database over new orders or executions. No destructive migration is planned.

## 11. Implementation steps

1. Add failing regression fixtures.
2. Correct position acquisition and account timeout handling.
3. Unify current dependencies, preparation leases and unsubscribe diagnostics.
4. Implement current-condition classification and evidence-based automatic recovery.
5. Remove optional breakout-history gates and integrate existing UI.
6. Run full verification, isolated browser acceptance, data-only observation and safety review.

Progress (2026-09-24): steps 1–5 implemented. Regression-first checks reproduce the timeout-driven disconnect, unused/terminal dependency locks, optional-history suspension, hidden current-attention rows and a broker-observed FX resubscription defect. Single-account snapshots, shared dependencies, renewable preparation leases, current-condition projection, automatic evidence-based resolution and existing-panel UI integration are in place.

Verification history: the initial broad backend run exposed 13 failures (outdated workflow expectations and actual recurrence/dependency defects). Those were corrected; the subsequent focused 68-test group passed. Eight isolated browser regressions passed after rebuilding the frontend, covering automatic current-attention recovery, retained legacy endpoints, polling cleanup, precise unsubscribe conflicts and mixed stock/FX requests.

Data-only adapter acceptance completed 375 seconds with 19 complete account snapshots, 3,535 bid/ask observations, 3,528 midpoint observations, 851 historical bars, successful subscription removal/restoration and no disconnect or order. An additional 331-second actual-engine observation completed 22 reconciliations with no incident or reconnect, but correctly failed feed acceptance: restoring a retired FX subscription did not requeue its streams. A failing regression was added, the stream restart was corrected, completed display history was preserved, and the corrected full-engine observation is recorded below. This evidence is not an execution trial.

The corrected full-engine observation completed 377 seconds with the data-only adapter and an independent watchdog: one handshake, 25 completed reconciliations, two safely superseded snapshots, zero actionable incidents, zero orders and successful unsubscribe/restore. All 147 samples after restored stream startup were healthy and execution-fresh; downloaded history remained present. The two-second observations recorded signed source/receipt ages. The final sample's source age was 1.63 seconds and receipt age 1.05 seconds. No production database, authorization, emergency stop or broker settings were modified. The broker's ordinary service-success messages remained diagnostics.

Safety review corrected positive never-submitted proof handling, recurrence after an intervening working/recovery observation, bounded duplicate diagnostics, stale account callback fencing, and terminal-operation handling. A remaining obsolete test expectation for delaying unused-feed retirement was updated to assert immediate retirement with current completed evidence while holding genuine service/order uncertainty.

Final verification (2026-09-24): `.\scripts\verify.ps1` completed successfully with 1,440 backend tests, 190 frontend tests and 26 isolated browser tests. Formatting, lint, type checks, compilation, production build, secret scanning and dependency audits passed; both dependency audits reported no known vulnerabilities. The new current-condition regression module contains 22 tests. The final build verification fingerprint returned `True`. The gate log is `.tmp/current-monitoring-final-verify.log` (ignored local artifact). The logging wrapper encountered a Windows console encoding error while echoing the completed log; the underlying verification command exited 0 and its log ends in `verify: ok`.

Implementation, automated acceptance and data-only broker acceptance are complete. Browser checks cover Activity recovery, subscription removal, preparation, policy adoption, polling cleanup, navigation and the existing strategy canvas. The separately operator-armed natural-breakout execution trial remains unperformed: no order was transmitted, emergency stop was not released, and no production authorization or saved workspace record was changed. Restart the workspace on the verified build before operational review; a strategy copy or republication is unnecessary.

## 12. Completion criteria

Healthy startup has zero actionable historical incidents. Incomplete account evidence blocks new entries without disconnecting healthy feeds. Unused subscriptions remove successfully; actual dependencies have precise reasons. Automatic recovery does not restore revoked authorization or replay triggers. Optional FX history does not gate a live-only breakout. Full verification and browser checks pass, with any unavailable broker/armed trial explicitly recorded as incomplete.

## 13. Risks and assumptions

Uncorrelated IBKR callbacks require strict serialization and connection identity. Unknown execution impact must remain blocking. Real currency balances cannot be inferred from the virtual FX portfolio. The production workspace will not be mutated or armed by automated development tests. A natural paper execution trial cannot be marked passed without operator authorization and a qualifying signal.
