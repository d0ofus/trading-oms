# Reusable stock strategies (schema 7)

For preparation from Desk, Studio and Testing, inactive-run archival, visible search status and combined routine recovery, see [Run preparation and recovery](RUN_PREPARATION_AND_RECOVERY.md).

For automatic US/SEHK rules and routine recovery, see
[Automatic recovery and stock rules](AUTOMATIC_RECOVERY_AND_STOCK_RULES.md).
For pre-market long-only execution and strategy removal, see
[Preparation, pre-market and library controls](PREMARKET_AND_LIBRARY.md).

The normal workspace remains `http://127.0.0.1:8000`. Navigation, canvas blocks,
saved table settings and Prepare -> Review -> Arm are unchanged. New catalog
drafts use schema 7; existing published schemas 3-6 and their hashes are retained.
Use **Create reusable copy** to convert a legacy definition explicitly. Conversion
does not change the original, create a broker order or restore authorization.

## Supported execution

The four existing templates and custom combinations of existing blocks can bind
to qualified IBKR `STK` share-based listings, including stocks, ETFs, ADRs, REITs,
preferred shares and closed-end funds with supported economics. The broker adapter
still rejects live accounts. Existing crypto/simulation records and execution
contracts are separate legacy behavior; schema 7 never interprets them as stocks.

Account permission is necessary but insufficient. Unknown lot rules, unsupported
order types, unavailable trade data, same-day resale restrictions, missing funding,
FX or shortability evidence block the affected execution plan. Broker metadata and
operator evidence are not proof of acceptance. There is no order-type, routing or
protection fallback after a rejection.

## Preparing a stock

1. Start `scripts/start-workspace.ps1` and pair the browser. Browsing works before
   Gateway login. Connect a verified IBKR paper context when ready for data.
2. Resolve the exact contract in Settings and subscribe. Numeric symbols and
   listing/routing exchanges are preserved by contract ID.
3. Publish a schema-7 template or explicit converted copy in Strategy Studio.
4. In the existing Prepare dialog, select the contract. Supported US whole-share
   and SEHK/HKD board-lot rules are derived from broker metadata and official
   references. **Automatic contract rules** is read-only. Funding fee allowances
   are calculated automatically. Missing or conflicting evidence shows a specific
   requirement rather than asking for technical values. Unknown is not equivalent
   to one share; SEHK entry and exit constraints are evaluated separately.
5. Review the native currency, USD ceilings and protection method. Local monitoring
   requires a separate unchecked acknowledgment inside Review & arm. OCA requires
   broker-held protected native OCA and cannot select local cancellation instead.
6. Select the stock risk profile and review. Initial qualification uses at most one
   legal lot within every financial limit. Arm manually only when readiness passes.

Rules are versioned and audited. Updating them invalidates old entry bindings;
prepare a new run. Existing owned positions retain their original exit contract.
Additive rule/profile/copy operations back up the state before first use. No
historical journal, approval or published strategy is rewritten.

## Quantities, currencies and risk

USD limits remain $1,000 entry notional, $10 planned stop risk per run, $50 aggregate
reserved stop risk, $5,000 exposure and five active runs. Lower published limits
remain effective, including the long-only template's $25 default. Copying it does
not increase that amount. Publish an explicitly reviewed higher limit if appropriate;
the program never increases it to satisfy a minimum lot.

Stock sizing uses Decimal quantities and verified increments. Partial fills are not
topped up, and exits never round owned quantities upward. OCA reserves both branches.
Same-contract stock runs share subscriptions but serialize entry/position capacity:
a second run cannot reserve that contract until the earlier reservation is released.
Reconciliation sums owned allocations against the broker contract position.

Fresh native CashBalance and SettledCash observations are required. Non-USD valuation
uses live direct/inverse USD FX bid/ask observations no older than 60 seconds. Assets
are valued conservatively and liabilities conservatively in the other direction.
FX subscriptions are data-only; there is no currency conversion or borrowing.
Some currencies/pairs may remain unavailable and must report a valuation blocker.
Summary values are translated totals, not added together as duplicate currency copies.
Native cash is requested through the account-specific ledger API; both prefixed and
unprefixed ledger cash keys are accepted. A ledger value is never inferred from an
all-account/base-currency aggregate. See [IBKR's per-currency account-value documentation](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/per-currency-account-value-prefix).
Native prices use the verified quote scale (for example minor-unit quoting); strategy
absolute price constants remain in broker quoted units. Daily P/L is informational.

## Sessions and protection

The approved exchange calendar and broker liquid intervals determine sessions.
Broker hours narrow regular hours. The separate explicitly approved pre-market
long-only policy is described in the guide above; ordinary bindings stay regular-only.
Holidays, half-days, DST and scheduled breaks are honored. Opening-range/window time
counts eligible trading minutes across a break. Previous-minute generations expire
at their minute boundary and wait for a fresh complete minute after lunch.

Actual qualifying execution trades remain mandatory. Historical downloads cannot
trigger entries. Price-only strategies do not require relative-volume reference
sessions; volume-dependent inputs remain unavailable when volume is absent.
Execution freshness remains 15 seconds. A quiet market can retain authorization
while waiting; genuine interruption requires recovery and fresh manual arming.

The regular-hours long-only stock template submits shares as a paper market buy, not a crypto cash
budget. It protects actual fill VWAP at 99%, rounded toward entry, cancels an unfilled
remainder, and pauses after the trade or confirmed zero-fill termination. Native
protection amendments preserve existing protection while acknowledgment is pending.
Local stops/targets submit real paper broker exits; only executions create fills.
Local protection cannot execute while the app, data or connection is unavailable.
During a scheduled market break, it is shown as waiting for the session; quiet
trade data during that break does not create a connectivity outage. A genuine
disconnect still suspends local protection and requires recovery.
Outages alone do not liquidate. Existing protection and risk-reducing exits can be
managed independently of entry funding/FX eligibility.

## Xiaomi and external qualification

Resolve **323608988 / 1810 / STK / HKD** and verify the actual exchange, lot and exit
rules through the connected account. The automated fixtures use a **synthetic
200-share lot**; this is not verified Xiaomi metadata or a sizing recommendation.
If one actual legal lot exceeds the selected strategy's USD budget/risk, arming
must remain blocked. No paper account permissions or real lot size were assumed.

Broker qualification requires a separately operator-armed natural breakout: compare
entry, protection acknowledgment, exit and reconciliation with TWS. OCA requires both
long and short cycles plus opposite-entry cancellation and sufficient fresh borrow.
Offline tests never count toward this evidence. Unavailable paper capability, session,
data or legal quantity must be recorded as an unavailable trial, not a passing trial.

Recorded replay retains its existing synthetic USD one-share US-session model for
single-entry strategies and explicitly labels it. It does not qualify HK execution;
the specialized previous-minute templates retain their explicit replay limitation.

## Rollback and verification

Set `OMS_DISABLE_STOCK_ARM=1` before launching to disable new schema-7 arming while
retaining management of existing positions. Do not restore a database over running
execution: stop the owner and reconcile exposure before any backup restoration.

Run `.\scripts\verify.ps1` with the project virtual environment and Node toolchain.
Regression coverage includes schema/hash compatibility, contract rules, FX/lot sizing,
sessions, native/local protection, partial fills, restart, serialized ownership,
bounded Activity behavior and the unchanged preparation/review workflow.
