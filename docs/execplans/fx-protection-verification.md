# ExecPlan: Correct FX protection verification

## 1. Goal

Verify accepted IDEALPRO paper stops accurately, preserve completed-order quantity evidence, and show specific protection status without disturbing an existing stop.

## 2. Non-goals

No strategy, quantity, funding, route or protection-method changes. No new trading authorization, live execution, forced trade, liquidation or emergency-stop release.

## 3. Safety constraints

Paper-only adapter enforcement, current ownership and risk checks remain authoritative. Never infer fills from intents. Keep original journal observations; corrections are additive and audited. Unknown/conflicting broker evidence blocks affected new risk. Protect actual fills independently. Do not restart the running workspace until current broker evidence confirms flat with no related outstanding orders/operations.

## 4. Current state

FX identity requires outsideRth=True although IBKR ignores it for these orders (2109). Completed callbacks can overwrite accepted quantity with zero while reporting a full fill. Generic 399 handling produces uncertainty and cancellation without awaiting authoritative outcomes. Protection projections can retain awaiting_fill and display a generic red badge.

## 5. Proposed design

Ignore the inapplicable outside-hours attribute only for supported IDEALPRO CASH orders; retain all meaningful identity/price/trigger checks. Preserve accepted quantity evidence and normalize a completed zero total only with matching accepted identity, full broker fill and corrected executions. Share this assessment across live projections and reconciliation. Record sanitized scoped 399 warnings, await authoritative confirmation and retain submission watchdogs. Use one structured FX protection assessment for readiness, recovery and UI; automatically resolve only conclusively corrected concerns.

## 6. Data model changes

Add optional quantity provenance and protection assessment fields to existing documents. Preserve raw reported observations. No table migration or strategy/binding rewrite. Back up persisted state before any additive production writes.

## 7. API changes

Existing order diagnostics and FX protection responses gain assessment state, reasons, evidence revision/time and reported/effective quantity. Existing protected boolean remains compatible and derives from the assessment. No new endpoint.

## 8. Test plan

Captured 1000-unit fill and PreSubmitted stop with ignored outside-hours flag; zero-total completed callback; conflicts/missing evidence; callback ordering/restart; 399 acceptance/rejection/timeout/late fill; partial fills and cancellation serialization; specific UI states. Include regression checks for strict stock identity and paper-only enforcement.

## 9. Verification commands

`.\.venv\Scripts\python.exe -m pytest backend/tests/test_workspace_fx_protection.py -q`

`.\scripts\verify.ps1`

Isolated browser regression with synthetic broker fixtures; no real order required.

## 10. Rollback plan

Disable new FX entries using existing host controls, preserve reconciliation/protection/exits and journal. Do not restore a database over broker exposure. Revert code only during a verified safe deployment window.

## 11. Implementation steps

1. Add failing regression fixtures.
2. Correct FX identity and quantity evidence projection.
3. Correct scoped warning handling and shared protection assessment.
4. Integrate existing UI and operator documentation.
5. Run focused and full verification, self-review, and check deployment eligibility read-only.

## 12. Completion criteria

Verified accepted stops show active; genuine failures remain specific and blocking. No duplicate/cancelled stops caused by this fix. Full verification passes. Production deployment occurs only when fresh evidence confirms flat and no outstanding related work; otherwise leave the running instance untouched and report deployment pending.

Implementation evidence (26 September 2026):

- Added reproductions before implementation: ignored outside-hours identity and 399 authorization failures reproduced. Added crash-interruption regressions before making evidence/audit writes atomic.
- 29 new focused protection regressions pass. The earlier focused compatibility run passed 117 existing FX, order, rejection and recovery tests.
- Independent isolated checks verified restart retains ownership without re-arming and a late execution creates exactly one stop after a zero-total completed callback.
- All 28 isolated browser regressions pass. The new presentation fixture does not create persistent shared-test runs; an initial fixture-isolation failure was corrected. Visually inspected the rendered stop card.
- Final `scripts/verify.ps1`: passed on the finished source. 1,525 backend tests, 190 frontend tests and 28 browser tests passed; formatting, lint, type checks, build, secret scan and both dependency audits passed. The exact source/build verification fingerprint was recorded. Existing deprecation and bundle-size notices are non-blocking.
- Deployment remains pending: the workspace HTTP service and configured paper Gateway were unavailable during read-only checks. No application startup/restart, order submission, cancellation, broker setting change or production-state correction was performed.

## 13. Risks and assumptions

399 text for the recorded episode was not retained, so its original cause cannot be retrospectively classified. PreSubmitted establishes broker acceptance, not a guarantee of stop execution. Current saved exposure is not proof of current broker state. Existing dirty worktree is preserved.
