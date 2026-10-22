# ExecPlan: Preparation, inactive-run archiving and combined recovery

## 1. Goal

Use the same published-version preparation form from Desk, Studio and Testing; archive only proven inactive runs; acknowledge verified routine recoveries together; show request-specific contract search progress and results.

## 2. Non-goals

No live execution, broker trials, automatic arming, strategy conversion, order cancellation, position closure, incident erasure or UI redesign. No production-state manipulation to demonstrate the features.

## 3. Safety constraints

Paper-only execution and all risk/protection controls remain enforced. Archiving requires disarmed, flat, unreserved, resolved state, with fresh reconciliation after broker activity. Batch operations revalidate atomically and are idempotent. Historical events and published hashes remain unchanged. Recovery never clears emergency stop or restores authorization. No secrets or raw broker errors are persisted.

## 4. Current state

Desk has a legacy symbol-only preparation implementation separate from PrepareRun. Stock conversion leaves the old draft selected. Runs have no archive metadata. Routine recovery is limited to watchdog/connectivity with individual Activity dialogs. Resolve returns a broker request number without visible completion and candidate resolution substitutes SMART.

## 5. Proposed design

Extract shared preparation content while retaining the Desk selector and existing modal. Add an engine-owned archive service with preview/confirmation, durable batch receipts and late-activity restoration. Extend validated routine recovery policy and provide exact-episode batch previews/confirmation using existing evidence and revisions. Add a bounded search registry correlated by connection epoch/request, explicit completion/errors/timeout and frontend polling. Preserve routing and distinguish current results from saved contracts.

## 6. Data model changes

Add optional archived metadata to run documents; archive and recovery batch receipts/previews to documents; journal all transitions. Search state is bounded ephemeral per engine (20 requests, 200 results each), invalidated on disconnect. Existing records default unarchived. Back up before additive persistent changes where existing state requires migration; no rewriting historical journal records.

## 7. API changes

Authenticated run archive-preview/archive-confirm endpoints (1–50 IDs); routine recovery preview/confirmation endpoints; contract search status endpoint. Resolve retains request and adds search identity/status. Existing APIs remain compatible. Archived runs cannot arm.

## 8. Test plan

Regressions for schema 7 Xiaomi preparation from all entry points, faithful schema 6 duplication and explicit conversion selection; archival eligibility/atomicity/idempotency/restart/late observations; combined routine recovery evidence/revisions/exclusions; search routing/status/timeouts/disconnect/stale callbacks/bounds. Browser walkthrough with isolated fixtures, no arming or broker orders. Preserve legacy UI and bounded Activity tests.

## 9. Verification commands

Run focused pytest and frontend tests during each slice. Final: `. .\\.tmp\\activate-dev.ps1` then `.\\scripts\\verify.ps1` from repository root. Record exact results below.

## 10. Rollback plan

Disable new actions and restore prior frontend/backend together with engines stopped. Never restore a stale database over broker exposure. Archived records retain ownership/protection processing. No destructive migration is required.

## 11. Implementation steps

1. Add regression tests and shared preparation.
2. Implement archive preview, atomic confirmation and late-observation recovery.
3. Implement combined verified recovery.
4. Implement correlated contract search and visible status.
5. Integrate browser tests, operator documentation, verification and safety review.

## 12. Completion criteria

All approved behaviors implemented, full verification passes, isolated browser preparation and archiving pass, no production trading changes, limitations documented. Progress and verification results will be appended here as implementation proceeds.

Implementation progress (22 September 2026):

- Shared preparation content is used by all three entry points. Desk loads immutable versions with stale-response cleanup; Testing clears old version selections; explicit stock conversion selects its new draft.
- Archive previews and atomic confirmations retain audit receipts, reject exposure/reservations/uncertainty, and restore archived records to recovery on unexpected broker activity. Archived runs cannot reserve, dispatch or arm new entries.
- Routine recovery supports one explicit batch acknowledgment. Feed episodes retain contract scope. Recognized farm interruptions require matching farm recovery; unidentified legacy broker messages remain dedicated reviews. Policy migration backs up state and never releases restrictions.
- Search status is correlated to request and connection, bounded to 20 searches/200 results, preserves routes, validates direct-ID filters, fences obsolete callbacks and shows persistent inline outcomes.
- The initial complete backend test run passed 1,153 tests. Subsequent focused regressions include API authentication, archive safety and adapter generation fencing. Ten focused browser workflows passed, including Xiaomi preparation/archive, SMART failure/SEHK success, stock-copy selection, Testing preparation and combined recovery.
- The first full `scripts/verify.ps1` completed successfully: 1,158 backend tests, 190 frontend tests, 18 browser tests, formatting/lint/type checks, build, secret scan and dependency audits. Existing visual baselines passed unchanged.
- Final safety review added three search-correlation regressions: shared connectivity failures cannot be swallowed by a search; informational farm messages cannot fail it; unrelated broker/order failures with overlapping numeric IDs retain their normal handling. These failures were reproduced before correction. Code 201 remains in the broker-order namespace at the adapter boundary.
- Final verification passed: **1,161 backend tests, 190 frontend unit tests, 18 browser tests**, formatting, lint, type checks, compile checks, production build, secret scan and both dependency audits; `verify: ok`. The stock review screenshot was inspected: HKD, contract identity, quantities, USD limits and protection acknowledgment fit the existing dialog. Existing visual baselines and bounded Activity tests passed without baseline changes for this task.
- Browser acceptance was data-only for the new workflows, using isolated Xiaomi fixtures. No production strategy was armed, no broker order was submitted, and no production run or incident was changed. Broker qualification, legal lot affordability and account funding remain separate operator checks.
- Completed safety review: archive confirmation is transactional and rechecks all selected runs; repeat confirmations do not duplicate archive events; late activity restores recovery without deleting ownership; broker order failures and connectivity are independent of search status; unknown service diagnoses do not gain routine-release permission. Published definitions and lower ceilings remain unchanged.

## 13. Risks and assumptions

Broker callbacks can arrive after terminal statuses or archival; authoritative observations must restore recovery handling. A restart is not proof of recovery. Unknown broker service classifications retain dedicated review. Xiaomi lot/funding qualification remains separate from this preparation fix. Existing dirty work from earlier tasks must be preserved.
