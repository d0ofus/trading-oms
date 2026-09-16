# Professional paper workspace implementation review

Reviewed by the implementation agent on 2026-09-16. This is a code self-review, not an independent architecture, trading-safety or security review. Baseline: `2f6569280ed272940e21f9c3a1af0702be457f15`, on the existing `main` checkout. Historical review packets and legacy simulation modules are preserved.

## Scope and evidence boundaries

The implementation covers the local UI, canonical strategy contract, shared replay/paper signal and sizing logic, durable outbox and order reducer, paper-only SDK boundary, data recovery, profiles/authorization, positions/protection, monitoring and state recovery. No actual Gateway API login, broker order, external notification or unattended paper session was performed. The selected Gateway installer was downloaded and verified; it was not installed or launched.

The ordinary gate uses local fixtures and broker doubles. Browser verification has an isolated temporary state directory and a broker whose networking and mutation methods fail. Replay orders exist only in simulation state. Actual broker evidence is only recorded by the concrete paper adapter, never by a test subclass. Human usability timing and final five-session acceptance remain external release requirements.

## Safety findings resolved during implementation

| Finding | Resolution and relevant checks |
|---|---|
| Duplicate submission after an interrupted dispatch | Persist identity, payload hash, reservation and dispatch state before SDK contact; restore unfinished dispatch as unknown; no resend. Core/chaos tests cover reservation/dispatch boundaries |
| Emergency activated between risk preview and send | Recheck durable emergency and current authorization inside reservation/dispatch transactions and batch arming |
| Partial entry could lack active broker protection | Cancel remainder, reconcile exact executions/position, require terminal evidence for prior sell legs, then persist and dispatch one replacement stop. Missing acknowledgement remains unknown |
| Flat position could retain a replacement sell | Reconciliation checks original and replacement sell intents; no capacity release or new entry until all are terminal |
| Competing exits could oversell | Serialized owned-quantity exit controller, same OCA group with block, pending-state exclusion, cancellation confirmation before replacement |
| Callback duplication, correction and cancel/fill races | Shared durable reducer deduplicates execution IDs, applies revisions and does not let a late cancellation erase a fill; inconsistent identity is blocking |
| Inactive broker status could be mistaken for a terminal rejection | Inactive remains unknown unless a correlated rejection proves the outcome; foreign-account executions never update owned position state |
| Reconciliation requests could overlap | Only one snapshot is in flight; timeout starts fresh connection recovery rather than mixing completion callbacks |
| Reconnect could resume with changed login or stale indicators | Retain account context only in adapter memory; changed context disarms. Repair/warm data and reconcile before resumption; restart always requires rearming |
| A cancelled request could be silently lost across disconnect | Durable cancellation queue; resend cancellation only after a new epoch positively identifies the same working order, never as an order replacement |
| Replay and paper could evaluate different transitions | Shared graph evaluator, warm-up/edge transition, sizing, durable outbox and observation reducer; replay preserves distinct synthetic fill assumptions |
| Late/gapped trades and forming indicators could change decisions | Reject finalized-candle late trades; stale data requires repair; no retrospective entries; forming EMA derives from completed state; relative volume matches completed boundaries |
| Notification failures or watchdog restarts could be hidden | Durable alert retries, current heartbeat/watchdog requirements, unattended disarming, persistent watchdog emergency and retirement when a new process takes over |
| Shutdown could stop monitoring before disabling entries | Shutdown stops and disarms the engine before stopping its notification worker |
| Historical approvals or restores could authorize new entries | Legacy records are read-only; supported definitions become drafts. Restore activates emergency and disarms; startup reconciles uncertain order state |
| SDK dependency had a known vulnerability | Packaging-only Protobuf pin changed from 5.29.5 to patched 5.29.6; official SDK source unchanged; archive hashes and installer signature recorded |
| Repeated calendar queries reduced tick throughput | Cache immutable exchange-session boundaries by date; long replay test duration dropped from about 91 seconds to 13 seconds locally |
| Accessible controls broke in canvas/zoom layouts | Add valid port roles, preserve Radix-managed panel IDs and label collapsed navigation. Browser checks include both editors, themes, keyboard access and desktop/zoom layouts |

The new production launcher binds only to `127.0.0.1`. Mutation requests require a same-origin authenticated local session and have idempotency handling. Paper account identifiers never leave the adapter; free-form SDK errors and credential URLs are excluded from application logging. Secret storage uses Windows Credential Manager. The broker endpoint is fixed to local paper port 4002 and the adapter checks paper context before each mutation.

No known P0/P1 finding remains open from this self-review. That statement is limited to inspected code and automated evidence; it is not a claim of real broker execution qualification.

## Verification record

Final Windows verification completed on 2026-09-16 at 16:42 Sydney time. `./scripts/verify.ps1` exited successfully with `verify: ok`.

| Check | Result |
|---|---|
| Backend tests | 831 passed, including 64 added workspace tests; 167.17 seconds |
| Frontend unit tests | 188 passed across 31 files |
| Repository, Ruff, Python compilation, frontend lint/types/format | Passed |
| Production frontend | Built successfully |
| Browser workflow | 1 passed; 38.6-second walkthrough, 45.4-second browser run |
| Visual and accessibility checks | Seven Windows baselines compared without updates; guided/canvas, arming, recovery, setup and both themes; automated accessibility and desktop/zoom layout assertions passed |
| Secret scan | No recognized credential patterns found in reviewable files |
| Python and npm dependency audits | No known vulnerabilities found; npm reported zero |

The recorded source/build fingerprint is `c9a2d95c6cd7b475f1be39d6d1fee066359e102cdb05468a9afd8cfc9ca89075`. The local gate record explicitly has `paper_trials: false`. Initial failures and their fixes remain in the ExecPlan. These results were obtained on Windows; remote CI results are separate evidence.

The first remote CI run passed Ubuntu and exposed three historical evidence hash failures on Windows with `core.autocrlf=true`. The corrective change pins the review-packet generator and Candidate 062 plan to LF in `.gitattributes`; it preserves historical content and expected hashes. An autocrlf-enabled checkout now produces identical bytes, and all 26 affected historical evidence tests passed in 6.83 seconds. Production code and the verified source/build fingerprint are unchanged by this checkout-only correction.
The checkout probe also reproduced Prettier rejecting automatically converted CRLF frontend files. TypeScript, TSX and CSS now have explicit LF attributes; representative copied files pass Prettier with autocrlf enabled. Source content remains unchanged.

Nonblocking warnings remain: Starlette deprecates its current HTTPX TestClient integration; the main frontend JavaScript bundle is 588.07 kB before gzip; pip-audit recommends artifact hashes in addition to the fully pinned dependency versions. The official SDK and Gateway downloads already have explicit SHA256 checks.

`./scripts/paper-preflight.ps1` then exited with an unresolved external prerequisite. Five checks passed: the verified build, official API 10.50.2, patched Protobuf 5.29.6, built frontend and Windows credential-storage platform requirement. The sole failed check was **Local paper Gateway endpoint**: no reachable TCP listener at `127.0.0.1:4002`. The exact script error was `Paper preflight found unresolved prerequisites. See the checks above.` No broker login or order was attempted. This endpoint check does not verify API handshake, account context, entitlements, credential delivery or actual broker behavior.

## External release work

Follow `GETTING_STARTED_WINDOWS.md` and `PAPER_OPERATOR_GUIDE.md`: install/login to the pinned paper Gateway, verify entitlements/five-symbol capacity and handshake, execute supervised one-share/protection/close and reconnect trials, qualify actual partial-fill repair before multi-share unattended execution, demonstrate notifications/watchdog/restore, time the trader workflow, and review five consecutive actual sessions. The software records session evidence and acceptance without turning automated tests into broker evidence. Live trading remains outside scope.
