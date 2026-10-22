# Current-risk incident recovery, quiet markets, and bounded history

The workspace remains paper-only. The watchdog and feed corrections do not enable
live execution, increase five-active-run or financial limits, or authorize a run.

## Starting and recovering

Build and start from the repository after stopping the previous workspace cleanly:

```powershell
.\scripts\start-workspace.ps1
```

Do not use `-SkipBuild` for the first launch after frontend changes. The app can
open before TWS/Gateway login. Complete paper connection, reconciliation and market
data readiness before reviewing incidents or arming. Never delete the state files
or journal to clear a blocker.

Each engine launch records a unique instance under the workspace's exclusive
ownership mechanism. Atomic engine/watchdog files include that identity, process
IDs, sequence and monotonic timestamps. A previous engine's heartbeat is ignored
during the 30-second startup grace. Once its own heartbeat is seen, the watchdog
uses a 20-second engine timeout. A superseded watchdog cannot raise an emergency
against the new owner. Atomic file replacement retries transient Windows reader
contention for up to 90 milliseconds, without exposing a partial heartbeat.

Activity shows independent watchdog health and heartbeat age. Reviewing a watchdog
incident requires a heartbeat newer than the incident, less than 15 seconds old,
acknowledging the current engine's fresh heartbeat. Missing, malformed, mismatched,
future or stale evidence explains the blocker. This health check also applies to
every arming review and immediately before new entry dispatch, including supervised
qualification. Health recovery does not clear an incident, emergency stop or arm a
run automatically. Protection, reconciliation, cancellation and risk-reducing exits
continue independently of this new-entry gate.

## Incident episodes and present restrictions

Incident age is not a trading control. The engine now keeps three independent
states: condition (`active`, `unknown`, `recovered`), entry restriction (`held`,
`ready_for_release`, `released`), and investigation (`open`, `closed`). Readiness
queries applicable unreleased restrictions through indexed projections, not the
whole incident history. A released historical episode or open investigation alone
does not block a new run. An old uncertain order still does.

Scope is assigned by engine policy, never by an operator's choice. Shared watchdog,
connection and unknown failures affect the workspace; unexplained account exposure
or protection affects all account entries. Confirmed contract failures affect runs
using that contract; validated strategy/run failures can be narrower. Unknown legacy
scope stays broad. New runs inherit applicable restrictions. Each occurrence is
journaled; a recurrence before release updates the episode/revision/count, and a
recurrence after release creates a new linked episode. Restriction activation
revokes affected authorizations and queues cancellation of pending entries, while
leaving protective orders and owned-position exits under their existing controls.

Routine watchdog and connectivity recovery can be acknowledged **inside Review &
arm**. Wait for 30 continuous seconds of healthy applicable infrastructure checks,
a current-owner watchdog acknowledgment less than 15 seconds old, a fresh engine
heartbeat under 20 seconds, and successful reconciliation begun after the latest
failure. Monotonic time measures stability. Routine reconciliation in progress can
retain a still-fresh completed proof for stability sampling, but release/arming
waits for reconciliation to finish. Quiet Last trades do not reset this interval;
execution freshness remains an independent entry requirement.

In Review & arm, explicitly select each recovered-incident acknowledgment. Nothing
is preselected. Confirmation rechecks current evidence, engine ownership, episode
revisions, paper context and existing readiness/risk rules. Release and selected
run authorization commit together; failure rolls both back. Requests are idempotent.
Other paused runs stay paused and need their own approval, but do not have to
acknowledge the same released episode again. A changed or stale review must be
refreshed. The engine checks restrictions again immediately before entry dispatch.

Unexplained engine faults, uncertain orders/protection and account problems require
**Activity > Current restrictions**; select the incident row to review it. An engine fault requires
fresh watchdog health, post-failure reconciliation, and 30 seconds without recurrence.
Review the evidence and explicitly acknowledge recovery. Optional notes can record
additional context; an empty note records "Operator acknowledged verified recovery."
Do not claim an unknown root cause is fixed. The visible dialog refreshes every two
seconds, with one request at a time, and disables release when status is unavailable.
The investigation can remain open after a deliberate operational release. Emergency
stop is separate and is never cleared by a recovery acknowledgment. No incident
review bypasses active or unknown risk merely by acknowledging an alert.

Activity offers separate bounded **Historical incidents** and **Investigations
without a trading restriction** views. Select an episode for diagnostic/evidence details.
Closing a released episode's investigation requires a recorded outcome; closing
an investigation cannot release a trading restriction. Actor identities are opaque
authenticated-session audit IDs, not authentication tokens or broker account IDs.
Release records include policy version, reviewed revision, current evidence and
rationale. Backend exceptions now retain only class, operation and up to eight safe
stack locations; exception strings, source lines and locals are omitted. The old
generic engine-fault record cannot retrospectively reveal its missing cause.

Stop old engine/watchdog processes before the first launch of this version. On the
next launch, existing state is backed up to
`<state-directory>/backups/incident-migration-<id>.sqlite3` before the incident
projection is migrated. Old events, approvals and published strategy hashes are
unchanged. Unresolved legacy incidents stay unknown/held until new evidence passes;
starting another engine or creating a new run cannot clear them. Do not run an old
binary against migrated state. A rollback requires offline recovery and broker
reconciliation, not replacing current trading evidence with an old backup.

## Quiet BTC markets

Fifteen seconds without a Last trade no longer means a broken feed. A quiet run
stays authorized, keeps valid history, and displays **Armed — waiting for fresh
trades**. Market-data details show Last/source/bid/ask ages, subscription status,
history progress and the exact stale or missing field. New entries still need
valid observations within the existing 15-second limits.

When a fresh eligible trade returns, the current authorization may become eligible
again. Disconnects, relevant subscription failures, callback overflow, invalid or
out-of-order trades and uncertain continuity still revoke entry authorization and
require repair and manual re-arming. A crossing while required quotes are stale
skips that candle generation; quote recovery cannot cause a delayed entry. Empty
minutes do not create invented candles or volume. Historical downloads and repaired
display candles never generate retrospective orders. Callback receipt time is
captured at the adapter, so queue delay cannot freshen an old observation.

For an operator observation session, connect and reconcile the paper account,
subscribe BTC/USD PAXOS, review its data and watchdog readiness, and manually arm
the approved long-only run. Observe quiet trade periods and minute changes in
Trading Desk/Activity. Let legitimate signals occur; do not force an order. Test
recovery only under supervision with known positions and protection. Verify that
an actual interruption pauses new entries, protection recovers after reconciliation,
and a new entry requires another review. Compare any broker fills with TWS.

## History browsing and API compatibility

Activity loads the latest 200 summaries, then streams events after its watermark.
It caches at most three pages, displays a small virtual row window, batches live
display changes every 250 milliseconds, and fetches a full payload only on selection.
Sorting, local filtering, column settings, density and keyboard row selection apply
to the loaded page. **Search all history** searches the entire immutable payload
and event type on the server. Each request scans at most 2,000 records, returning
up to 200 matches. Use **Older records / continue search** even if a sparse page
contains no match. Newer-page navigation also preserves search continuation.

The recent stream resumes by sequence. A backlog over 2,000 events refreshes the
bounded recent window and displays a notice; older evidence remains searchable.
Leaving Activity closes the stream, aborts requests and releases its page state.
Hiding the tab pauses the stream; showing it reloads the recent window. Historical
simulation imports remain separate read-only evidence, now paged with lazy details.

The UI uses `/api/workspace/overview`, a shared one-second read snapshot without
candle arrays or completed-order history. Each view has one refresh request in
flight. Candles load only in an open panel for one contract/timeframe, at most 120
per page, with a bounded shared aggregation cache. Trading Desk exposes paged
saved runs and order history; active positions and working orders remain prominent.

New read interfaces are `/api/events/page`, `/api/events/detail/{sequence}`,
`/api/events/stream?summaries=true`, `/api/market-data/{conid}/candles`,
`/api/workspace/records/{runs|orders}` and paged legacy-record endpoints.
Existing session, full-payload event and legacy endpoints retain their semantics.
Browser caches never participate in authoritative order validation. Historical
events, approvals, published hashes and execution evidence are not rewritten.

Incident interfaces are `/api/incidents?view=current|history|investigations`,
`/api/incidents/{episode}`, and revision-checked review/investigation-close actions.
Pages contain at most 200 summaries, use sequence cursors and fetch evidence only
on demand. Compact overviews return at most one current-incident page plus stored
counts, regardless of historical volume. Legacy code-based reviews only work when
one current episode is unambiguous. Older arming clients that omit required explicit
acknowledgments remain blocked.

The footer clock renders independently of workspace state. Audit columns have stable
definitions and the audit component ignores unrelated overview refreshes. The UI
shows frontend/backend build identities; an asset mismatch offers a manual reload
notice. Use a fresh tab after rebuilding/restarting when measuring browser behavior.
The backend identity is captured at startup, so editing source does not update an
already running process.

## Repeatable capacity checks

Run the normal repository gate, then the isolated probes:

```powershell
.\scripts\verify.ps1
python scripts/workspace_load_probe.py
node scripts/activity_memory_probe.cjs 1800
```

The browser probe serves the built application with synthetic HTTP/events and no
broker access. It checks 5,000 incoming events, repeated navigation, up to 60 mounted
audit rows, and under 25 MiB retained JavaScript heap after garbage collection during
a 30-minute stream. Heap is not total browser process RAM. The load probe creates a
temporary one-million-event journal, 100,000 released incident projections, 50
contracts, 1,000 saved strategies, 1,000 saved runs and five active run fixtures,
with concurrent audit/incident readers and quote callbacks. Its adapter has no
order submission methods. Results measure these workloads, not unlimited capacity,
actual broker pacing or live qualification. Protective behavior is separately
covered by deterministic tests.

The incident-recovery 30-minute probe processed 357,400 synthetic events and ended
at 6.00 MiB retained JavaScript heap, 22 mounted table rows (20 audit plus two
incidents) and 686 DOM nodes. Final summed browser-process working sets were
252.17 MiB, with 113.91 MiB private allocation. Steady streaming consumed roughly
3% of one CPU core. A repeat against the final frontend build, after stable-column
and detail-display refinements, passed 5,000 events/five navigations at 5.06 MiB
retained heap and 22 rows; private allocation was about 105 MiB and summed working
sets 438 MiB. Working sets include mapped/shared pages and vary with OS residency;
they are not equivalent to retained heap or a browser task manager's per-tab figure.
These isolated measurements do not establish the RAM/CPU use of the user's existing
browser profile, which was unavailable for direct profiling. No live paper observation
or forced trading action was used to complete the probe.

The current incident-history load run completed 883 combined audit/incident read
cycles with 78 ms p95 latency, 1,406 ms maximum overview latency and 1,422 ms maximum
engine-loop age. Compact overview size was 84,188 bytes. There was no callback
overflow, watchdog incident, engine fault or order. Measurements depend on the
machine and competing work. Saved-run evaluation and broker data/request pacing
remain constraints; five active runs is still the supported ceiling.

The existing shutdown audits every saved run and can take longer with large saved
histories; the probe waits for that writer before removing its temporary state.
This remains a capacity consideration, separate from steady-state broker handling.

## Hosting

Continue supervised paper testing locally. Eventual unattended operation needs a
dedicated always-on execution host, either a local machine with reliable power,
network and monitoring, or a managed cloud VM. Cloud hosting separates execution
from home-PC interruptions but adds ongoing cost, patching and secure-access work;
broker GUI login and periodic operator reauthentication still apply. Windows is
the lowest-change path for the current launchers and Credential Manager integration.

Keep engine, watchdog, journal and Gateway together, with one active execution
owner. Use private authenticated UI access and keep the broker API on localhost.
Cloud placement does not reduce browser-side rendering memory or bypass IBKR
entitlements/pacing. Local stops cannot execute while the host or connection is
unavailable. No infrastructure deployment or live readiness is claimed here.
