Read these files before editing:

- `AGENTS.md`
- `PLANS.md`
- `docs/CODEX_OPERATING_GUIDE.md`
- `docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md`
- `docs/SLICES.md`
- `docs/ROADMAP.md`

Run exactly one autonomous slice: the slice in `docs/SLICES.md` marked `approved_for_autonomous_run`.

Do not auto-advance to the next slice.
Do not push to remote.
Do not merge to `main`.
Do not add live trading.
Do not add broker order transmission.
Do not add real credentials or secrets.

Process:

1. Identify the single approved slice from `docs/SLICES.md`.
2. If zero or more than one slice is approved, stop and report the issue.
3. Confirm the branch name from the slice entry.
4. Inspect the repo state with `git status`.
5. If the working tree has unrelated uncommitted changes, stop and report.
6. Create or switch to the slice branch.
7. Create an ExecPlan using `PLANS.md` if the slice is complex or safety-critical.
8. Implement only the approved slice scope.
9. Add or update tests first where practical.
10. Run verification:
    - use `make verify` if available;
    - on Windows without `make`, use `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1`.
11. Perform up to three focused repair cycles if verification fails.
12. Self-review the diff for safety, correctness, test coverage, scope creep, and secret leakage.
13. Red-team the diff for trading safety issues.
14. Fix P0 and P1 findings.
15. Run final verification.
16. Update `docs/SLICES.md` so the current slice status becomes `ready_for_human_review` only if verification passes and acceptance criteria are satisfied. If blocked, mark it `blocked` and explain why.
17. Stop and return a `READY FOR HUMAN REVIEW` report using the exact format from `docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md`.

Important:
- You may iterate within the current slice.
- You may not start the next slice.
- You may not hide failures.
- You may not weaken safety requirements to pass tests.
- You may not leave the repo in a state where live trading is possible.
