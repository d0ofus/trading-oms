# Trading OMS

A self-hosted Windows workspace for reusable strategies, IBKR market data across asset classes, US equity paper execution and BTC/ETH PAXOS long-only paper execution. One address, **http://127.0.0.1:8000**. Live trading is excluded.

The current application has five workspaces: Trading Desk, Strategy Studio, Testing, Activity and Settings. Guided forms and an editable React Flow canvas share one executable strategy graph. Publishing creates an immutable version; explicit session arming authorizes new entries. Draft changes never change a running contract.

The paper service uses the official asynchronous IBKR API behind an adapter, a single engine owner, Decimal calculations, exchange sessions, durable order identities and an append-only SQLite event ledger. It blocks entries on stale data, unknown orders, missing protection, emergency stop, expired authorization or failed reconciliation. Application restart restores monitoring with new entries disarmed.

Runs can be armed for a selected future exchange date. Strategies default to regular hours, with an explicit supervised pre/post-market option and broker-held stop-limit protection. Settings includes a reviewed one-share acknowledgement/cancellation test that needs fresh quotes but no price-crossing signal. Flat runs can be removed from Active runs while preserving audit history. See the [flexible-session implementation plan](docs/execplans/paper-diagnostics-and-flexible-sessions.md) and [current operator guide](docs/PAPER_OPERATOR_GUIDE.md).

## Start here

Read [Windows setup and first paper test](GETTING_STARTED_WINDOWS.md), followed by the [operator guide](docs/PAPER_OPERATOR_GUIDE.md). The [implementation plan](docs/execplans/professional-paper-workspace.md) records scope and evidence; [dependency pins](docs/PAPER_DEPENDENCIES.json) record the SDK and selected Gateway artifact.

```powershell
python -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend exec -- playwright install chromium
.\scripts\verify.ps1
.\scripts\install-paper-sdk.ps1
.\scripts\paper-preflight.ps1
.\scripts\start-workspace.ps1
```

Verification is offline with respect to the broker. Dependency audits use package-advisory services. Tests never transmit broker orders. Preflight checks the loopback TCP endpoint without an API login or order submission. The [minimal paper workflow](docs/MINIMAL_PAPER_WORKFLOW.md) automates paper verification, subscriptions, warm-up and reconciliation. One final human authorization remains; new schema-8 stock runs use explicit quantities with optional monetary ceilings.

The [IDEALPRO paper-FX guide](docs/IDEALPRO_PAPER_FX.md) covers explicit schema-9 FX copies,
Midpoint/Bid/Ask signals, funded base-currency sizing and currency ownership. FX starts
with Previous-minute Long-only Breakout; existing publications are not converted in place.

For reusable stock/ETF strategies, native currencies, verified lot rules and exchange
sessions, follow the [schema-7 stock guide](docs/REUSABLE_STOCK_GUIDE.md).

Follow the [unified workspace guide](docs/UNIFIED_WORKSPACE_GUIDE.md) for migration,
contract discovery, reusable strategy preparation and crypto paper execution. Both
legacy launchers now open this same application. The former crypto simulator is
archived; its records are never reinterpreted as broker positions or qualification.

The [previous-minute OCA breakout](docs/OCA_BREAKOUT_GUIDE.md) retains opposing native
stock stops and fixed 1% fill-based protection. The separately named long-only PAXOS
template sends paper market orders and monitors its stop locally. Crypto starts with
a supervised $25 ceiling; actual account availability requires broker acceptance.
Local protection cannot execute while the application or connection is unavailable.

Daily P/L remains informational. Gateway 2119 is informational, and reconciliation
separates currency/FX positions from securities. Disconnects retain positions, retry
connection and notify the operator; new entries require fresh manual arming.

See [watchdog recovery, quiet markets and bounded history](docs/WORKSPACE_HEALTH_AND_CAPACITY.md)
for heartbeat readiness, quiet-trade waiting, audit search/pagination, memory limits
and repeatable capacity probes. Quiet Last trades preserve authorization while
stale observations continue to block new entries.

## Safety and release status

The repository contains a **paper-capable implementation**, not completed paper acceptance. Automated broker doubles and replay results do not establish real Gateway compatibility, market-data entitlement, protective-order behavior or unattended reliability. Those require the supervised trials and five consecutive accepted sessions in the operator guide. The application records these evidence categories separately and gates expanded/unattended arming.

Gateway credentials stay in Gateway. Monitoring secrets and the local browser-launch key use Windows Credential Manager. The API and Gateway endpoint are loopback-only. No live endpoint setting or live-mode control exists. Never change Gateway's paper port to point at a live login.

Stop-based sizing is **planned stop risk**; gaps can exceed it. Emergency stop prevents entries and requests cancellation of working entries while retaining owned-position monitoring and protection. An uncertain submission is never automatically resent. Clearing emergency stop does not restore entry authorization.

## Development and state

- Backend: `backend/src/trading_oms_backend/workspace` (FastAPI, SQLite WAL/FULL, official SDK boundary).
- Frontend: `frontend/src/workspace` (React, React Flow, Radix, TanStack Table, React Hook Form).
- Windows state: `%LOCALAPPDATA%\TradingOMS\paper`; replay data: sibling `simulation` directory.
- Archived local simulation: original `%LOCALAPPDATA%\TradingOMS\simulation\live-crypto` is preserved, with a separate provenance-labelled backup under `TradingOMS\archives`.
- Commands: [verification script](scripts/verify.ps1), [workspace launcher](scripts/start-workspace.ps1), [read-only preflight](scripts/paper-preflight.ps1), [restore tool](scripts/restore-paper.ps1).
- Verification includes backend tests, formatting/lint, frontend types/unit tests, production build, browser/visual/accessibility tests, secret and dependency checks.

Keep one checkout on `main`. Disarm and reconcile before changing the running build. Restore into a separate recovery directory; never overlay a running database or replay pending orders from a backup.

Historical simulation modules and review records remain available. The [previous README](docs/history/PRE_WORKSPACE_README.md) describes that baseline, not the new paper service. Supported legacy definitions import into drafts requiring fresh protection review; historical approvals never authorize paper trading. No independent review is claimed by this implementation.

The historical Candidate Slice 062 concrete connector ExecPlan is planning-only: it does not install an SDK or contact IBKR. Its [external review handoff](review/candidate-062/REVIEW_GUIDE.md) and Candidate 063 record remain `not_ready`, not independently reviewed; external-review evidence remains `missing`. They are preserved records. The subsequently approved professional-workspace plan defines the current internal paper gate and does not retroactively certify those records.
