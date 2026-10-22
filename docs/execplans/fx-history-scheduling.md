# ExecPlan: Restore FX candles and isolate historical-data jobs

## 1. Goal

Restore timestamped AUD.USD streams and source-matched candles when unrelated paused,
flat stock runs remain saved. Keep the existing panels and paper authorization workflow.
Status: complete. Full verification, isolated browser regression and data-only observation passed.

## 2. Non-goals

No changes to signals, strategy schemas, financial limits, IBKR settings, routes or
order methods. No live trading, automatic arming, incident erasure or historical entries.

## 3. Safety constraints

Preserve paper guards, freshness, ownership, reconciliation, protection and explicit
authorization. Unexpected data-job startup exceptions remain engine restrictions with
sanitized diagnostics. Continue independent data work without declaring failed jobs
healthy. Preserve current incident recovery evidence and manual engine-fault review.

## 4. Current state

The saved workspace has inactive HIVE/META subscriptions and paused pre-market runs.
Premarket maintenance queues their history regardless of current dependency. The broker
rejects unresolved contracts, aborting maintenance before FX work. Repeated exceptions
invalidate reconciliation and produce a reconnect/incident loop. An isolated reproduction
confirmed two consecutive failures with zero FX-maintenance calls and zero orders.
The existing 20 FX-data/pre-market tests passed but miss this combined arrangement.
FX display also treats initial queues as retries, renders null prices and question marks.

Data-only acceptance exposed a second request-lifecycle defect with the pinned SDK
10.50.2 and Gateway server 226: protobuf account-summary cancellation was issued but
the third snapshot hit broker code 322 (account-summary subscription limit), followed
by a reconciliation timeout. Three observations reproduced it. An isolated comparison
using only the SDK's legacy account-summary cancellation completed repeated snapshots
without that error. The implementation therefore selects the SDK's legacy encoding
only for CANCEL_ACCOUNT_SUMMARY on server 226; order messages and other versions retain
normal SDK negotiation. Regression tests cover both affected and unaffected versions.

## 5. Proposed design

Use shared dependency and request-scheduling helpers for regular, extended and FX
history. Dependencies include active subscriptions/current preparation, authorized or
suspended runs, owned positions, unresolved orders, reservations and outstanding exits
or protection. A paused flat unsubscribed run is not a download dependency.

Retire unused request work while retaining completed bars and durable history. Required
contracts wait for current-generation resolution through a paced coordinator. Share
history concurrency and pacing across all three families and prioritize protection.
Contain startup exceptions to their job, record a failed state once, and continue other
jobs; unclassified faults also raise a sanitized engine restriction. Old callbacks cannot
activate current contract or request readiness. Unsubscribe/startup/reconnect/archive use
the same dependency rules.

Expose queued, resolving, pacing, requested, receiving, complete and failed request
states, a waiting reason and a future eligible time. Initial queues are not retries.
Missing prices render Unavailable; FX signal labels follow Midpoint/Bid/Ask. Watchlist
quotes remain distinct from timestamped signals; green readiness still needs fresh
required streams, history and session health. No new pages or controls.

## 6. Data model changes

No persistent schema migration. Add bounded in-memory dependency/request readiness
state and additive response fields. Retain published hashes, orders, approvals and events.

## 7. API changes

Extend existing market-data projections with request state, waiting reason and next
eligible request time. Existing status fields and retry endpoints remain compatible.

## 8. Test plan

Add a failing mixed FX/paused-stock maintenance regression before implementation.
Cover unresolved required contracts, reconnect generations, failed job isolation,
position/protection dependencies, shared pacing, cleanup, source-specific candles,
missing-price/status rendering and bounded polling. Keep entry freshness and absence
of historical/reconnect signals. Add an isolated browser walkthrough with synthetic
saved stock runs and progressing FX callbacks; no broker order capability.

Final review added Midpoint/Bid/Ask badge regressions: Bid/Ask signal status now follows
the real timestamped bid/ask request instead of assuming it is healthy. The new test
failed for Bid and Ask before the correction and all three variants now pass.

## 9. Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_workspace_data_scheduling.py backend/tests/test_workspace_fx_data.py backend/tests/test_workspace_premarket_execution.py -q
. .\.tmp\activate-dev.ps1
.\scripts\verify.ps1
```

Then observe AUD.USD data without arming/orders. Record availability and limitations;
do not change broker settings, silently release incidents or bypass a current hold.

Data-only acceptance on 24 September 2026 used a separate client, temporary store and
order-disabled adapter against the existing paper Gateway. The final 90-second
observation received 408 MIDPOINT history bars, timestamped bid/ask and midpoint,
and both historical and live candle rows (120 rows in the bounded viewer page).
It reached FX-ready state after same-contract request pacing, completed seven
successful reconciliation snapshots, stayed connected, and created zero orders.
There was no engine fault or code 322. A later broker 2105 history-service warning
was retained; quiet observations could still fail the unchanged freshness check.
This validates data scheduling and reconciliation, not broker order qualification.
The user's running application, incidents and authorizations were not restarted,
released or modified; it must be restarted to load the corrected implementation.

Evidence: `.tmp/fx-data-observation-final.log` (sanitized health/request states only),
the mixed-run browser fixture, and the regression suite. No persistent migration
was needed, so no production state rewrite or backup restoration was performed.

Final gate: `.\scripts\verify.ps1` exited 0 with `verify: ok`: 1,323 backend tests,
190 frontend tests and 24 browser tests passed. Formatting, lint, compilation,
type checking, production build, secret scan and dependency audits passed.
The gate reported existing deprecation/build-size warnings and no known dependency
vulnerabilities. Full output is in `.tmp/fx-scheduling-accepted-verify.log` and
`.tmp/fx-scheduling-accepted-warnings.log`. The new mixed-stock/FX browser screenshot
was visually reviewed; request labels and historical/live candle rows are present.

Load the fix by stopping the old workspace process, running
`.\scripts\start-workspace.ps1`, and refreshing the browser. No IBKR setting change
is needed for this defect. Existing dedicated engine restrictions still require
their normal current-health/reconciliation/stability evidence and explicit review.

## 10. Rollback plan

Disable new FX arming using the existing host switch if needed. Keep reconciliation
and position protection running. Do not restore database backups over broker exposure.

## 11. Implementation steps

1. [x] Record approved scope and investigation evidence.
2. [x] Add regression and shared dependency/request scheduling.
3. [x] Add current-generation broker readiness and job failure containment.
4. [x] Correct market-data response/UI states and add browser coverage.
5. [x] Verify, self-review, document results and perform data-only observation.

## 12. Completion criteria

Inactive stock history cannot starve FX. Required unresolved work waits explicitly,
shared budgets hold, independent jobs progress after failures, and candles/statuses
reflect actual observations. Full verification and isolated browser tests pass; real
data observation is reported without implying broker execution qualification.

## 13. Risks and assumptions

Watchlist bid/ask delivery does not prove tick-by-tick/history entitlement. Requests
may reveal a genuine broker failure after the scheduler is repaired; report it rather
than substituting sampled data. The current dedicated engine incident remains subject
to its normal recovery checks. No data migration or operator budget change is required.

Self-review covered adapter generation fences, shared pacing/capacity, dependency
retention for exposure/protection, bounded caches, failure journaling, and UI polling
cleanup. Entry comparisons, historical-signal exclusion, paper-only guards, risk
reservations and authorization consumption are unchanged. No unresolved P0/P1 issue
was identified in this slice. Real order/protection qualification remains separate.
