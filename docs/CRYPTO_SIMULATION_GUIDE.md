# Retired local crypto simulator: historical reference

The normal trading workflow now uses the [unified IBKR paper workspace](UNIFIED_WORKSPACE_GUIDE.md)
at port 8000. `start-crypto-sim.ps1` is a compatibility launcher for that application;
it no longer starts a simulator at port 8001. The instructions below describe the
previous isolated simulator and are retained only to interpret its historical records.
Those records, including hypothetical shorts, are not broker executions or qualification.

# Live Paxos data with local simulated execution

This workspace tests the full Strategy Studio with BTC/USD or ETH/USD on PAXOS,
including weekends. It connects to an IBKR **paper** login for data. All fills,
cancellations, protective stops, balances and positions belong to a local simulator.
No crypto order is sent to IBKR, and these results cannot qualify broker paper execution.

## Start and connect

From the repository root, activate your Python/Node development environment, then run:

```powershell
. .\.tmp\activate-dev.ps1
.\scripts\verify.ps1
.\scripts\start-crypto-sim.ps1
```

The activation helper is specific to the local installation. On another installation,
activate `.venv\Scripts\Activate.ps1` and put the supported Node/npm installation on PATH.
The launcher prefers the repository virtual environment. Verification builds the UI and
records the source fingerprint required to authorize a strategy. Re-run verification
after source changes and restart the application before arming.

The launcher opens an authenticated session at `http://127.0.0.1:8001`. Keep its process
running. Open IB Gateway with the paper login, socket API enabled on localhost port 4002.
**Read-Only API may remain enabled for the simulator.** In Settings, connect and confirm
the paper login. Live account contexts are rejected. Account credentials stay in Gateway.

The simulator uses API client 72, while the equity paper workspace uses client 71.
Its durable state is `%LOCALAPPDATA%\TradingOMS\simulation\live-crypto`; paper state
remains separate. Cookies and local launcher credentials are distinct. A state directory
cannot be reopened under another execution environment.

## Exercise a strategy

1. In Settings, resolve BTC or ETH and choose **Subscribe & warm up**.
2. Inspect Last/bid/ask and their timestamps on the Trading Desk. History download
   completion and fresh-feed readiness are separate. Initial requests are paced.
3. In Strategy Studio, start from a template. Review the symbol, fractional quantity,
   planned stop risk and all entry/exit conditions. All existing blocks and 5-second,
   1-minute and 5-minute candle intervals are available.
4. Publish the version, prepare a run, then review and explicitly arm a supervised
   simulation session. Historical downloads never create retrospective entries.
5. Observe the local entry, protective stop, position and eventual exit on the Desk.
   A condition must transition from false to true after warm-up; an already-true
   condition does not produce an entry merely because you armed it.
6. Use **Close** to request an exit of the owned simulated position, then wait for
   a matching fresh quote and reconciliation. Inspect Activity for the audit trail.

To reuse a stock strategy, export its JSON in Studio's **Strategy import / export**
panel. Import it in the crypto workspace to create a schema-v4 BTC copy. Review the
symbol, sizing and UTC assumptions before publishing. The original version and hash
are preserved. Schema-v3 equity strategies continue to execute under equity rules.

## UTC sessions and history

Crypto sessions are UTC calendar days, including Saturdays and Sundays. Entry windows,
opening ranges and time exits refer to UTC midnight. New authorizations and entries
stop in the last 15 minutes of that daily session; the configured session exit begins
at least five minutes before midnight. Authorization expires at midnight. Data remains
available outside these entry windows, subject to Gateway and exchange availability.

Warm-up requests twelve UTC days of one-minute `AGGTRADES` bars plus the recent hour of
five-second bars. Relative volume needs ten complete reference days. Missing bars are
not replaced with invented volume. Dependent calculations remain unavailable while
other calculations can warm independently. After an interruption, history and buffered
live trades must form a continuous boundary before new entries resume. Stale Last
observations or bid/ask quotes block new entries.

## Limits, P/L and execution assumptions

The local ledger starts with USD 10,000 and persists between launches. Execution is
long-only for existing templates. The [previous-minute OCA template](OCA_BREAKOUT_GUIDE.md)
also supports hypothetical, fully cash-secured local shorts. Per-run ceilings are
USD 1,000 notional and USD 10 planned stop risk; aggregate
reserved stop risk is USD 50 and gross exposure is USD 5,000. BTC and ETH permit two
distinct simultaneous symbol runs. Session entry counts and custom tighter limits apply.
Quantity is rounded down using IBKR-reported minimum sizes/increments; values below the
minimum are rejected. Emergency stop, approval, reconciliation and protection still apply.

**There is no daily P/L entry gate.** Broker P/L is informational in paper mode; the
simulator computes its own marked P/L. Missing marks make simulated P/L unavailable,
not zero. The daily simulation baseline resets on the first fully marked observation
of the UTC day. Restarting does not reset cash or positions. Historical daily-loss
profile fields are retained for audit and are unenforced.

Local limit fills require a subsequent fresh eligible quote: buys use the ask and
sells use the bid. Stops trigger on actual Last trades and fill at a subsequent fresh
ask for buys/covers or bid for sells, so gaps can exceed planned stop risk. Fills are
full-size and deterministic;
fees, queue priority and liquidity are not modeled. Protection is local and cannot
execute while the app is stopped or the feed is unavailable. On restart, unfilled
entries are cancelled locally, holdings and protection are recovered, and fresh
authorization is required for new entries. An uncertain broker outcome is never
inferred from simulator state.

Recorded-tick replay remains a separate deterministic exercise with its documented
synthetic spread and next-trade fill model. It does not validate broker execution.
