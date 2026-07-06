# First Autonomous Codex Loop

This file replaces the manual Step 7 workflow with a bounded autonomous one-slice loop.

## One-time setup

Copy this pack into your repo root so these files exist:

- `docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md`
- `docs/SLICES.md`
- `.codex/prompts/07-run-one-approved-slice-autonomously.md`
- `.codex/prompts/08-human-approved-commit.md`
- `.codex/prompts/09-human-approved-next-slice.md`
- `.codex/prompts/10-autonomous-slice-self-check.md`

Commit these files before asking Codex to run Slice 002.

```powershell
git add docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md docs/SLICES.md .codex/prompts/07-run-one-approved-slice-autonomously.md .codex/prompts/08-human-approved-commit.md .codex/prompts/09-human-approved-next-slice.md .codex/prompts/10-autonomous-slice-self-check.md FIRST_AUTONOMOUS_CODEX_LOOP.md
git commit -m "Add autonomous slice protocol"
```

## Start the autonomous Slice 002 loop

Open Codex in VS Code and paste:

```text
Read `.codex/prompts/07-run-one-approved-slice-autonomously.md` and execute it exactly.
```

Codex should then:

1. find Slice 002 in `docs/SLICES.md`;
2. create or switch to `slice-002-backend-frontend-skeleton`;
3. implement the slice;
4. run checks;
5. repair failures;
6. self-review;
7. red-team safety;
8. stop with a `READY FOR HUMAN REVIEW` report.

## Human review after Codex stops

Run:

```powershell
git status
git diff --stat
git diff
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

If you have `make`:

```powershell
make verify
```

## Approve local commit

If the result is acceptable, paste this into Codex:

```text
Read `.codex/prompts/08-human-approved-commit.md` and execute it exactly.
```

## Push after you approve

If you want Codex to push, paste:

```text
APPROVE PUSH.
Push the current slice branch to origin. Do not merge to main.
```

## Approve the next slice

After the PR is merged or after you explicitly accept the slice, paste:

```text
Read `.codex/prompts/09-human-approved-next-slice.md` and execute it exactly.
```

Codex should mark exactly one next slice as approved and then stop. To run that next slice, paste:

```text
Read `.codex/prompts/07-run-one-approved-slice-autonomously.md` and execute it exactly.
```
