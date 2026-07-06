# Prompt 12 — Merge current PR and run next recommended slice

## Purpose

Use this prompt after Codex has finished a slice, pushed the branch, and stopped at the next-slice gate.

This prompt lets the human approve **one combined action**:

```text
merge the current reviewed PR
→ sync local main
→ identify the next recommended slice
→ approve that one next slice
→ create the next slice branch
→ run exactly one autonomous slice
→ stop again at READY FOR HUMAN REVIEW
```

This is still human-gated because the human must explicitly type:

```text
APPROVE MERGE CURRENT PR AND RUN NEXT RECOMMENDED SLICE
```

Do not run this prompt unless that exact approval was given in the current conversation.

## Meaning of approval

The approval phrase means:

1. The human has reviewed the current PR or accepts responsibility for Codex performing the final mechanical merge checks.
2. Codex may merge the current PR into `main` if all hard-stop checks pass.
3. Codex may select the next recommended slice from `docs/SLICES.md`.
4. Codex may approve and run exactly that one next slice.
5. Codex must stop again after the next slice implementation and verification.

The approval phrase does **not** allow:

- live trading;
- broker order submission;
- IBKR implementation unless the slice explicitly says IBKR paper adapter and prerequisites are met;
- secrets;
- bypassing CI;
- bypassing verification;
- starting more than one next slice;
- merging if checks fail;
- force-pushing;
- editing GitHub repository settings;
- changing branch protection rules;
- merging unrelated PRs.

## Required tools

Codex may use GitHub CLI only if available and authenticated:

```bash
gh auth status
```

If GitHub CLI is unavailable, unauthenticated, or blocked by sandbox/network settings, stop and provide manual merge instructions.

## Hard stops

Stop immediately and report the problem if any of these are true:

1. The human did not type the exact approval phrase.
2. Current branch is `main`.
3. Working tree is dirty before merge.
4. There is no open PR for the current branch.
5. PR base branch is not `main`.
6. PR head branch does not match the current local branch.
7. Local HEAD SHA does not match the PR head SHA.
8. PR is draft.
9. PR is not open.
10. Required checks are failing, pending too long, cancelled, or missing.
11. The PR has requested changes.
12. PR is not mergeable.
13. `make verify` or `.\scripts\verify.ps1` fails before merge.
14. `gh pr merge` fails.
15. Local `main` cannot be fast-forwarded after merge.
16. `docs/SLICES.md` is missing or ambiguous.
17. No next pending/queued slice can be identified.
18. The next slice would skip roadmap order.
19. The next slice asks for live trading, real credentials, real broker order submission, or unsafe scope.
20. The next slice requires a human design decision that is not already documented.

## Procedure

### 1. Read project instructions

Read:

- `AGENTS.md`
- `PLANS.md`
- `docs/CODEX_OPERATING_GUIDE.md`
- `docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md`
- `docs/SLICES.md`
- `docs/ROADMAP.md`

### 2. Confirm approval phrase

Confirm the latest human message contains exactly:

```text
APPROVE MERGE CURRENT PR AND RUN NEXT RECOMMENDED SLICE
```

If not, stop and ask for that phrase.

### 3. Inspect current branch and tree

Run:

```bash
git branch --show-current
git status --porcelain
git rev-parse HEAD
```

Stop if the current branch is `main`, the working tree is dirty, or `git rev-parse HEAD` fails.

### 4. Run local verification before merge

On Windows, prefer:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Otherwise run:

```bash
make verify
```

Stop if verification fails.

### 5. Inspect the PR

Use GitHub CLI:

```bash
gh auth status
gh pr view --json number,url,state,isDraft,baseRefName,headRefName,headRefOid,mergeStateStatus,reviewDecision,statusCheckRollup,title
```

Validate:

- `state` is `OPEN`;
- `isDraft` is false;
- `baseRefName` is `main`;
- `headRefName` matches current branch;
- `headRefOid` matches local `HEAD`;
- `reviewDecision` is not `CHANGES_REQUESTED`;
- status checks are successful;
- merge state is mergeable.

If the checks are not clearly successful, stop and show the PR URL.

### 6. Merge current PR

Merge with squash and delete branch:

```bash
gh pr merge <PR_NUMBER> --squash --delete-branch --match-head-commit <LOCAL_HEAD_SHA>
```

Do not use force flags.

If the repository disallows squash merge, stop and explain the available merge methods rather than guessing.

### 7. Sync local main

Run:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --porcelain
```

Stop if the working tree is dirty or `main` cannot be fast-forwarded.

### 8. Identify the next recommended slice

Use `docs/SLICES.md` as the source of truth.

Select the first slice after the just-merged slice whose status is one of:

- `queued`
- `pending`
- `not_started`
- `ready`

Do not select a blocked, completed, skipped, live-trading, or ambiguous slice.

If `docs/SLICES.md` has a different format, infer carefully from the roadmap order and update the file minimally so the selected next slice is explicit.

If there is no clear next slice, stop and recommend one exact approval phrase for the human.

### 9. Announce the selected next slice

Before editing, state:

```text
Selected next slice:
<Slice ID> — <Title>

Reason:
<one short reason>

Safety boundary:
I will run exactly this one slice and stop at READY FOR HUMAN REVIEW.
```

Then continue. The human already approved the next recommended slice through the approval phrase.

### 10. Mark exactly one next slice approved

Update `docs/SLICES.md` minimally so exactly one next slice is marked:

```text
approved_for_autonomous_run
```

Do not mark multiple slices approved.

### 11. Create the next slice branch

Create a branch from updated `main`.

Use the branch name specified in `docs/SLICES.md` if present.

If no branch is specified, use a slug like:

```text
slice-004-append-only-event-journal
```

Run:

```bash
git switch -c <next-slice-branch>
```

### 12. Run one autonomous slice

Read and execute:

```text
.codex/prompts/07-run-one-approved-slice-autonomously.md
```

Run exactly one slice.

### 13. Stop at human review

After implementation, verification, repair cycles, self-review, red-team review, and docs updates, stop with:

```text
READY FOR HUMAN REVIEW
```

Also include:

- merged PR number and URL;
- new slice ID/title;
- new branch name;
- changed files;
- verification commands and results;
- safety implications;
- exact next approval options.

## Final next approval text

At the end of the new slice, include this exact copy/paste block:

```text
After reviewing the diff and CI, reply with one of:

APPROVE COMMIT AND PUSH
REQUEST CHANGES: <specific changes>
STOP
```
