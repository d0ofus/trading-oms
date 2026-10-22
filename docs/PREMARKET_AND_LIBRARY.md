# Preparation, pre-market paper execution and library removal

Preparation and recovery now use [automatic stock rules and routine recovery](AUTOMATIC_RECOVERY_AND_STOCK_RULES.md).
The manual contract-rule/fee forms described in the original preparation section below
are retained only for historical API compatibility; the current dialog uses a read-only summary.

The workspace remains at `http://127.0.0.1:8000`, with the existing navigation,
canvas and Prepare → Review → Arm workflow. Restart the workspace with
`.\scripts\start-workspace.ps1` after updating. Build the frontend before using
`-SkipBuild`; that switch intentionally serves the existing compiled assets.

## Preparing META or another qualified stock

Choose the exact resolved contract in Prepare a run. The application derives
documented whole-share conventions for supported USD listings on NASDAQ, NYSE and
ARCA. Reported API decimal precision does not grant fractional-order permission:
META's reported `0.0001` does not become the NASDAQ share default. Other exchanges
retain verified rules or show the missing evidence; no board lot is guessed.

The compact summary shows the minimum quantity, increments and compatibility.
Advanced contract rules contains unresolved fields and manual overrides. Only
capabilities relevant to this strategy/protection are shown. A reusable fee
allowance is saved once per native currency and route. Choose it deliberately:
it is a funding reserve, not a commission quote. Automatically derived values
are labelled documented support, distinct from operator evidence and completed
paper qualification. Changing rules invalidates old entry bindings, while
existing positions retain their pinned management policy.

Fixed sizing asks for Shares (or Shares per branch for OCA). Risk sizing displays
an indicative quantity when fresh prices/valuation exist. Both the notional and
stop-risk ceilings remain necessary. Preparation states exactly why its button
is disabled and can focus missing advanced fields. Missing fresh funds/prices
remain arming requirements; preparation never authorizes an order.

The long-only template still publishes a **USD 25 ceiling**. If one whole share
costs more, preparation explains the minimum required amount. Publish a new
explicitly reviewed ceiling within the existing USD 1,000 notional/USD 10 stop-risk
limits, or choose another suitable instrument. Neither budget nor route changes
automatically. Initial qualification remains the smallest permitted quantity.

## Pre-market + regular hours

Select this session inside the same preparation dialog. It supports only schema-7
Previous-minute Long-only Breakout, whole-share US USD listings, SMART/NASDAQ
routes and locally monitored protection. Other combinations report a blocker.
Regular hours remains the default; existing runs/hashes are unchanged.

Eligible time is the intersection of current broker trading/liquid schedules,
the exchange calendar, and 04:00 Eastern through regular close. DST, holidays
and half-days apply. Stale/missing schedules block execution; resolve the contract
again in Settings to obtain current broker evidence. There is no after-hours or
overnight execution. At 09:30, the previous trigger expires and a new complete live
minute is required. The approved limit/local method continues during regular hours.

Extended `TRADES` history downloads separately with `useRTH=0`. Its status appears
under feed diagnostics and it can be retried independently of successful regular
history. Display candles may include labelled extended history; they never produce
entry signals. Arming waits for history and actual fresh trade/quote observations.
Quote subscription alone proves neither execution support nor permission.

After a qualifying breakout, the engine reserves at the maximum entry price and
submits one paper BUY LMT at the fresh ask, rounded up to the valid price increment.
`outsideRth=True`, TIF `GTD` and a UTC `goodTillDate` enforce the earliest of 30
seconds, the candle trigger expiry and interval end. The entry is not chased.
Partial execution becomes the trade; its unfilled remainder is cancelled without
top-ups. Protection is persisted before dispatch, then updated from confirmed fill
VWAP to 99%, rounded toward entry.

A qualifying stop breach, manual close or session exit persists an exit request.
The engine submits SELL LMT at fresh bid, rounded down, for remaining owned shares
only. After ten unfilled seconds it requests cancellation. Replacement waits for
terminal cancellation, fresh execution/position reconciliation and a fresh bid;
exits never overlap. A rejection requires recovery and an explicit Close action
before retry. Unknown submission outcomes remain blocked until reconciled. After
30 seconds an outstanding-exit incident alerts once; it does not disable the
risk-reducing exit workflow. At closure, unfilled ownership and exit intent persist
until the next eligible session and successful reconciliation.

Review & arm explicitly acknowledges local protection. **1% is the trigger distance,
not a guaranteed loss limit.** Limit orders can remain unfilled; later bids can be
materially lower. Local monitoring cannot execute while the application, market data
or broker connection is unavailable. An interruption itself never requests liquidation;
already-requested exits resume only after recovery. Only broker executions create fills.

The API fields follow IBKR's [Order reference](https://interactivebrokers.github.io/tws-api/classIBApi_1_1Order.html)
(`OutsideRth`, `Tif`, `GoodTillDate`). Acceptance of this exact route/account and
structure still requires a supervised paper trial. No rejection override is used.

## Strategy library removal

Select saved strategies using the library checkboxes and choose **Remove selected**.
One preview displays each action and existing affected runs:

- Unpublished drafts without durable usage are deleted. A minimal audit record and
  tombstone remain. Local recovery data and cached mutation bodies are cleared;
  earlier backups are retained.
- Published or referenced strategies are archived, hidden from normal library and
  new-run selection. Definitions, hashes, approvals, tests and execution history remain.
- **Archived → Restore** returns an archived strategy to the active library. Archived
  strategies cannot be edited/published or used for a new run until restored.

Existing runs, authorizations, orders, protection and subscriptions continue unchanged.
Removing a library entry does not stop trading. Built-in template buttons remain.
Batches are limited to 50 and revalidated transactionally; changed publication,
draft revisions or durable references require another preview. Late autosave cannot
recreate a deleted identity. Mutation responses are idempotent.

## Rollback and qualification

`$env:OMS_DISABLE_PREMARKET_ARM = "1"` before launching disables new pre-market
arming/entries while retaining management of existing positions and requested exits.
Do not roll back code or restore a database over an active execution owner/exposure.
State is backed up before additive persistent policy or removal operations.

Offline verification uses synthetic contracts, accounts and broker observations.
It does not establish META broker acceptance. A separately operator-armed paper
trial must compare the next natural breakout, entry, actual protection-triggered
exit and reconciliation with TWS. Do not force a trade for test completion.
