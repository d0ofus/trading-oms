# Trading OMS

A production-oriented, self-hosted, semi-automated trading workflow and order-management platform.

## Status

Initial safety foundation with a backend/frontend scaffold, safe configuration, append-only event journal, deterministic market-data replay reader, local bar builder, replay-only strategies including the first product breakout/volume-filter strategy, non-routable order-intent proposals, replay-to-risk-to-approval simulation orchestration, simulation-only approval decision endpoints, approved-order OMS/fake-broker simulation execution, simulated positions with protection alerts, a read-only simulation run detail UI, structured risk engine, simulation-only fake broker, explicit OMS state machine, local approval tickets, local no-op alerts, a backend-connected read-only UI shell, a read-only audit explorer, a simulation-only approval inbox, read-only order and position detail sections, a read-only protection monitoring dashboard, a read-only paper trading operator section, deterministic local audit export bundles, a typed replay-only Strategy DSL, an interactive typed visual workflow editor with backend-validated versioned local definition persistence and deliberate fixed-replay simulation start, restart-safe local workflow-run evidence bound to the append-only journal, a local SQLite persistence foundation, a local IBKR paper adapter foundation, deterministic local resilience/chaos tests, an auditable live-readiness checklist gate, typed backend read models, read-only backend API endpoints, a frontend read API client, and deterministic simulation run records for safe inspection workflows.

No concrete IBKR application-protocol connector, authenticated broker session, production strategy
engine, real alert delivery, production deployment, or live order submission exists.

## Safety posture

- No live trading.
- No real broker credentials.
- No real Telegram tokens.
- No live order submission path.
- Product strategy behavior is replay-only signal generation and cannot create order intents.
- Order-intent proposals are explicitly non-routable and cannot submit orders.
- Simulation orchestration stops at pending approval and cannot execute broker orders.
- Simulation approval endpoints decide local approval tickets only and cannot execute orders.
- Approved-order simulation execution uses only the local fake broker.
- Simulated position protection alerts are local/no-op only.
- Simulation run inspector loads saved workflow-run history through existing read APIs, exposes
  backend-recorded node and journal evidence, and cannot execute actions.
- Saved workflow run start requires an unchanged validated version, fixed local replay, local admin
  authorization, inactive emergency stop, and explicit two-step confirmation. It stops at manual
  approval and adds no broker transport.
- Saved workflow run history persists the exact request and approval-wait evidence locally. Exact
  retry after restart does not rerun; incomplete or contradictory SQLite/JSONL evidence is
  unavailable rather than partially displayed.
- Fake broker behavior is local simulation only.
- OMS behavior is local state transition validation only.
- Approval ticket behavior is local decision recording only.
- Alert behavior is local no-op recording and formatting only.
- Simulation run behavior is local lifecycle recording and journaling only.
- Operations shell records are backend-derived read-only inspection data with a safe fallback.
- Backend read models are local read-only inspection summaries only.
- Backend read API endpoints are `GET`-only inspection views backed by local demo read data.
- Operations read API responses carry explicit provenance; current data is not broker-derived and
  remains externally unverified.
- Frontend read API client calls are `GET`-only and fall back to a safe no-live-trading posture.
- Audit explorer behavior is read-only filtering and detail inspection with secret-shaped text
  redaction.
- Approval inbox behavior records simulation-only approval decisions and cannot execute broker
  orders.
- Order and position detail behavior is read-only inspection of existing read models and linked
  audit records.
- Protection monitoring behavior is read-only visibility into expected protection, exceptions,
  missing-protection states, and local critical/emergency alerts.
- Paper trading operator behavior is read-only paper-state visibility and cannot connect, submit,
  transmit, route, cancel, modify, or configure broker connectivity.
- Paper trading operator data is representative adapter/test-double state, not an authenticated
  IBKR paper session or paper-trading history evidence.
- Audit export behavior is deterministic local JSON output with recursive safety scanning and no
  external delivery.
- Strategy DSL behavior is local replay-only validation and signal generation only.
- Visual workflow editor behavior is typed graph editing, continuous safety validation,
  preview-only simulation DSL compilation, and deliberate backend-validated local definition
  list/load/create/update with optimistic version checks. It has no run, delete, broker,
  credential, arbitrary-code, or live-trading controls.
- Local SQLite persistence behavior includes restart-safe saved-workflow run evidence and local
  journal indexing only; it rejects secrets, live-enabled payloads, broker routing fields, and
  order-transmission-shaped payloads.
- IBKR paper adapter behavior is a paper-only validation boundary with a localhost TCP reachability
  probe, injected connector contracts, callback validation, and journaling. Default contract lookup
  and order submission remain unavailable without a separately implemented connector.
- Resilience/chaos behavior is local event journaling and risk-gate verification only.
- Live-readiness behavior is checklist evaluation and journaling only; it cannot enable live trading.
- The Candidate Slice 061 independent-review packet is an internally prepared, deterministic
  inventory of the exact merged Slice 060 baseline. It remains not independently reviewed,
  reports `not_ready` and `no_go`, and leaves all 14 rollout evidence categories blocking.
- The Candidate Slice 062 concrete connector ExecPlan is planning-only; it selects the official
  native Python TWS API 10.48 design but does not install an SDK or contact IBKR.
- The Candidate Slice 062 external design-review handoff at
  `review/candidate-062/REVIEW_GUIDE.md` is deterministic and bound to the exact merged design. It
  is not independently reviewed: readiness remains `not_ready`, external-review evidence remains
  `missing`, all 14 rollout categories remain blocking, and zero are verified. Candidate 063 still
  requires separate explicit human approval and accepted architecture, trading-safety, and security
  review of every P0/P1 finding.
- Default mode is paper/simulation.
- A concrete IBKR application-protocol connector remains future, separately approved, paper-only
  work. Local TCP reachability and injected test doubles are not paper-session evidence.

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

Initialize the optional local SQLite persistence schema:

```powershell
$env:PYTHONPATH = "backend/src"
python -m trading_oms_backend.local_persistence init --database .tmp/trading-oms.sqlite3
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
- `docs/PRODUCT_STRATEGY.md`: first 5-minute breakout plus 1.5x volume-filter strategy.
- `docs/ORDER_INTENTS.md`: non-routable order-intent proposal model.
- `docs/SIMULATION_ORCHESTRATION.md`: deterministic replay-to-risk-to-approval path.
- `docs/SIMULATION_EXECUTION.md`: approved-order OMS and fake broker simulation execution.
- `docs/SIMULATED_POSITIONS.md`: simulated positions and protection monitoring alerts.
- `docs/SIMULATION_RUN_DETAIL_UI.md`: read-only simulation run detail UI.
- `docs/RISK_ENGINE.md`: structured risk checks and journaled risk decisions.
- `docs/FAKE_BROKER.md`: simulation-only fake broker behavior.
- `docs/OMS_STATE_MACHINE.md`: explicit OMS lifecycle states and transitions.
- `docs/APPROVAL_TICKETS.md`: semi-automatic approval ticket behavior.
- `docs/ALERTS.md`: local alert intent, no-op dispatch, and formatting behavior.
- `docs/SIMULATION_RUNS.md`: deterministic simulation run lifecycle model.
- `docs/UI_SHELL.md`: read-only frontend operations shell behavior.
- `docs/AUDIT_EXPLORER.md`: read-only audit explorer filters, detail view, and redaction boundary.
- `docs/APPROVAL_INBOX.md`: simulation-only approval inbox behavior and idempotency boundary.
- `docs/ORDER_POSITION_DETAILS.md`: read-only order and position detail behavior.
- `docs/PROTECTION_MONITORING.md`: read-only protection dashboard behavior.
- `docs/AUDIT_EXPORT_BUNDLE.md`: deterministic local audit export bundle behavior.
- `docs/STRATEGY_DSL.md`: typed replay-only Strategy DSL shape and safety boundary.
- `docs/VISUAL_WORKFLOW_BUILDER.md`: local replay-only visual builder behavior.
- `docs/LOCAL_PERSISTENCE.md`: local SQLite persistence foundation and safety boundary.
- `docs/IBKR_PAPER_ADAPTER.md`: local IBKR paper adapter foundation and safety boundary.
- `docs/RESILIENCE_CHAOS.md`: local reconnect, reconciliation, and chaos-test behavior.
- `docs/LIVE_TRADING_READINESS_CHECKLIST.md`: auditable live-readiness checklist gate.
- `docs/POST_SLICE_018_REVIEW.md`: post-queue planning boundary before any rollout work.
- `docs/POST_SLICE_059_REVIEW.md`: evidence-backed program closeout, product traceability, and
  blocking follow-up review after Slice 059.
- `docs/PRODUCT_GAP_ANALYSIS.md`: post-Slice-018 product gap map and approval gates.
- `docs/READ_MODELS.md`: typed backend read-model behavior and limitations.
- `docs/READ_API.md`: backend read-only API endpoints and safety boundary.
- `docs/EVIDENCE_PROVENANCE.md`: read API provenance labels and fail-closed readiness evidence.
- `review/candidate-061/REVIEW_GUIDE.md`: human entry point for the immutable Slice 060 review
  packet, its reproduction procedure, and its no-authorization boundary.
- `review/candidate-061/packet.json`: deterministic machine-readable source, dependency, test,
  verification, evidence, traceability, finding, and unresolved-evidence inventory.
- `docs/execplans/candidate-slice-062-ibkr-paper-connector-execplan.md`: official-source-backed,
  planning-only design and entry gates for a future concrete IBKR paper connector.
- `review/candidate-062/REVIEW_GUIDE.md`: immutable Candidate 062 source identities, independent
  architecture/trading-safety/security questions, blocking findings, response procedure, and the
  closed Candidate 063 gate.
- `review/candidate-062/packet.json`: deterministic machine-readable Candidate 062 design-review
  handoff with complete baseline manifests and unresolved evidence.
- `docs/SIMULATION_APPROVAL_API.md`: simulation-only approval decision endpoints.
- `docs/FRONTEND_READ_API_CLIENT.md`: frontend read API client and safe loading states.
- `docs/ROADMAP.md`: staged roadmap.
- `docs/SECURITY_BASELINE.md`: secret and network rules.
