# Codex Operating Guide

## Purpose

Use this guide to work with Codex safely and efficiently on this repository.

The repository is for a safety-first trading workflow and OMS. Treat every trading-related change as safety-critical.

## Recommended local workflow

1. Sync the repo.

```bash
git pull
```

2. Create a branch.

```bash
git switch -c slice-XXX-short-name
```

3. Ask Codex for a plan first for non-trivial work.

```text
Read AGENTS.md, PLANS.md, and docs/CODEX_OPERATING_GUIDE.md.
Create an ExecPlan for <task>.
Do not edit files yet.
```

4. Review and adjust the plan.

5. Ask Codex to implement the approved plan using `.codex/prompts/02-implement-approved-plan.md`.

6. Run verification.

```bash
make verify
```

On Windows without make:

```powershell
.\scripts\verify.ps1
```

7. Ask Codex for self-review using `.codex/prompts/03-self-review.md`.

8. Fix P0/P1 findings.

9. Commit and push.

```bash
git status
git add .
git commit -m "Implement slice XXX"
git push -u origin slice-XXX-short-name
```

10. Open a pull request and wait for CI.

## Good Codex task size

Good:

- Create FastAPI health endpoint and tests.
- Add config model with `LIVE_TRADING_ENABLED` default false.
- Create fake broker interface and tests.
- Create event journal schema and append-only unit tests.

Bad:

- Build the whole OMS.
- Connect to IBKR and place orders.
- Create the full visual strategy builder.
- Make it production ready.

## Plan-first rule

Use an ExecPlan before editing if the task touches:

- trading behavior;
- broker adapters;
- orders;
- fills;
- risk checks;
- approvals;
- event journal;
- database migrations;
- security;
- deployment;
- CI.

## Device-to-device continuation

The durable context lives in the repo:

- `AGENTS.md`
- `PLANS.md`
- `docs/`
- `.codex/prompts/`
- issues and PRs

When switching devices:

```bash
git pull
code .
```

Then ask Codex:

```text
Read AGENTS.md, PLANS.md, docs/ROADMAP.md, and recent git history.
Summarize current state and propose the next safe slice.
```
