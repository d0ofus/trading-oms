# ExecPlan: Restore saved paper work and publish main

## 1. Goal

Integrate the saved local paper-workspace changes with the current GitHub `main`, verify the combined build, and publish the reviewed result to GitHub `main`. Provide exact operator steps for a supervised IBKR paper FX breakout test.

## 2. Non-goals

- No live-trading capability, account login, broker order, or automatic arming.
- No expansion of strategy behavior beyond reconciling the saved work and incoming `main` commits.
- No claim that broker fill or protective-order qualification has already passed.

## 3. Safety constraints

- Preserve paper-only transport, localhost Gateway binding, human authorization, risk checks, stale-data blocks, unknown-state blocks, duplicate prevention, protection, reconciliation, and append-only audit records.
- Do not add secrets, account identifiers, or private broker data to commits, logs, or screenshots.
- Keep the saved stash intact until the published tree and local work are verified.

## 4. Current state

`main` equals GitHub commit `4abf934`. A stash rooted at `03bef16` contains 44 tracked edits; 187 untracked source, test, documentation, and script files remain. The saved changes include a previous-minute long-only FX paper breakout and other paper-workspace work. Applying them directly to the newer `main` produced broad conflicts. The current checkout's full verification fails because untracked tests expect the saved tracked code.

## 5. Proposed design

Create a local integration branch from the stash's original base. Restore the stash there and add the intended untracked files after inspecting for secrets and generated artifacts. Verify that coherent local snapshot, then merge the two newer `main` commits, resolve each overlap with behavior and safety checks, rerun the full gate, review the publish diff, and fast-forward GitHub `main` only if all required gates pass.

## 6. Data model changes

Preserve only the saved work's additive migrations and event schema. Review migration compatibility with current `main`; do not reset paper state.

## 7. API changes

Preserve the saved paper-workspace API additions. Review route collisions and current `main` endpoints during integration.

## 8. Test plan

Run focused FX candle, policy, broker, execution, protection, recovery, and safety tests, plus the full backend/frontend/e2e verification gate. Check merge conflicts, duplicate routes, paper-only transport, secret scan, and frontend build fingerprint.

## 9. Verification commands

`git diff --check`, `python -m pytest -q backend/tests/test_workspace_fx_broker_candles.py backend/tests/test_workspace_fx_policy.py backend/tests/test_workspace_fx_execution.py`, and `.\scripts\verify.ps1` with `.venv\Scripts` on `PATH`. Confirm `git rev-list --left-right --count main...origin/main` after publication.

## 10. Rollback plan

Keep the original stash and original remote tip recorded. If verification or safety review fails, leave GitHub `main` unchanged and retain the integration branch for repair. Do not rewrite remote history.

## 11. Implementation steps

1. Preserve the current remote tip and create a branch at the stash base.
2. Restore the tracked stash, inspect and stage intended untracked files, scan for secrets, and verify the original local snapshot.
3. Merge current `main`; resolve overlaps and add focused regressions if a merge behavior changes.
4. Run all verification, review trading safety and publication diff.
5. Commit the verified integration, fast-forward local and remote `main`, and record exact paper testing instructions.

## 12. Completion criteria

GitHub `main` contains the saved work and previous upstream commits, full verification passes, no secrets or live-order path are introduced, the original stash remains recoverable, and paper-account initiation steps describe the verified commit.

## 13. Risks and assumptions

The saved work is large and spans broker, risk, OMS, UI, tests, and migrations; historical successful verification does not prove compatibility with the newer GitHub commits. An upstream semantic conflict, secret finding, or failing verification blocks publication until resolved.
