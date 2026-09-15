# ExecPlan: Selective typed strategy v2 integration

## 1. Goal

Execute the user's approved next step from the local/GitHub merge review: preserve local work,
start from current GitHub main, and integrate the useful typed simulation builder without losing
the newer saved-workflow approval, execution, recovery, comparison, and audit behavior.

## 2. Non-goals

- No broker connectivity, SDK, market-data worker, order transport, paper lab, or live trading.
- No changes to Candidate 062/063 review packets or readiness decisions.
- No automatic replacement or migration of existing v1 workflow files or simulation evidence.
- No general graph interpreter: unsupported topologies must be rejected before execution.
- No push, merge to main, or deployment in this task.

## 3. Safety constraints

- Simulation and fake fills only; preserve all current main safety gates.
- Explicit risk evaluation, human arming, immutable workflow/dataset binding, and protective plan.
- Reject stale/unknown data and reconciliation states and emergency-stop execution.
- Journal critical transitions and validate persisted run references against exact journal evidence.
- Reserve execution durably before producing fill evidence. An incomplete attempt is unavailable
  and cannot be retried into a second fill; preserve the partial audit trail.
- Reject unsupported graph wiring instead of silently executing a different strategy.
- No secrets or private account data in code, tests, docs, backup manifest, or output.

## 4. Current state

GitHub main is 0d1224b275ed52a4c1df0c48fc6f66a83b9311d1. The original local Slice 058 tree
equals merged main commit 3e57154 and has 42 modified/new paths. A verified archive of 265 tracked
and untracked source files is outside the repository at
../trading-oms-backups/20260914-162833/local-source-snapshot.zip. Ignored runtime state and build
dependencies remain in the untouched original folder; the source archive excludes them.

The review reproduced ignored stop wiring, duplicate fill evidence after interrupted persistence,
and completed results served with a missing journal. Current main already has stronger durable
v1 evidence handling and must remain the base. Work occurs in a healthy sibling checkout on
integration/typed-strategy-v2 with core.autocrlf=false.

## 5. Proposed design

- Port local typed DSL, definitions, runtime, service, UI, and client into explicitly named typed
  modules. Keep existing v1 implementations and route contracts intact.
- Use a separate typed workflow namespace and SQLite version store. Existing v1 saved definitions
  continue using their current storage and UI; there is no silent storage switch.
- Restrict executable typed graphs to the supported opening-breakout topology, allowing node IDs,
  labels/layout, range duration, and supported lifetimes to vary. Reject ignored nodes/edges/configs.
- Add expected-version conflict checks to typed saves, including safe exact retries.
- Add durable execution reservation, journal manifests, and validation on read/retry. Reuse main's
  journal write sessions and the reserve/finalize/fail-closed pattern; typed records remain separately
  identified because their Decimal envelope and arming semantics differ from v1 approval tickets.
- Keep typed API routes in a separate router and add a typed builder view alongside the existing
  workflow UI. Reuse operator authorization and emergency-stop services.
- Add clear simulation-only results and retain immutable dataset/version details. Keep optional
  read-only broker-data planning outside this implementation.

## 6. Data model changes

Add the typed workflow version/head, dataset, policy, run, authorization, report, execution-artifact,
and run-evidence tables from the local foundation with additive schema initialization. Typed runs
gain an internal executing reservation state and checksummed journal manifests. Existing v1
tables and JSON records remain unchanged. Pending execution cannot be automatically reset.

## 7. API changes

Add typed workflow catalog/validation/version/save routes under /api/typed-workflows, dataset
registration/detail under /api/strategy-datasets, risk-policy read, draft/arm/disarm/simulate/detail/
events under /api/strategy-runs. Exact paths will be documented with the implemented router.
Use distinct namespaces so existing /api/workflows and saved-run approval/execution contracts are
preserved. Mutation routes require the relevant author/operator permission. Evidence failures
return a generic unavailable response. No broker routes are added.

## 8. Test plan

- First add regressions for accepted-but-ignored stop wiring, interruption/retry duplication,
  missing/tampered journal evidence, concurrent execution, stale saves, and authorization boundaries.
- Retain and adapt local typed DSL, runtime, service, persistence, API, and frontend tests.
- Verify both UI variants and unchanged v1 approval/execution/run-comparison APIs.
- Check schema compatibility, immutable datasets, Decimal sizing, graph validation, stop monitoring,
  risk rejection, emergency stop, exact retries, and generic failures without private details.
- Run the complete repository gate, frontend build, diff checks, and bounded secret/live-path scan.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider backend/tests/test_typed_strategy_integration.py
python -m pytest -p no:cacheprovider backend/tests/test_typed_strategy_simulation.py backend/tests/test_strategy_run_service.py
npm.cmd --prefix frontend run test
npm.cmd --prefix frontend run build
.\scripts\verify.ps1
git diff --check
```

Use unique temporary pytest directories. Install frontend dependencies from the unchanged main
lockfile. Preserve LF bytes in the checkout for byte-sensitive review evidence.

## 10. Rollback plan

The original folder and source archive remain intact. Revert this branch's additive typed router,
view, and modules to return to main. Keep any typed journal/state directory for audit; do not
truncate or automatically replay incomplete attempts. No broker reconciliation is needed.

## 11. Implementation steps

1. Verify source backup and create healthy integration checkout from current main. Done.
2. Record this plan, then add the failing safety regression tests. Done.
3. Port typed modules additively and fix graph/runtime semantics, stale saves, and evidence lifecycle. Done.
4. Add isolated permission-checked typed APIs and adapt the typed UI alongside existing workflows. Done.
5. Update behavior/operation documentation and record review dispositions. Done.
6. Run targeted checks, full verification, build, and self-review; correct P0/P1 findings. Done;
   interactive browser verification is unavailable in this session and remains a manual follow-up.
7. Preserve the verified integration in a local commit and report the checkout/branch, backup,
   checks, and limitations. No push or main merge.

## 12. Completion criteria

- Original local source hashes still match the backup manifest.
- Existing main workflows, approval/execution evidence, comparison, and readiness behavior pass tests.
- Typed save/draft/arm/simulate flow works only with validated supported graphs and fake fills.
- All three reproduced P1 defects have regression coverage and are fixed in the integrated path.
- Stale saves and incomplete/tampered evidence fail closed; repeated requests cannot duplicate fills.
- Required verification and build pass, or exact blocking output is documented.
- No transport, secret, external publication, or main merge is introduced.

Final verification on 2026-09-15:

- `./scripts/verify.ps1`: passed; 767 backend tests, 188 frontend tests, four resilience tests
  rerun, formatting, linting, compilation and frontend type checking all passed.
- `npm.cmd --prefix frontend run build`: passed. Vite warns about a 591.20 kB minified JS chunk.
  The backend test client also emits a Starlette/httpx deprecation warning; no test failures remain.
- `git diff --check`: passed. Changed source files retain LF line endings.
- Original source SHA-256 verification: all 265 files match the verified archive manifest.
- Bounded scan of all 32 integration paths: no credential-pattern or enabled-live-config hits;
  no new transport imports. `git fsck --connectivity-only` passed in the integration checkout.
- Fresh `git fetch origin`: main remains `0d1224b275ed52a4c1df0c48fc6f66a83b9311d1`.
- Browser attempt: `No browser is available`; inventory contains no browser surfaces. Both
  builder sections pass static rendering checks. Local QA servers were stopped after the attempt.

Self-review fixes additionally cover exact-request retries, strict reconciliation, administrator
role separation, expiry at server time, emergency-state persistence, actual-fill risk resizing,
and protection/time exits across later supplied sessions. See `docs/TYPED_STRATEGY_SIMULATION.md`
and `docs/TYPED_STRATEGY_INTEGRATION_REVIEW.md` for the behavior and retained limitations.

## 13. Risks and assumptions

The user's instruction to execute the recommended next step authorizes this implementation plan;
no additional approval round is needed for the reversible isolated work. The typed simulator is
an intentionally bounded model, not a fill-quality claim. The application journal serializes within
one process; SQLite reservations must also prevent a second process from executing the same run.
Schema-v1 and typed workflows have separate storage and clearly separated UI/API identities until
a separately designed migration exists. The original missing Git objects are avoided by the fresh
checkout and are not repaired in place. New issues found during integration may require narrowing
accepted runtime inputs rather than adding speculative execution behavior.
