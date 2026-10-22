# ExecPlan: preparation, pre-market long-only execution and library removal

## 1. Goal

Implement the approved preparation automation, explicit pre-market long-only paper
execution policy, and delete-unused/archive-used strategy library controls.

## 2. Non-goals

No live trading, automatic routing/budget changes, fractional pre-market execution,
extended-hours OCA, after-hours execution, or changes to published strategy hashes.
No production-state mutation or forced broker trial during development.

## 3. Safety constraints

Paper adapter guards, explicit arming/local-protection acknowledgment, fresh trades
and quotes, risk reservations, ownership reconciliation and durable order IDs remain
mandatory. Protection and exits survive entry restrictions. Unknown cancellation
outcomes cannot permit replacement. Historical journal and published versions remain
immutable. No secrets or account identifiers in diagnostics.

## 4. Current state

Stock rules are entirely manual. Preparation defaults quantity from raw min_size
and omits sizing feedback. StockSession/history/orders are regular-hours-only.
Local stock exits are market orders. Studio has autosave but no library lifecycle.
The approved investigation's 20 stock policy/session/API tests pass.

## 5. Proposed design

Resolve qualified US whole-share rules with per-field provenance and a reusable
currency/route fee allowance; preserve manual non-US rules. Separate preparation
blockers from arming requirements and show indicative sizing. Never infer fractional
eligibility from precision. Preserve existing regular-hours bindings.

New versioned pre-market policy supports only schema-7 long-only breakout on US USD
shares through qualified SMART/NASDAQ routes. Session intersection: broker hours,
exchange calendar, 04:00 through regular close in America/New_York; reset minute
generations at regular open. New extended history is separately covered. Limit buy
at fresh ask, no chasing, deadline min(30s, trigger expiry, interval end). Persist
local protection before submission; actual VWAP stop at 99%. Limit sell at fresh
bid, cancel after 10s and replace only after terminal state and fresh reconciliation.
Unfilled exits alert at 30s; uncertain/rejected exits require recovery. No fills are
inferred. Exit deadlines prevent unapproved session carryover. Pending exit intent
survives closures/restarts. Regular behavior is unchanged.

Library removal previews a batch (max 50), deletes only unpublished/unreferenced
drafts, otherwise archives. Transactional revalidation, mutation receipts, tombstones
and autosave fencing prevent resurrection. Restore archived records explicitly.
Existing runs continue using their pinned versions, unaffected by library hiding.

## 6. Data model changes

Additive rule provenance/fee settings, versioned execution-plan session/order policy,
independent extended-history coverage and durable exit diagnostics. Library lifecycle,
deletion tombstones and idempotent batch receipts use existing document storage.
Back up before first additive persistent operation; retain legacy rule interpretation.

## 7. API changes

Extend run compatibility/create with session mode, sizing assessment, field evidence,
can_prepare, preparation blockers and arming requirements. Add reusable fee allowance
endpoint. Add strategy removal preview/confirmation/restoration and archived listing.
Legacy request defaults remain regular-hours. Existing version endpoints remain valid.

## 8. Test plan

Regression tests: META min_size, route/fractional checks, fee reuse, missing rules,
budget conflict; pre-market boundaries/DST/holidays/half-days, independent history,
LMT deadlines, protection, partial/late fills, serialized retry/rejection/restart;
library delete/archive/restore, stale preview, autosave race, preserved history.
Frontend and browser tests cover shared preparation, local acknowledgment, removal,
unchanged navigation/canvas and bounded Activity. Isolated fixtures only.

## 9. Verification commands

Focused pytest/vitest during slices, then `.\scripts\verify.ps1`. Record unavailable
operator-armed META pre-market trial separately; tests cannot establish broker acceptance.

## 10. Rollback plan

Disable new pre-market arming with OMS_DISABLE_PREMARKET_ARM=1 while continuing
existing position management. Do not restore a DB over an active engine/exposure.

## 11. Implementation steps

1. Regression tests and library lifecycle backend/frontend.
2. Rules resolver, fee reuse and preparation assessment/UI.
3. Versioned pre-market sessions, history, entry and protection/exit lifecycle.
4. Browser tests, documentation, full verification and safety self-review.

## 12. Completion criteria

All approved behavior implemented, regression/full verification passing, no production
orders or state edits, docs updated, external broker checks clearly reported.

## 13. Risks and assumptions

Pre-market local stops require application/data/connection availability. Limit exits
may remain unfilled and fresh-bid retries can execute below the 1% trigger. Fee
allowance is operator policy, not an exact commission estimate. USD 25 published
limits remain unchanged. Whole-share META may require an explicitly published budget
change within existing limits. Broker permissions/acceptance remain externally qualified.

## Progress

- ExecPlan recorded before implementation. No production trading state changed.
- Implemented US rule derivation/field evidence, reusable fee allowances, preparation
  assessment and the shared dialog changes. Existing rules/versions remain supported.
- Implemented independent extended history and versioned pre-market schedules,
  GTD limit entries, persisted local stops and serialized limit exit recovery.
- Implemented transactional delete/archive/restore with reference/revision checks,
  tombstones, response-cache cleanup and Studio autosave fencing.
- Added focused preparation, library, session, API and execution regressions plus
  two browser workflows. Initial focused suite: 61 passed; final pre-market suite:
  13 passed. Browser preparation/removal and the existing Studio workflow pass.
- Safety review caught and corrected: exact GTD/outside-hours acknowledgment;
  missing current broker schedules; stale/invalid extended history; regular/extended
  request separation; rejection evidence after cancellation; pending exit timeout;
  blank OCA groups on standalone SDK exits; and HTTP preview-cache self-references.
- First broad run: 1,178 backend and 190 frontend tests passed; accessibility found
  the new library checkbox target was too small. Enlarged it and passed the complete
  existing Studio walkthrough. No screenshot tolerance changes were needed.
- Final `.\scripts\verify.ps1`: **passed** on 22 September 2026. 1,182 backend
  tests, 190 frontend tests, 20 browser tests; formatting, lint, type checking,
  build, secret scan, Python/npm dependency audits and verification fingerprint passed.
  `git diff --check` passed. Nonblocking upstream deprecation/bundle-size warnings remain.
- Visually inspected isolated META preparation and delete/archive confirmation
  screenshots. Existing navigation/canvas visual assertions and accessibility pass;
  bounded Activity tests pass. No baseline tolerance was widened.
- Updated operator documentation in `docs/PREMARKET_AND_LIBRARY.md` and linked it
  from the reusable stock guide. Real META pre-market broker qualification remains
  external: no operator-armed trial, production order or broker setting change made.
