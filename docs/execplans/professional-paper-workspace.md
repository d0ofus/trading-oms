# ExecPlan: Professional Trading Workspace with Reliable IBKR Paper Execution

Status: software implementation and automated Windows verification complete; external paper acceptance pending. Approved by the operator in this conversation on 2026-09-16.
This is the current internal paper implementation scope. Historical Candidate 062/063 packets
remain immutable historical evidence, not completed independent reviews. The operator explicitly
selected an internal paper gate: automated verification, code review, supervised paper trials,
and operator acceptance before unattended operation. Live trading remains excluded.

## 1. Goal

Deliver a local professional Strategy Studio and Trading Desk with synchronized guided/canvas
configuration, executable OHLCV strategies, IB Gateway paper execution, persistent safety state,
recovery, and unattended-session monitoring. Support five distinct long-only US equity symbols,
intrabar rules, bounded human arming, Telegram and Healthchecks monitoring. Use external charts.

## 2. Non-goals

Live accounts/orders, public hosting, shorts, derivatives, extended-hours entries, multiple
accounts, arbitrary strategy code, scale in/out, multiple strategies owning the same symbol,
embedded charts, mobile controls, and detachable multi-monitor workspaces.

## 3. Safety constraints

Simulation/paper only; localhost Gateway port 4002; manual paper login attestation, exactly one
transient account, reconciliation, fresh data, risk reservation and authorization before entries.
Never persist/log account identities or secrets. Notification credentials are entered by the
operator locally into Windows Credential Manager. No credentials are added by implementation.
Persist intent before dispatch; uncertain dispatch is reconciled, never blindly retried. Keep
protection after disarm and durable emergency state across restarts. Re-arm after process restart.
Do not claim paper trials, usability acceptance, or independent review from automated tests.

## 4. Current state

Baseline 2f6569280ed272940e21f9c3a1af0702be457f15: legacy simulation workbench with two
restricted builders, process-local broker bookkeeping and no concrete SDK session. Prior audit
passed 767 backend and 188 frontend tests. Preserve legacy evidence and portable tests.

## 5. Proposed design

- Routed Trading Desk, Strategy Studio, Testing, Activity and Settings. Dark/light themes,
  balanced resizable desktop panels, accessible controls, stable operational tables, exchange
  and local clocks, persistent paper badge and emergency control.
- One canonical typed graph, one backend compiler/evaluator, guided and React Flow projections;
  OHLCV, prior values, arithmetic, rolling extrema, SMA/EMA, volume, relative volume, comparisons,
  crossing, Boolean groups, opening range, sessions/cooldowns, sizing and protected exits.
- Mutable autosaved drafts, immutable published semantic versions, layout separate from hashes,
  template duplication, generated explanations, validation that identifies fields/nodes.
- Names/pickers/presets replace raw run/dataset IDs, JSON, role headers and UTC strings. Setup
  covers Gateway, market data, risk, notifications and actionable readiness. One arming review,
  all-or-none batch authorization; editing never changes an active version.
- One engine/reducer with SQLite WAL/FULL event ledger, outbox, risk reservations, order IDs,
  positions, protection, incidents and preferences. Durable normalized capture before decisions.
- Official asynchronous Python TWS API 10.50 behind an adapter, pinned compatible offline Gateway;
  handshake, heartbeat, bounded backoff, 1100/1101/1102/1300 handling, complete reconciliation.
- One Last tick subscription and quotes per symbol; Decimal calculations, exchange calendar,
  current/completed 5s/1m/5m candles, matching completed-minute relative volume, gap recovery,
  no retrospective orders and no fabricated intrabar replay from OHLCV-only data.
- Durable dispatch and execution identity, partial fills and corrections, cancel/fill races,
  bracket transmission, GTC stops, optional targets, OCA protection and serialized exits.
- Same strategy/risk/OMS path for replay and paper; local authenticated sessions and strict
  loopback origin checks; built frontend; supervisor; alert outbox; external heartbeat; backup.
- Data directory: LOCALAPPDATA/TradingOMS, separate simulation/paper. Retain critical events,
  decision captures and daily verified backups; archive closed-session evidence deliberately.

## 6. Data model changes

Strategy drafts/versions, presentation preferences, named risk/session profiles, runs and
authorizations, capture manifests and market quality, broker epochs/reconciliation, intents,
outbox/order allocation, executions/positions/protection, events/incidents/emergency/notifications.
Layout is not executable strategy state. Legacy simulation approvals never authorize paper.

## 7. API changes

Canonical authenticated families: /api/paper/session, /api/market-data, /api/strategies,
/api/risk-profiles, /api/runs, /api/operations, /api/preferences, /api/events, /api/notifications.
Structured ValidationIssue/ReadinessCheck/ActionEligibility; server-authoritative eligibility,
optimistic draft concurrency, idempotent mutations, final arming revalidation and resumable SSE.

## 8. Test plan

Graph/form round trips, version isolation, replay determinism, intrabar EMA, clock/calendar/gaps,
concurrent risk reservations, partial fills/corrections, duplicate dispatch, cancel/fill races,
crashes around dispatch, reconnect/reconciliation, emergency persistence, missing protection,
notification failures and restore. Browser tests cover configuration through recovery, draft
conflicts, stable selection, both themes, keyboard/drag alternatives and realistic failure states.
Actual paper tests remain separate from injected/simulated evidence.

## 9. Verification commands

`./scripts/verify.ps1`; production frontend build; browser E2E/accessibility; dependency and
secret checks. Add `./scripts/paper-preflight.ps1` (read-only broker diagnostics) and
`./scripts/start-paper.ps1`. Ordinary verification never connects or submits broker orders.

## 10. Rollback plan

Use verified commits on main. Backup before migration. Disarm/reconcile before replacement;
retain protection/monitoring for open positions. Restore incompatible state separately and
reconcile against current broker truth. Never resend pending entries from a restored backup.
Keep presentation rollback independent from trading state and historical evidence read-only.

## 11. Implementation steps

- [x] 1. Record plan/internal gate, dependencies and baseline checks.
- [x] 2. Canonical persistence, emergency state, outbox and OMS corrections.
- [x] 3. Shared UI components/navigation/tokens and operational states.
- [x] 4. Executable graph/data contract and deterministic replay.
- [x] 5. Strategy Studio, synchronized editors, templates, drafts and publishing.
- [x] 6. Local authentication, setup, profiles and arming review.
- [x] 7. Official read-only Gateway connection and diagnostics.
- [x] 8. Streaming data, warm-up, intrabar evaluation and recovery.
- [x] 9. Paper orders, protection, exits and shared multi-run risk.
- [x] 10. Trading Desk and Activity backed by actual state.
- [x] 11. Alerts, watchdog, packaging, backup and restore.
- [ ] 12. Usability, supervised paper tests and five-session acceptance.

## 12. Completion criteria

No technical identifiers needed for configuration; template setup under five minutes, common
parameter change under two minutes, prepared session arm under 30 seconds, actionable blocker
identified within 30 seconds (excluding broker login/data waits). Lossless guided/canvas editing,
draft recovery, no clipped critical controls at 1280x720/1440x900/1920x1080, tested keyboard and
both themes. Two distinct strategies execute through shared replay/paper runtime; five runs obey
shared limits; zero duplicate entries in fault tests; positions/protection reconcile; restart is
entry-disabled; Telegram/heartbeat/restore demonstrated. Five consecutive US paper sessions with
no unresolved P0/P1 or unexplained orders/positions plus operator usability acceptance.

## 13. Risks and assumptions

Single Windows operator; Gateway manually paper-authenticated, compatible SDK, subscriptions
and five-symbol tick capacity verified during setup. Smoke profile: one share/one run. Qualified
limits: five runs/positions on distinct symbols; ten shares and $1,000 per run; $10 planned stop
risk per run/$50 aggregate; $5,000 gross exposure; $100 daily loss; five entries/run/session;
30s entry lifetime; stop new entries 15 minutes before close, initiate exits five minutes before
close; one-session authorization; restart requires re-arming. Multi-share unattended use remains
blocked until protection qualification. Hardware/network/login failures can need intervention.
Broker stops do not guarantee a maximum loss. Local automation cannot fabricate market-session
acceptance or the operator's external service configuration.

## Implementation evidence

This section is updated as work and verification complete. No broker trial has been performed.

Baseline: main at `2f6569280ed272940e21f9c3a1af0702be457f15`; the original Windows gate
passed with 767 backend tests, 188 frontend tests and four resilience checks. No branch or
worktree was created. The original application and historical review records remain intact.

The new workspace is in `backend/src/trading_oms_backend/workspace` and
`frontend/src/workspace`. Production startup is explicitly loopback-only. The first implementation
includes a checksummed ledger, immutable strategy publications, optimistic draft concurrency,
durable order identities, restart disarming, authenticated APIs, shared replay/graph execution,
guided/canvas editing, five routed workspaces, dark/light themes and operational tables.

The new browser walkthrough passed cleanly (one test, 30.3 seconds): create/rename/recover a
draft, switch views without semantic changes, publish, replay synthetic ticks, prepare a run,
inspect blocked arming, and preserve emergency stop over refresh. Automated accessibility
checks passed in both themes. Layouts were inspected at 1280x720, 1440x900 and 1920x1080.
These are synthetic browser and broker-double results, not broker-session evidence or user
usability acceptance. Playwright uses a separate local browser process because Windows process
pipe shutdown stalled the first harness; the completed rerun exited normally.

Frontend type checks, lint, 188 existing unit tests and the production build passed. The npm
audit reported zero vulnerabilities after dependency updates. New backend tests cover immutable
versions, layout-independent hashes, draft conflicts, local authentication/origin checks,
emergency persistence, shared reservations, crash uncertainty, duplicate/corrected executions,
cancel/fill races, calendar boundaries, completed candles, forming EMA, configurable opening
ranges, historical seeding, and backup/restore with captures.

The official API archive `twsapi_macunix.1050.02.zip` was obtained from IBKR, SHA256
`673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3`, and its Python
package reports 10.50.2. Licensed SDK source stays in ignored local storage. No real Gateway
connection or order submission has been attempted. The installed Gateway directory observed
earlier was build 1044; compatibility with the selected official build still needs qualification.

The execution service now includes serialized reconciliation snapshots, bounded reconnect,
unchanged-context resumption, historical warm-up/repair without retrospective signals, broker
market increments, durable GTD bracket entries, execution correction reduction, exact protection
checks, partial-fill repair, serialized OCA exits and shared five-run capacity. Replay shares the
signal transitions, sizing, outbox and observation reducer. The two templates execute on ticks;
longer opening-range tests include ten complete reference sessions. Session boundaries are cached
by exchange date for intrabar throughput.

The UI now includes six guided sections, canvas editing, autosave/conflict recovery, immutable
versions, publication review, profile/session arming, actual rule values, order timelines, saved
table sizing/visibility/order/density, full-ledger search, replay comparison and legacy read-only
history import. Authentication, vault-backed notifications, watchdog, sleep prevention, backups,
restore validation and five-session acceptance recording are implemented. Qualification remains
fail-closed until actual paper evidence and operator acceptance exist.

The initial expanded full gate found three historical documentation checks that assumed no new
connector could exist. The legacy-source assertion now remains scoped to preserved legacy
modules; workspace paper-boundary tests cover the newly authorized runtime. Historical packets
and their hashes were not changed. Accessibility testing found and fixed canvas port roles,
Radix panel IDs and accessible names for collapsed navigation. Final command results are recorded
in the implementation review after completion.

The final browser harness uses Playwright's matching dedicated headless Chromium shell with a
fresh loopback debugging port, direct local networking and bounded action/navigation timeouts.
Earlier harness runs had port collisions and intermittent first-navigation timeouts; those failed
runs are not counted as passing evidence. Visual comparisons use a fixed desktop viewport, with
the arming dialog captured separately. Temporary toast overlays are excluded from pixel comparisons,
and guided captures wait for the block catalog. Full-page inspection artifacts remain available.
These changes remove scrollbar-height and transient-overlay differences from the seven checked-in
Windows baselines. The ordinary full gate compares those baselines without updating them.

Final `./scripts/verify.ps1` passed on 2026-09-16 at 16:42 Sydney time: 831 backend tests,
188 frontend unit tests, one complete browser walkthrough, seven Windows visual baselines,
accessibility/layout assertions, lint/type/format/compilation/build checks and dependency/secret
audits. The final browser walkthrough took 38.6 seconds. The exact source/build fingerprint
and nonblocking warnings are recorded in `docs/PAPER_IMPLEMENTATION_REVIEW.md`.

Read-only `./scripts/paper-preflight.ps1` passed five prerequisites and reported one failure:
the local paper Gateway TCP endpoint at `127.0.0.1:4002` was unavailable. The official SDK,
patched Protobuf runtime, verified production bundle and Windows platform checks passed.
Install/login to the selected Gateway and enable the local paper API before connection trials.
The preflight did not log in or submit any broker order.

The first pushed CI run passed Ubuntu but found three historical byte-identity failures on a
fresh Windows checkout. Git's automatic CRLF conversion changed the review packet generator and
Candidate 062 plan bytes. Two explicit LF attributes now preserve those hashed files, alongside
the existing review JSON/digest attributes. No historical content, expected hash or runtime
behavior was changed. An autocrlf-enabled checkout of the two files produced bytes identical to
the verified local files, and all 26 tests in the two affected historical evidence suites passed
(6.83 seconds). The verified source/build fingerprint remains unchanged.

**External acceptance remains outstanding.** No real Gateway API login, paper order, Telegram
message, external outage test or actual unattended session was performed by implementation.
The verified Gateway installer was downloaded and signature/hash checked, not installed or
launched. The software gate is distinct from real Gateway compatibility and paper release
acceptance. Step 12 remains incomplete until the operator completes the procedures in
`docs/PAPER_OPERATOR_GUIDE.md` and accepts the usability walkthrough and five consecutive sessions.
