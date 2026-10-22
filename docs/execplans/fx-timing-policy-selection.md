# ExecPlan: Correct FX timing and persist current-policy selection

## 1. Goal

Remove false FX freshness failures, provide explicit restoration of an unchanged unused policy replacement, and keep that run selected across review, navigation and reload. Preserve the existing canvas, panels and final authorization.

## 2. Non-goals

No strategy changes, quantity changes, route changes, broker configuration changes, production arming, order submission, emergency-stop release, or automatic restoration of saved runs during development.

## 3. Safety constraints

Paper-only adapters remain enforced. Preserve 15-second source and receipt freshness, the five-second clock-health bound, risk/funding/ownership checks and final human authorization. Never execute on future, historical or replayed observations. Do not log secrets or every quote. Preserve original bindings, approvals and archive history.

## 4. Baseline state

`fx_data.py` stores arrival-time freshness in permanent `valid`; slightly future observations can subsequently show fresh ages but remain invalid. FX review/funding independently evaluate timing. `run_policies.py` reuses linked replacements but rejects archived targets. `ArmReview.tsx` replaces only its local preview while Desk selection remains persisted on the original. MarketData's badge uses instantaneous execution readiness.

## 5. Proposed design

Separate structural validity from a common signed timestamp evaluation. Stage slightly future live observations in a bounded generation-fenced buffer, drain only matured fresh events in source order and reset signal continuity on discarded events. Use one evaluation instant for ages, reasons and eligibility. Add bounded timing diagnostics. Start reference minutes conservatively after authorization plus clock uncertainty.

Extend replacement preview/confirmation with explicit restore intent and expected target-state fingerprints. Revalidate unused target safety and compatibility inside the transaction. Preserve archive metadata and append an authenticated restoration event. Old creation receipts never restore visibility. Lift Desk selection into shared persisted workspace state; update it on adoption/restoration and discard stale review responses. Show stable feed health separately from neutral execution waiting, including clock alignment, with funding terms derived from the selected binding.

## 6. Data model changes

Add bounded in-memory FX pending observations, structural/freshness metadata and diagnostics. Add optional restore action/fingerprint to existing replacement requests and audit receipts, and append restoration metadata to the unchanged run. No schema migration or published hash change. Existing backup-before-policy-installation behavior remains; back up before first restoration installation.

## 7. API changes

Extend authenticated `/api/runs/policy-replacement` with explicit action and expected replacement-state fingerprints. Extend previews with restoration eligibility/action/fingerprint. Extend FX data and readiness responses with evaluation time, structural validity, signed ages and freshness reason. Existing eligibility fields remain authoritative and older requests retain creation semantics.

## 8. Test plan

First reproduce slightly future arrival with subsequently fresh ages and archived replacement rejection. Cover independent streams, malformed/crossed/stale observations, future buffering, expiry, ordering, overflow, generation changes, conservative minute boundary and no duplicate/future execution. Cover exact restoration, idempotency, stale state and broker activity rejection. Browser regressions cover close/reopen, navigation/reload, stable healthy badge and policy-specific review terms. Use isolated fixtures and a read-only data connection for broker observation.

## 9. Verification commands

Run focused pytest suites using `.venv\Scripts\python.exe -m pytest`, frontend typecheck/lint and targeted Playwright tests, then `.\scripts\verify.ps1`. Record outcomes below. Run a data-only AUD.USD timing probe without creating runs or submitting orders.

## 10. Rollback plan

Disable policy replacement via the existing host rollback flag if necessary. Revert this slice while retaining journals, bindings, restored archive history and position management. Do not restore a database backup over a running engine. No saved authorization is revived by rollback.

## 11. Implementation steps

1. Add failing timing/restoration regressions.
2. Implement shared FX timing, bounded buffering and conservative reference minute eligibility.
3. Add transactional explicit restoration and API validation.
4. Persist workspace selection and update existing status presentation.
5. Run focused, browser and full verification; inspect a data-only stream; document results.

## 12. Completion criteria

Fresh observations cannot retain an old timing rejection. Future observations never drive orders. Restored runs retain exact 0.01 AUD settings, bindings and history. Adoption remains selected after reload. Healthy quiet streams have stable health labels, with real failures visible. Full verification passes or precise outstanding limitations are reported.

## 13. Risks and assumptions

Live clock offsets were initially unmeasured; the data-only observations below subsequently confirmed slightly future source timestamps. Buffer limits must fail visibly rather than silently lose signal continuity. IBKR delivery can be quiet and independent across streams; health is not execution eligibility. Archived replacement restoration requires an explicit current request, including after concurrent archival. The repository includes substantial pre-existing changes which this slice must preserve.

### Progress and evidence

- Plan recorded before implementation. Baseline relevant behavior and immutable binding findings are recorded in the approved user plan.
- Added regressions before implementation; initial timing tests failed on missing structural/freshness separation. Timing/restoration suites subsequently passed (47 tests), and the broader initial FX execution/data/replacement slice passed (62 tests). Strengthened target-binding integrity checks then passed all 32 replacement tests.
- Implemented the shared signed evaluator, 4,096-observation alignment buffer, generation/retirement fencing, conservative authorization boundary and bounded diagnostics. Invalid quotes and excessive clock offsets remain blocking.
- Added explicit authenticated restoration with target-state fingerprints, pre-installation backup, transaction checks, preserved archive metadata and audit. Old creation receipts cannot restore archived records. No saved production run was changed.
- Lifted selection into persisted workspace state shared by Desk/Studio/Testing. Replacement/refreshed reviews cancel prior requests. Market data shows stable stream health, and existing review text reflects the selected policy.
- Isolated browser regressions passed for FX publication/canvas behavior and stable market-data health. Adoption/restoration/reload regression passed after accounting for the existing inspected-run drawer and intentionally aborted in-flight test requests. Original/target bindings and absence of authorization are asserted.
- Data-only AUD.USD observation used a temporary store and `GatewayData.execution_enabled=False`, with no runs/orders. The 90-second probe captured 43 snapshots, 16 healthy/fresh snapshots, and 120 displayed candles. Sampled signed source-minus-receipt offsets ranged from -0.075423 to +1.091559 seconds. There were zero fresh-age/permanent-invalidity contradictions.
- Broker acceptance limitation: neither the first observation nor a 65-second diagnostic follow-up received `positions_end`; the other four reconciliation completion markers arrived. The isolated engine therefore retried reconciliation/reconnected and no fully verified account snapshot was established. This does not validate stable live reconciliation or trading readiness. The follow-up again observed aligned healthy FX quotes without contradictions. No account uncertainty was bypassed, and no production settings/state were changed.
- Self-review added stream-specific continuity handling: stale unused MIDPOINT data cannot reset a BID/ASK strategy. Its failing regression was fixed and all 18 timing cases passed at that stage.
- Expiry review added an explicit signal-window check on buffered processing, before reservation and at final dispatch. Tests first reproduced submission of an expired synthetic signal, then verified future/expired signal rejection and reservation release when expiry occurs between reservation and dispatch. Fixture signals now include their actual window metadata. A delayed end-of-minute crossing is separately covered.
- Full verification attempts were intentionally stopped when these review findings required code changes. Only the subsequent final gate will establish verification for the completed build.
- Corrected ordering to use the last processed observation rather than a rejected raw timestamp. Added malformed/nonfinite/extreme-future timestamp recovery regressions, including a valid correction with the same timestamp and price that restores evidence without replay. This prevents rejected timestamps from poisoning later recovery.
- The expanded FX execution/data/timing/credit/replacement subset passed 104 tests; the additional delayed-minute regression passed separately. Browser adoption/restoration/reload passed after preserving a closed inspector rather than opening a new drawer.
- A complete gate passed 1,418 backend tests and 190 frontend tests, then exposed an existing unstable browser selector: unchecking a run caused its `:checked` locator to stop matching during Playwright's completion check. The page had correctly deselected the run. Changed the test to snapshot accessible names and use stable checkbox locators; all three preparation/archive browser tests then passed. The other 24 browser checks passed in that gate. The full gate was rerun after this test-only correction.
- The next gate again passed all 1,418 backend tests but stopped at Prettier on the edited browser test. Applied Prettier, confirmed the full frontend format check passes, and restarted the unmodified full gate. Separate secret and Python/npm dependency audits passed. No application behavior changed during these test-only corrections.
- Final `.\scripts\verify.ps1` completed successfully with exit code 0 and `verify: ok`: 1,418 backend tests, 190 frontend tests and 25 browser tests passed. Repository checks, Python formatting/lint/compilation, frontend formatting/lint/typecheck/build, secret scanning and Python/npm dependency audits all passed. The final browser suite includes the corrected archive selector, FX display timing, canvas behavior and restoration across review close/navigation/reload. Existing dependency deprecation and bundle-size warnings are non-blocking.
- Completion: implementation and automated verification are complete. `verified()` confirms the exact tested build. The data-only broker observation limitation above remains explicit; no operator-armed trial was conducted. No production run was restored/armed, and no broker order, emergency-stop release or broker-setting change was made. Restart the workspace normally and use the explicit **Restore current-policy run** action for the archived unused replacement.
