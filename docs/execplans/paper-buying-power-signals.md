# ExecPlan: Paper buying power and visible signal outcomes

## 1. Goal

Implement the approved account buying-power policy for supported paper stock/FX entries, without mandatory What-If or native-currency cash gates. Report every detected signal and its actual entry outcome in the existing workspace.

## 2. Non-goals

No live execution, production arming, emergency-stop release, forced trade, resizing, rerouting, strategy republication or mutation of existing approved bindings. Preserve 0.01 AUD and all existing protection and signal semantics.

## 3. Safety constraints

Paper-only adapter enforcement, explicit final authorization, current reconciled account evidence, 15-second execution freshness, legal quantities, published optional ceilings, ownership, protective intent, transactional reservations and duplicate prevention remain. Unknown submitted orders retain allocation until positively reconciled. Risk-reducing management remains independent of new-entry capacity.

## 4. Current state

The 10:37:01 AUD.USD capture confirms 0.702595 exceeded 0.702585. FX funding rejection silently returned before signal journaling; the UI incorrectly showed generic readiness and missing graph values. broker_credit_v1 requires a preview whenever native cash is unavailable. Informational broker code 2109 incorrectly rejects previews. Audit baseline: 94 focused tests passed; they do not cover the proposed behavior. The working tree contains substantial earlier approved work and must be retained.

## 5. Proposed design

Add paper_buying_power_v1 alongside legacy funding policies. Allocate notional plus fee allowance against fresh broker BuyingPower; require positive AvailableFunds and ExcessLiquidity, without treating notional as margin consumption. Normalize monetary evidence consistently, serialize allocations and avoid double-counting positively reflected orders. New-policy entries do not request or require previews. Journal deduplicated signal detection and outcome before any gate, expose the current outcome and FX comparison values in existing responses and UI. Preserve legacy previews with accurate informational/error classification and sanitized diagnostic reasons.

## 6. Data model changes

Add policy metadata and bounded latest-per-run signal state in existing document storage, plus append-only transition events. Add BuyingPower to account snapshots. Reuse versioned bindings, approval fingerprints and replacement links keyed by source binding and target policy. Back up before installing additive persistent policy metadata. Never migrate an active authorization in place.

## 7. API changes

Extend preparation/review/run readiness and snapshot responses with funding policy, buying-power allocation, evidence revision, signal progress and exact blocking reason. Extend current-policy replacement target revision; maintain backward-compatible existing fields and reject unsupported authorization terms. No new page or additional acknowledgment.

## 8. Test plan

Regression-first coverage for cross-currency FX/stocks without preview, notional above AvailableFunds but within BuyingPower, stale/missing/insufficient evidence, concurrent and reflected allocations, adverse updates, exact signal capture, blocked/expired/rejected/partial outcomes, legacy preview warnings, no duplicate dispatch, policy replacement and unchanged legacy hashes. Isolated frontend/browser coverage for run details, status labels, adoption, polling and canvas. Broker execution remains separately operator-authorized.

## 9. Verification commands

Focused pytest modules and frontend tests during slices. Run `.\scripts\verify.ps1` after implementation, including isolated Playwright browser fixtures. Inspect final build verification fingerprint. A natural operator-armed paper trial is reported separately; absent execution is not a passing trade test.

## 10. Rollback plan

Disable new-policy arming/entries with an explicit rollback switch. Preserve legacy policies, existing positions, reconciliation, protection, requested exits and audit records. Never restore an old database over newer broker outcomes.

## 11. Implementation steps

1. Add failing regression tests.
2. Add account-based funding policy and transactional allocation/adapter validation.
3. Add durable signal detection/outcome reporting and correct legacy preview diagnostics.
4. Integrate policy adoption, existing UI status and FX rule values.
5. Verify, review safety-sensitive changes and document operating behavior.

## 12. Completion criteria

New-policy cross-currency entries reach a paper adapter exactly once without a funding preview when checks pass. Every signal has a visible reason/outcome; real rejection and unknown order state remain truthful. Current selections, published hashes and existing bindings are preserved. Full automated verification passes; production state is untouched by development checks. Operator trial limitations are explicit.

## 13. Risks and assumptions

Aggregate buying power can overestimate instrument-specific capacity; the operator explicitly selected broker decision at paper submission. Full notional allocation is an application concurrency allowance, not broker margin. Actual cost can differ for market orders. Known restrictions and broker rejection remain authoritative. Future real-money use needs a separate approved policy and remains disabled.

Progress: regression-first policy and informational-2109 tests reproduced the missing behavior. Implemented the new policy, shared allocation check, version-aware replacement, durable signal/order linkage, signal outcomes, required-input status and UI terms. The exact 0.702585 to 0.702595 crossing reaches one isolated 0.01 AUD paper submission without a preview. Additional tests cover pre-existing currency debits, execution-derived ownership, actual-fill protection and external balance discrepancies.

Self-review corrected two integration issues found by the full suite: compact run records can lack a contract identity, and the data-only adapter must not invoke the executable adapter's preview handler for unrelated errors. The full backend suite then passed 1,473 tests; frontend lint, type checks, formatting, 190 tests and the production build passed. The first full browser run passed 26 of 27 tests; its remaining assertion still named the earlier policy. After correcting that assertion, the FX and signal-outcome walkthroughs passed. The final gate is being rerun without PowerShell output redirection, which otherwise treats Vite's bundle-size warning as a terminating native-command error.

Final verification (2026-09-25 Australia/Sydney): `.\scripts\verify.ps1` completed with exit code 0 and `verify: ok`. All 1,473 backend tests, 190 frontend tests and 27 isolated browser tests passed. Repository checks, Python formatting/lint/compilation, frontend lint/type checking/formatting, production build, secret scan and Python/npm dependency audits passed. The gate recorded the exact source/build fingerprint in `.tmp/paper-verification.json`. Existing dependency-deprecation and bundle-size warnings are non-failing. The FX copy/canvas, preparation, policy adoption and signal-outcome browser walkthroughs passed; the rendered outcome panel was visually inspected.

Implementation and automated acceptance are complete. Production state, authorizations and broker orders remain untouched. The natural-breakout TWS trial is pending separate operator final authorization; isolated submissions are not evidence of broker acceptance. Load the verified build, explicitly adopt the current execution policy for an eligible disarmed run, review the preserved exact settings, and use the normal final paper authorization. Do not replay the missed crossing. Record any broker refusal accurately; a rejection or a session without a qualifying signal is not a successful execution trial.
