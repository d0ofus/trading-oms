# Human-Gated Slice Conveyor

Use this prompt when the user wants Codex to keep moving through the application roadmap with minimal repeated prompting, while still requiring human approval at every safety boundary.

## Core rule

Codex may work autonomously inside exactly one approved slice. Codex must stop and ask the human before:

1. committing;
2. pushing;
3. marking the next slice approved;
4. starting the next slice;
5. adding dependencies that require network access;
6. changing sandbox/security settings;
7. any broker, order, risk, OMS, credential, or deployment-sensitive work beyond the approved slice.

Codex must never merge to `main` unless the user explicitly gives a separate merge instruction. For this project, prefer human-created PRs and GitHub CI before starting the next slice from `main`.

## Non-negotiable safety rules

- No live trading.
- No live order transmission path.
- No real broker credentials.
- No real Telegram tokens.
- No OpenAI, GitHub, database, broker, or production secrets.
- Default mode must remain paper/simulation.
- No IBKR integration until the roadmap explicitly reaches the paper-adapter phase.
- Broker integration must be behind an adapter.
- Risk, OMS, event journal, replay, fake broker, and approval flow come before IBKR.
- If instructions conflict with `AGENTS.md`, follow `AGENTS.md`.

## Required startup behavior

Read these files before acting:

- `AGENTS.md`
- `PLANS.md`
- `docs/CODEX_OPERATING_GUIDE.md`
- `docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md`
- `docs/SLICES.md`
- relevant docs for the current slice

Then inspect the repo state:

```bash
git status --short
git branch --show-current
```

If the working tree contains unrelated user changes, stop and ask for guidance.

## Slice selection behavior

Find the slice in `docs/SLICES.md` with status:

```text
approved_for_autonomous_run
```

Rules:

- If exactly one slice is approved, run only that slice.
- If zero slices are approved, propose the next safest slice and ask the human to reply:

```text
APPROVE NEXT SLICE AND RUN: <slice id and title>
```

Then stop.

- If more than one slice is approved, stop and ask the human to resolve the ambiguity.

## Autonomous run behavior for one approved slice

For the approved slice:

1. Create or switch to the correct slice branch.
2. Create an ExecPlan if the slice is non-trivial or safety-sensitive.
3. Implement only the approved scope.
4. Add or update tests where practical.
5. Run verification.
6. Repair failures for up to three focused cycles.
7. Run self-review.
8. Run trading-safety red-team review.
9. Fix all P0/P1 findings.
10. Update docs when setup, commands, or behavior changes.
11. Update `docs/SLICES.md` to mark the current slice as `ready_for_human_review`.
12. Stop and report.

At the human-review stop, include:

- slice completed;
- files changed;
- verification commands run;
- verification result;
- self-review findings;
- red-team findings;
- safety implications;
- exact manual review commands;
- exact approval choices.

Use this approval block exactly:

```text
READY FOR HUMAN REVIEW

Please review the diff and run verification locally.

Recommended commands:
  git status
  git diff --stat
  git diff
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1

After review, reply with one of:
  APPROVE COMMIT AND PUSH
  REQUEST CHANGES: <specific changes>
  STOP
```

## If the human replies APPROVE COMMIT AND PUSH

Before committing:

1. Re-read `AGENTS.md`.
2. Re-run verification.
3. If verification fails, repair within the approved slice only, then ask for review again.
4. If verification passes, create a clear commit.
5. Push the current slice branch to `origin`.
6. Update `docs/SLICES.md` only if this update is part of the commit or a follow-up commit on the same branch. Do not silently modify `main`.

After pushing, do not start the next slice automatically. Ask the human for the next approval using this block exactly:

```text
PUSH COMPLETE — NEXT SLICE GATE

Open or review the pull request for this branch. Wait for GitHub CI to pass.

After the PR is merged to main, reply with:
  PR MERGED. APPROVE NEXT SLICE AND RUN: <next slice id and title>

If you want a stacked branch before merging the PR, reply with:
  STACKED BRANCH APPROVED. APPROVE NEXT SLICE AND RUN: <next slice id and title>

To stop here, reply:
  STOP
```

## If the human replies PR MERGED. APPROVE NEXT SLICE AND RUN: <slice>

1. Confirm the requested next slice exists in `docs/SLICES.md` or add it if it is the next roadmap slice.
2. Switch to `main`.
3. Pull latest `main`.
4. Ensure working tree is clean.
5. Mark exactly that one slice as `approved_for_autonomous_run` in `docs/SLICES.md`.
6. Commit that slice-status update if needed, or keep it as part of the new slice branch only if the repo convention allows it.
7. Start running that one approved slice using this same protocol.

If `git pull` fails, CI status is unknown, or the working tree is not clean, stop and ask for guidance.

## If the human replies STACKED BRANCH APPROVED. APPROVE NEXT SLICE AND RUN: <slice>

Stacked branches are allowed only with explicit human approval.

1. Keep the current branch lineage.
2. Create a new branch for the next slice from the current state.
3. Clearly report that the new branch is stacked on the previous unmerged branch.
4. Start running that one approved slice using this same protocol.

## If the human replies REQUEST CHANGES

1. Implement only the requested changes within the current slice.
2. Run verification.
3. Self-review the new diff.
4. Stop again at `READY FOR HUMAN REVIEW`.

## If the human replies STOP

Stop. Do not modify files or run additional commands.

## Completion discipline

Never end a slice by saying only that work is done. Always end at one of the explicit gates:

- `READY FOR HUMAN REVIEW`
- `PUSH COMPLETE — NEXT SLICE GATE`
- blocked with a clear reason

