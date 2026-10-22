# Previous-minute OCA breakout

The **Previous 1-minute candle — OCA breakout** template is shared in the unified
Strategy Studio. Its native opposing-stop broker execution is initially available only
for supported US equity paper contracts. PAXOS crypto requires the separately named
**Previous-minute long-only breakout**, with a local trigger and locally monitored stop;
see [the unified guide](UNIFIED_WORKSPACE_GUIDE.md).

## Run locally

No commit or push is needed. Activate the environment, run `.\scripts\verify.ps1`,
then `.\scripts\start-workspace.ps1`. Open the authenticated launcher link at port
8000. In Settings resolve the exact US equity contract and subscribe. In Studio publish
the reusable OCA rules, choose **Prepare published vN**, select the contract and reviewed
sizing, then **Prepare bound run**. Select it on the Desk and choose **Review & arm**.
Begin with one share per branch during the regular equity session.

Monitor OCA group status, orders, positions/protection and Activity. Compare executions
with paper TWS. After a completed trade the run pauses and requires manual re-arming.

## Exact trading behavior

A buy stop-market is placed at the completed candle's high and a sell stop-market
at its low. Entry prices round outward to qualified increments. Invalid/zero ranges,
stale data, or a Last already at/outside either level skip that candle. No order
is placed merely because historical data warmed an indicator.

The first execution chooses long or short. The other entry and its held protective
child are cancelled; an unfilled winning remainder is cancelled too. Refreshing
requires positive terminal observations plus a complete reconciliation before the
old reservation is released. Missing orders are never treated as cancellation proof.
Parent GTD deadlines expire at the next minute boundary; protective orders are GTC.

The fixed protective trigger is 99% of the actual average fill for longs and 101%
for shorts, rounded toward entry to a qualified tick. It is not a trailing stop.
There is no profit target. Stop-market gaps can cause a loss larger than 1%.

Paper brackets have provisional stops based on the entry trigger before release.
The engine amends the existing protective order after confirming fills, retaining
its previous protection until acknowledgment. A partial parent's child may be
cancelled by the broker: replacement protection requires terminal prior legs and a
matching position/execution snapshot. Missing or uncertain protection raises an incident.

## Limits and qualification

The **sum of both pending branches** must fit the run's USD 1,000 notional and USD 10
planned stop-risk ceilings (or tighter chosen limits). Both stock branches use the same whole-share
quantity. Aggregate reserved risk
remains USD 50 and gross exposure USD 5,000. The stock short branch requires fresh sufficient shortable quantity and accepted credit preview. There is no daily P/L gate.

Paper testing starts supervised with one share per branch. Larger profiles require
separate successful long and short paper OCA cycles: opposite cancellation, verified
protection and flat reconciliation. Local simulation never supplies broker qualification.
Fresh sufficient shortable shares and an accepted broker what-if credit preview are
required before staging either paper branch. Unknown/rejected previews block the pair.

Both protected paper brackets are staged before release, using native entry OCA type 1
with block. Stop children belong to separate exit groups. Unsupported/rejected Gateway
structures stop the workflow; there is no unprotected or client-only OCA fallback.
Actual Gateway acceptance remains an operator-armed paper trial during equity hours.

Equity paper uses regular exchange sessions. Restart or data/connection interruption
invalidates new-entry authorization. Existing broker protection is retained. Reconcile
before fresh arming; an outage alone does not liquidate positions.

## Historical simulation and acceptance

The old local simulator supported hypothetical long and short cycles for deterministic
verification. It has been retired from normal launchers. Its full-fill, zero-fee model,
without borrow costs, queues or liquidity, never established PAXOS short capability or
paper acceptance. Existing simulation records are archived with their provenance.

Recorded-tick replay continues to support the existing single-entry templates; paired
execution requires the paper workflow or isolated offline test fixtures. Automated tests
do not establish Gateway acceptance. Operator-armed native paper trials for both long
and short cycles remain mandatory before expansion. See the [original implementation
evidence](execplans/previous-minute-oca.md) and [unified plan](execplans/unified-ibkr-workspace.md).

References: [IBKR native OCA](https://interactivebrokers.github.io/tws-api/oca.html),
[what-if credit preview](https://interactivebrokers.github.io/tws-api/margin.html),
[PAXOS short-sale prohibition](https://gdcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=4488).
