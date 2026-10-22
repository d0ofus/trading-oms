# ExecPlan: Watchdog ownership, quiet markets, and bounded workspace reads

## 1. Goal

Implement the approved September 21 correction: reliable independent watchdog startup and review, waiting instead of disarming on quiet Last trades, and bounded Activity/browser memory with complete audit access.

## 2. Non-goals

No live trading, deployment, automatic arming, broker trials without operator arming, raising five-run/risk limits, or edits to historical journal records. Preserve pre-existing uncommitted work and do not restart the operator's running workspace.

## 3. Safety constraints

Paper only; no credentials in artifacts. Keep 15-second execution freshness, approvals, risk reservations, protection, reconciliation, and immutable journaling. Real interruptions revoke entry authorization. Watchdog health gates entries, never protective exits. Browser caches cannot authorize trading.

## 4. Current state

Watchdog starts before the engine loop, incorrectly exits on an old fresh PID, and incident review ignores watchdog health. Last inactivity invokes history repair/disarm. Activity replays from sequence zero, mounts 5,000 rows, and polls full snapshots including candles. Isolated baseline: 92 MiB retained JS heap, 65,333 DOM nodes, returning to 5 MiB after navigation. Two BTC pauses followed 17/16-second trade gaps with continuing quotes.

## 5. Proposed design

Persist an engine-instance owner before watchdog launch, bind atomic heartbeats to it, and fence alert writes transactionally. Startup grace 30 seconds, engine timeout 20 seconds, watchdog readiness age under 15 seconds. Gate review/arming/entry and latch watchdog loss after startup. Use monotonic timeouts and reject invalid heartbeat records.

Separate history, subscription health and execution freshness. Quiet trades preserve authorization/history but cannot execute until fresh observations; genuine gaps still repair/disarm. Record adapter receipt timestamps. Skip a crypto candle crossing with stale required data without delayed submission.

Add bounded audit pages, lazy payload details, watermark-based summary SSE and bounded catch-up. Render virtual rows, retain at most three summary pages, batch updates at 250 ms, and cancel hidden/unmounted reads. Add compact shared workspace reads and on-demand paged candles/run/order history. Preserve old API contracts.

## 6. Data model changes

Add a current engine-owner document and versioned health-file fields (instance, PIDs, wall/monotonic timestamps, sequence). Additive read indexes only; preserve immutable events, versions and captures. Feed health/read models are derived, not new execution authorities.

## 7. API changes

Add audit summary pages/detail and summary stream mode, compact workspace overview, paged records, and bounded per-contract/timeframe candle queries. Expose watchdog health, field ages and candle provenance. Existing session/event endpoints retain default semantics.

## 8. Test plan

Regression tests for rapid restart, startup/hang/termination, ownership fencing, malformed/future/stale health, review/entry guards, quiet trades, delayed callbacks, real gaps, stale crossings, protection and rollover. Browser tests for audit pagination/search/detail/reconnect/virtualization, lazy candles and bounded refreshes. Load fixture: 1M journal events, 50 subscriptions, 1,000 saved runs, five active runs. Repeat 5,000-event heap fixture (under 25 MiB and <=60 mounted audit rows), navigation and 30-minute stream soak. Record unavailable operator trials explicitly.

## 9. Verification commands

Targeted pytest/vitest/Playwright tests, then `.\scripts\verify.ps1` using `. .\.tmp\activate-dev.ps1`. Record commands/results below as work progresses.

## 10. Rollback plan

Stop the new application without altering broker positions, restore the previous code/build, and restart with manual reconciliation/arming. Ignore the additive owner/read fields in old builds. Never restore an older trading database over newer execution evidence. Existing watchdog startup workaround remains necessary on old code.

## 11. Implementation steps

1. Add regression tests and implement watchdog lifecycle and freshness gates.
2. Add quiet-market and callback-age tests; implement feed state and safe trigger handling.
3. Add bounded backend read APIs and frontend audit/candle consumers.
4. Run performance/recovery/browser tests, full verification, safety review, and operator documentation.

## 12. Completion criteria

All requested behavior and automated checks pass; bounded UI memory is measured; immutable history and paper-only execution remain intact. Operator-armed observations are reported separately and never simulated as broker evidence.

## 13. Risks and assumptions

Current app may remain running old code until the operator restarts after build. Busy histories must not starve the engine. Wall-time adjustments must not extend monotonic freshness. Exact browser total RAM varies; measure retained JS heap plus DOM separately. Scaling fixtures do not qualify increased active trading limits or live deployment.

Progress: implementation, targeted safety review and automated verification complete.

- Added instance-bound monotonic health, startup/ownership fencing, atomic writes,
  review/arming/dispatch gates and independent protection/exit handling. Concurrent
  testing exposed a Windows `os.replace` reader-handle race; bounded atomic-rename
  retries now cover it. A same-instance starting-to-running transition is explicitly
  distinguished from an ownership transfer.
- Removed inactivity-driven gaps, preserved 15-second entry freshness, captured
  adapter receipt times, and skipped stale crossings. Invalid, out-of-order and
  late completed-candle observations are rejected before local trigger evaluation.
- Added bounded audit summaries/details, bidirectional sparse search continuation,
  watermark/catch-up streaming, virtual rows, lazy historical evidence and candles,
  compact snapshots, and paged run/order history. Removed the unused accumulating
  audit-search component. Existing compatibility endpoints remain available.
- Deterministic tests cover watchdog health loss without stop suppression, a health
  loss after reservation but before dispatch, ownership transfer during file reads,
  20-second hangs, monotonic startup, quiet Last gaps, late callbacks and crossings,
  sparse audit continuation, lazy legacy details and older candle coverage/cache.
- Browser regression workflows passed after rebuilding the frontend. The initial
  failure in older audit paging was an undefined query parameter, corrected. Adding
  receipt time to execution observations also changed duplicate execution hashes;
  receipt timestamps are now restricted to market-data observations. Broker
  execution callback identity is preserved.
- `node scripts/activity_memory_probe.cjs 1800`: passed, 361,200 events, 20 mounted
  rows, 5.66 MiB final retained heap. The sustained phase stayed approximately
  5–7 MiB. A final-build 5,000-event/five-navigation repeat passed at 4.93 MiB.
- `python scripts/workspace_load_probe.py`: passed with one million events, 50
  contracts, 1,000 saved strategies, 1,000 saved runs and five active runs. Final
  measured run: 1,072 audit requests, 62 ms p95 audit latency, 1,844 ms maximum
  overview latency and 1,859 ms maximum engine-loop age,
  no orders, overflow, watchdog incidents or engine faults. This is an offline
  quote/read workload; deterministic tests cover protective actions separately.
  Cleanup waits for the existing shutdown audit of all saved runs; no production
  shutdown semantics were changed. The final probe completed with exit code zero.
- Final `.\scripts\verify.ps1`: **984 backend tests, 190 frontend tests and six
  browser workflows passed**, plus formatting, lint, types, compile/build, secret
  scan and dependency audits (zero known vulnerabilities). `verify: ok`; current
  source/build fingerprint matches the verification record. Evidence is in
  `.tmp/watchdog-gate.txt`; load and memory probes are in
  `.tmp/workspace-load-final.txt`, `.tmp/activity-memory-soak.txt` and
  `.tmp/activity-memory-current.txt`.
- Initial gate interruptions were formatting/import-order issues and Windows
  PowerShell treating redirected native stderr warnings as terminating errors.
  The complete gate passed in a child PowerShell process with native exit-code
  checking unchanged. Remaining non-failing notices concern a test-client
  deprecation, frontend chunk size, console colors and dependency hash advice.
- Browser checks include keyboard event selection, WCAG 2 A/AA scanning, lazy
  payloads, paging/search, hidden-tab pause, resync and navigation cleanup. Visual
  inspection covered the new Activity panel and the existing recovery layout.
  The keyboard test caught Enter's default action immediately closing a newly
  focused dialog; row activation now prevents that default action.
- Operator-armed BTC paper observation/recovery remains an external acceptance
  check. No real account was armed, no broker orders were forced, no running
  workspace was restarted, and no commit/push/deployment was performed.
