# Unified IBKR paper workspace

The normal application uses **http://127.0.0.1:8000** and one paper-account ledger.
No commit or push is needed to test this checkout. Live accounts cannot execute.

## Start and migrate

1. Disarm and reconcile the old paper workspace. It must have no open positions,
   unresolved orders, or working protective children before migration.
2. Stop both old workspace processes. Gateway can remain closed while you start
   and browse the app. When ready to connect, log into paper Gateway on localhost
   port 4002. If using TWS instead, use the paper login and configure its API socket
   port to 4002. Avoid simultaneous TWS/Gateway sessions with the same username.
3. Activate the development environment and launch:

   ```powershell
   . .\.tmp\activate-dev.ps1
   .\scripts\verify.ps1
   .\scripts\start-workspace.ps1
   ```

Both `start-paper.ps1` and `start-crypto-sim.ps1` now call this same launcher. There
is no normal workspace on port 8001. The launcher builds the current frontend and
opens a private local pairing link. Restart a running process after changing code.
The `.tmp` activation helper is specific to this prepared checkout. On another PC,
activate `.venv\Scripts\Activate.ps1` and make the documented Node.js version
available on PATH before running the launcher.

Migration holds both engine locks, checks the paper ledger is flat, and creates a
backup under `%LOCALAPPDATA%\TradingOMS\paper\backups\before-unification` before
recording the change. Local simulation is archived under the sibling `archives`
directory with a provenance manifest. Its original state, including recorded open
positions, is preserved. Neither those positions nor its qualification evidence
become broker positions or paper evidence. The simulation archive is labelled inside
the bundle as well and is rejected by the paper restore command. Historical simulation test APIs remain
separate; their existence does not add a broker execution destination.

If an older saved reconciliation is not ready (for example, positions were recorded
before instrument types were preserved), the app backs up the state and opens with
**Workspace migration pending**. You can navigate the app and edit strategies with
Gateway closed. Execution and broker order recovery remain disabled during migration.
In **Settings**, click **Connect paper Gateway** after logging into Gateway. This
requests a fresh read-only snapshot in the background, taking up to 30 seconds; it
cannot submit or cancel broker orders. Confirmed CASH currency positions can pass;
nonzero security/unknown positions, working orders, live accounts, interrupted or
incomplete snapshots remain blocked. Keep Gateway's API read-only setting enabled
for this check if desired. With Gateway unavailable (including code 502), Settings
reports the failure while the app stays open. Open Gateway and click **Connect paper
Gateway** again; no launcher restart is required. A successful migration starts the
normal connection; then click **Verify paper context** and complete reconciliation.
Runs remain disarmed and require new approval. Do not delete the journal
or edit the migration marker. Unresolved local OMS orders still require reconciliation
with their original execution model and cannot be cleared by this snapshot refresh.

## Find market data

In Settings, connect and verify the paper context. Search by symbol/name, or select
a security type and routing exchange (for example CRYPTO / PAXOS, CASH / IDEALPRO,
or STK / SMART). A direct contract ID can identify a particular derivative. Name
search results require **Resolve contract** before subscription. Review the conid,
currency, routing and primary exchanges, expiry, strike/right, class and multiplier.
IBKR may return multiple results; the application does not select one silently.

Choose **Subscribe & warm up**. The watchlist is independent of the five active-run
limit. Requests are paced; rejected requests show IBKR codes for entitlement, API
support or data limits. Missing data for a data-only instrument does not create an
account-wide incident. Contracts that cannot execute remain useful for observation.

The Desk shows Last, bid, ask, sizes, timestamps, available volume, feed quality,
history progress and expandable 5-second/1-minute/5-minute candle tables. History
uses AGGTRADES for crypto, MIDPOINT for spot FX, and TRADES elsewhere. Unsupported
volume remains unavailable. Sampled quotes do not manufacture trade ticks or volume.
Only complete live trade data can authorize an entry; historical downloads never do.

## Reuse a strategy

New templates publish schema 6 rules without an instrument. In Studio, configure
rules and ceilings, then **Review & publish**. Open that review again and choose
**Prepare published vN**. Select the exact resolved instrument and review sizing.
The new run pins that contract identity, sizing, strategy hash and session policy;
arming additionally journals the chosen risk limits. Another contract or sizing
requires a new run and approval. Existing schema 3–5 definitions and hashes are
unchanged. **Create reusable copy** explicitly creates a separate schema 6 draft.

Select the run on the Desk and choose **Review & arm**. Incompatible contracts show
the missing execution capability. Equity and UTC-session runs are reviewed separately
because their authorizations expire at different boundaries. Daily P/L is informational.

## Execution choices and protection

**Previous 1-minute candle — OCA breakout** retains native opposing stock stop entries,
protected brackets, combined reservations and one completed trade followed by a pause.
It initially executes only on supported US equities during their regular session.
Supervised one-share qualification remains mandatory before expansion. It cannot
execute its short/native-stop structure on PAXOS. See the [OCA guide](OCA_BREAKOUT_GUIDE.md).

**Previous-minute long-only breakout** is a distinct BTC/USD or ETH/USD PAXOS paper
template. After arming it waits for a complete live minute, monitors that high, and
refreshes the local trigger at the next boundary. A later fresh Last crossing submits
one market buy, IOC, with the reviewed USD cash budget. Initial qualification caps
that budget at $25; broker minimums never increase it automatically. Partial fills
count as the trade, with no automatic top-up. A zero-fill terminal entry pauses.

An order in **Awaiting broker acknowledgment** is still pending, not rejected or
filled. Inspect its broker status, identity evidence and cancellation reason in
**Orders & executions**. See [pending orders and recovery](PENDING_ORDER_RECOVERY.md)
for the 30-second deadline and recovery from the former `ApiPending` classification bug.

The persisted local stop uses 99% of actual entry VWAP, rounded toward entry. A fresh
Last at/below that stop requests a market sell, IOC, for the confirmed remaining owned
quantity. Manual, stop and session exits are serialized. After a reconciled close the
run pauses. A completed broker entry/protection-monitoring/exit/reconciliation cycle
qualifies the crypto adapter for the existing approved ceilings: $1,000 notional,
$10 run stop risk, $50 aggregate reserved risk and $5,000 aggregate exposure. Published
strategy/run/profile ceilings can remain lower; expansion requires a reviewed new run.

**Locally monitored protection is not a broker-held stop. It cannot execute while the
application, paper connection or required fresh data is unavailable.** Gaps and market
execution slippage can exceed the 1% trigger distance. Paper crypto availability and
minimums are account-specific; a rejection blocks execution without local-fill fallback.
[IBKR documents crypto market buys using cashQty and market sells using quantity, both IOC.](https://www.interactivebrokers.com/campus/?p=195739&post_type=ibkr-api-page)

## Monitor and recover

Use Desk order/position panels, local protection status, OCA group status and Activity
for broker order IDs, execution observations, reconciliation and incidents. Compare
broker executions with paper TWS Orders/Trades or the broker's trade reports. The old
local simulator's records will never appear as IBKR executions.

Recoverable connection failures retry after 1, 2, 4, 8, 16 and then 30 seconds, with
one connection attempt in progress. Entries lose authorization on interruption.
Existing positions are retained. Reconnect restores exact contract subscriptions,
reconciles orders/executions/positions and repairs history. Local protection resumes
after ownership and fresh data are established. An already requested exit remains
durable; uncertain submissions are reconciled before retrying. Otherwise only fresh
trades evaluate stops. Outages themselves do not liquidate positions. Normal manual,
session or genuine stop exits still apply, including while new entries are disarmed.

Configure Telegram in Settings; Healthchecks is optional for Telegram use. Credentials
stay in Windows Credential Manager. The durable queue sends an initial interruption
notice, five-minute reminders, and recovery after reconciliation. Without configuration,
the same status remains in the UI/journal. Delivery failure cannot cause liquidation.

## Acceptance still requiring an operator

Offline automated tests use isolated doubles and cannot establish PAXOS paper availability.
During an equity session, manually arm a one-share OCA trial and compare both directional
cycles, cancellation, protection and return-to-flat with TWS. For crypto, manually arm
the long-only template with at most $25, inspect the actual broker entry and local stop,
request a close, then compare broker executions and final reconciliation. Record rejected
permissions/minimums as unavailable checks; never substitute local simulated fills.
