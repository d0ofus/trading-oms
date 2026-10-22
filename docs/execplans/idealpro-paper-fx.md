# ExecPlan: IDEALPRO spot-FX paper execution

## 1. Goal

Allow a compatible, explicitly published FX strategy to prepare, review and execute
on a qualified IDEALPRO spot-currency pair using live IBKR data and paper orders.
Start acceptance with AUD.USD / CASH / IDEALPRO / conid 14433401, then validate USD
as base currency and non-USD crosses. Qualification is generic by exact contract
identity; a successful AUD.USD trial does not qualify every pair or order structure.

Status: implementation and isolated verification complete; operator-armed broker qualification remains separate. Currency pairs only; Previous-minute Long-only
Breakout first. Signal source is a published Strategy Setting (Midpoint default,
Bid or Ask alternatives); breakout is strictly above the previous complete minute's
unrounded high. Entry is BUY MKT / IOC; funding uses existing usable currency funds.
No intentional margin borrowing. The approved conversational plan supersedes earlier
limit-entry and expanded-template proposals. Broker trials remain separately armed.

Preserve navigation, layouts, Strategy Studio drag/drop nodes and connections,
saved preferences and prepare -> review -> arm. Keep one final authorization.

## 2. Non-goals

- Live-money transmission, new credentials or changes to IBKR account permissions.
- Removing the stock guard and sending CASH orders through stock execution.
- Silently converting a published trade-based strategy to quote-based signals.
- Automatic leverage, borrowing, unrelated currency conversion, route substitution,
  order splitting to bypass broker size limits, or rejection overrides.
- Assuming all IDEALPRO products are currencies: IBKR also lists spot metals there.
- Promising volume-dependent strategies or unqualified native OCA structures work
  on FX. Unsupported dependencies receive precise compatibility results.

## 3. Safety constraints

Retain the independent adapter paper guard, human authorization, legal quantities,
fresh source and receipt timestamps, current funds, reservations, ownership,
protection, immutable intent identity, duplicate prevention and journal evidence.
No historical bar, sampled watchlist quote or reconnect replay creates an entry.
No outage alone liquidates holdings. Unknown orders or unexplained currency changes
block affected new risk while reconciliation and established protection continue.

Stock/crypto strategies, bindings, profiles and position management remain unchanged.
Optional monetary ceilings stay nullable for the new selected-quantity paper policy;
do not reintroduce the former fixed application ceilings. Broker size/funding rules
and explicitly published optional limits remain binding. Retain five active runs
across the shared workspace, not five additional runs for each asset family.

## 4. Current state

- `stock_policy.compatibility` rejects non-STK contracts, then adds missing stock
  rule messages. The screenshot is this intentional asset restriction; no broker
  rejection or incident is demonstrated by it.
- `stock_strategies.requirements` requires trade ticks for every schema-7/8 stock
  graph. Changing only contract eligibility would leave FX permanently waiting.
- `contracts.capabilities` exposes CASH as data-only, with MIDPOINT candles and
  no qualified execution adapter. Its generic non-stock session is UTC 24x7,
  which is not an adequate executable FX calendar.
- `GatewayData.subscribe` requests quotes and five-second MIDPOINT bars for CASH;
  `history` also uses MIDPOINT. The SDK wrapper currently handles trade ticks but
  has no execution-grade FX midpoint/bid-ask tick callbacks.
- `broker_valuation` subscribes to selected FX quotes solely for stock valuation.
- `PaperStocks._stock_contract` separately rejects non-STK orders at the SDK boundary.
- Reconciliation currently excludes typed CASH rows from run-owned securities.
  FX execution therefore needs a currency allocation ledger, not a stock-position
  comparison or reliance on the editable virtual FX portfolio in TWS.
- Existing readiness/unified/stock-policy/minimal-policy suites passed 57 tests
  during this audit. They do not validate a future FX execution path.

Official evidence consulted on 2026-09-24:

- [IBKR historical data types](https://interactivebrokers.github.io/tws-api/historical_bars.html):
  Forex history supports MIDPOINT/BID/ASK/BID_ASK, not TRADES.
- [IBKR tick-by-tick data](https://interactivebrokers.github.io/tws-api/tick_data.html):
  distinct MidPoint/BidAsk callbacks and a Forex MidPoint request example.
- [Transaction currency](https://www.interactivebrokers.com/campus/glossary-terms/transaction-currency/):
  FX order quantity is expressed in the first currency in the pair.
- [Current spot-currency size table](https://www.interactivebrokers.com/en/trading/forexOrderSize.php):
  AUD standard minimum 25,000; do not treat an older static table as current evidence.
- [FX disclosure](https://gdcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=3024):
  orders below standard IDEALPRO size have separate odd-lot handling. The standard
  size threshold is not a universal claim that every smaller order is rejected.
- [Real versus virtual FX balances](https://www.ibkrguides.com/traderworkstation/fx-portfolio-virtual-fx-position.htm).
- [IBKR FX market schedule](https://www.interactivebrokers.co.uk/es/trading/cacheFX.php):
  Sunday-Friday 17:15-17:00 Eastern with a Forex holiday calendar. Actual current
  contract/broker schedules must govern execution, not this summary alone.
- [Spot currencies](https://www.interactivebrokers.com/en/trading/products-spot-currencies.php):
  currencies and capabilities vary by IBKR affiliate.
- [IDEALPRO products](https://www.interactivebrokers.com/campus/glossary-terms/idealpro/):
  spot currencies and spot metals are distinct products.

## 5. Proposed design

### Contract and strategy qualification

Introduce a separate `spot_fx` capability family and paper adapter behind the existing
interface. Resolve base currency, quote currency, conid, CASH security type and exact
IDEALPRO route; obtain permitted order types, market rules, quantity increments,
standard/odd-lot treatment, schedules and account evidence automatically. Missing
required evidence remains unsupported, with no manual technical questionnaire.
Do not subscribe every available pair; share only current run and valuation dependencies.

Introduce an explicit FX graph schema 9, preserving schemas 3-8.
Create an FX copy with existing node positions/connections and compatible parameters;
publication is explicit. Store price basis and session semantics in the published
definition and hash. Volume, traded-last and volume-weighted indicator requirements
are unavailable unless a separately qualified source supplies their actual meaning.
Quote counts or bid/ask sizes must not masquerade as traded volume. VWAP of the run's
own fills remains valid for protection calculations.

Only Previous-minute Long-only Breakout is executable in this slice. Other graphs
receive a precise unsupported-template explanation. Their future qualification is
outside this implementation. No silent block removal or published-rule conversion.

### Data and signal semantics

Published default: canonical live midpoint observations and MIDPOINT history,
plus synchronized live bid/ask for execution. Use broker MidPoint and BidAsk streams
with independent timestamp/generation evidence; never relabel them execution trades.
Bid and Ask settings use BID/ASK history and matching live observations throughout.
Missing one side, crossed/invalid quotes, old source time, delayed/frozen data or
discontinuity block new decisions. Retain the existing 15-second freshness ceiling.

After arming, wait for the next complete eligible live minute, monitor its unrounded
high in the next minute, and act only on a fresh strict crossing of the approved
price basis. A complete flat minute is eligible. Seal the old candle before checking
the first next-minute observation. Equality never triggers; order tick increments
do not round signal highs.
No synthetic gap filling or historical/reconnect crossings. Expire triggers across
scheduled breaks and wait for a new complete minute after reopening.

Use current broker trading intervals plus a versioned FX calendar, with Eastern-time
DST, weekends, holidays and daily maintenance. Normal closures are waiting states,
not feed incidents. FX has no stock pre-market/regular toggle; show the approved
FX session in the existing control. Do not describe it as uninterrupted 24/7.
Make recovery dependencies asset-aware: FX midpoint/bid-ask health must not wait
for nonexistent trade ticks, while existing stock runs still require real trades.

### Quantity, funds and currency ownership

Display `Quantity (AUD)` for AUD.USD and price as USD per AUD. BUY acquires base
currency and spends quote currency. Use Decimal throughout and separate price/pip
increments from base-unit quantity increments. Never reinterpret `Shares: 1` as a
currency lot, silently raise size to the standard minimum, or assume all pairs have
the same standard or odd-lot policy. Qualify entry and residual exits separately.

Reserve quote-currency funding plus bounded execution costs and fees before entry;
reserve base currency for exits. Keep baseline pre-existing cash, other runs' cash
and valuations separate from run-owned allocations. Serialize competing reservations
across pairs sharing a currency, as well as same-pair order/exit operations.
Compute P/L in quote currency with evidenced conservative conversion to USD where
needed. Preserve fee currency, unsettled balances and settlement constraints.

Adopt a funded execution policy initially: no new negative currency balance or
assumed borrowing entitlement. Account AvailableFunds or a virtual FX position alone
is insufficient. If settlement, margin or credit evidence cannot establish the
approved round trip, report that limitation. Leveraged FX would need a separately
specified credit policy, not an implicit consequence of removing monetary caps.

Maintain a durable double-currency execution ledger from authoritative fills and
commissions, with per-run base allocation and quote cash flow. Reconcile expected
changes against complete real cash snapshots, orders and executions. Detect external
conversions, stock settlements, deposits, fees and late fills without attributing
unrelated cash to a run. Ambiguous changes require reconciliation, not automatic
adoption. Never sell pre-existing AUD or another run's allocation to close this run.

### Orders, protection and recovery

Pin a separate FX execution method in the binding and final review. Entry is a
BUY MKT / IOC for explicit base-currency units, requiring support for that combination.
Retain the 30-second unresolved-submission watchdog and cancellation/reconciliation;
never resend an uncertain order. Reserve estimated fresh-ask cost plus fees before
dispatch; actual market-order cost is not capped. Reconcile actual fills/fees and
hold further entries on an unexpected funding shortfall.
This is explicit new FX behavior, not a modification of the published stock order.
Protect partial fills immediately; cancel the remainder without automatic top-ups.

Keep the published 1% stop distance unless explicitly edited. Calculate from actual
entry fill VWAP and round toward entry. Prefer broker-held FX protection only when
its trigger basis, effective session, parent/partial-fill amendments and residual
quantity support are qualified. Otherwise offer explicitly authorized local bid-based
monitoring within the current review. Never switch automatically after rejection.

For the approved local policy, serialize SELL limit exits at a fresh bid, cancel
unfilled orders on the defined deadline, and reconcile terminal status and late fills
before replacement. Reserve only remaining run-owned base quantity; no overlapping
sells. Retrying can fill below the stop trigger; retain that review term. A rejection
or uncertain outcome blocks replacements, preserves the exit intent and uses current
incident recovery. Capture unsupported residual/odd-lot exits as capability blockers
before entry; never round an owned residual upward to a standard lot.

Respect current routine suspension/resumption policy only when explicitly pinned.
Restart/account change/order uncertainty require fresh entry review. Recover existing
protection independently. Do not clear unrelated incidents or restore old authorization.

### Existing UI

Replace stock-only messages for CASH with one accurate compatibility explanation.
On qualified FX copies, use currency units, signal basis, FX session and native cash
amounts inside the same preparation/review panels. Show `Midpoint signal feed` or
`Ask signal feed`, not `Waiting for execution trades`. Do not show stock board-lot,
shortability, pre-market or fractional-share questions for FX.

Keep Studio interactions, navigation, layouts, filtering and bounded Activity views.
Unsupported strategy inputs name the exact node/dependency. Loading and stale review
behavior retain current polling, cleanup and material-fingerprint checks.

## 6. Data model changes

Add explicit FX schema/requirements, immutable contract capability and execution-policy
revisions, base/quote quantity conventions, market-size treatment, calendar evidence,
signal basis, run currency allocations, cash-flow/commission ledger and reconciliation
baseline revisions. Add distinct live FX observation types with source/request epochs.
Back up before additive migrations. Preserve existing hashes, journals and approvals.
Never migrate an existing stock run or position into FX in place.

## 7. API changes

Extend existing catalog/copy, compatibility, preparation, approval, market-data and
order/position responses with the FX family, base/quote units, price basis, supported
method, funding and missing capabilities. Keep legacy stock fields/endpoints compatible.
Pin FX policy and ledger revisions in approval; older clients cannot authorize FX by
omitting them. Reads and preparation cannot transmit orders. No new mandatory page.

## 8. Test plan

- Reproduce AUD.USD stock-definition rejection without changing legacy behavior.
- FX explicit-copy hashes, canvas parity, midpoint/ask distinction, missing volume,
  custom/MA requirements, explicit opening-session and native-OCA incompatibility.
- AUD.USD, EUR.USD, USD.JPY and EUR.GBP fixtures; reverse valuations, non-USD quote
  currency, quantity/tick precision, standard versus odd-lot policy and residual exits.
- Actual midpoint/bid/ask callbacks, five-second data-only separation, historical
  warm-up, source/receipt freshness, frozen feeds, stale generations and no replay entry.
- Daily breaks, Sunday/Friday boundaries, DST and holidays; normal closed/waiting
  status and new-live-minute requirements after reopening.
- Funded quote balances, fees, settlement, cross-pair reservations, external cash
  changes, partial fills, late commissions and restart ledger reconstruction.
- SDK paper rejection of live/mismatched context; exact FX identity; unknown order,
  rejection, partial fill, cancellation races, stop amendments and no duplicate exits.
- Explicit local-protection terms, fresh authorization, combined verified recovery,
  routine suspension, no restart resumption or outage-driven liquidation.
- Same browser routes/dialogs/canvas/keyboard/table behavior and bounded Activity.
- Separately operator-armed AUD.USD paper trial of a natural signal, then representative
  base-USD and cross-currency trials. Compare fills, protection and actual currency
  changes to TWS. No forced order or assumption that one successful pair proves all.

## 9. Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_workspace_readiness.py backend/tests/test_workspace_unified.py backend/tests/test_workspace_stock_policy.py backend/tests/test_workspace_minimal_policy.py -q
. .\.tmp\activate-dev.ps1
.\scripts\verify.ps1
```

Audit baseline: focused command passed 57 tests. Full `scripts/verify.ps1` passed
with `verify: ok`: 1,254 backend tests, 190 frontend unit tests and 22 browser tests,
plus formatting, lint, type checks, build, secret scan and dependency audits. Logs:
`.tmp/idealpro-audit-verify.log` and `.tmp/idealpro-audit-warnings.log`. Existing
non-failing dependency deprecation, bundle-size and tooling warnings remain. This
pre-implementation baseline did not validate FX execution or broker qualification.
An isolated, side-effect-free compatibility call for the screenshot's AUD.USD identity
reproduced both displayed blockers, `trade_ticks=True` and no qualified adapter;
the original strategy hash remained unchanged.

Implementation progress (24 September 2026):

- Added explicit schema-9 compiler/copy and a separate paper-FX SDK path, FX sessions,
  source-specific bounded data/candles, funded sizing, durable currency allocations,
  protection/exit serialization, and existing-panel integration.
- Focused tests first established copy/hash/source/strict-boundary behavior, then added
  SDK, lifecycle, currency accounting, pending timeout, cancellation/replacement,
  restart/current-account proof and API regressions. The fake broker cannot transmit.
- An initial full gate passed 1,299 backend / 190 frontend / 23 browser tests with
  `verify: ok`. Subsequent edge-case tests found and corrected newest-entry selection
  on a re-armed run and restoration of the published source after restart.
- Final `scripts/verify.ps1` completed successfully with `verify: ok`: **1,305 backend
  tests, 190 frontend unit tests and 23 browser tests**. The backend total includes
  51 new FX regressions. Formatting, lint, type checks, production build, secret scan
  and dependency audits passed. Logs: `.tmp/fx-final-verify.log` and
  `.tmp/fx-final-warnings.log`. Existing non-failing dependency deprecations,
  frontend bundle-size and tooling warnings remain.
- Inspected isolated FX preparation and authorization screenshots. The existing
  dialogs, canvas, navigation and one-action review remain intact. Browser tests
  intercept authorization and use an adapter whose FX submission method raises.
- All runtime account/contract fixtures are synthetic. No application database,
  incidents, Gateway settings or trading state were changed during implementation.
- An actual AUD.USD broker trial was not performed. It requires separate operator
  arming, current account/contract eligibility and a natural breakout. Base-USD and
  cross-currency broker qualifications remain separate from automated fixture coverage.

## 10. Rollback plan

`OMS_DISABLE_FX_ARM=1` disables new FX arming and entry dispatch while preserving existing
FX ledger reconciliation, protection and requested exits. Keep stock/crypto paths
unchanged. Never restore a database over unresolved broker exposure or discard FX
ledger allocations. Database restoration requires a stopped engine and reconciled
paper exposure. Do not allow a rollback flag to strand protection.

## 11. Implementation steps

1. [x] Record approved price source, comparison, product scope, market entry and funding.
2. [x] Add regressions, explicit FX schema/strategy copy and contract compatibility.
3. [x] Implement FX tick ingestion, history dependencies, calendar and readiness.
4. [x] Implement currency reservations, allocations and authoritative reconciliation.
5. [x] Add isolated paper-FX SDK methods, entries, protection, exits and recovery.
6. [x] Connect existing preparation/review/Studio panels; update labels and operator docs.
7. [x] Run verification and isolated browser walkthroughs; record broker-trial limitation.

## 12. Completion criteria

An explicitly published FX graph prepares and authorizes through the existing workflow
on a qualified pair, calculates signals from the published data basis, sizes in correct
currency units, respects broker/funding constraints, and reconciles protected positions
and completed exits without duplicate orders or spending another allocation. Unsupported
pairs/strategies explain the actual missing capability. Full verification passes; broker
trials are recorded separately. Legacy behavior and paper-only guards are preserved.

## 13. Risks and assumptions

The screenshot proves an application compatibility block, not a missing IBKR permission.
This audit has not queried or changed the connected account's FX permissions or current
pair execution eligibility. Broker metadata alone cannot prove future acceptance.
IBKR's standard minimum and smaller-order handling must not be conflated. Current
schedule/reference retrieval and account/affiliate differences need explicit evidence.
Midpoint signals and trade-based stock signals differ; price basis is explicit in
the published FX definition. Metals and other templates are excluded. Existing-funds
validation estimates market-order cost, so a gap/fee can still produce a broker
shortfall that must be reconciled. No guarantee of maximum fill price is made.
