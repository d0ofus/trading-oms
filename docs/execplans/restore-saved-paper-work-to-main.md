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

`main` equals GitHub commit `4abf934`. A stash rooted at `03bef16` contains 44 tracked edits; 187 untracked source, test, documentation, and script files remain. The saved changes include a previous-minute long-only FX paper breakout and other paper-workspace work. Applying them directly to the newer `main` produced broad conflicts. The current checkout's full verification fails because untracked tests expect the saved tracked code.

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
