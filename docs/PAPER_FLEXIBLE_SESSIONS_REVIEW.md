# Flexible paper sessions: implementation self-review

This records the 2026-09-17 implementation of the approved
[diagnostics and flexible-session plan](execplans/paper-diagnostics-and-flexible-sessions.md).
It is a code self-review and automated verification record, not an independent
review or evidence of actual paper execution.

## Incident findings

- IBKR 2119 is a data-service connection status. The prior application incorrectly
  retained it as a critical blocker after connectivity recovered. It is now
  informational and subsequent 2104/2106 recovery is recorded. Separate feed
  freshness, permission and reconciliation checks still apply.
- 321 is a real broker validation rejection. Raw historical detail was discarded,
  so the cause of the operator's historical incident cannot be reconstructed.
  New callbacks classify recognized read-only-mode responses into fixed safe
  descriptions; they never persist raw messages, credentials or account text.
- Windows file replacement can raise `PermissionError` while the watchdog holds
  the existing health file open. This was reproduced using temporary files on
  this PC. Publication now retries on later engine cycles, bounded to five
  seconds. Persistent failures still raise an engine incident, and the independent
  watchdog still enforces heartbeat freshness. The reproduction is not proof of
  the historical fault's cause.
- New engine faults retain the failed operation, exception type, and source-code
  frames, excluding exception arguments, locals and full filesystem paths. The
  callback loop retains the rest of a batch after a reducer failure. Recovery
  requires a successful repeat and a healthy interval, then current reconciliation
  and explicit acknowledgement. Legacy contextless faults require a new process
  and a successful setup recheck.

## Execution and persistence review

- Scheduled authorization binds the immutable version, chosen exchange date,
  hours and bounded risk. The engine and transactional reservation reject early
  entries. Dispatch rechecks the broker schedule and its 15-minute cutoff. All
  new-entry authorizations remain disarmed after restart.
- Extended hours intersect broker schedule intervals with 04:00-20:00 New York on
  XNYS dates. DST, holidays, early closes and unavailable schedules are covered.
  No overnight venue or live endpoint has been added. Extended unattended arming
  is blocked. Regular-hour versions retain their existing stop-order contract.
- Extended brackets use GTD limit entries and GTC stop-limit protection with the
  outside-hours flag on each leg. Reconciliation verifies order type, flag and
  protective limit. Replacement protection preserves the same contract. Risk
  reservations and replay sizing include the protective-limit offset; a stop-limit
  is never described as a guaranteed maximum loss.
- The connection test uses the existing durable outbox, risk reservation and
  reducer. Reusing its preview cannot create a second entry. It needs fresh
  quotes, not historical warm-up or a crossing signal. Submission, acknowledgement,
  cancellation and flat reconciliation remain separate states. Unexpected fills
  remain owned and monitored. This diagnostic never unlocks ordinary strategy
  execution qualification.
- Removal archives a run only after flat ownership, terminal orders/children,
  released risk and current reconciliation. No order, execution, version or event
  is deleted. A late execution restores the run to recovery. Unused prepared runs
  can be removed without a broker connection.
- Schema 3 remains supported. The original opening-range template execution hash
  is asserted against the pre-change baseline. Schema 4 adds explicit session and
  stop-limit settings; published old versions are not rewritten. Startup creates
  a checksummed backup before the first additive paper-state compatibility update.

## UI and operator workflow review

Strategy naming is visible above the editor. Operation names are expanded in both
editor views, with internal codes unchanged. The arming review includes a New York
date and per-run windows. Trading Desk shows session/data waiting states and run
history. Settings and Testing expose the one-share connection test. Activity
separates incident inspection, read-only recheck and acknowledgement.

The isolated browser walkthrough covers guided/canvas switching, autosave, naming,
operation labels, execution-hours selection, publication, replay, blocked arming,
run removal/history, diagnostics and incident inspection. Its broker cannot open
a socket or submit orders. Dark/light accessibility and desktop layout checks are
included. Visual baselines are regenerated only for intentional UI changes and
then compared by the ordinary gate.

## Remaining operator evidence

No actual paper order, cancellation, account-setting change, notification or
unattended session was performed by this implementation. The running application
was not restarted. Supervised Gateway acknowledgement/cancel and extended bracket
behavior must still be observed on the actual paper account. Five-session release
acceptance and human usability timing remain separate requirements.

Follow [the current operator guide](PAPER_OPERATOR_GUIDE.md) after a deliberate
disarmed restart. Historical audit/review records retain their original status.

## Verification results

Final `scripts/verify.ps1` passed at 2026-09-17 18:36 Sydney time:

- 857 backend tests passed (71.55 seconds).
- 188 frontend unit tests passed; lint, formatting, typechecking and build passed.
- The browser walkthrough passed (21.6 seconds), including accessibility and
  layout checks; seven Windows visual baselines were compared without updates.
- Secret scan found no recognized credential patterns. Python and npm audits
  reported no known vulnerabilities.
- `git diff --check` passed.

Verified source/build fingerprint:
`33ca3bbf6fef2177ecad36e7990e5de8831d7737e505f607b4d53aba7db0d023`.
The verification record explicitly reports `paper_trials: false`.

`scripts/paper-preflight.ps1` passed all six checks: verified application build,
official API 10.50.2, patched Protobuf runtime, local paper Gateway TCP endpoint,
built frontend and Windows credential-storage platform. This is a TCP reachability
check, not API attestation, data entitlement or broker execution qualification.
No broker order was submitted.

Nonblocking tooling warnings remain: the test client's upstream httpx deprecation,
the production bundle size advisory, pip-audit's recommendation for fully hashed
requirements, and the browser harness's NO_COLOR/FORCE_COLOR environment notice.
No verification failure remains.
