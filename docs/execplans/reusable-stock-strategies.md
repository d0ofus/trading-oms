# ExecPlan: Reusable stock strategies with the existing interface

## 1. Goal

Implement the approved stock-only reusable strategy plan: schema 7 for the four current
templates and custom blocks, contract-aware quantities, currencies, sessions and protection,
with Xiaomi 1810 (contract 323608988, HKD) as a non-USD paper qualification candidate.

## 2. Non-goals

No live trading, new asset-family execution, automatic currency conversion/borrowing,
automatic budget increases, new pages, workspace switches, canvas redesign or forced trials.
Existing crypto and schemas 3–6 retain their behavior and evidence.

## 3. Safety constraints

Paper attestation remains at every adapter submission boundary. Preserve immutable strategy
hashes, authorization, durable intents/reservations, actual broker fills, incident recovery,
15-second execution freshness, and existing financial/active-run ceilings. USD remains the
risk currency. Missing lot, session, funding, FX, shortability or protection evidence blocks
new risk. Local protection requires explicit approval. Outages alone never liquidate.

## 4. Current state

Schema 6 projects through US/crypto definitions. Stock execution assumes USD, US sessions
and 1–10 shares; non-crypto contract size defaults are one. Long breakout selects crypto.
The repository contains extensive uncommitted earlier work, which must be preserved.

## 5. Proposed design

Add an isolated stock policy/controller layer with direct schema-7 compilation, requirement
manifests, versioned instrument evidence and immutable execution plans. Resolve contracts
by conid/routing identity. Calculate quantities/values using Decimal and verified quote
scales; use fresh conservative FX conversion and explicit currency funding. Use exchange
calendars plus current broker liquid intervals, including lunch breaks. Integrate existing
order reducers, protection and OCA semantics without changing legacy paths. Reuse current
Prepare Run/Review/Desk components for necessary currency, sizing and capability fields.

## 6. Data model changes

Add versioned stock rule/evidence documents and schema-7 run plans. Currency-aware account
facts, FX observations and execution-plan references are additive. Publish successor risk
profiles; never rewrite original profiles, journal events, approvals or published versions.
Back up state before schema-7 migration metadata is first written.

## 7. API changes

Add authenticated stock compatibility and instrument-rule review operations; extend existing
run preparation/arming with plan revisions and local-protection acknowledgment. Existing
endpoints retain their legacy meaning. Capability/valuation metadata augments responses.

## 8. Test plan

Tests first for schema/hash compatibility, HK/US stock metadata, lots, minor-unit pricing,
FX/funding, session breaks/DST/half-days, all templates, local/broker protection, OCA,
partial/late fills, rejects, concurrent ownership, restart, and paper-only boundaries.
Browser tests retain layout/navigation/canvas and exercise only existing workflows.

## 9. Verification commands

Run focused backend/frontend tests while implementing, then `.\scripts\verify.ps1` after
completed integration stages. Source the existing `.tmp/activate-dev.ps1` toolchain helper.
All automated broker tests use isolated doubles; no production-state manipulation.

## 10. Rollback plan

Disable new schema-7 arming and preserve management of existing owned positions. Restore
backups only with the engine stopped and broker exposure reconciled. Never roll back the
journal over outstanding activity. Existing engines/launchers remain offline-browsable.

## 11. Implementation steps

1. Capture legacy/visual regressions and add stock policy tests.
2. Implement schema 7, contract evidence, sizing/currency/session policy and compatibility.
3. Integrate stock execution, broker metadata, funding/FX observations and recovery.
4. Extend existing API/UI fields, preserving structure and old execution contracts.
5. Add lifecycle, browser and operator documentation; run full verification and self-review.
6. Record external Xiaomi/US paper qualification as passed or unavailable, never inferred.

## 12. Completion criteria

All approved automated behavior passes the verification gate. Legacy hashes and behavior
remain stable. UI layout/workflow is unchanged. Every unsupported or unverified combination
has actionable reasons. Actual paper trials require fresh operator arming and natural
signals; unavailable broker/session/lot-budget conditions are explicitly documented.

## 13. Risks and assumptions

API size metadata may not establish SEHK board lots; official/operator-verified evidence
is required. Broker metadata/WhatIf cannot guarantee acceptance. Currency conversion and
cash funding differ. Native OCA is not replaceable by local cancellation guarantees.
No change can make missing trade data or short-selling permission exist.

Implementation status: code, interface integration and operator documentation implemented;
final full verification passed on 22 September 2026. No production state, arming, broker
execution, settings, commit or push was performed.

Implemented evidence and decisions:

- Added stock strategy/compiler, policy, sessions, market, controller, paper adapter,
  read-only FX valuation and additive profile modules. Schema-7 API bindings pin rules,
  sizing, protection and strategy hashes; conversion creates explicit copies.
- Native funding uses account-specific ledger updates, accepts the optional `$LEDGER-`
  prefix and never treats an aggregate balance as native cash. Live FX observations use
  conservative sides and a 60-second maximum age. Unknown observations block entries.
- Qualify the smallest legal lot; retain the lower $25 long-only strategy definition.
  Same-contract stock runs may share data but reserve entry/position capacity serially.
  No simultaneous conflicting exposure is introduced by removing legacy share caps.
- Actual-fill VWAP protection, partial remainder cancellation, precise odd-lot exits,
  price-scale valuation, local protection recovery and broker-held amendments use the
  existing durable OMS. Initial protection and risk reservations remain in uncertain states.
- Added isolated stock policy/API/execution/session tests and a stock browser workflow.
  Existing legacy browser visual/canvas/replay tests explicitly request schema 6, while
  the new browser test exercises the default schema-7 catalog and HK binding. Existing
  screenshot baselines were not changed by this implementation.
- Focused stock and legacy OCA tests passed together (54 tests); subsequent stock/legacy
  recovery tests passed (52 tests). The first broad run exposed simulation clock coupling;
  keeping the out-of-scope simulator on its original balance path fixed it without relaxing
  the original tests. Two earlier legacy regressions were likewise fixed.
- The retained recorded-replay model is explicitly synthetic USD/US sessions with one
  share; it does not qualify international execution. Specialized previous-minute replay
  remains unavailable as before. Unsupported currencies/calendars/economics remain blocked.
- Operator instructions and limitations are in `docs/REUSABLE_STOCK_GUIDE.md`.
- Final self-review added a scheduled-break regression: local protection waits for
  the qualified session without treating expected trade inactivity as an outage;
  actual disconnection remains a suspension. The final stock/unified focused run
  passed all 39 tests, and Ruff passed after this change.
- Visual review corrected the stock authorization summary to show effective USD
  strategy ceilings separately from risk-profile ceilings. OCA trigger prices use
  the bound contract's native currency and quote scale. The existing dialog and
  canvas layouts remain unchanged. A synthetic account fixture was replaced with
  an unmistakable zero-only placeholder after the secret scan rejected its shape.

Final verification evidence:

- `. .\.tmp\activate-dev.ps1` followed by `.\scripts\verify.ps1`: `verify: ok`.
- Backend: 1,142 tests passed. Frontend: 190 unit tests and 14 browser tests passed.
- Formatting, lint, type checking, compilation, production build and repository
  checks passed. Secret scan passed; Python and npm audits found no known vulnerabilities.
- Existing browser visual baselines, bounded Activity workflows, legacy execution
  behavior and the new stock prepare/review workflow passed together.
- Non-failing tool warnings remain: third-party test/calendar deprecations and the
  frontend bundle-size advisory (approximately 637 kB before gzip).

External acceptance is unavailable in this implementation session: no operator-armed Xiaomi
or US trial was conducted, and actual Xiaomi lot/odd-lot/protection permissions, FX and
funding were not qualified. The 200-share HK fixtures are synthetic, not verified exchange
metadata. Offline evidence never publishes broker qualification or raises a budget.
