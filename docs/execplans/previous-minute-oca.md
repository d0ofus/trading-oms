# ExecPlan: Previous-minute OCA breakout

## 1. Goal

Provide a schema-v5 Strategy Studio template placing opposing stop-market entries at
the previous live one-minute high/low, refreshing while flat, protecting either fill
at 1% of its actual average entry, and pausing after one completed trade. Support
US equity paper execution and hypothetical BTC/ETH local simulation shorts.

## 2. Non-goals

Live execution, real Paxos short sales, deployment, commits/pushes, trailing stops,
profit targets, unattended OCA qualification, or changes to historical simulation APIs.

## 3. Safety constraints

- Paper/simulation only; no secrets or broker execution capability in the data adapter.
- Manual authorization, fresh data, known reconciled state, funds, combined pending-leg
  reservations, protective orders, emergency stop, and duplicate prevention remain mandatory.
- No daily P/L eligibility gate. Immutable historical strategies and journals remain valid.
- Cancel acknowledgments and executions, never absence, determine replacement eligibility.
- Every intent, transition, risk decision, amendment, fill, reconciliation, and pause is audited.

## 4. Current state

Uncommitted readiness and crypto simulation work is present and must be preserved.
Workspace graph schemas 3/4 describe one long limit entry with attached protection.
Order allocation assumes three IDs; ledger quantities are signed but controllers,
protection, reconciliation, and the crypto simulator assume positive long holdings.
The existing crypto workspace uses a separate state directory, cookie, client and port.

## 5. Proposed design

Add an explicit paired-stop block and a durable OCA group state machine alongside
the existing long-entry lifecycle. Wait for a newly completed live minute after arming;
skip incomplete/zero-range/already-crossed candles. Cancel and reconcile the prior
generation before replacing; expire parents at the next minute boundary. First fill
cancels the opposing parent, its child, and any unfilled winning remainder. Maintain
and acknowledge exact-quantity protection rounded toward entry at 99%/101% of VWAP.
Keep provisional protection while a fill-based amendment is pending. Pause after flat.

Reserve both branches' combined planned risk/notional under existing ceilings using
one shared quantity. Paper uses native OCA type 1, protected STP parents, fresh borrow
and short-account eligibility; begin supervised at one share. Expansion needs distinct
long/short OCA paper-cycle evidence. No unsafe fallback for unsupported Gateway structure.
Simulator performs local atomic first-fill selection and cancellation, signed accounting,
fresh Last triggers and subsequent ask/bid fills, fully cash-secured shorts, no leverage,
fees, liquidity, or borrow costs. Restart/reconnect require reauthorization.

## 6. Data model changes

Schema 5 introduces explicit instrument profile and paired-entry block. Existing hashes
remain unchanged. Add durable execution-group documents with generation/candle, leg IDs,
direction, VWAP/protection acknowledgment, cancellation state and completion evidence.
Allocate order IDs by persisted high-water mark with legacy range compatibility. Keep
immutable intents; record amendments separately. Simulator persists signed quantities,
average entry and short liabilities with its existing atomic ledger journal transaction.

## 7. API changes

Extend catalog/templates, approval preview and workspace responses with paired levels,
candle, per-branch quantity, combined reservation, group/direction/protection state.
Keep existing endpoints and separate startup-selected paper/crypto environments.
Expose hypothetical crypto shorts clearly and direction-aware close actions.

## 8. Test plan

Closed-bar selection/no historical entry; both stop directions; rounding and gap fills;
combined reservations and ID allocation; one-cycle pause; partial/duplicate/corrected
executions; cancel/amend races and rejections; unknown borrow and account eligibility;
short marks/funds, emergency, session rollover, disconnect/restart; legacy hash regressions;
SDK execution traps for crypto; browser template/approval/orders/protection/cover workflows.

## 9. Verification commands

```powershell
. .\.tmp\activate-dev.ps1
python -m pytest backend/tests/test_workspace_oca.py -q
.\scripts\verify.ps1
```

Live-data local simulator smoke tests for long/short when Gateway data is available.
Native paper one-share trials require operator arming during the equity session;
record unavailable external checks rather than representing them as passed.

## 10. Rollback plan

Disarm runs and reconcile/cancel entries before changing builds. Preserve journals and
state backups. Do not reopen schema-v5 orders/short holdings with a long-only old build;
close/reconcile first or retain this build for risk-reducing recovery. Revert only this
slice's source changes; preserve the earlier uncommitted crypto/readiness work.

## 11. Implementation steps

1. Add focused failing tests, schema/template and pure sizing/leg helpers.
2. Add durable group allocation, side-aware accounting and simulator execution.
3. Integrate arming, candle generation, cancellation/protection/recovery and paper adapter.
4. Add Studio, approval and Desk diagnostics and browser acceptance tests.
5. Run checks, self-review trading safety and compatibility, fix findings, document evidence.

## 12. Completion criteria

All requested behavior is implemented with meaningful passing acceptance checks and full
verification; no live execution path or secrets; documentation explains operation and
simulator limitations; external trial status is stated accurately. No commit or push.

## 13. Risks and assumptions

Stop-market gaps may exceed planned risk and the 1% trigger distance. IBKR OCA/bracket
staging needs actual paper validation and remains unavailable on rejection. Protection
amendments are asynchronous; prior protection stays in place pending acknowledgment.
Crypto shorts are hypothetical only. Pending-pair lifetime is specific to this template;
other templates retain their existing 30-second timeout. All tests use synthetic account
contexts, no account IDs or credentials are copied into artifacts.

Implementation completed locally: schema/template and durable four-leg groups;
combined reservation and qualification; paper bracket staging/short credit checks;
signed simulator, fixed fill-based protection, cancellation/recovery; Studio and Desk
review/status; operator documentation. No commit or push.

Self-review corrected failed simulator commits, gaps with unrepresentable protection,
early paper rejection/release races, and recovery of a buy-to-cover intent that never
reached the local adapter. These cases have explicit regression tests. The focused OCA
suite passes 36 tests; browser coverage exercises both local directions, manual cover,
long close, verified protection, one-cycle pause, and paper template publication.
Legacy v3 template hashes are unchanged. No real paper OCA execution has been claimed.

Final automated verification on 2026-09-20: `.\scripts\verify.ps1` exited 0 with
`verify: ok`: 894 backend tests, 188 frontend tests, and 2 browser workflows passed;
format/lint/type checks, production build, repository/secret checks, pip audit and
npm audit passed. Audits found no known vulnerabilities. Nonblocking warnings concern
the existing Starlette/httpx test-client deprecation, frontend bundle size, test terminal
colors, and pip-audit's recommendation for hash-pinned dependencies. The gate wrote
fingerprint `8143edc9658e3d137ea8235ab2fea545c24fa8440bdb2e850b805df5c7888341`
at `2026-09-20T10:30:21Z`. An earlier attempt redirected native stderr in Windows
PowerShell and stopped on a Vite warning; running the gate directly succeeded.
The browser rename race was fixed by waiting for the newly created template draft
before editing it. No test failure was waived.

External smoke on Sunday 2026-09-20, 10:30–10:35 UTC: executed
`python .tmp/oca_live_smoke.py` after the gate, using data-only client 79 and separate
state `.tmp/oca-live-smoke-20260920-103027`. Gateway handshake, paper attestation,
BTC/PAXOS discovery, live Last/bid/ask, history download, informational P/L and manual
local authorization succeeded. The download initially contained 6,860 minute bars
and 720 five-second bars, with zero complete reference days (explicitly unavailable
relative volume; this template does not depend on it).

The four-minute authorized observation window recorded four `market.gap` events for
stale Last trades. Each repair resets the required complete live-minute boundary;
no eligible pair was submitted. The smoke reported `Timed out: await_actual_breakout`.
It ended disarmed with zero orders, zero executions and no positions. All 70 journal
events passed integrity verification; the final source fingerprint still matches
the successful gate. Log: `.tmp/oca-live-smoke.log`. No broker order or cancellation
was sent and existing workspace state/processes were not changed. Natural live-feed
long/short fill, protection and exit checks remain incomplete; deterministic and
browser coverage of those paths passed and is not represented as live-feed evidence.

Native one-share paper trials remain operator-armed and unavailable during the Sunday
equity closure. Larger paper sizing remains blocked until separate successful native
long and short OCA cycles provide qualification evidence.
