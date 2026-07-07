# Trading OMS

A production-oriented, self-hosted, semi-automated trading workflow and order-management platform.

## Status

Initial safety foundation with a backend/frontend scaffold, safe configuration, append-only event journal, deterministic market-data replay reader, local bar builder, first replay-only strategy, structured risk engine, simulation-only fake broker, explicit OMS state machine, and local approval tickets.

No live broker integration, production strategy engine, alerts, UI trading workflow, or live order submission exists yet.

## Safety posture

- No live trading.
- No real broker credentials.
- No real Telegram tokens.
- No live order submission path.
- Fake broker behavior is local simulation only.
- OMS behavior is local state transition validation only.
- Approval ticket behavior is local decision recording only.
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
- `docs/EVENT_JOURNAL.md`: append-only audit journal format and guarantees.
- `docs/MARKET_DATA_REPLAY.md`: deterministic local market-data replay format.
- `docs/BAR_BUILDER.md`: deterministic local OHLCV bar builder behavior.
- `docs/REPLAY_STRATEGY.md`: deterministic replay-only strategy behavior.
- `docs/RISK_ENGINE.md`: structured risk checks and journaled risk decisions.
- `docs/FAKE_BROKER.md`: simulation-only fake broker behavior.
- `docs/OMS_STATE_MACHINE.md`: explicit OMS lifecycle states and transitions.
- `docs/APPROVAL_TICKETS.md`: semi-automatic approval ticket behavior.
- `docs/ROADMAP.md`: staged roadmap.
- `docs/SECURITY_BASELINE.md`: secret and network rules.
