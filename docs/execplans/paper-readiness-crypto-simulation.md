# ExecPlan: Paper readiness and live-data crypto simulation

## 1. Goal

Implement the user-approved plan: classify Gateway 2119 correctly, distinguish CASH
positions during reconciliation, remove the workspace daily P/L gate, and provide
an isolated weekend crypto simulator with live Paxos data and full Strategy Studio.

## 2. Non-goals

No live trading, broker crypto order execution, equity extended-hours execution,
changes to historical simulation APIs, fees/liquidity realism, or rewriting old audit records.

## 3. Safety constraints

Paper remains the default. Crypto execution is local only, behind a separate adapter
that cannot send broker orders/cancellations. Gateway remains loopback port 4002 with
a verified paper login. Preserve approval, fresh data/marks, reconciliation, protective
plans, duplicate prevention, journal, emergency stop, notional/exposure/risk limits.
No credentials/account identifiers in stored observations. P/L is informational only.

## 4. Current state

The workspace couples XNYS/STK data and execution to PaperGateway. The engine
classifies 2119 as critical, drops position security type, and gates readiness and
entry on fresh daily P/L. Graph v3 and runtime sizing use whole shares. Immutable
risk profiles include daily_loss. The UI does not expose quote/history diagnostics.

## 5. Proposed design

Correct the existing paper engine first. Journal an idempotent classification
correction only for broker_2119; separate confirmed CASH positions from managed
securities, retaining checks for unknown/external instruments and working orders.
Remove P/L execution gates and subscription-specific blocking errors, preserving
position mark validation. Publish replacement risk profiles without daily_loss.

Add startup-only paper/live_crypto_simulation environments, distinct state/auth/client
IDs, neutral session routes, and a data-only IB transport composed with a durable
local execution adapter. BTC/ETH USD PAXOS contracts supply Decimal increments.
Simulation starts with USD 10000, long only; caps USD 1000 notional/run, USD 10
planned stop risk/run, USD 50 aggregate reserved risk, USD 5000 gross exposure.
Full fills use subsequent fresh bid/ask; local stops model gaps; zero fees/no queue
or liquidity model. Persist ledger/orders/positions and recover disarmed.

Graph v4 adds crypto profiles and fractional sizing while v3 hashes remain stable.
UTC calendar days replace XNYS sessions for crypto across live/replay/warm-up;
preserve all graph fields/timeframes. Fetch 12 UTC days of minute AGGTRADES and
recent fine bars; require ten complete days for relative volume. Never synthesize
missing volume or trigger entries from downloaded history. Keep actual feed health
and indicator readiness explicit. Simulation cannot create paper qualification evidence.

## 6. Data model changes

Add environment identity, simulator balances/working orders, typed position metadata,
informational P/L status, and additive quote/history diagnostics. New profile versions
retire daily_loss without altering originals; original versions remain historical.
New crypto graphs use schema v4; conversion creates copies of v3 documents.

## 7. API changes

Add --environment live_crypto_simulation and scripts/start-crypto-sim.ps1 (port 8001),
environment-bound cookies, neutral workspace session routes, environment metadata,
crypto contract resolution and profile-aware graph/catalog/template responses.
Keep paper session routes compatible. Decimal quantities are strings for crypto.

## 8. Test plan

Regression tests cover 2119 migration, typed CASH reconciliation versus foreign/
unknown positions, optional P/L values/errors and retired profile migration. Test
crypto UTC sessions/rollovers, full graph indicator warm-up, fractional risk sizing,
subsequent quote fills/stops, stale data, idempotency, restart recovery and isolation.
Transport traps prove no broker execution in simulation. Test API/auth/UI environment
identity and diagnostics. Run full gate and a live-data BTC local execution smoke.

## 9. Verification commands

Use .venv/Scripts/python.exe -m pytest for targeted regressions, frontend unit tests,
and ./scripts/verify.ps1 after activating .tmp/activate-dev.ps1.
Run a local-only BTC smoke with all order/cancellation traffic confined to the simulator.

## 10. Rollback plan

Stop the new simulator and revert code if required. Preserve all journals and original
profile versions. Paper state is separate and no crypto order is transmitted to IBKR.
Do not delete user data or roll back an active execution process in place.

## 11. Implementation steps

1. Add regressions and implement readiness/P&L/profile fixes.
2. Add environment/session/graph/Decimal primitives and simulator transport isolation.
3. Integrate engine, API, launcher, UI, diagnostics and recovery.
4. Verify, self-review, fix failures, update operator docs and collect smoke evidence.

Implementation is complete through the UI and operator guides. Self-review additionally
blocked unexpected instrument types, recovered UTC session exits after downtime,
and checked direct SDK/protobuf order methods for data-only isolation. The offline
backend suite passed 858 tests and the frontend suite passed 188 tests. Both browser
flows passed, including authenticated environment isolation and crypto diagnostics.
The dependency audit detected CVE-2026-63374, CVE-2026-64847 and CVE-2026-63349 in
the existing AnyIO 4.14.1 pin. The minimal 4.14.2 patch was installed and pinned;
a repeat pip audit and npm audit report no known vulnerabilities.

Final automated verification on 2026-09-20: `./scripts/verify.ps1` completed with
`verify: ok` (exit 0): 858 backend tests, 188 frontend tests, two browser workflows,
formatting, lint, type checking, production build, secret scan, pip audit and npm
audit. `python -m pip check` reports no broken requirements. The source/build
fingerprint matches the successful gate. Non-blocking warnings remain for the
existing Starlette test-client deprecation and the frontend bundle size.

## 12. Completion criteria

Full verification passes; optional P/L cannot block entries; currency-only accounts
reconcile without hiding external security/orders; crypto works on UTC weekends with
full studio, fractional quantities and local fills; live-data smoke is documented
honestly, separately from broker paper qualification. Any external availability
limitations are reported explicitly.

## 13. Risks and assumptions

User explicitly approved removing the cumulative daily loss circuit breaker; all
other risk controls remain. PAXOS data was available on the user's paper login during
planning, but permissions/farm availability may vary. Quotes/history remain required.
Simulation estimates execution and excludes fees/liquidity; it is not broker acceptance.
Implementation authorized by the user on 2026-09-20.

Live validation on 2026-09-20: a separate read-only connection (client 73)
received connection failure 502. OS listener/process inspection confirmed that
Gateway was no longer running and port 4002 was closed. The existing paper web
process on port 8000 remained running. No broker orders or cancellations were sent.
The operator was asked to reopen and log in to paper Gateway for the BTC smoke.
This is an external prerequisite; it does not substitute for a successful live-feed test.

After the successful full gate, the Sunday BTC smoke was attempted using the
verified build and data-only client 72. Command:
`./.venv/Scripts/python.exe .tmp/crypto_live_smoke.py`.
It stopped before authorization with `RuntimeError: Timed out: handshake` because
Gateway port 4002 remained unavailable. The isolated test ledger contains zero
orders, executions and positions; journal integrity passed and the engine stopped.
Live history warm-up, authorization, fill, protection and exit still require a
connected paper Gateway. Those execution paths passed deterministic offline tests,
but a successful live-feed BTC smoke has not been claimed. No running paper service
was restarted or user trading state altered by the connection probes.

Follow-up on 2026-09-20, 10:30 UTC, during the approved OCA addition: Gateway had
reopened. An isolated data-only connection successfully resolved BTC, downloaded
history, received live Last/bid/ask, and armed the new local template. Four stale
trade gaps prevented an eligible complete live candle during that smoke window;
there were no fills. See [the OCA implementation evidence](previous-minute-oca.md)
for the successful automated gate and the remaining external execution checks.
