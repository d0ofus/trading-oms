# ExecPlan: Unified IBKR workspace and reusable strategies

## 1. Goal

Implement the approved single-address IBKR paper workspace, broad contract data discovery,
instrument-independent schema 6 strategies, and a BTC/ETH PAXOS long-only paper breakout.

## 2. Non-goals

Live execution, depth, Greeks, new execution support for other asset classes, automatic
liquidation on outages, and interpreting historical local fills as broker evidence.

## 3. Safety constraints

Paper account validation remains mandatory at the adapter boundary. No secrets in files
or logs. Every risk decision, approval, intent, transition, execution and recovery is
journaled. Fresh data, known ownership, funds, risk reservations and explicit authorization
precede entries. Local crypto protection is disclosed and persisted before entry. Unknown
outcomes require reconciliation; interruptions alone never liquidate positions.

## 4. Current state

The uncommitted readiness and OCA implementations use separate startup environments.
Paper supports US stocks; local crypto simulation has independent state and signed fills.
Graph schemas 3–5 bind symbols. Broker discovery and data are restricted by environment.
The existing engine owns authentication, journal, approval, risk and recovery workflows.

## 5. Proposed design

Use one paper engine and address with a shared contract catalog and capability checks.
Keep old strategy semantics and hashes; schema 6 publishes reusable rules and binds a
resolved contract plus sizing and session policy at run creation. Retain native equity
OCA. Add a distinct UTC-session local-trigger breakout sending only paper crypto MKT IOC
cash-budget buys and quantity sells. Serialize exits and recover local protection after
broker ownership reconciliation and fresh data. Use durable, deduplicated outage alerts.

## 6. Data model changes

Add complete contract identity, data source/health, execution capability and protection
metadata. Store immutable run bindings and schema 6 definitions. Persist crypto trigger,
protection and execution state and separate broker qualification. Back up migration state;
preserve all immutable history and archive former simulation state with provenance.

## 7. API changes

Extend contract search with filters and conid, data responses with candles and quality,
run creation with reviewed sizing, and review/workspace responses with capability and
protection details. Add explicit legacy conversion. Add start-workspace.ps1 and redirect
legacy launchers to port 8000. Telegram configuration becomes independent of Healthchecks.

## 8. Test plan

Test contract ambiguity/identity, independent subscriptions, immutable bindings, legacy
hashes/OCA, crypto full/partial/zero fills, rounding, serialized exits, unknown outcomes,
recovery without outage liquidation, notification deduplication, safe migration and no
live/local-fill broker path. Cover UI discovery, preparation, labels and recovery.

## 9. Verification commands

Run focused backend/frontend tests during implementation and .\scripts\verify.ps1 at
completion. Operator-armed equity and PAXOS paper acceptance requires an available broker
and suitable session; record unavailable checks without treating unit tests as acceptance.

## 10. Rollback plan

Stop the new engine, resolve broker exposure, restore the pre-migration state backup and
matching prior code. Never restore historical state over a running or exposed engine.

## 11. Implementation steps

1. Add contract capabilities, schema 6 and immutable runtime bindings with focused tests.
2. Extend broker discovery/data and paper crypto order adapter and execution lifecycle.
3. Integrate reconciliation, protection recovery, pacing and independent notifications.
4. Unify launchers with guarded backup migration and archived simulator provenance.
5. Update Studio, Desk, settings, browser coverage and operator documentation.
6. Run the full gate, review safety paths, and record external checks.

## 12. Completion criteria

All approved behavior is implemented and verified; old histories/hashes preserved; live
accounts rejected; no outage-induced liquidation; unavailable external trials documented.

## 13. Risks and assumptions

PAXOS paper permission is account-specific and not proven by quote access. Crypto stops
are local and unavailable during process/connectivity outages. Initial crypto ceiling is
USD 25, never automatically raised for a broker minimum. Existing modified files must be
preserved. No commit or push is part of this task.

Implementation status: code, browser workflows, launchers and operator documentation
are implemented. The final full verification gate passed on 2026-09-21 AEST.

Final verification: `.\scripts\verify.ps1` exited 0 with `verify: ok`:

- 914 backend tests passed, including 19 unified-workspace tests.
- 188 frontend tests and all 3 browser workflows passed.
- Repository checks, Python formatting/lint/compilation, frontend lint/types/formatting,
  production build, secret scan, pip audit and npm audit passed. Both audits reported
  no known vulnerabilities. The exact source/build fingerprint was recorded.
- Visual baselines were regenerated and inspected. `git diff --check` passed.
- Nonblocking tool warnings remain for the Starlette test client deprecation, Vite's
  bundle-size advisory and pip-audit's recommendation to hash locked dependencies.

An earlier gate correctly rejected an account-shaped synthetic fixture value. The
fixture now uses the repository's zero-prefixed synthetic convention; the secret
scanner was not weakened. No real credentials or account identifiers were introduced.

Implementation evidence:

- Added shared contract capabilities, schema 6 compilation and immutable run bindings;
  legacy strategies retain their original documents and hashes.
- Added a paper-only crypto SDK boundary and durable local-trigger/protection controller;
  cash buys and fractional sells cannot select the old simulator as an execution provider.
- Added typed contract discovery, paced subscriptions, candle-source/health reporting,
  reconnect restoration and durable outage notices independent of Healthchecks.
- Unified the normal launchers and guarded migration under both engine locks. Backups
  precede the migration marker. Simulator archives retain provenance inside the bundle
  and are rejected by the paper restore command.
- Updated preparation, approval, monitoring and recovery views, browser coverage,
  visual baselines and operator guides.

Self-review checked paper-account guards, contract identity, durable reservation before
dispatch, fresh position marks, single-flight reconnects, serialized crypto exits,
unknown-order recovery and absence of liquidation on outages. Review fixes included
legacy reservation identity normalization, external-position migration rejection,
simulation archive classification and distinct local/broker protection labels.

External acceptance remains unavailable as of 2026-09-21 AEST (2026-09-20 UTC): no
Gateway listener was present on localhost port 4002 and the US equity session was
closed. No operator-armed equity or PAXOS paper order, comparison with TWS, real
Telegram delivery or actual user-state migration was performed. Automated SDK doubles
and browser fixtures do not establish account-specific PAXOS paper availability.
The next external slice is the supervised one-share equity trials and at-most-USD-25
PAXOS entry/protection/exit/reconciliation trial described in the operator guide.
