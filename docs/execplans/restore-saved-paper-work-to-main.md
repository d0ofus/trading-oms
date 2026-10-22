# ExecPlan: Integrate saved paper work and verify locally

## 1. Goal

Integrate the saved local paper-workspace changes with the current GitHub `main` on `codex/restore-paper-work` and produce a verified, reviewed local integration commit. Publication and an IBKR paper trial are subsequent steps.

## 2. Non-goals

- No live-trading capability, account login, broker order, or automatic arming.
- No expansion of strategy behavior beyond reconciling the saved work and incoming `main` commits.
- No claim that broker fill or protective-order qualification has already passed.
- No GitHub publication or broker connection during this slice.

## 3. Safety constraints

- Preserve paper-only transport, localhost Gateway binding, human authorization, risk checks, stale-data blocks, unknown-state blocks, duplicate prevention, protection, reconciliation, and append-only audit records.
- Do not add secrets, account identifiers, or private broker data to commits, logs, or screenshots.
- Keep the saved stash intact until the published tree and local work are verified.

## 4. Current state

`main` and GitHub remain at `4abf934`. The saved 44 tracked edits and 187 additional files are preserved in `7e6248c`; the original stash `206503c1238f10bd4b141847c93cc5cc95b7e49d` remains recoverable. The local integration branch now combines that workspace with upstream main. Schema/compiler and execution-policy conflicts are resolved and the complete offline verification gate passes. Real broker execution qualification remains outstanding.

## 5. Proposed design

Merge `main` into the preserved branch and resolve overlaps by behavior. Schema 4 crypto retains its interpretation; explicit stock session settings select the upstream stock schema-4 compiler, and mixed shapes fail closed. Preserve existing publication hashes. Port scheduled stock sessions, broker-held extended stop-limit protection, the explicitly authorized one-shot stock paper test, diagnostics and safe run removal into the saved workspace's existing risk, ownership, authorization and recovery flow. Existing pre-market and FX policies retain their meaning. Carry forward upstream patched lockfiles and run focused regressions plus the full offline gate.

## 6. Data model changes

Preserve only the saved work's additive migrations and event schema. Review migration compatibility with current `main`; do not reset paper state.

## 7. API changes

Preserve saved APIs and upstream session-date, diagnostics, paper-test preview/start, incident recheck and run-removal routes. Extend typed frontend contracts accordingly. Review route collisions and bind operator identity to explicit authorizations.

## 8. Test plan

Add schema-4 family/hash and mixed-shape regressions first. Cover future sessions, quote-only one-shot stock tests, stale previews/quotes, duplicate starts, uncertain submissions, unexpected fills, protection, removal and restart/reconciliation. Retain FX candle, policy, execution, protection and recovery coverage. Run the full backend/frontend/e2e verification gate, secret scan, dependency audits, duplicate-route review and frontend build fingerprint check.

## 9. Verification commands

`git diff --check`, focused `python -m pytest` commands covering the above scenarios, `python -m pip check`, `npm.cmd --prefix frontend ci`, and `.\scripts\verify.ps1` with the verification environment on `PATH`. Require `verify: ok` without reducing audit thresholds.

## 10. Rollback plan

Keep the original stash and original remote tip recorded. If verification or safety review fails, leave GitHub `main` unchanged and retain the integration branch for repair. Do not rewrite remote history.

## 11. Implementation steps

1. Record this approved scope, preserving original commits and stash.
2. Merge current `main`; add compatibility regressions and resolve schema/compiler overlaps.
3. Integrate session authorization, paper diagnostic lifecycle, protection, removal and UI behavior through existing safety controls.
4. Install the upstream patched dependencies and run focused and full verification.
5. Review trading safety and compatibility, fix findings, update operator docs and commit the verified local integration.

## 12. Completion criteria

The local branch contains saved work and upstream commits; old publication hashes remain valid; every order-capable path remains paper-only, risk-gated and journaled; full verification reaches `verify: ok`; the original stash is recoverable; and GitHub `main` is unchanged.

## 13. Risks and assumptions

The saved work is large and spans broker, risk, OMS, UI, tests, and migrations; historical successful verification does not prove compatibility with the newer GitHub commits. An upstream semantic conflict, secret finding, or failing verification blocks publication until resolved.

### Integration checkpoint, 22 October 2026

The saved files are preserved in local commit `7e6248c` on `codex/restore-paper-work`; the original stash remains intact. On their original base, formatting, lint, 1,525 backend tests, 190 frontend tests, 28 browser tests, build, and secret scan passed. The full gate stopped at the older lockfile's vulnerable `certifi 2026.6.17`; GitHub `main` has the patched dependency.

Merging `main` produced 18 conflicting files. The newer session feature uses strategy schema 4 for extended stock hours, while the saved workspace uses schema 4 for crypto. Its one-shot paper test cannot publish through the saved compiler, and its old engine fixture does not represent the saved workspace's additional watchdog readiness. The merge was reset to the preserved local commit. GitHub `main` remains unchanged. Before publication, design a compatibility migration for both schema-4 document families, adapt the paper connection test and future-session authorization to the saved broker/risk/OMS architecture, then rerun the full gate and review paper-only dispatch semantics.


### Implementation decisions

- Scheduled/extended sessions apply to legacy stock graphs with explicit session settings. Reusable stocks, saved pre-market local protection, FX and crypto retain their versioned policies. The saved authorization transaction handles scheduled approvals; reservation and the final dispatch guard recheck the selected window.
- Schema 4 stock is selected by stock session fields. Crypto settings mixed with those fields are rejected. Unmarked saved crypto drafts retain their old defaults. Golden publication hashes cover both families and schema 3.
- Upstream incident inspection/recheck is adapted into the existing scoped IncidentPanel/IncidentRecovery flow. Recovery cannot overwrite episodes. Contextual engine faults require a matching successful operation and 30 healthy seconds; post-failure reconciliation and explicit critical-incident review remain required.
- Run removal uses existing dependency, cancellation, ownership and reconciliation archival checks. The broker test is explicitly stock-only, binds its preview to process/epoch/context/contract, uses the existing risk reservation/outbox and cannot qualify normal strategy execution.
- Additional audit findings in Vitest 5.0.1 require patching to 5.0.5. Maintainer advisories GHSA-qxg6-89mg-rqv8 and GHSA-xp26-3454-mjgp identify fixes in 5.0.3 and later. No audit threshold or exclusion changes.


### Integration review and corrections

Self-review found missing legacy extended exit flags/session bounds and regular-only historical requests. These are corrected; regression coverage verifies that closed sessions retain pending exits and that accepted extended exits carry the original outside-hours contract. The first completed backend gate reported 1,563 passes and two integration regressions: saved pre-market callbacks must validate the execution plan's outside-hours flag, and archived runs must be rejected before strategy lookup. Both fixes passed a 47-test focused rerun.

The browser walkthrough initially passed 28 of 29 tests; the new legacy fixture ran before a pre-existing test with a global name selector. It now follows the existing serial fixture sequence. The original walkthrough passed after reviewing and updating only the canvas and guided Studio baselines for the visible strategy-name label and readable operation/session explanations. Both images were inspected individually; no layout clipping or order/approval regression was found. Baselines for the other views and snapshot tolerance were retained.


### Completed local verification, 22 October 2026

The final `./scripts/verify.ps1` completed with `verify: ok` at 23:35 Sydney time using the isolated `.venv` (Python 3.12.3) and local Node 24.21.0. Results: 1,565 backend tests, 190 frontend unit tests, 29 browser tests, formatting, lint, type checks, build, secret scan and both unchanged-threshold dependency audits passed. `pip check` reported no broken requirements. Locked installation via `npm ci` reported zero vulnerabilities. Earlier failures and their corrections are recorded above; the restored browser test also required newline/format normalization before the final gate.

The final verification record has fingerprint `a2c6dc68f41a9f38a7304dacc582f8cc3192e0494395703449938d18afecf16c` and explicitly retains `paper_trials: false`. Only the two reviewed Studio baselines changed. Existing nonblocking TestClient/calendar deprecations, bundle-size and color-environment notices remain; no check, audit threshold or snapshot tolerance was weakened.

Safety self-review covered adapter paper-account enforcement, session rechecks at authorization/reservation/dispatch, risk and protective-limit sizing, immutable published hashes, one-shot preview identity, duplicate and uncertain-outcome handling, owned exits, cancellation evidence, restart disarming, reconciliation, scoped incident recovery and secret exposure. No outstanding P0/P1 finding remains in this integration review. Automated results do not establish real Gateway fill/protection acceptance.

GitHub main was checked directly after verification and remains `4abf9341af578d5a797e83012191efd8f27c2a20`. This slice creates a local integration commit only. No broker connection, order, service restart or GitHub publication was performed. Publication review and supervised paper qualification are the next slices.
