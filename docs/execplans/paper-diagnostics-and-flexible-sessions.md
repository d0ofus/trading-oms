# ExecPlan: Paper diagnostics and flexible sessions

## 1. Goal

Implement the operator-approved incident recovery, plain-language strategy controls,
pre-market acknowledgement/cancel test, scheduled arming, optional pre/post-market
execution, and audited removal of runs. The label `Op` becomes `Operation`.

## 2. Non-goals

Live trading, overnight venues, unprotected execution, forced fills, automatic
resubmission of uncertain orders, and deletion of audit evidence are excluded.

## 3. Safety constraints

Keep the localhost paper adapter, single-account attestation, risk reservations,
durable dispatch and reconciliation. Never log credentials, accounts, exception
arguments/locals or raw broker messages. Closed sessions and stale quotes cannot
authorize submissions. Restart disarms; protection and monitoring remain.
Broker-held stop-limit protection is mandatory for extended execution. Extended
unattended use stays disabled pending actual qualification. No automated test
may submit broker orders. Do not alter or restart the operator's running process
while implementing; state upgrades occur on a deliberate, disarmed restart.

## 4. Current state

Baseline main 03bef16 is clean. Gateway 2119 is incorrectly latched critical;
321 detail and engine exception context are discarded. Arming/data/order flags
are regular-hours-only. Studio operator labels abbreviate codes. There is no
run-removal action. The active paper ledger is separate from repository files.

## 5. Proposed design

Use structured allowlisted broker diagnostics and exception type/code frames;
incident detail, recheck and acknowledge are separate. Transient connectivity
events resolve on recovery, while unexplained engine/order failures block.
Add visible strategy naming and full operator descriptions without changing codes.
Add audited archive/removal: disarm and confirm cancellation before hiding a run;
positions/unknown outcomes block removal; late fills reactivate recovery.
Add schema 4 settings for regular/extended hours and protective limit offset,
preserving schema 3 hashes/semantics. Select one exchange date (within seven
days), authorize ahead of time, and revalidate at dispatch. Intersect broker
hours and exchange dates with 04:00-20:00 New York for extended execution.
Keep opening-range/relative-volume definitions anchored to the regular open.
The connection test first checks connection/quotes, then explicitly authorizes
a one-share BUY below bid by max(1%, ten increments), a $1 protective distance,
and $0.10 stop-limit offset for extended hours. Cancel five seconds after
acknowledgement, with a 30-second broker deadline. Unknown transmission is never
resent. Unexpected fills keep protection and require a deliberate close.

## 6. Data model changes

Add incident diagnostics/recovery evidence; authorization date/hours/bounds;
archived/removal state; broker trading schedules and order session attributes;
typed diagnostic runs, preview identities and durable deadlines. Preserve old
versions and ledgers. Backup before durable compatibility updates.

## 7. API changes

Add incident detail/recheck; connection diagnostics and order-test preview/start;
run-removal preview/action and archived-run inspection. Extend arm preview with
selected date and deferred readiness. Mutations are idempotent; server decides
eligibility. Existing review gains recovery validation.

## 8. Test plan

Exercise broker status classification, readonly rejection, safe exception evidence,
engine recovery, schedule/DST/holiday/early-close boundaries, scheduled arming,
flat/cancel/position/uncertain run removal, late fills, fixed-quote test submission,
ack/cancel and crash races, and extended protective identity. Browser coverage
includes labels/name, incident drawer, diagnostic review, arming and run history.
Keep actual paper trials and automated evidence distinct.

## 9. Verification commands

Run focused pytest/frontend checks during implementation, then
`./scripts/verify.ps1` and `./scripts/paper-preflight.ps1`. Full verification
includes browser, dependency and secret checks. Preflight is read-only.

## 10. Rollback plan

Preserve the baseline commit and back up state before upgrades. Disarm and
reconcile before restarting. Never overwrite a running database. Restore into a
separate recovery directory; old pending records never authorize retransmission.

## 11. Implementation steps

1. Record baseline and diagnose/fix the reported engine failure with regression evidence.
2. Implement structured incidents/recovery and plain-language controls.
3. Implement safe run removal/history.
4. Implement selected-session authorization, extended data and stop-limit protection.
5. Implement quote/connection diagnostics and the one-share order test.
6. Complete browser verification, self-review, docs and operator trial instructions.

## 12. Completion criteria

Automated gate passes; existing schema 3 behavior is preserved; no live dispatch
or secret exposure; no duplicate submission after restart; new screens expose
pending, blocked and recovery states. Actual pre-market acknowledgement/cancel,
protective execution and supervised acceptance remain operator trials and are
never inferred from test doubles.

## 13. Risks and assumptions

Unchanged prices do not imply a broken feed; absent fresh quotes still block.
Broker hours and stop-limit support must be validated. Stop-limit activation
does not guarantee a fill. Legacy engine exceptions cannot be reconstructed from
discarded context. Record any reproduced causes and verification evidence below.

## Implementation evidence

- Started from a clean checkout; no broker orders or notifications authorized by implementation.

- Implemented all six software steps. Added structured incident recovery, bounded
  Windows health-file retries and retention of callbacks after a reducer fault;
  schema-4 session settings and broker-held extended stop-limit protection;
  scheduled arming; one-shot paper connection tests; and audited run removal.
- Added deterministic coverage for session/DST/early-close boundaries, quote-only
  tests, duplicate/expired previews, unexpected and late fills, cancellation and
  removal, stop-limit replay, legacy hashes and safe diagnostic redaction.
- Final `scripts/verify.ps1` passed on 2026-09-17 at 18:36 Sydney: 857 backend tests,
  188 frontend tests, complete browser/accessibility/layout checks, seven visual
  baselines, build/type/format/lint, dependency audits and secret scan.
- Read-only `scripts/paper-preflight.ps1` passed all six prerequisites, including
  the local paper Gateway TCP endpoint. It submitted no orders and did not attest
  a login or prove market-data entitlement.
- Updated Windows setup and the operator guide. Self-review and the exact verified
  fingerprint are recorded in `docs/PAPER_FLEXIBLE_SESSIONS_REVIEW.md`. The active
  operator process was not restarted and no broker order or notification was sent.
- Remaining external evidence: deliberate disarmed restart, actual supervised
  acknowledgement/cancel and extended protective-order trials, and the existing
  human usability/five-session release acceptance. None is claimed by these tests.
