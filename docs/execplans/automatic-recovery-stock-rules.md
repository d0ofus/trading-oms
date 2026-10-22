# ExecPlan: Automatic routine recovery and stock rules

## 1. Goal

Release verified routine restrictions automatically, retire unused feed dependencies,
and prepare US/Hong Kong stock runs without operator-entered contract rules.

## 2. Non-goals

No live execution, broker order trials, automatic arming, budget increases, route
substitution, deletion of evidence or changes to existing position management.

## 3. Safety constraints

Paper-only adapters, fresh data and valuation, explicit entry approval, durable
reservations and journal remain authoritative. Recovery requires current ownership,
watchdog/paper context, post-failure reconciliation and 30 healthy seconds. Dedicated
order/account/protection/engine incidents and emergency stop are not auto-cleared.

## 4. Current state

Incident policy v2 requires acknowledgment, including legacy service messages without
farm diagnostics. Unsubscribe leaves contract holds behind. Stock rules auto-resolve
only US USD contracts and require a manually saved fee allowance. Xiaomi metadata
already contains 200-share constraints, SEHK routing and broker schedules.

## 5. Proposed design

Policy v3 marks recognized routine episodes automatic; migrate projections with an
audit event without releasing on startup. An owner-checked transaction releases only
verified stable episodes. Retire unused contract feed holds following fresh complete
reconciliation, without claiming feed recovery. Reconnect recovery uses current
dependency evidence instead of requiring an obsolete farm. Deduplicate identical
service callbacks within an uninterrupted failure episode.

Resolve stock rules from route-specific documented policies and fresh broker
metadata, with HKEX board-lot reference corroboration. Fetch references off the engine
loop with bounded caches; unknown/conflicting evidence blocks new authorization.
Use automatic, versioned funding fee estimates. Preserve legacy bindings and manual
endpoints, but automatic bindings cannot accept manual rule overrides. UI uses a
read-only rules summary, explicit blockers and clearly labelled strategy versions.

## 6. Data model changes

Add incident release policy/reason, connection generation and dependency evidence;
reference cache records and field provenance; automatic stock policy revisions.
Published definitions, hashes, event rows and historical approvals are immutable.
Back up before additive migrations. New policy is pinned only to new bindings.

## 7. API changes

Extend compatibility with resolution/refresh state, provenance, missing requirements
and minimum-lot calculations. Extend incident projections with automatic recovery and
retirement status/countdown. Keep legacy recovery/rule endpoints compatible.

## 8. Test plan

Regression tests before behavior changes: routine stable recovery, owner/revision
races, same/new connection generation, retirement dependencies, dedicated holds;
US/HK rule derivation, stale/conflicting references, fees, USD25 lot conflict,
legacy hashes/bindings, partial quantities. Browser tests use isolated fixtures for
recovery status, stock preparation and unchanged canvas/navigation.

## 9. Verification commands

Targeted pytest and frontend tests during development, then `.\scripts\verify.ps1`.
No production state opened through mutating engine constructors or broker orders.

## 10. Rollback plan

Disable new automatic-policy arming through the policy rollback setting. Existing
positions retain pinned management contracts. Stop/reconcile before database restore.
Audit records of completed releases remain; rollback must not replay authorizations.

## 11. Implementation steps

1. Record plan and failing regression tests.
2. Implement incident classification, transactional release and dependency retirement.
3. Implement automatic policies, bounded reference refresh and binding compatibility.
4. Replace technical forms with summaries and recovery status within existing UI.
5. Run targeted/full verification, self-review and update operator documentation.

## 12. Completion criteria

Requested behavior implemented; tests and verification pass; no live path or secrets;
routine release never arms; unsupported rules/budgets remain explicit; existing
positions/history preserved. External broker acceptance remains operator-qualified.

## 13. Risks and assumptions

IBKR metadata is not proof of acceptance. Official references can be unavailable;
fail closed for new authorizations without affecting existing protection. HK board-lot
and odd-lot execution are distinct. USD25 may not fund one Xiaomi lot. Worktree contains
prior user changes; preserve them. Do not restart or mutate the user's running engine.

## Progress

- Planning recorded before implementation. Investigation baseline: 22 focused tests.
- Implemented policy v3 migration, audited automatic release, unused dependency
  retirement, farm recovery across connection generations and service deduplication.
- Replaced stock-rule forms with automatic US/SEHK summaries, bounded HKEX reference
  retrieval, current-connection metadata checks and automatic round-trip fee reserves.
- New regressions were observed failing before fixes for dependency recovery, missing
  farm diagnostics, legacy binding preservation, actual-fill fees and stale price rules.
- Focused recovery/stock/API/pre-market/legacy tests: 88 passed. The first full backend
  gate identified two legacy fixtures lacking required feed evidence; corrected them.
- Isolated Xiaomi browser walkthrough passed, including 200-share rules, the USD25
  conflict, absence of editable technical fields and unchanged navigation. Screenshot
  inspected for clipping/overflow. The first full browser run passed 20 tests and
  exposed an authentication wait missing in the new test; fixed and rerun successfully.
- Actual HKEX public file retrieval parsed 3,229 supported listing records and confirmed
  Xiaomi 1810 / HKD / 200. No account data was sent; no broker trial was performed.
- Final `.\scripts\verify.ps1` completed with `verify: ok`: 1,213 backend tests,
  190 frontend tests, 21 browser tests, formatting/lint/type checks, production build,
  secret/dependency audits and isolated paper-workspace verification passed.
- Final callback review added one regression for retired Gateway clients supplying price
  rules. It failed before the connection-generation guard and passed afterward, together
  with 49 focused adapter/stock/search tests. Formatting/lint were rechecked after this
  guard. The complete gate's test collection preceded this additional regression.
- An earlier gate invocation redirected native warning output through PowerShell and
  stopped on Vite's bundle-size warning despite a successful build. Rerunning the
  unchanged verification script without that redirection passed. Non-failing dependency
  deprecations and the existing bundle-size warning remain.
- Production engine/state have not been restarted or mutated by this task. Migration
  runs on normal updated launch; automatic release still requires verified recovery.
