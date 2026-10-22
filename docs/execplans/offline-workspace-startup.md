# ExecPlan: Open the workspace before Gateway login

## 1. Goal

Open localhost:8000 and browse the application with Gateway closed. Complete any
required read-only migration check from Settings when the operator connects later.

## 2. Non-goals

No trading strategy changes, migration bypass, live execution, or broker trials.

## 3. Safety constraints

Keep paper-only validation, local engine locks, backups and immutable history.
While migration is pending, instantiate only a data-only adapter, block execution
commands and trading maintenance, and retain the original ledger. Do not submit,
cancel, repair protection, liquidate, attest the execution connection or arm runs.
After migration require the existing paper attestation, reconciliation, fresh data,
risk checks and manual approval. Never expose credentials or account identifiers.

## 4. Current state

serve.py calls prepare_workspace before starting HTTP. An old untyped/non-ready
snapshot requires Gateway and code 502 therefore prevents all application access.
The ordinary Engine can mutate broker orders during recovery and cannot run that
recovery until migration succeeds. migration_snapshot.py already uses GatewayData,
whose SDK write methods are disabled.

## 5. Proposed design

Attempt only offline migration checks before app initialization. Back up a blocked
legacy workspace before allowing UI activity. Pass an explicit pending migration
controller to Engine; delay normal restoration and execution-adapter creation.
Keep HTTP, engine command processing and watchdog heartbeat available. Connect
starts a bounded background data-only snapshot; poll its result on the single
engine owner, audit it and apply existing migration validation. Failed checks stay
visible and retryable. Success activates the normal paper adapter and connects;
the operator still verifies the paper context and manually arms later. Local OMS
orders/positions that require the old engine remain blocked and explained.

## 6. Data model changes

Add append-only deferred/cancelled migration diagnostics. No schema changes or
rewrites of existing journal, executions, orders, versions or approvals.

## 7. API changes

Add migration status to workspace snapshots. Existing session connect initiates
the deferred check; disconnect/shutdown cancel it safely. Other execution actions
return a migration conflict while pending. Existing authentication remains intact.

## 8. Test plan

Cover offline launch and authenticated navigation, backup/history preservation,
execution-command rejection and absence of broker writes, failed connection and
successful retry, duplicate requests, shutdown/disconnect, fresh CASH acceptance,
blocking security/unknown positions and local orders, and no automatic arming.
Add browser coverage for offline navigation and actionable migration status.

## 9. Verification commands

Run focused pytest and browser tests, then `.\scripts\verify.ps1` with the prepared
development environment active. Record external checks that cannot be performed.

## 10. Rollback plan

Stop the app before restoring code. Preserve current state and migration backups;
never delete the migration marker or journal to force migration. The prior launcher
requires Gateway before opening HTTP.

## 11. Implementation steps

1. Add regression tests for the startup and pending migration lifecycle.
2. Add the deferred controller, engine boundary and nonblocking launcher flow.
3. Display pending/checking/blocked status and retry instructions in the app.
4. Update operator docs, run targeted checks, review safety, and run the full gate.

## 12. Completion criteria

The app opens and supports navigation without Gateway; failed checks do not stop
HTTP. Migration still requires flat, complete paper evidence. No writable adapter
or normal trading maintenance exists before success. Full verification passes.

## 13. Risks and assumptions

The real Gateway may be offline; automated fake-broker tests cannot establish live
broker availability. Both engine locks remain held during deferred migration.
Snapshot completion must not outlive shutdown or start an unwanted connection
after an operator disconnect. Historical local orders require the prior model.

Implementation and verification completed locally. The launcher now starts HTTP
without contacting Gateway. DeferredMigration backs up pending legacy state,
keeps Engine on GatewayData with trading maintenance disabled, and activates the
paper adapter only after the original migration guards pass. Settings and the
workspace banner explain pending checks and retryable failures. No real Gateway
connection, user-state migration, order submission or cancellation was performed.

Verification: 59 focused migration/unified tests passed, including 20 new offline
startup tests. `.\scripts\verify.ps1` finished with `verify: ok`: 955 backend tests,
188 frontend tests, four browser workflows, formatting/lint/type checks, production
build, secret scan and dependency audits passed. Browser coverage opens a legacy
workspace with no Gateway, reports a simulated 502, and continues navigation.
Existing Starlette deprecation, Vite bundle-size and pip-audit hash advisories are
nonblocking. `git diff --check` passed with only existing line-ending warnings.
