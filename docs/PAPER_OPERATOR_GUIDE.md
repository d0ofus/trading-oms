# Internal paper operations and acceptance

New stock/FX runs use [paper account buying power and visible signal outcomes](PAPER_BUYING_POWER_AND_SIGNALS.md). This supersedes native-currency cash and mandatory credit-preview requirements for `paper_buying_power_v1`; older bindings retain their approved policies.

Current monitoring and recovery behavior is defined in [Current operational monitoring](CURRENT_OPERATIONAL_MONITORING.md). It supersedes the historical recovery intervals and acknowledgment workflow described below.

See [Minimal paper workflow](MINIMAL_PAPER_WORKFLOW.md) for schema-8 sizing, automatic preparation, final authorization and routine resumption. It supersedes the legacy monetary caps and manual setup instructions below for newly published schema-8 stock runs. [Automatic recovery and stock preparation](AUTOMATIC_RECOVERY_AND_STOCK_RULES.md) describes contract rules; [Run preparation and recovery](RUN_PREPARATION_AND_RECOVERY.md) describes inactive-run archival and legacy recovery APIs.

Current release: use [the unified IBKR workspace guide](UNIFIED_WORKSPACE_GUIDE.md)
for contract search, reusable templates and the new crypto paper workflow. Both legacy
launchers open port 8000. Stop old engines and reconcile the paper account flat before
first migration. Local PAXOS protection is distinct from broker-held equity protection.

For pending acknowledgment, code 201 rejection diagnostics, and explicit incident
recovery, see [pending paper orders and recovery](PENDING_ORDER_RECOVERY.md).

This guide applies to the professional workspace in `workspace/`. Historical simulation and review packets describe earlier releases. The current gate is automated verification, recorded code self-review, supervised actual paper trials, then operator acceptance. No independent review, real broker test or five-session acceptance is implied by a passing automated test.

## Session operation

Stock execution uses the contract's approved exchange session, including holidays, breaks and early closes. Qualified US whole-share long-only runs may explicitly select pre-market plus regular hours with limit entries and locally monitored protection. Other runs retain their approved regular-session policy. The published entry/exit cutoffs remain effective. The PAXOS long-only template retains UTC calendar days and its existing execution policy.

Legacy smoke/qualified profiles retain one-share qualification and their USD 1,000 notional, USD 10 run risk, USD 50 reserved risk and USD 5,000 exposure ceilings. New schema-8 profiles default to selected quantity and five runs with no monetary ceilings, subject to funding, reservations, legal quantities and optional published limits. One-lot qualification is optional. Profiles are immutable versions; changing a published strategy requires explicit publication and a new run. There is no cumulative daily-loss entry stop.

Select several runs and review them together. Batch arming succeeds for the whole set or fails for the whole set. Fix or deselect a blocked run. Server checks run again at arming, reservation and dispatch; the UI cannot override a failed check.

Existing equity graph entries are whole-share limit orders using current broker quotes and market increment rules, with a broker GTD deadline bounded by 30 seconds. Brackets transmit the parent and optional target before the final GTC stop. Protective legs use an OCA group with proportional reduction and overfill blocking. The previous-minute OCA template instead uses protected native stop-market entry pairs and minute replacement. The PAXOS long-only template uses cash-budget market IOC buys and fractional market IOC sells, with a locally monitored stop. The service verifies actual broker identities, quantities, prices, executions, positions and protection. A connected socket alone never means permission to trade.

Daily P/L is informational, with its value, timestamp and current/stale/unavailable status in Settings. Missing or invalid P/L, a quiet subscription, subscription-specific errors and losses do not prevent arming or entry. This deliberately permits continued paper entries after cumulative losses. Current account facts, reserved capacity, fresh position marks, quotes, protection and other risk checks still apply. The old commission-adjusted daily-loss calculation has been removed; commissions remain journaled. Historical profiles with a daily-loss field are retained and labelled retired/unenforced; a successor without that field is published for new authorizations.

Gateway 2119 is an informational market-data farm connection message, not a critical incident. A one-time audited correction resolves old `broker_2119` incidents without clearing unrelated incidents or arming runs. Connection and feed readiness are still independently checked.

Reconciliation preserves position instrument types. Confirmed own-account `CASH` currency/FX contracts are displayed separately from OMS-managed security positions; they do not create a false stock-quantity mismatch. They are not treated as proof that the account is empty. Unknown instrument types, external security holdings and unexpected working orders still block. Currency symbols alone are never used to infer CASH classification. Historical journal entries are unchanged; a new typed snapshot is required.

The Trading Desk shows Last, bid and ask with separate timestamps, downloaded history counts and feed readiness. `History downloaded` does not imply a fresh trade stream or that every strategy indicator is ready. Closed-market equities can have complete history while waiting for the next session's trades. See the [unified workspace guide](UNIFIED_WORKSPACE_GUIDE.md) for weekend PAXOS paper testing. Former local simulation records remain historical and do not establish broker execution capability.

## Strategies and replay

Drafts autosave with optimistic revision checks and local recovery. A conflicting save preserves the local draft and offers a recovered copy or the latest server draft. Published execution semantics are immutable. Canvas layout changes do not change the semantic hash. A new version needs a new run and authorization; existing positions keep their original exit contract.

Guided configuration and the canvas share typed nodes/edges. Shared calculations remain one node. The catalog includes OHLCV, trade price, prior values, constants, arithmetic, rolling high/low, SMA/EMA, candle/session/relative volume, crossings/comparisons/Boolean groups, opening range, session windows, cooldown and time exits. Sizing and entry lifetime are graph settings. Risk, authorization, journaling and broker access cannot be removed from the graph.

Entry requires a false-to-true condition after warm-up, at most once per candle. A crossing is evaluated against the previous eligible evaluation. `Prior value` means the preceding evaluation, while `prior_close` means a prior completed candle. Completed-candle mode never reads the next candle's OHLCV. Forming EMA is recomputed from completed-bar state. Relative volume compares cumulative volume at matching completed-minute boundaries against ten complete reference sessions.

Replay shares the graph evaluator, signal transitions, Decimal sizing, durable outbox and broker-observation reducer with paper execution. Its broker double uses next-trade fills and a fixed simulated quote spread, with no fee/liquidity model. It is not a broker simulator qualification. Dataset-end positions remain open, and missing intervals are not fabricated. Synthetic practice data is labelled separately. Replay state and orders are stored only under the simulation directory.

## Interruptions and operator recovery

Current recovery uses scoped trading restrictions, separately from incident history
and ongoing investigation. See [current-risk recovery and capacity](WORKSPACE_HEALTH_AND_CAPACITY.md)
for migration and evidence requirements. After a routine watchdog/connectivity
failure, allow a fresh post-failure reconciliation and 30 healthy seconds, then
explicitly acknowledge verified recovery inside **Review & arm**. Active failures
cannot be acknowledged away. Engine faults and order/protection uncertainty still
need dedicated review by selecting the incident in **Activity > Current restrictions**
and explicitly acknowledging verified recovery. Notes are optional; no typing is
required to release a verified restriction. The dialog refreshes every two seconds
while visible and shows individual checks and the remaining observation interval.
See [feed diagnosis and recovery controls](FEED_RECOVERY.md) for targeted retries.
Emergency stop is separate. Released historical episodes do not block later runs;
new runs cannot bypass applicable unresolved uncertainty. Operational recovery can
leave an investigation open without claiming that the root cause has been fixed.

| Situation | Service behavior | Operator action |
|---|---|---|
| Temporary Gateway disconnect | Disarm entries; bounded reconnect; restore data, repair history and reconcile; never resend unknown dispatch or liquidate solely because of the outage | Watch recovery status. Existing protection resumes after ownership and fresh data are established; new entries require fresh manual arming |
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

Daily backups contain a SQLite snapshot, committed market-data captures and SHA256 manifest. Settings can create a backup and validate restoration into a separate directory. Captures used by decisions and historical ledgers are retained; archive closed-session state/backups deliberately and monitor disk capacity. No automatic deletion of decision evidence occurs.

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

For the new paired-stop workflow, follow the [OCA breakout guide](OCA_BREAKOUT_GUIDE.md).
It adds a separate supervised one-share qualification for each direction, native OCA
entry groups, fresh borrow checks and a non-executing broker credit preview. Unlike
legacy session resumption, OCA runs require fresh manual arming after disconnect.
Do not treat simulator results as evidence of Gateway acceptance.

The selected official [IBKR API distribution](https://interactivebrokers.github.io/) is 10.50.2. The selected [Windows offline Gateway](https://www.interactivebrokers.com/en/trading/ibgateway-latest.php) is 10.51.1a. Download scripts reject a changed artifact hash. File hashes and the verified installer signature are recorded in `PAPER_DEPENDENCIES.json`; actual paper handshake and market-data capacity still require operator trials.

The vendor Python setup metadata requests Protobuf 5.29.5. The installer changes only that dependency pin to 5.29.6 to address the [Protobuf denial-of-service advisory](https://github.com/advisories/GHSA-7gcm-g887-7qv7); SDK protocol source is unchanged. All generated SDK Protobuf modules imported locally with the patched runtime. Installed compatibility is checked again before connecting.

Bracket/partial-fill tests follow IBKR's [order submission behavior](https://interactivebrokers.github.io/tws-api/order_submission.html) and [OCA types](https://www.interactivebrokers.com/docs/general/order-types/complex-orders/oca-types). Broker-held protection is subject to broker/session rules; custom exits require a working engine and usable quotes/data. Successful internal paper acceptance confers no live-trading capability.
