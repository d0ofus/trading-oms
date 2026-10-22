# ExecPlan: Minimal paper reviews and automatic readiness

## 1. Goal

Implement the approved minimal-review paper stock workflow: automatic preparation and
paper-context verification, stable reconciliation, consistent session/data readiness,
optional monetary ceilings, explicit share quantities, scoped recovery, and one final
authorization including verified dedicated recoveries. Preserve Studio nodes, ports,
positions, graph calculations, published behavior and live IBKR input semantics.

## 2. Non-goals

No live-account orders, broker credential/settings changes, automatic strategy conversion,
automatic publication, forced execution trial, extra trade entries, UI redesign or new
asset families. No changes to legacy crypto execution contracts.

## 3. Safety constraints

Retain paper adapter guards, human session authorization, fresh qualifying trades and
quotes (15 seconds), known ownership/protection, five active runs, legal quantities,
native funding and fresh FX, duplicate prevention, durable reservations and audit.
Emergency stop remains explicit. Protection/exits do not depend on entry authorization.
No production state is opened through a mutating Store during implementation/tests.

## 4. Current state

The working tree includes prior approved, uncommitted implementations; preserve them.
Schema 7 stocks inherit legacy monetary ceilings and forced one-lot qualification.
Reconciliation clears verified dictionaries on every refresh. Regular-hour card state
and broad recovery dependencies disagree with pre-market bindings. Review polling and
automatic preparation are incomplete. Incidents unconditionally disarm affected runs.
Baseline: 53 earlier and 36 additional focused tests passed; isolated reproductions
confirmed reconciliation clearing and the pre-market display mismatch.

## 5. Proposed design

Use versioned schema-8 stock risk settings (nullable ceilings), successor profiles and
fixed explicit quantity by default. New-policy validation is shared through sizing,
reservation and broker boundaries; old records retain their policy. New authorization
records pin engine/account context, material review fingerprint and resume permission.
Routine failures suspend eligible new-policy approvals; only verified same-process,
same-account, unexpired approvals resume with fresh live generations and counters intact.
Uncertain risk, integrity failures, manual stops and restart revoke approvals.

Stage broker reconciliation separately and atomically publish a complete snapshot.
Only clean, fresh previous snapshots survive background refresh; intervening trading
or contradictory evidence invalidates them. Generation-fence callbacks and refreshes.
Resolve dependencies per run/session, share subscriptions/history, and automate paper
verification using existing adapter guards. Shared recovered service incidents may
release only with unresolved contained dependencies retained as scoped restrictions.
One review includes optional local-protection acknowledgment and fully verified dedicated
incident releases, revalidated atomically. Dynamic checks refresh without stale approvals.

## 6. Data model changes

Schema 8, immutable successor risk profiles, pinned risk/recovery policy, authorization
status/context, reconciliation generation/revision evidence, and structured readiness
projections. Additive writes back up state before first migration. Preserve all old
versions, hashes, orders, approvals, journal records and protection plans.

## 7. API changes

Extend compatibility/preparation/arming/status responses with nullable monetary limits,
automatic progress, typed readiness, run/session context, review fingerprint, dedicated
recovery revisions and authorization state. New authenticated preparation mutations
ensure dependencies. Legacy endpoints remain compatible; unsupported clients cannot
authorize new behavior. Read-only status calls never authorize or submit orders.

## 8. Test plan

Add failing regressions first for schema-8 compilation/evaluation preservation, uncapped
funded quantities, old ceilings, reconciliation staging/invalidation, automatic context
and preparation, HIVE session/freshness, scoped recovery, routine suspension/resumption,
restart/integrity fencing, combined recovery approval and idempotency. Browser checks
cover the single-action review, cleanup, unchanged canvas interactions and bounded audit.
Fake brokers and isolated temporary stores only. No forced live/paper broker orders.

## 9. Verification commands

Use `.venv/Scripts/python.exe -m pytest` for focused regressions. Run frontend type/lint/
unit/browser checks and `./scripts/verify.ps1` with `.tmp/activate-dev.ps1` for full gate.
Record exact results and any unavailable separately operator-armed broker observation.

## 10. Rollback plan

Disable new-policy arming and auto-resume using execution-host flags; preserve management
of positions/exits. No hot database rollback. Restoring a backup requires a stopped owner
and reconciliation of broker exposure. Legacy published definitions remain available.

## 11. Implementation steps

- [x] Regression fixtures and gate inventory.
- [x] Stable reconciliation and run-aware readiness.
- [x] Automatic paper preparation and scoped recovery.
- [x] Schema-8 monetary policy and explicit-share profiles.
- [x] Routine authorization suspension and combined final review.
- [x] Existing UI integration, canvas regression checks and documentation.
- [x] Full verification, self-review and isolated browser acceptance.

## 12. Completion criteria

All approved behavior implemented; offline verification passes; new paths remain paper
only; no legacy/hash/canvas/signal regressions; current evidence gates each dispatch.
Normal healthy run requires one final authorization, no routine acknowledgments or
technical form entry. Separately armed broker observation is reported honestly if absent.

## 13. Risks and assumptions

Broker metadata/What-If cannot promise acceptance or odd-lot protection. Unknown essential
capabilities still block. Freshness is required before arming by explicit user selection.
Routine auto-resume is newly approved but never inherited by old authorizations. Keep
published entry limits and one-trade pause. Local stops remain explicitly acknowledged.
Preparation is reversible; execution trial needs the operator's separate arming.

## Progress notes

- 2026-09-23: Approved plan recorded before implementation; repository guidance read.
- Implemented schema 8 and successor profiles without changing legacy hashes. The
  isolated funded-share regression traverses binding, sizing, reservations, adapter
  validation and partial-fill protection above all former monetary caps. Old clients
  cannot authorize new policy without its fingerprint and resumption terms.
- Staged snapshots preserve clean verified evidence during ordinary refresh. New
  adverse funds/exposure, execution/ownership changes and superseded generations
  invalidate it immediately. Protection knowledge is retained when only funding
  evidence changes.
- Self-review corrected two unsafe overwrite paths after interrupted generic/OCA
  dispatch, and ensured invalid continuity revokes already suspended approvals.
  Transient feed reason codes now reach the authorization policy; pre-market history
  failures are session-scoped and share the verified recovery lifecycle.
- Recovery tests distinguish required history from unrelated watchlist warm-up and
  establish a contract restriction before releasing recovered shared infrastructure.
  Three old tests assumed unrelated warm-up must block; they were replaced with
  both required/unrelated cases and an explicit containment regression.
- `docs/MINIMAL_PAPER_WORKFLOW.md` records the gate inventory, migration behavior,
  operator workflow, policy differences and rollback switches. Operator guide and
  README link to it.
- Focused results: 57 recovery/pre-market tests, 11 monetary/adapter tests and 30
  reconciliation/stock/protection tests passed. Browser suite: 22 passed, including
  direct preparation-to-review, fail-closed polling and cleanup, canvas interactions,
  legacy simulation, library/archive flows and bounded Activity rendering.
- Inspected the new META and Xiaomi review screenshots: existing modal styling and
  layout retained, text wraps within the dialog, and the final action is accessible.
- Final `scripts/verify.ps1` completed with exit code 0 and `verify: ok`:
  1,254 backend tests, 190 frontend tests and 22 browser tests passed; lint,
  formatting, types, compilation, production build, secret scan and dependency audits
  passed. Pip/npm reported no known vulnerabilities. Existing dependency deprecation
  and Vite bundle-size warnings remain nonfatal.
- The first fully tested source run was interrupted after its successful build by
  PowerShell merging native warning output into its terminating error stream. The
  final gate ran unchanged in a child PowerShell with separate output streams and
  completed normally. Logs: `.tmp/minimal-verify-passed.log` and
  `.tmp/minimal-verify-warnings.log`. The superseded concurrent verification process
  was stopped before browser execution; no application process was stopped.
- No real broker trial, production incident release, account setting change or order
  submission was performed. A natural, separately operator-armed paper trial remains
  broker acceptance work; offline tests do not establish IBKR acceptance.
