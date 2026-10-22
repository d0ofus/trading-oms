# ExecPlan: Reliable recovery controls and independent market-data health

## 1. Goal

Keep recovery reviews current, allow verified one-click recovery without required
typing, and expose/retry quote, execution-trade and history failures independently.

## 2. Non-goals

No live execution, sampled-quote trading fallback, risk relaxation, automatic
incident release or arming. Do not restart or modify the user's running workspace,
clear its incidents, or submit/cancel broker orders. Investigation closure remains
a separate action with its existing recorded-outcome requirement.

## 3. Safety constraints

Actual qualifying trades, valid history, fresh execution observations, paper context,
watchdog, reconciliation and protective plans remain mandatory. Retry only failed
data components and never interrupt healthy protection feeds. Journal retries and
recoveries, retain immutable history and use opaque authenticated actor identities.
Broker free-form messages, account identifiers and reject JSON never enter diagnostics.

## 4. Current state

IncidentPanel reads once per opening and requires ten rationale characters for
dedicated reviews. Quotes and trade/history failures share coarse status and one
overwritten diagnostic. A history error drops all remaining jobs. Broker requests
lack durable-in-memory generation/retired context, so expected cancellation code
300 can become a workspace incident. Captured quotes continued while 10189 trade
and 162 history failures prevented execution. Later resubscription restored both.

## 5. Proposed design

Poll only the visible selected incident every two seconds, one request at a time,
with cancellation, freshness/error states, structured recovery checks and recheck.
Keep optional notes collapsed and record a standard operator reason when omitted.

Add adapter-owned request lifecycle/generation metadata and bounded terminal context.
Classify known broker message patterns into safe reason enums and fixed descriptions.
Track quote/trade/history components separately, with contract-scoped incident codes.
Retain successful history ranges and retry failed units with existing account pacing.
Automatic transient delays are 15/30/60 seconds, pacing 60/120/240; other failures
require manual retry. Three automatic attempts maximum per failure episode. Retry
actions are authenticated/idempotent; healthy components are untouched. Late callbacks
cannot revive or invalidate a newer request generation. Legacy aggregate incidents
remain conservative. Historical bars and sampled quotes never create entry signals.

## 6. Data model changes

Add bounded in-memory component/request/history-job states, projected health/checks,
generation metadata and safe diagnostic records. Reuse mutation storage and immutable
journal for retry actions. New contract-scoped incident codes; preserve legacy
episodes, approvals and strategy hashes. No rewrite of historical records.

## 7. API changes

POST /api/market-data/{conid}/retry accepts selected failed components and mutation_id.
Market data responses add components/diagnostics/progress/retry state. Incident detail
adds recovery checks, checked time and stability remaining. Existing review rationale
stays optional on the wire and no longer has a backend minimum-length policy.

## 8. Test plan

Tests first for blank-note dedicated recovery, active/stale review rejection,
classification redaction, simultaneous trade/history failure, retry isolation,
pacing/deduplication, retained history and stale callbacks. Browser tests for polling
blocked-to-ready without reopen, optional notes, errors, visibility/abort cleanup,
separate sampled/execution Last and retry controls. Keep quiet-market/protection tests.

## 9. Verification commands

./scripts/verify.ps1

Focused backend and Playwright recovery/feed tests; bounded Activity probe against
the final build. A supervised data-only broker observation is optional if available;
external checks not performed must be recorded explicitly. Never force a trade.

## 10. Rollback plan

Stop the workspace at a supervised recovery point before changing binaries. Preserve
state/journal and reconcile on restart. Do not restore old authorizations or remove
incidents. New incident codes remain conservatively blocking in incompatible builds.

## 11. Implementation steps

1. Add failing regressions and adapter request lifecycle/classification.
2. Implement independent component/history-unit recovery and bounded retry scheduling.
3. Add API projections, optional rationale and current recovery evidence.
4. Implement polling dialog, component status and retry controls.
5. Verify, inspect browser output, review safety/compatibility, update operator docs.

Implemented on 2026-09-21. Added `broker_feeds.py` (safe reason classification,
generation fencing, synchronized request retirement and bounded terminal context)
and `feed_recovery.py` (component projections, per-range history state and paced
idempotent retries). Integrated the existing adapter, engine, incident policy and
authenticated API without changing execution/approval rules. Added the visible-only
detail polling hook, optional notes and shared feed/retry component in the frontend.
Updated operator/capacity documentation and added `docs/FEED_RECOVERY.md`.

Self-review corrected cancelled/completed callbacks surviving unsubscribe, an SDK
error/cancellation race, and stream resets unnecessarily cancelling independent
history requests. History retries retain repair identity and completed ranges;
retained job lookups are indexed per contract. A heartbeat expiring between evidence
reads now returns a blocking explanation instead of raising an engine exception.
Released historical incident details retain their original release evidence rather
than displaying current recovery checks.

Regression tests were added before implementation; the initial new test collection
failed because the new adapter lifecycle module did not yet exist. The focused
feed/incident/quiet-market suite subsequently passed 48 tests. A final boundary
regression was added during review: all 21 incident tests then passed. The first
full backend pass ran 1,020 tests; an intermediate verify invocation passed 1,023
backend and 190 frontend tests but PowerShell's redirected stderr treated Vite's
bundle-size warning as a terminating native-command error. The gate was restarted
without stream redirection; its final result is recorded below when complete.

Browser recovery workflows initially passed six focused tests, including existing
bounded Activity/accessibility tests. Added a further slow-response/abort test for
the final gate. Visually inspected the generated recovery-dialog and independent-feed
screenshots. Synthetic Activity probing after 5,000 streamed events and five visits
retained 5.07 MiB JavaScript heap, 22 mounted rows and 686 DOM nodes. The isolated
Chromium process working set was about 258 MiB (109.5 MiB private memory); this is
not a measurement of the user's existing browser or a repeated 30-minute soak.

## 12. Completion criteria

Requested behavior and regression/browser verification pass; all exceptions and
unavailable external checks are recorded. No real user state/trading action is changed.

Implementation complete. Final `./scripts/verify.ps1` finished with `verify: ok`:
1,029 backend tests, 190 frontend unit tests and all 11 browser workflows passed;
formatting, lint, type checks, compilation, build, secret scan and both dependency
audits passed. The separately added heartbeat-expiry boundary regression passed in
the 21-test incident suite against the final recovery implementation. The gate
recorded the current source/build verification fingerprint. Non-blocking upstream
warnings remain for the existing Vite bundle size and Starlette's httpx deprecation.
No snapshot baseline changes were needed for this feature. The external broker
observation remains unavailable as documented below; no production qualification
or broker permission was inferred from offline acceptance.

## 13. Risks and assumptions

IBKR permissions/session conflicts need operator correction; code cannot grant access.
The original 162 detail was discarded and cannot be reconstructed. Quiet periods
remain distinct from rejected streams. New feed state is rebuilt on restart; old
callback generations and history downloads must never be treated as execution proof.

External acceptance limitation: the configured local broker API port 4002 had no
listening service during the final check. A supervised IBKR data-only recovery
observation could not run. No alternate broker endpoint was tried, no real order
was submitted/cancelled and no running user workspace/incident/authorization state
was changed. The new operator guide records the post-restart observation steps.
