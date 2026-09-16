# Trading OMS

A self-hosted Windows workspace for configuring, testing and operating long-only US stock/ETF strategies through **IB Gateway paper trading**. Live trading is excluded.

The current application has five workspaces: Trading Desk, Strategy Studio, Testing, Activity and Settings. Guided forms and an editable React Flow canvas share one executable strategy graph. Publishing creates an immutable version; explicit session arming authorizes new entries. Draft changes never change a running contract.

The paper service uses the official asynchronous IBKR API behind an adapter, a single engine owner, Decimal calculations, exchange sessions, durable order identities and an append-only SQLite event ledger. It blocks entries on stale data, unknown orders, missing protection, emergency stop, expired authorization or failed reconciliation. Application restart restores monitoring with new entries disarmed.

## Start here

Read [Windows setup and first paper test](GETTING_STARTED_WINDOWS.md), followed by the [operator guide](docs/PAPER_OPERATOR_GUIDE.md). The [implementation plan](docs/execplans/professional-paper-workspace.md) records scope and evidence; [dependency pins](docs/PAPER_DEPENDENCIES.json) record the SDK and selected Gateway artifact.

```powershell
python -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend exec -- playwright install chromium
.\scripts\verify.ps1
.\scripts\install-paper-sdk.ps1
.\scripts\paper-preflight.ps1
.\scripts\start-paper.ps1
```

Verification is offline with respect to the broker. Dependency audits use package-advisory services. Tests never transmit broker orders. Preflight checks the loopback TCP endpoint without an API login or order submission. Setup, verified paper login, subscriptions, warm-up, reconciliation and human arming still happen in the workspace.

## Safety and release status

The repository contains a **paper-capable implementation**, not completed paper acceptance. Automated broker doubles and replay results do not establish real Gateway compatibility, market-data entitlement, protective-order behavior or unattended reliability. Those require the supervised trials and five consecutive accepted sessions in the operator guide. The application records these evidence categories separately and gates expanded/unattended arming.

Gateway credentials stay in Gateway. Monitoring secrets and the local browser-launch key use Windows Credential Manager. The API and Gateway endpoint are loopback-only. No live endpoint setting or live-mode control exists. Never change Gateway's paper port to point at a live login.

Stop-based sizing is **planned stop risk**; gaps can exceed it. Emergency stop prevents entries and requests cancellation of working entries while retaining owned-position monitoring and protection. An uncertain submission is never automatically resent. Clearing emergency stop does not restore entry authorization.

## Development and state

- Backend: `backend/src/trading_oms_backend/workspace` (FastAPI, SQLite WAL/FULL, official SDK boundary).
- Frontend: `frontend/src/workspace` (React, React Flow, Radix, TanStack Table, React Hook Form).
- Windows state: `%LOCALAPPDATA%\TradingOMS\paper`; replay data: sibling `simulation` directory.
- Commands: [verification script](scripts/verify.ps1), [paper launcher](scripts/start-paper.ps1), [read-only preflight](scripts/paper-preflight.ps1), [restore tool](scripts/restore-paper.ps1).
- Verification includes backend tests, formatting/lint, frontend types/unit tests, production build, browser/visual/accessibility tests, secret and dependency checks.

Keep one checkout on `main`. Disarm and reconcile before changing the running build. Restore into a separate recovery directory; never overlay a running database or replay pending orders from a backup.

Historical simulation modules and review records remain available. The [previous README](docs/history/PRE_WORKSPACE_README.md) describes that baseline, not the new paper service. Supported legacy definitions import into drafts requiring fresh protection review; historical approvals never authorize paper trading. No independent review is claimed by this implementation.

The historical Candidate Slice 062 concrete connector ExecPlan is planning-only: it does not install an SDK or contact IBKR. Its [external review handoff](review/candidate-062/REVIEW_GUIDE.md) and Candidate 063 record remain `not_ready`, not independently reviewed; external-review evidence remains `missing`. They are preserved records. The subsequently approved professional-workspace plan defines the current internal paper gate and does not retroactively certify those records.
