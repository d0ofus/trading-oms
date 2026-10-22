# IDEALPRO spot-currency paper execution

The paper workspace supports an explicit FX version of **Previous-minute Long-only
Breakout**. Select a resolved `CASH` contract routed to `IDEALPRO`. Qualification uses
the pair's identity, currencies, broker quantity/price evidence, order types, current
trading intervals and the versioned spot-currency policy. Metals and other strategy
graphs are outside this execution policy. A successful subscription or metadata lookup
does not establish that the paper account will accept an order.

## Use the existing workflow

1. In Strategy Studio, select a previous-minute long-only strategy. Open **Review &
   publish → Create FX copy**. The new draft is selected automatically; the original
   and all of its published versions remain unchanged.
2. In **Strategy Settings**, choose **Signal price source**: Midpoint (default), Bid,
   or Ask. Publish explicitly. Changing the source requires a new publication and run.
3. Prepare that published version in Studio or Trading Desk. Select the exact pair,
   enter its base-currency quantity and select broker-held or locally monitored
   protection. For AUD.USD, quantity means AUD and price means USD per AUD.
4. Preparation obtains matching subscriptions/history and current account evidence.
   Review the quantity, session, source, market entry, protection and funding terms.
   Use the existing final authorization action when readiness passes.

If an FX strategy is already published, reuse that version. Adopting the current
execution policy does not require another FX copy or publication. New FX preparations
pin `idealpro_broker_candles_v2`; existing runs retain their approved reference policy.

No new page or asset switch is required. Canvas positions, node connections and editing
interactions are preserved. The initial FX template has its existing long-only block;
other graphs are rejected rather than having incompatible nodes removed. Stock and
crypto publications retain their original interpretation.
The existing trade-tick replay format cannot represent FX quote sources; Testing can
prepare the published FX run, but trade-tick replay reports that incompatibility explicitly.

An FX copy preserves existing published financial ceilings. A copy from the older
USD 25 definition still has that ceiling. The newer nullable policy supports explicit
quantity without a monetary ceiling, but it never disables funding, legal quantities,
reservations, five-run capacity or paper-only enforcement. Limits are not silently raised.

## Signal and session semantics

Both the one-minute candle and the live comparison use the published source:
`MIDPOINT`, `BID`, or `ASK`. Forex does not use a traded Last or traded-volume proxy.
Watchlist sampled quotes and historical/repaired candles alone cannot submit entries.

With `idealpro_broker_candles_v2`, an independent persistent IBKR one-minute stream
supplies the immediately preceding completed candle. Its bootstrap can establish
that reference immediately after authorization. A new authorized live tick strictly
above the reference's unrounded high can trigger entry; equality does not trigger.
Missing reference minutes never fall back to older candles. Quiet tick intervals do
not erase completed broker candles. Source and receipt freshness remain 15 seconds.
Expired live evidence, invalid/crossed quotes, connection changes and session
boundaries prevent dispatch. A historical callback may reevaluate retained fresh
authorized tick evidence, but cannot create that evidence.

Legacy `idealpro_funded_fx_v1` bindings retain the earlier requirement for a complete
eligible live minute beginning after authorization. Prepare a new binding to adopt
the broker-candle policy; do not reinterpret a used run's history or authorization.

Current broker intervals are intersected with `idealpro_fx_week_v1`: Sunday through
Friday, with the Eastern-time 17:00–17:15 maintenance break and no Friday/Saturday
evening session. DST and broker-reported holiday closures apply. Missing or expired
schedule evidence blocks authorization. Scheduled closures are waiting conditions.
The original compatible session-exit offset is preserved in the FX copy.

The market-data panel labels the selected signal source and timestamped bid/ask.
The candle viewer shows the same source, identifies IBKR candles and their completion,
and shows volume as unavailable. Recovery follows the selected FX source rather than
waiting for stock execution trades or an unrelated FX price series.

Data requests follow current dependencies. Saved paused, flat stock runs whose
subscriptions have been removed do not start unrelated historical downloads. A run
with an owned position, unresolved order, reservation or outstanding protection/exit
still retains its required data. Required unresolved contracts wait for current
connection evidence instead of repeatedly failing the engine maintenance loop.

Regular-stock, pre-market and FX history share two in-flight requests and the existing
pacing limits. The panel distinguishes initial queues, contract-resolution waits,
pacing, requested streams, receiving data and completed history. A pacing deadline is
shown only while it is in the future. "Retry" means a failed request is being retried;
it does not describe the initial subscription. A missing signal displays Unavailable.
Watchlist bid/ask can arrive before timestamped FX observations; execution readiness
still requires the selected source and both timestamps to satisfy freshness checks.

## Orders, funding and protection

Entry is one paper **BUY MKT / IOC** for the approved base quantity. The adapter does
not substitute a route, order type or time-in-force. Authorization consumption,
funding reservation, order identity and protection intent are durable before dispatch.
Pending submission has a 30-second watchdog; uncertain submissions are never resent.
Partial fills become the trade and the remainder is cancelled, without top-ups.
Completion or a confirmed zero-fill terminal outcome pauses the run.

New runs use [automatic broker credit and quiet-feed authorization](BROKER_CREDIT_AND_QUIET_FX.md).
Preparing a new run adopts that policy without creating another FX strategy copy.
The following cash-only description applies to existing original-policy bindings.

Usable quote cash requires fresh real cash and settled-cash evidence. Reservations
across pairs and stock runs are deducted; other runs' owned currency cannot fund a new
entry. Commission is reserved in the broker-reported account base currency. The
versioned public first-tier estimate reserves both entry and exit, using 0.20 basis
points with a USD 2 equivalent minimum per order. It is an estimate, not a guaranteed
charge. Non-USD reporting and fees require fresh conservative USD conversion evidence.
No currency conversion, credit override or intentional borrowing is introduced.

Market execution can cost more than its pre-dispatch estimate. Actual fills and fees
are reconciled against real currency balances; a shortfall or unexplained cash change
holds new entries. The ledger records pre-existing cash separately from per-run base
allocations and quote flows. TWS's editable virtual FX position is not ownership proof.
On reconnect, current account-specific order/execution evidence must re-establish the
run's ownership before new protection or exit orders can be sent. If broker history
is unavailable, the application keeps a recovery hold rather than adopting cash.

Protection uses actual fill VWAP × 0.99, rounded toward entry to valid broker increments:

- **Broker-held:** a SELL STP with explicit bid/ask trigger method 4, after confirmed
  fills. Partial-fill amendments cancel/reconcile the previous stop before replacement.
- **Local:** a fresh bid at or below the stop persists an exit request and submits a
  SELL LMT at the fresh bid, rounded down, for the remaining owned quantity. Unfilled
  exits are cancelled after ten seconds. Replacement requires terminal cancellation,
  a reconciliation begun after that terminal observation, current ownership and a
  fresh bid. Exits cannot overlap. A 30-second unfilled alert is raised once per intent.

Manual, protective and session-end exits use the same serialized workflow. Rejection
or uncertainty blocks replacement pending recovery. Previously requested exits survive
closures, restart and late executions; an outage alone does not create an exit. Local
protection depends on the application, data and connection. One percent is a trigger
distance, **not a guaranteed loss limit**. The method never changes automatically.

Broker minimum/increment fields govern entry sizing; the versioned smaller-currency
order policy and quantity precision govern residual exits separately from standard
IDEALPRO size thresholds. Unknown constraints remain unsupported, not a universal
one-unit default. Owned residuals are never rounded upward. Broker rejection remains
authoritative, including for a smaller order or its residual protection.

## Records, recovery and rollback

Schema 9 is additive. The store backs up before the first schema-9 write, and explicit
copy creation also backs up state. Existing schemas, hashes, approvals, journal evidence
and positions are retained. The final authorization pins the FX policy revision,
price source, strategy hash, contract, quantity, session, protection and funding currency.
An older client cannot arm FX by omitting these terms.

Routine verified recovery and the explicitly approved same-engine resumption policy
continue to apply. Restart, account change, manual disarm, emergency stop or uncertain
order/protection state requires a fresh entry review. Resumption starts a new live
minute and preserves consumed entries; it never replays a crossing.

Set `OMS_DISABLE_FX_ARM=1` on the execution host to prevent new FX authorization and
entry dispatch. Existing currency reconciliation, protection and requested exits remain
available. `OMS_DISABLE_PAPER_RESUME=1` disables automatic entry resumption. Never restore
a database over unresolved broker exposure; stop the engine and reconcile first.

## Verification and broker qualification

Gateway server 226 uses the pinned SDK's legacy account-summary cancellation format.
Data-only testing showed that its protobuf cancellation left summary subscriptions
active and caused code 322 on later reconciliation snapshots. This compatibility
handling changes only that cancellation message; order encoding and other Gateway
versions retain the SDK's normal negotiation. No TWS setting change is required.

The automated suite uses isolated SDK doubles and synthetic currency balances. Browser
fixtures cannot connect or send broker orders. They cover explicit FX copy/publication,
all three signal sources, currency labels, preparation and one final review.

An actual broker qualification trial remains separate: freshly operator-arm AUD.USD
paper execution during a qualified session and observe the next natural breakout.
Compare entry, stop/exit, commissions and real cash changes with TWS. Record USD-base
and cross-currency trials separately; one successful pair does not qualify every pair.
No order should be forced to obtain a passing result.

## Verifying accepted FX protection

The existing Positions panel and run/order details distinguish **Broker stop active**,
**Checking broker protection**, **Exit in progress**, and **Protection requires attention**.
An accepted `PreSubmitted` stop is held by IBKR pending its trigger; it is eligible
for active verification just like `Submitted`. Verification requires current paper
identity, execution-derived currency ownership, matching stop price/trigger method,
and remaining stop quantity covering the remaining position, without competing sells
or pending cancellation. The badge does not guarantee execution at the stop price.

IDEALPRO CASH orders do not use the stock outside-regular-hours attribute. IBKR may
ignore it (notification 2109); that flag alone does not invalidate FX protection.
All stock session rules remain unchanged.

A completed fully filled callback can report zero total quantity. The application
retains that original observation and verifies effective quantity only from matching
earlier broker acceptance and actual corrected executions. Missing or conflicting
evidence remains unresolved. No intended quantity is treated as a fill.

Message 399 is retained as an unclassified order message, awaiting authoritative
acceptance/rejection evidence rather than automatically cancelling an FX order.
Actual rejections, conflicting evidence and submission deadlines still apply.
The application cannot recover text that older builds discarded. Verified outcomes
resolve applicable restrictions automatically; original diagnostics remain in history.

For the protection-verification correction, deploy only once fresh broker evidence
confirms the run is flat and has no related working/uncertain order or outstanding
operation. Do not restart or alter a working stop to load the correction. The first
additive evidence write takes a database backup. No strategy copy or republication
is required, and no authorization is restored automatically.

Reference policies reviewed on 24 September 2026:
[FX history](https://interactivebrokers.github.io/tws-api/historical_bars.html),
[timestamped streams](https://interactivebrokers.github.io/tws-api/tick_data.html),
[stop trigger methods](https://interactivebrokers.github.io/tws-api/trigger_method_limit.html),
[standard FX sizes](https://www.interactivebrokers.com/en/trading/forexOrderSize.php),
[FX commissions](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php),
[real versus virtual balances](https://www.ibkrguides.com/traderworkstation/fx-portfolio-virtual-fx-position.htm).


## Broker candle execution revision

New preparations select `idealpro_broker_candles_v2` with `paper_buying_power_v1`.
Existing bindings and published hashes remain unchanged. The final authorization
reviews this execution revision; no new strategy publication is needed.

IBKR's persistent one-minute MIDPOINT, BID or ASK stream supplies the exact
preceding completed minute. The 30-minute bootstrap may supply the reference
immediately after authorization. A new timestamped live observation received
after authorization or permitted resumption must strictly exceed that high.
A quiet tick interval does not erase the broker candle. Missing minutes never
fall back to older references. A delayed candle may evaluate retained live
evidence only while that evidence and current bid/ask remain fresh, and the
current selected price still exceeds the reference. Clock alignment, the
15-second source/receipt limits, buying power and all dispatch guards remain.

The candle viewer labels these rows `IBKR MIDPOINT` (or BID/ASK); its current
minute is partial until broker rollover. Reconnect clears current-generation
reference evidence and pending ticks. Historical data alone cannot submit.

Code 10318 is a terminal fractional-quantity validation rejection only when
correlated to an initial, unaccepted submission. An amendment error or conflicting
acceptance/fill remains uncertain. A later 10147 cannot replace a proven rejection.
A previously misclassified rejection is corrected by appended audit evidence only
after a complete post-rejection snapshot and matching dispatch/error history,
without acceptance or executions. The used run stays paused and its entry count
is preserved. Observed fractional refusal is retained for its contract/MKT/IOC
context. Metadata precision does not override that evidence.

Rollback: `OMS_DISABLE_FX_BROKER_CANDLES_ARM=1` blocks new-policy authorization
and entry while preserving protection, reconciliation and exits. Legacy bindings
retain their earlier post-authorization tick-built-minute semantics.
