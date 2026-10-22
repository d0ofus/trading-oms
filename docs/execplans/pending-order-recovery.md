# ExecPlan: Pending broker acknowledgment and accurate order recovery

## 1. Goal

Allow a valid paper BTC entry to progress through IBKR `ApiPending` without a false
unknown-order incident or application cancellation. Explain pending acknowledgment,
incomplete identity evidence, and known cancellation causes in the operator UI.

## 2. Non-goals

No live execution, new strategy behavior, automatic resubmission, changed financial
limits, automatic incident release, restored authorization, or historical migration.
Do not manipulate the operator's running workspace or broker orders during development.

## 3. Safety constraints

- Paper-only broker guards and the $25 crypto qualification ceiling remain enforced.
- Pending is neither accepted nor filled; reservations and duplicate prevention remain.
- Unknown outcomes, genuine mismatches, stale data, and unresolved restrictions block entries.
- Protection, cancellation, reconciliation, and risk-reducing exits retain their checks.
- Audit every observed callback and material transition; preserve immutable history.
- No secrets or raw broker rejection messages. Tests use isolated stores and broker doubles.
- Recovery requires current evidence, explicit acknowledgment, and fresh manual arming.

## 4. Current state

The shared reducer in workspace/oms.py omits ApiPending and maps it to unknown.
An incident then disarms the run and queues entry cancellation. The isolated reproduction
matches the recorded September 21 attempt. Crypto identity checking treats absent fields
in orderStatus as mismatches. Only Filled currently guards against status regression.
Crypto no-fill messages suggest permissions/minimum size even for local cancellations.

## 5. Proposed design

Recognize ApiPending as dispatching and display awaiting broker acknowledgment. Reduce
callbacks conservatively: retain audit observations, avoid duplicate transitions and
regression from working/cancelling/terminal states, preserve cancellation intent, and
require reconciliation on contradictory evidence. Executions remain authoritative for
owned quantity including late fills. Merge full details without erasing validated identity.
Missing crypto identity fields produce pending evidence; supplied mismatches remain failures.
Keep the existing default 30-second entry deadline, never extend it on repeated callbacks,
and cancel/reconcile without resubmitting. Record bounded cancellation reason codes and
expose read-only diagnostics in existing order views. Keep historical episodes unchanged.

## 6. Data model changes

No database or strategy schema migration. Add compatible projection fields for callback
disposition and safe cancellation reason in existing broker/order/cancel documents and
journal events. Existing records without those fields remain readable.

## 7. API changes

Extend order list/detail read models with broker status, acknowledgment-pending flag,
identity status, and known cancellation reason. Existing fields/endpoints retain meaning.
No new trading command or recovery bypass.

## 8. Test plan

Reproduce ApiPending without false incident/cancellation; acceptance, immediate and partial
fills, rejection, zero-fill cancellation, duplicates, delayed pending, fill before details,
late fill after cancellation, missing versus mismatched identity, deadline cancellation,
restart/reconnect and reservations. Confirm genuine unknowns still restrict entries and
protection remains available. Browser fixtures show acknowledgment and actual cancellation
cause. Full offline gate, then an operator-armed natural BTC paper opportunity if available;
record unavailable external checks without forcing an order.

## 9. Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_workspace_pending_orders.py -q
. .\.tmp\activate-dev.ps1
.\scripts\verify.ps1
```

## 10. Rollback plan

Stop the workspace normally before replacing executable code. Revert only this slice's
changes, retaining all user work and journal/state. Reconcile and explicitly review before
any new authorization. Old code retains the known false-cancellation defect.

## 11. Implementation steps

1. Add deterministic failing regression tests using isolated crypto fixtures.
2. Correct reducer, identity checking, cancellation reasons, and read models.
3. Add UI diagnostics and browser coverage; document operator recovery.
4. Run focused checks, full verification, and self-review; fix safety/correctness findings.
5. Record validation evidence and external test limits below.

## 12. Completion criteria

Regression and full gate pass. ApiPending cannot itself create a restriction/cancellation,
nor authorize another entry. Cash-budget zero quantities never prove fills or terminality.
Callbacks cannot regress lifecycle or discard late executions. UI communicates known
causes. Existing incidents and authorizations are not automatically changed.

## 13. Risks and assumptions

IBKR sends duplicate and incomplete callbacks; no individual status proves a complete
broker snapshot. Passing offline checks does not prove PAXOS paper acceptance. A natural
broker trial requires current connection, operator arming, and a qualifying breakout.

Implementation status: implemented and automated verification complete. External operator trial unavailable.

- Added regression tests first: the initial run reproduced 24 failures, including
  ApiPending causing unknown state, a restriction, disarm, and cancellation.
- Corrected pending/terminal reduction, current-snapshot lifecycle consistency, bounded
  deadline cancellation, explicit reason records, and missing-versus-mismatched identity.
- The first focused integration run passed 96 tests across pending orders, unified crypto,
  the shared engine, protection, and OCA. Expanded targeted checks cover immediate mismatch
  invalidation and delayed PendingCancel after terminal acknowledgment.
- A new isolated browser test passes for pending acknowledgment, identity evidence, cash
  budget, live dialog refresh, and known local cancellation cause.
- The new order-detail tests exposed invalid existing SQLite JSON paths. Corrected them
  as part of making the requested diagnostic endpoint usable.
- Self-review tightened immediate mismatch invalidation and included status conflicts in
  direct ownership checks. These remain blocking until fresh reconciliation; incomplete
  status-only observations do not raise a false identity incident.
- Retain a fresh broker working status after PendingCancel while latching the separate
  OMS cancellation intent. This preserves the existing once-per-connection cancellation
  retry after reconnect. The added regression reproduced the lost retry before correction.
- Latest focused run: 66 passed across 41 pending-order regressions, unified crypto and
  protection. An earlier full gate passed (1064 backend / 190 frontend / 12 browser);
  final verification is repeated after self-review corrections. An intermediate rerun
  was deliberately interrupted before its completion record; it is not acceptance evidence.
- Read-only inspection found no listeners on localhost paper ports 4002/7497 or UI port
  8000. The operator-armed natural BTC trial and TWS comparison are unavailable here.
- No real broker calls, incident releases, authorization changes, or production-state
  migrations were performed. Existing historical records remain unchanged.

Final verification evidence:

- Final backend gate: **1071 passed** (including all 41 new pending-order regressions).
- Frontend lint, TypeScript, formatting and unit gate: **190 tests passed**.
- Production build and final browser gate: **12 passed**, including bounded Activity,
  incident recovery, pending-order inspection and the unified crypto workflow.
- Secret scan passed; Python and npm dependency audits report no known vulnerabilities.
- The current source fingerprint is recorded by the normal verification module after
  all final-source checks completed. No implementation files changed afterward.
- An earlier direct `.\scripts\verify.ps1` invocation passed end to end. For the final
  source, `.\scripts\verify.ps1 *> .tmp/pending-order-verification.log` passed backend,
  frontend lint/type/format/unit checks and built the frontend, then Windows PowerShell
  redirection converted Vite's nonfatal bundle-size warning into a terminating error:

  ```text
  npm.cmd : [plugin builtin:vite-reporter]
  At D:\Python\trading-oms\scripts\verify.ps1:12 char:3
  +   & $FilePath @Arguments
  +   ~~~~~~~~~~~~~~~~~~~~~~
      + CategoryInfo          : NotSpecified: ([plugin builtin:vite-reporter] :String) [], RemoteException
      + FullyQualifiedErrorId : NativeCommandError
  ```

  The remaining gate commands were rerun directly, checking every exit code, without
  PowerShell stream redirection; all succeeded:

  ```powershell
  npm.cmd --prefix frontend run build
  npm.cmd --prefix frontend run test:e2e
  python scripts/secret_scan.py
  python -m pip_audit --disable-pip --no-deps -r backend/requirements-lock.txt
  npm.cmd --prefix frontend audit --audit-level=low
  python -m trading_oms_backend.workspace.verification
  ```

  Thus final-source coverage includes every command in the gate; the interrupted
  wrapper is not claimed as a successful single end-to-end invocation.
