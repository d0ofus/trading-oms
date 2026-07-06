# Trading OMS

A production-oriented, self-hosted, semi-automated trading workflow and order-management platform.

## Status

Initial application scaffold.

No trading logic, broker integration, market data, strategy engine, OMS, or order submission exists yet.

## Safety posture

- No live trading.
- No real broker credentials.
- No real Telegram tokens.
- No live order submission path.
- Default mode is paper/simulation.
- IBKR integration will come later as paper-only first.

## Local verification

Install backend dependencies:

```bash
python -m pip install -r backend/requirements-dev.txt
```

Install frontend dependencies:

```bash
npm install --prefix frontend
```

On systems with `make`:

```bash
make verify
```

On Windows without `make`:

```powershell
.\scripts\verify.ps1
```

## Recommended development loop

1. Create a branch.
2. Ask Codex for an ExecPlan.
3. Review and approve the plan.
4. Ask Codex to implement only the approved plan.
5. Run verification.
6. Ask Codex for self-review.
7. Fix P0/P1 issues.
8. Commit and push.
9. Open a PR.

## Important files

- `AGENTS.md`: permanent repo instructions for Codex.
- `PLANS.md`: ExecPlan format.
- `backend/`: minimal FastAPI backend.
- `frontend/`: minimal React TypeScript frontend.
- `.codex/config.toml`: project-scoped Codex defaults.
- `.codex/prompts/`: reusable Codex prompts.
- `docs/CONFIGURATION.md`: safe configuration defaults and validation rules.
- `docs/ROADMAP.md`: staged roadmap.
- `docs/SECURITY_BASELINE.md`: secret and network rules.
