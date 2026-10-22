# Feed diagnosis and recovery controls

Current monitoring and recovery behavior is defined in [Current operational monitoring](CURRENT_OPERATIONAL_MONITORING.md). It supersedes the historical recovery intervals and acknowledgment workflow described below.

The workspace remains paper-only. Data recovery never arms a strategy, releases
an incident, clears emergency stop, or retries an uncertain broker order.

## Recovery review

Select an incident under **Activity > Current restrictions**. The dialog refreshes
its selected episode every two seconds while visible. **Recheck recovery** refreshes
immediately. Individual checks explain what is missing, including post-failure
reconciliation and the remaining 30-second healthy-observation interval. A failed
refresh disables acknowledgment until a successful refresh. Closing the dialog or
hiding the browser tab cancels its request and stops polling; returning refreshes it.

After recovery is verified, select **Acknowledge recovery and release restriction**.
The collapsed **Optional notes** field is optional for every recovery review. Empty
notes record the standard reason **Operator acknowledged verified recovery.** The
authenticated operator identity, reviewed revision, policy version, time and evidence
are still recorded. The engine rechecks current health and revision at confirmation.

Engine faults, uncertain orders and protection problems retain dedicated incident
review and all evidence requirements. A fresh quote cannot establish the outcome of
an uncertain order. Routine watchdog/connectivity recovery can still be explicitly
acknowledged in Review & arm. Investigation closure remains separate and still needs
a recorded outcome; operational release does not assert that an unknown cause is fixed.

## Three independent data components

The market-data panel and contract incident review distinguish **Quotes**, **Execution
trades**, and **Historical data**. Both **Sampled Last** (the quote subscription) and
**Last execution trade** (qualifying trade ticks) show their own timestamps. Updating
sampled prices or bid/ask does not establish execution-trade or history readiness.
For instruments with display-only real-time bars, those bars never supply execution
trades. Candle history and quiet-market handling retain their existing rules.

For example, a rejected trade request with code 10189 and a history failure with
code 162 remain visible independently. New incidents are component-specific and
contract-scoped. Legacy combined incidents require all applicable feeds/history to
recover; their historical records are not rewritten or silently released.

The adapter converts recognized broker text into a fixed reason and safe description:
permissions, session conflict, pacing, unavailable data, unsupported request,
transient service failure, expected cancellation, or unknown. Raw broker messages,
account identifiers and reject payloads are never persisted. Code 162 alone cannot
identify the cause; unknown failures remain unknown. Inspect TWS/Gateway locally
when more detail is required. Correct any permissions or competing-session issue
before retrying; this application cannot grant broker entitlements.

## Retry without removing the subscription

**Retry failed feeds** queues only the failed components. Healthy feeds, completed
history ranges and their downloaded bars remain available. The panel shows failed,
completed, pending and queued history requests and any retry countdown. Repeated
clicks are deduplicated. Requests retain the existing subscription and history pacing
limits, including no same-contract resubscription within 15 seconds and at most two
concurrent historical requests. Pending work may wait longer under account pacing.

Recognized transient service failures retry after **15, 30 and 60 seconds**; pacing
failures after **60, 120 and 240 seconds**. After three unsuccessful automatic attempts,
manual retry is required. Permission, session-conflict, unsupported, unavailable-data
and unknown failures require manual retry. Manual retry respects existing cooldowns
and starts a fresh automatic-attempt budget if another recognized transient failure
occurs. No recovery acknowledgment is implied.

Each request has a connection epoch and generation. Late callbacks from failed,
cancelled or replaced requests cannot overwrite a current feed. The adapter retains
at most 1,024 terminal request contexts. A code 300 proven to concern a cancelled data
request remains diagnostic. Unknown request errors retain conservative handling.

The authenticated `POST /api/market-data/{conid}/retry` accepts `components` containing
`quote`, `trade` and/or `history`, and a 32-character hexadecimal `mutation_id`. Reusing
an identity returns its recorded result; reusing it for different parameters conflicts.
Existing review APIs still accept optional `rationale` and `revision` fields. Clients
should always send the reviewed revision. Market data adds `components`; incident
detail adds `recovery` checks/timing and contract `feeds` where applicable.

## Taking the update into use

At a supervised safe stopping point, stop the old application and run
`.\scripts\start-workspace.ps1` from the repository root. Do not use `-SkipBuild`
for the first launch after updating frontend code. Refresh the browser or use its
build-mismatch reload notice. Login/attestation, reconciliation, incident release,
emergency-stop review and fresh strategy authorization remain separate actions.

For a data-only observation, keep runs disarmed. Subscribe to the resolved contract,
check both Last values and all three component states, and inspect an existing failed
feed's retry and recovery checks. Do not intentionally disrupt a connection while it
is needed for local position protection. No order is needed to validate the dialog or
feed recovery, and automated fixtures do not prove account-specific permissions.
