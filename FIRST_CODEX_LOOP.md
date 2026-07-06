# First Codex Loop

Use this after the starter files are committed and the repo is open in VS Code/Codex.

## Step 1: Ask Codex to inspect the repo

Paste this first:

```text
Read AGENTS.md, PLANS.md, docs/CODEX_OPERATING_GUIDE.md, and docs/ROADMAP.md.

Do not edit files.

Summarize:
1. the project purpose;
2. the non-negotiable safety rules;
3. the standard implementation loop;
4. the current repo state;
5. the next recommended safe slice;
6. any setup problems you notice.
```

## Step 2: Ask Codex for a Slice 002 plan only

Paste this next:

```text
Read AGENTS.md, PLANS.md, docs/CODEX_OPERATING_GUIDE.md, and docs/ROADMAP.md.

Create an ExecPlan for Slice 002: minimal backend/frontend skeleton with real verification commands.

Do not edit files yet.

Goal:
Make the repo ready for application development with a minimal backend, minimal frontend, and real local/CI verification.

Scope:
- backend Python project skeleton;
- FastAPI health endpoint;
- safe config model;
- pytest tests for health/config behavior;
- frontend React TypeScript skeleton;
- frontend lint/typecheck/test command where practical;
- Makefile commands should run real checks where practical;
- CI should run make verify;
- README should explain local setup;
- no broker integration;
- no market data;
- no order submission;
- no IBKR;
- no live trading;
- no secrets.

Acceptance criteria:
1. Backend skeleton exists.
2. Frontend skeleton exists.
3. Health endpoint exists.
4. Config defaults to APP_MODE=paper.
5. LIVE_TRADING_ENABLED defaults to false.
6. make verify runs real checks where practical.
7. CI can run make verify.
8. No code path can transmit broker orders.
9. No secrets are introduced.
10. Docs are updated if setup changes.

Return:
- affected files;
- proposed structure;
- test plan;
- verification commands;
- implementation steps;
- risks and assumptions.
```

## Step 3: Review the plan

Reject or revise the plan if Codex proposes:

- IBKR integration;
- broker order submission;
- real market-data feeds;
- live trading;
- secrets;
- an oversized implementation.

## Step 4: Approve implementation

After you are satisfied with the plan, paste:

```text
Implement the approved Slice 002 ExecPlan.

Follow AGENTS.md strictly.

Add or update tests first where practical.
Run make verify.
If make is unavailable on Windows, run .\scripts\verify.ps1 and explain the difference.
Repair failures up to 3 focused cycles.
Self-review.
Fix P0/P1 findings.
Update docs.
Summarize:
- files changed;
- checks run;
- verification result;
- safety implications;
- recommended next slice.

Do not add broker integration, market data, order submission, IBKR, live trading, or secrets.
```

## Step 5: Commit after verification passes

```powershell
git status
git add .
git commit -m "Add backend and frontend skeleton"
git push -u origin slice-002-backend-frontend-skeleton
```
