# Trading OMS

A production-oriented, self-hosted, semi-automated trading workflow and order-management platform.

## Status

Initial safety foundation with a backend/frontend scaffold, safe configuration, append-only event journal, deterministic market-data replay reader, local bar builder, first replay-only strategy, structured risk engine, simulation-only fake broker, explicit OMS state machine, local approval tickets, local no-op alerts, a backend-connected read-only UI shell, a typed replay-only Strategy DSL, a local visual workflow builder foundation, a local IBKR paper adapter foundation, deterministic local resilience/chaos tests, an auditable live-readiness checklist gate, typed backend read models, read-only backend API endpoints, a frontend read API client, and deterministic simulation run records for safe inspection workflows.

No live broker integration, production strategy engine, real alert delivery, connected UI trading workflow, or live order submission exists yet.

## Safety posture

- No live trading.
- No real broker credentials.
- No real Telegram tokens.
- No live order submission path.
- Fake broker behavior is local simulation only.
- OMS behavior is local state transition validation only.
- Approval ticket behavior is local decision recording only.
- Alert behavior is local no-op recording and formatting only.
- Simulation run behavior is local lifecycle recording and journaling only.
- Operations shell records are backend-derived read-only inspection data with a safe fallback.
- Backend read models are local read-only inspection summaries only.
- Backend read API endpoints are `GET`-only inspection views backed by local demo read data.
- Frontend read API client calls are `GET`-only and fall back to a safe no-live-trading posture.
- Strategy DSL behavior is local replay-only validation and signal generation only.
- Visual workflow builder behavior is local replay-only DSL preview only.
- IBKR paper adapter behavior is local configuration, state, and order-plan journaling only.
- Resilience/chaos behavior is local event journaling and risk-gate verification only.
- Live-readiness behavior is checklist evaluation and journaling only; it cannot enable live trading.
- Default mode is paper/simulation.
- IBKR transport will come later as paper-only first.

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

Run the backend read API locally:

```bash
python -m uvicorn trading_oms_backend.app:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

Run the frontend UI shell locally in a second terminal:

```bash
npm run dev --prefix frontend
```

The Vite dev server proxies `/api` and `/healthz` to `http://127.0.0.1:8000`.

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
- `docs/ALERTS.md`: local alert intent, no-op dispatch, and formatting behavior.
- `docs/SIMULATION_RUNS.md`: deterministic simulation run lifecycle model.
- `docs/UI_SHELL.md`: read-only frontend operations shell behavior.
- `docs/STRATEGY_DSL.md`: typed replay-only Strategy DSL shape and safety boundary.
- `docs/VISUAL_WORKFLOW_BUILDER.md`: local replay-only visual builder behavior.
- `docs/IBKR_PAPER_ADAPTER.md`: local IBKR paper adapter foundation and safety boundary.
- `docs/RESILIENCE_CHAOS.md`: local reconnect, reconciliation, and chaos-test behavior.
- `docs/LIVE_TRADING_READINESS_CHECKLIST.md`: auditable live-readiness checklist gate.
- `docs/POST_SLICE_018_REVIEW.md`: post-queue planning boundary before any rollout work.
- `docs/PRODUCT_GAP_ANALYSIS.md`: post-Slice-018 product gap map and approval gates.
- `docs/READ_MODELS.md`: typed backend read-model behavior and limitations.
- `docs/READ_API.md`: backend read-only API endpoints and safety boundary.
- `docs/FRONTEND_READ_API_CLIENT.md`: frontend read API client and safe loading states.
- `docs/ROADMAP.md`: staged roadmap.
- `docs/SECURITY_BASELINE.md`: secret and network rules.
