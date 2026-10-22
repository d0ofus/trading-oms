# ExecPlan: Recover a stale migration snapshot at startup

The pre-HTTP startup behavior in this historical plan is superseded by
[offline workspace startup](offline-workspace-startup.md). Snapshot validation
remains; the UI now opens first and Settings initiates the read-only check.

## 1. Goal

Allow the unified launcher to refresh an obsolete reconciliation snapshot using a
read-only paper Gateway connection, without requiring the previous application.

## 2. Non-goals

Bypassing flat-account migration, adopting external positions, clearing unknown
OMS orders, sending broker orders/cancellations, or enabling live accounts.

## 3. Safety constraints

Hold both state-directory locks. Keep all execution disabled during the check.
Require a complete, current, single-paper-account snapshot. Currency positions must
be positively typed CASH; unknown/nonzero security positions and working orders
block migration. Preserve history and back up before recording the migration.
No account identifiers or credentials may appear in output or journal records.

## 4. Current state

The launcher exits before the application can start if the last reconciliation was
not ready. This user's old snapshot has two untyped positions, with no local orders,
executions, saved broker orders or runs. The migration guard therefore prevents
obtaining the fresh typed snapshot needed to correct that legacy observation.

## 5. Proposed design

Keep strict offline migration validation. Distinguish a stale broker snapshot from
unresolved local exposure. For the former, the launcher performs a bounded snapshot
request through GatewayData, which has no order submission/cancellation capability.
Validate all stream completion markers, context and snapshot contents before retrying
migration. Journal fresh evidence separately from strategy/execution qualification.
Return an actionable startup message for unavailable Gateway or unresolved exposure.

## 6. Data model changes

Append migration snapshot evidence to the journal after the pre-migration backup.
Do not rewrite old reconciliation events, order records, positions or qualifications.

## 7. API changes

No public API or trading-mode changes. The existing launcher automatically performs
the read-only check when a stale snapshot prevents migration.

## 8. Test plan

Cover legacy untyped positions followed by fresh CASH/empty snapshots; external
security positions, unexpected accounts and working orders; missing end markers,
disconnection, queue overflow and live context; local unresolved orders; preservation
of history/backups; adapter execution firewall and clean startup errors.

## 9. Verification commands

Run focused migration/recovery tests, then `.\scripts\verify.ps1`. If the user's
paper Gateway is available, run the actual read-only check without arming a strategy.

## 10. Rollback plan

Restore the prior launcher/migration code while stopped. Retain all append-only
evidence and backups. Never replace a running or exposed account's state database.

## 11. Implementation steps

1. Add regression tests reproducing the old untyped snapshot.
2. Add bounded, read-only snapshot collection and strict flat-state validation.
3. Integrate automatic startup recovery and actionable failures.
4. Update migration instructions, verify and record available external checks.

## 12. Completion criteria

Stale snapshots can be refreshed without old code. Migration still refuses unknown
or exposed state. No broker writes are possible. Required verification passes and
the operator receives a concrete launch/recovery command.

## 13. Risks and assumptions

A working paper Gateway is required for fresh evidence; elapsed time and missing
orders cannot substitute for complete callbacks. Local unresolved order histories
remain a separate recovery problem and cannot be erased by this check. The ordinary
engine still requires its own fresh reconciliation and manual arming after startup.

Implementation: added bounded snapshot collection through GatewayData, automatic
launcher refresh for obsolete snapshots, strict validation of typed positions and
terminal orders, a backup before recording refresh evidence, and concise startup
failures. The read-only adapter pins the same paper account while accepting duplicate
account-context callbacks; it never enables SDK writes. Local unresolved OMS state
still blocks before a broker refresh is attempted.

Self-review found and fixed a disconnect race where an unsuccessful connection's
callback thread could exist before it had started. Cleanup now checks the thread's
start state. Regression tests cover this and enforce the SDK execution firewall even
after read-only account verification. Browser-test timing races were fixed by waiting
for the new template, its name-save acknowledgment and the close-request response.
The isolated browser fixture now serializes engine calls and synthetic broker fills;
without the production command loop, concurrent UI reads could otherwise cache an
intermediate owned quantity. No production trading behavior changed for this fixture fix.

External check on 2026-09-21 AEST: the actual read-only connection returned Gateway
code 502, and no listener was present on port 4002. Fresh broker-position confirmation
and actual migration remain unavailable. No broker orders or cancellations were sent,
and this investigation did not rewrite or migrate the user's historical state.

Verification completed on 2026-09-21 AEST: `.\scripts\verify.ps1` exited 0 with
`verify: ok`. All 935 backend tests (including 20 migration-recovery tests), 188
frontend tests and 3 browser workflows passed. Formatting, lint, type checks,
production build, secret scanning and both dependency audits passed; the audits
reported no known vulnerabilities. The verified source/build fingerprint was recorded.
Earlier browser failures were resolved by the synchronization and ownership fixes
above; no gate check was skipped or weakened. `git diff --check` also passed.
