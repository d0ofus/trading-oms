# Internal paper operations and acceptance

This guide applies to the professional workspace in `workspace/`. Historical simulation and review packets describe earlier releases. The current gate is automated verification, recorded code self-review, supervised actual paper trials, then operator acceptance. No independent review, real broker test or five-session acceptance is implied by a passing automated test.

## Session operation

Arming selects one New York exchange date, up to seven calendar days ahead. The default is the next eligible session. You can authorize a future session while the market is closed once Gateway, paper verification, reconciliation, risk and incident checks pass. Data/indicator checks deferred before that session opens remain mandatory at entry. The desk distinguishes waiting for the session, waiting for data, and waiting for a signal. Restart always requires fresh arming.

Strategies default to regular XNYS hours, including holidays and early closes. In Strategy Studio, **Market & session > Execution hours** can select **Regular + pre/post-market**. This uses the broker's contract schedule intersected with 04:00-20:00 America/New_York on exchange trading days; no overnight venue is enabled. Missing or discontinuous broker schedules block extended execution. New entries stop 15 minutes before the selected broker session ends. The published exit setting starts a serialized close at least five minutes before that end. Times appear in New York and your browser's local timezone.

Extended sessions are supervised only and use broker-held GTC stop-limit protection with `outsideRth` on the entry, protection, target and explicit exits. Configure the protective limit offset under **Protective stop & profit target**. A stop-limit can trigger without filling when price gaps through its limit; planned risk is sized to the protective limit and is not a maximum-loss guarantee. Regular-hour versions continue to use stop orders. Old schema-3 versions retain their hashes and regular-hours behavior; **Enable session settings in this draft** upgrades only the editable draft. Publish and prepare a new run to use changed execution settings.

The default smoke profile allows one run and one share. After a protected paper entry, deliberate close and successful reconciliation, the operator may accept supervised expansion. Qualified limits are five distinct symbols/runs, ten shares and $1,000 notional per run, $10 planned stop risk per run, $50 reserved stop risk and $5,000 gross exposure account-wide, a $100 daily loss stop and five entries per run/session. Strategy and custom profile limits may be tighter. Profiles are immutable versions.

Select several runs and review them together. Batch arming succeeds for the whole set or fails for the whole set. Fix or deselect a blocked run. Server checks run again at arming, reservation and dispatch; the UI cannot override a failed check.

Entries are whole-share limit orders using current broker quotes and market increment rules, with a broker GTD deadline bounded by 30 seconds. Brackets transmit the parent and optional target before the final GTC stop. Protective legs use an OCA group with proportional reduction and overfill blocking. The service verifies actual broker identities, quantities, prices, executions, positions and protection. A connected socket alone never means permission to trade.

The daily loss gate uses current broker daily P/L, including unrealized P/L, and conservatively subtracts reported USD costs received today. This can count some costs twice; it cannot silently omit a missing P/L value. Current account facts and reserved capacity constrain sizing.

## Strategies and replay

Drafts autosave with optimistic revision checks and local recovery. A conflicting save preserves the local draft and offers a recovered copy or the latest server draft. Published execution semantics are immutable. Canvas layout changes do not change the semantic hash. A new version needs a new run and authorization; existing positions keep their original exit contract.

Guided configuration and the canvas share typed nodes/edges. Shared calculations remain one node. The catalog includes OHLCV, trade price, prior values, constants, arithmetic, rolling high/low, SMA/EMA, candle/session/relative volume, crossings/comparisons/Boolean groups, opening range, session windows, cooldown and time exits. Sizing and entry lifetime are graph settings. Risk, authorization, journaling and broker access cannot be removed from the graph.

Entry requires a false-to-true condition after warm-up, at most once per candle. A crossing is evaluated against the previous eligible evaluation. `Prior value` means the preceding evaluation, while `prior_close` means a prior completed candle. Completed-candle mode never reads the next candle's OHLCV. Forming EMA is recomputed from completed-bar state. Relative volume compares cumulative volume at matching completed-minute boundaries against ten complete reference sessions.

Replay shares the graph evaluator, signal transitions, Decimal sizing, durable outbox and broker-observation reducer with paper execution. Its broker double uses next-trade fills and a fixed simulated quote spread, with no fee/liquidity model. It is not a broker simulator qualification. Dataset-end positions remain open, and missing intervals are not fabricated. Synthetic practice data is labelled separately. Replay state and orders are stored only under the simulation directory.

## Quick paper connection test

This is an explicit one-shot diagnostic, separate from price-crossing strategy evaluation. It does not require moving prices or historical indicator warm-up. It still requires current bid/ask observations, real-time entitlement, a verified build, paper attestation, reconciliation, current account facts and a clear emergency/incident gate.

1. After a disarmed restart into this build, connect and verify the paper Gateway in Settings. Resolve and subscribe to a symbol. Keep API access on localhost port 4002. Broker credentials remain in Gateway.
2. Open **Settings > Paper connection test** (also linked from Testing). Select the symbol and execution hours, then **Check connection & data**. This operation submits no order and works when the market is closed. A fresh quote can repeat an unchanged price; an old quote is not fresh.
3. During an eligible broker session, choose **Review paper order test**. The preview shows BUY 1 share below bid by the greater of 1% or ten broker increments, a $1 stop distance, and a $0.10 stop-limit offset in extended hours. Prices are rounded down to valid increments. Limits still apply. Disarm other runs and finish outstanding orders/positions first.
4. Review and click **Submit paper test** within 15 seconds, or refresh the preview. Final readiness and price checks run again. A closed session supports connection/data checks only; it cannot submit a held overnight entry.
5. Monitor acknowledgement, cancellation and reconciliation. The application requests cancellation five seconds after acknowledgement; the broker entry deadline is 30 seconds. A cancellation request is not confirmation. `Cancelled verified` requires a flat reconciled result and released reservation. An unknown dispatch is never retried automatically.
6. If filled, open Trading Desk, verify the exact position and protection, and use **Close owned position**. A session-end exit is also retained. Monitoring and protection continue after disarming. This diagnostic does not satisfy the normal strategy-fill/protection qualification gate.

## Strategy naming and removing runs

**Strategy name** is the labelled field at the top of Strategy Studio. It autosaves with the draft. **Operation** uses full descriptions such as **Greater than or equal to**; internal graph codes are unchanged.

To remove a prepared run, select its row in **Trading Desk > Active runs**, then **Remove run** in the details drawer. An unused flat run can be removed immediately. A working entry is disarmed and cancelled; removal stays pending until fresh reconciliation proves the run flat, every order/child terminal, and capacity released. Positions and uncertain orders block removal. Use Close owned position or recovery first. **Run history** retains removed runs and the audit ledger is never erased. A late fill reactivates the run for recovery.

## Interruptions and operator recovery

| Situation | Service behavior | Operator action |
|---|---|---|
| 2119 data service connecting | Informational status; a recovered 2104/2106 observation resolves it. Freshness still independently gates entries | Check data readiness; this message alone is no longer a permanent critical blocker |
| 321 request validation | A genuine broker rejection, with allowlisted reason details when recognized; generic historic text cannot be reconstructed | Open Activity > View incident. If the detail identifies Read-Only API, disarm, disable Read-Only API in the paper Gateway, then Recheck recovery. Otherwise inspect Gateway and repeat the affected setup operation. Mark resolved only after recovery checks pass |
| Engine fault | New entries blocked; preserve exception type, failed operation and code frames without arguments/locals | Repeat the failed operation successfully, allow 30 healthy seconds and reconcile. Legacy faults with no diagnostic detail need a new process and successful setup recheck. Then Mark resolved |
| Temporary Gateway disconnect | Pause entries; bounded reconnect; restore data, repair history and reconcile; never resend unknown dispatch | Watch recovery status. Unchanged valid session authorization can resume only after all checks pass |
| 1100 / 1101 / 1102 / 1300 | Treat lost connectivity/data as a recovery boundary; restore subscriptions as required | Inspect incidents and wait for fresh data/reconciliation; a changed port does not authorize another endpoint |
| Application restart | Restore emergency state and order monitoring; all new entries disarmed | Verify paper context, reconcile and review a fresh session authorization |
| Changed login or unresolved order | Invalidate authorization and block entries | Return to the correct paper login; inspect Gateway and Activity. Do not retry an uncertain order |
| Stale or late data / callback overflow | Block entries, mark gaps and repair history; overflow requires restarting/reconciling | Fix entitlement/connectivity/capacity. Recovery data cannot trigger retrospective entries |
| Partial entry lacks active protection | Cancel remaining entry, await terminal evidence and execution/position agreement; cancel known old sell legs before a durable replacement stop | Supervise Gateway until the exact confirmed position has active protection. Missing acknowledgement is not cancellation proof |
| Conditional/time exit | Serialize an owned-quantity SELL in the same OCA group; retain protection; refresh unfilled limits only after confirmed cancellation | Pending is not filled. Investigate rejections or stale quotes |
| Flat position with leftover sell | Cancel known working sells; retain reservation and block reconciliation until every leg is terminal | Inspect Gateway; never manually resubmit a duplicate replacement |
| Emergency stop | Persist immediately, disarm entries, request entry cancellation; keep protection/monitoring | Review causes before clearing. Clearing requires fresh arming; it does not liquidate positions |
| Watchdog detects missing engine heartbeat | Persist emergency, queue Telegram alert; external Healthchecks heartbeat ceases | Inspect process/Gateway and protective orders. Restart restores monitoring with entries disarmed |

Manual broker edits and externally owned orders/positions are not silently adopted. They block reconciliation. Use the paper account exclusively for this workflow during qualification. Broker corrections replace earlier execution revisions in owned-quantity calculations; contradictory duplicates raise an incident.

If Gateway cannot positively identify the outcome of an interrupted multi-leg transmission, the application stays blocked. Resolve the actual paper orders in Gateway and retain the incident evidence; do not clear local state to manufacture certainty. Daily broker reauthentication and Gateway availability remain external operating requirements.

## Monitoring, backup and restore

Telegram credentials and the Healthchecks URL are stored only in Windows Credential Manager. Broker account identifiers remain transient in the adapter. Logs/events do not include outbound credential URLs or raw broker error messages. The independent watchdog has no broker interface.

Healthchecks receives an empty heartbeat every 30 seconds while the engine is healthy. Configure its external period to one minute and grace to two minutes. Explicit notification tests must pass within 24 hours before unattended arming, alongside a current heartbeat, fresh watchdog and validated restore. A failed monitoring channel disarms unattended entries while preserving positions/protection. Telegram delivery uses a durable retry queue; failed watchdog delivery remains queued for recovery.

The first restart into the flexible-session build backs up existing paper state before additive compatibility updates. Daily backups contain a SQLite snapshot, committed market-data captures and SHA256 manifest. Settings can create a backup and validate restoration into a separate directory. Captures used by decisions and historical ledgers are retained; archive closed-session state/backups deliberately and monitor disk capacity. No automatic deletion of decision evidence occurs.

```powershell
.\scripts\restore-paper.ps1 -Backup '<backup zip path>' -RecoveryDirectory '<new empty recovery directory>'
```

Restoration validates inventory, hashes, database integrity, published hashes and the event chain. It restores emergency stop active and entries disarmed. Never replace a running database, copy only a WAL database file, or resend an intent from an older backup. Reconcile current broker truth before considering any recovery directory for operation. Windows Credential Manager secrets are not included in backups.

## Supervised trials and the five-session gate

1. Complete the first-run flow and one-share trial in the Windows guide. Compare the application's order identity, fill, exact owned quantity and active GTC stop with Gateway. Close the owned position and verify all sell legs are terminal.
2. During another supervised bounded session, interrupt Gateway connectivity without changing the login. Observe blocked entries, subscription/history restoration, reconciliation and automatic resumption only within the original authorization. Repeated callbacks must not create duplicate entries.
3. Restart the application while monitoring a paper position. Confirm the position/protection returns and entries remain disarmed. Demonstrate emergency persistence and the close/cancel pending states. Record broker-side outcomes separately from automated crash tests.
4. After accepting supervised expansion, qualify multi-share partial-fill protection under observation. Actual partial-fill repair evidence is required before multi-share unattended arming. A fake callback cannot satisfy this gate. Do not weaken the gate merely because a particular paper order fills in one piece.
5. Test Telegram delivery, external Healthchecks outage detection, watchdog emergency behavior and backup restoration. Complete the configuration-to-recovery walkthrough and accept unattended trial operation in Settings. This acknowledgement is an operator review, not an independent review claim.
6. Run five consecutive US exchange sessions. The service records real paper unattended session start/end, run count, process continuity, flat terminal state and incident status. Restarted or unresolved sessions are ineligible. Review each eligible session in Settings and attest there are no unresolved P0/P1 defects or unexplained orders/positions. Missing exchange days break the consecutive count. Retain the duration/evidence and your usability observations with the session report.

Both visual strategies and five distinct concurrent symbols must be demonstrated before release acceptance. Time the actual trader workflows after familiarization: template configuration under five minutes; parameter edit/review/publish under two minutes; prepared-session arming and blocker-to-remedy identification under 30 seconds. Automated browser tests establish behavior, not those human task timings.

## Version and dependency provenance

The selected official [IBKR API distribution](https://interactivebrokers.github.io/) is 10.50.2. The selected [Windows offline Gateway](https://www.interactivebrokers.com/en/trading/ibgateway-latest.php) is 10.51.1a. Download scripts reject a changed artifact hash. File hashes and the verified installer signature are recorded in `PAPER_DEPENDENCIES.json`; actual paper handshake and market-data capacity still require operator trials.

The vendor Python setup metadata requests Protobuf 5.29.5. The installer changes only that dependency pin to 5.29.6 to address the [Protobuf denial-of-service advisory](https://github.com/advisories/GHSA-7gcm-g887-7qv7); SDK protocol source is unchanged. All generated SDK Protobuf modules imported locally with the patched runtime. Installed compatibility is checked again before connecting.

Bracket/partial-fill tests follow IBKR's [order submission behavior](https://interactivebrokers.github.io/tws-api/order_submission.html) and [OCA types](https://www.interactivebrokers.com/docs/general/order-types/complex-orders/oca-types). Broker-held protection is subject to broker/session rules; custom exits require a working engine and usable quotes/data. Successful internal paper acceptance confers no live-trading capability.
