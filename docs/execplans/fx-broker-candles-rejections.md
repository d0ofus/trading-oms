# ExecPlan: Independent FX broker candles and explicit quantity rejection

## 1. Goal

Implement the approved independent IBKR one-minute candle reference and fresh live-tick breakout policy. Correct code 10318 handling, reconcile the earlier misclassified rejection safely, and prepare an unarmed 1,000 AUD successor for operator review.

## 2. Non-goals

No live execution, automatic arming, emergency-stop release, forced trade, historical signal replay, route/protection changes, automatic resizing or mutation of published strategy hashes or existing bindings.

## 3. Safety constraints

Paper adapter enforcement, one final authorization, 15-second source/receipt freshness at dispatch, exact legal quantity, current buying-power evidence, durable intent/reservation, duplicate prevention and actual-fill protection remain. A rejection of an amendment cannot terminate a previously accepted order. Contradictory fills/acceptance remain unresolved and protected.

## 4. Current state

The 9:28 source timestamps jumped from :28 to :45; the legacy FX tick aggregator marked the minute partial and reset runtime. A 0.700875 tick then lacked the preceding 0.700865 reference. At 9:33:06 the already-authorized engine detected another signal and transmitted 0.01 AUD; broker 10318 was misclassified as uncertainty, followed by cancel/not-found 10147. The audit found no executions and passed 83 existing focused tests. This is baseline evidence only.

## 5. Proposed design

Pin idealpro_broker_candles_v2 for new FX bindings with paper_buying_power_v1. Share keepUpToDate one-minute MIDPOINT/BID/ASK requests with a 30-minute bootstrap. Keep request generations and shared pacing; bootstrap completion frees the finite download slot without retiring the stream. Reference exactly the completed minute preceding each live tick, including the latest completed minute at authorization. Candle callbacks can reevaluate only fresh, post-authorization live evidence. Quiet ticks do not erase broker bars. True stream/generation/session faults discard pending evidence. Preserve legacy evaluation for old bindings.

Classify exact initial-submission 10318 responses as fractional-quantity rejection; retain actual code and sanitized diagnostics. Append a conclusive correction for the saved uncertainty only after matching dispatch/rejection and current reconciliation without conflicting execution evidence. Preserve history and pause the used run. Prepare a separate 1,000 AUD run only after verification and safe current evidence; leave final authorization to the operator.

## 6. Data model changes

Add execution-policy metadata and broker quantity-restriction evidence in existing document storage; use existing backups before additive durable records. Add bounded current-generation candle stream caches, immutable signal reference revisions and appended rejection-repair audit events. No rewrite of journals, approvals, bindings or strategy versions.

## 7. API changes

Extend existing policy replacement targeting with FX execution revision and authorization terms. Extend existing market-data, candle, readiness and run results with candle stream state, reference minute/high/revision, live observation and precise waiting/rejection reason. Existing pages and polling remain.

## 8. Test plan

Regression-first cases for 0.700865 to 0.700875 across 17 quiet seconds, exact one 1,000 AUD simulated submission, immediate previous broker minute after authorization, equality, delayed candle/tick ordering, missing/stale/partial bars, corrections, duplicate callbacks and generation fences. Cover 10318, 10147, initial versus amendment rejection, restart correction, late fills, reservation release and unchanged legacy policy/hash/protection. Browser tests cover source labels, quantity, current policy adoption, final terms and existing canvas workflow.

## 9. Verification commands

Use focused pytest and frontend checks per slice. Run .\scripts\verify.ps1 directly (not PowerShell all-stream redirection), then isolated browser walkthroughs and data-only connected observation. Natural-breakout paper execution requires separate final operator authorization.

## 10. Rollback plan

Disable new-policy arming/entry with OMS_DISABLE_FX_BROKER_CANDLES_ARM=1. Preserve old policy behavior, reconciliation, protection, requested exits and all audit records. Do not restore a database over newer broker events.

## 11. Implementation steps

1. Add failing regressions for independent candle references and 10318.
2. Implement versioned candle subscription, lifecycle and evaluator.
3. Integrate preparation, review, dispatch and policy adoption.
4. Correct rejection classification and conclusive historical repair.
5. Integrate existing UI, document behavior, verify and self-review.
6. Observe current broker data and prepare the separately reviewed 1,000 AUD run without arming.

## 12. Completion criteria

Fresh post-authorization ticks above the exact previous completed broker candle reach one paper submission in isolated tests, independently of quiet tick gaps. Rejections remain accurate. Full verification passes and source fingerprint matches. Live acceptance is reported truthfully; an unarmed prepared run is not an execution trial.

## 13. Risks and assumptions

Broker bar close callbacks can lag boundary ticks, so pending evidence must remain fresh and current price must still exceed the reference. Candle revisions may change pending comparisons but never replay an executed signal. 1,000 AUD acceptance is broker-controlled. Worktree contains earlier approved work; retain it. Production remains separate from test fixtures.

Progress: ExecPlan created before implementation.


Progress update: Added failing regressions first. Implemented persistent broker
candle subscriptions, bounded references and pending live evidence, policy pinning,
preparation/review wording, rejection classification and append-only reconciliation
repair. Sixteen new focused regressions pass. Broader verification and connected
acceptance remain in progress; no production state or order has been changed.


Verification progress: 22 new broker-candle/rejection tests now pass, including
source selection, bootstrap lifetime, current-generation fencing, slightly
future bar starts, late cancellation and late-fill protection after reconciliation
repair. The initial full run passed 1,489 backend and 190 frontend tests; one
browser assertion expected the old policy. Updated that assertion to require the
new policy in the final authorization payload. The final full gate is running.

Read-only connected acceptance (125 seconds): separate GatewayData client 89
requested only the new persistent MIDPOINT candle stream. Received 31 bootstrap
bars, 24 subsequent updates spanning three minutes, and seven of seven sampled
existing MIDPOINT/bid-ask readiness checks were fresh. No unexpected data error
codes; no order-capable adapter was used. Production state backup completed with
SQLite integrity `ok` and a copy of capture files at
`backups/before-fx-broker-candles-20260925T002049Z` in the paper state directory.
Final verification: `.\scripts\verify.ps1` exited 0 (`verify: ok`): 1,495 backend,
190 frontend and 27 isolated browser tests passed, with formatting, lint, types,
build, secret scan and both dependency audits passing. A final presentation-only
self-review correction distinguishes an unarmed prepared run from an armed run;
49 focused FX tests passed afterward, including 23 new candle/rejection regressions.
The verification fingerprint covers the final files. Existing deprecation and
bundle-size warnings are non-failing.

Deployment: restarted the flat, disarmed paper workspace after checking the
verification fingerprint and zero recorded executions. Fresh complete broker
reconciliation matched order 26's dispatch/rejection sequence (142911/142914),
appended one `order.validation_rejection.reconciled` event, corrected the outcome
to rejected 10318 and released its allocation. The source binding hash, 0.01 AUD
quantity and consumed entry count of one remain unchanged; the source stays paused.
Emergency-stop state was preserved.

Prepared separate run `af396103a8d849dc969cf2598a656b77` for existing
`AUDUSD - Paper Test` v1 with 1,000 AUD, IDEALPRO, MIDPOINT, MKT/IOC,
broker-held protection, `paper_buying_power_v1` and `idealpro_broker_candles_v2`.
The original published hash and optional ceilings are unchanged. Current arming
preview reports verified build, eligible authorization and no blockers. The new
run is unarmed with zero consumed entries. The existing viewer now returns
`IBKR MIDPOINT` candles, complete prior minutes and a partial current minute.
Updated-workspace data observation completed over 304.83 seconds: all 143 samples
were connected, reconciled and fresh, with the persistent candle stream complete.
Six distinct completed reference minutes were observed within one connection
generation. Every sampled authorization preview was eligible with no blockers.
Final state remains zero recorded executions, no armed runs, three cancelled
historical orders and the one accurately rejected 10318 order. Reports are retained
locally in `.tmp/fx-updated-workspace-observation.json` and
`.tmp/fx-broker-candles-data-observation.json`.

Implementation, automated verification, isolated browser walkthroughs, audited
repair, unarmed run preparation and connected data acceptance are complete.
A natural-breakout execution trial remains pending separate operator authorization;
no order was submitted by this implementation or its data-only checks. Broker
acceptance/fill/protection for 1,000 AUD has not been claimed as tested.
