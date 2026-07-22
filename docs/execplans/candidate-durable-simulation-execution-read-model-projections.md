# ExecPlan: Durable simulation execution read-model projections

## 1. Goal

Project fully validated, committed schema-v4 saved-workflow simulation executions into the existing
orders, positions, alerts, protection, and audit inspection surfaces. Operators must be able to
trace each projected record back through its saved workflow version, run, execution, order intent,
risk decision, manual approval, fake fill, position, protection observation, local alert, and
append-only journal references after process restart.

## 2. Non-goals

- No new mutation endpoint, workflow execution command, automatic execution, retry, or repair.
- No persistence schema migration, data deletion, journal rewrite, or representative-data import.
- No IBKR dependency, SDK, socket, probe, host, port, account, credential, or broker transport.
- No external alert delivery, deployment, production rollout, or live-trading capability.
- No Candidate 063 implementation or relaxation of any existing paper-transport gate.

## 3. Safety constraints

- Live trading remains disabled and no order can leave the local deterministic fake broker.
- Only committed schema-v4 SQLite evidence whose digest-bound manifest exactly matches the local
  append-only JSONL journal may be projected.
- Pending, partial, malformed, missing, digest-invalid, source-mismatched, contradictory, or
  otherwise unavailable evidence must fail the complete execution-backed snapshot closed.
- Projected records must be explicitly local-only, simulated, fake-broker-derived, and externally
  unverified; fake-broker evidence must never be represented as real broker evidence.
- Risk-pass and separate manual-approval attribution must remain present on every projected order.
- Missing expected protection must remain critical, retain its risk-increasing-action block, and
  remain linked to its local no-op alert evidence.
- Reads must be deterministic and idempotent, add no journal records, and expose no secrets or
  unsafe order/broker controls.

## 4. Current state

- `workflow_simulation_run_evidence` schema version 4 stores committed saved-run execution records
  and digest-bound journal manifests.
- `WorkflowSimulationRunner` reconstructs each run strictly and compares every manifest record to
  the JSONL source, but it currently lists runs only for one workflow and exposes no validated
  all-workflow projection source.
- `build_demo_operations_read_model()` supplies representative orders, positions, alerts, and
  audit events to the existing read APIs.
- The frontend operations shell, audit explorer, order detail, position detail, and protection
  monitor consume those legacy record shapes and cannot display saved-workflow execution lineage.

## 5. Proposed design

1. Add a deterministic all-workflow evidence listing operation to local persistence and expose a
   runner method that returns only fully validated run records paired with their verified manifest.
2. Add a pure projection module that filters committed executed runs, rejects duplicate projected
   identities, and creates one atomic projection snapshot for orders, positions, local alerts, and
   execution-related audit events.
3. Add one reusable simulation-execution attribution read model to the affected legacy rows. It
   carries exact workflow/version/run/execution/order/risk/approval/fill/position/protection/alert
   and journal references plus fixed local simulation provenance.
4. Keep representative rows unchanged when no execution exists. When at least one committed
   execution exists, replace the affected representative collections rather than mixing sources,
   and replace their resource provenance with durable local simulation provenance.
5. Build the affected API envelopes from one projected operations snapshot. Convert any durable
   evidence or projection failure into a generic HTTP 503 without returning partial data.
6. Extend the existing frontend types and inspection panels to display provenance and exact
   workflow/run drill-down while preserving read-only behavior.

## 6. Data model changes

- No SQLite schema change.
- Add `SimulationExecutionAttributionReadModel` to the read-model layer.
- Add optional execution attribution to audit, order, position, and alert read models. Existing
  representative records use `null`; durable projected records require complete attribution.
- Add an immutable projection snapshot and validated source record in backend code only.

## 7. API changes

- No endpoint or HTTP method is added.
- Existing `GET /api/audit-events`, `GET /api/orders`, `GET /api/positions`, and
  `GET /api/alerts` return durable projected rows when committed execution evidence exists.
- The four affected envelopes report a durable local simulation provenance classification.
- Any integrity/unavailability failure affecting execution evidence returns a generic HTTP 503 for
  the affected read APIs; no paths, SQL details, raw evidence, or partial records are returned.

## 8. Test plan

- Backend unit tests for exact projection of protected and missing-protection executions.
- Backend tests for deterministic order, stable IDs, duplicate rejection, fixed provenance, and
  representative-data replacement/separation.
- Persistence/runner tests for all-workflow listing, restart recovery, repeated reads, and exact
  source-manifest validation.
- API tests for projected payloads, generic unavailable responses, corruption and pending evidence,
  filtering attribution, and absence of mutation or unsafe affordances.
- Frontend tests for attribution validation and rendering in operations rows, audit detail, order
  detail, position detail, and protection monitoring, including missing-protection critical state.
- Frontend tests that no broker, account, credential, transmit, deployment, production, or live
  controls are introduced.

## 9. Verification commands

```powershell
$env:PYTHONPATH = "backend/src"
python -m pytest backend/tests -q --basetemp backend/.test-tmp/projection -p no:cacheprovider
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
.\scripts\verify.ps1
git diff --check
git fsck --full
```

Run repository secret/live/broker-path scans over changed files and inspect the loaded operations
shell through the Vite proxy at `http://localhost:5173` with a real protected and missing-protection
execution fixture.

## 10. Rollback plan

Revert this branch's bounded commit. Because the slice adds no migration or write behavior, rollback
restores representative read models without modifying saved workflows, schema-v4 execution rows,
or the append-only journal.

## 11. Implementation steps

1. Add failing backend tests for validated projection sources and projection behavior.
2. Add the all-workflow persistence/runner read path and pure projection module.
3. Extend read models and affected API assembly with atomic fail-closed behavior.
4. Add failing frontend tests for exact attribution, drill-down, provenance, and safety controls.
5. Extend API types, validation, details, audit explorer, protection monitor, and operations rows.
6. Update read-model, persistence, execution, audit, order/position, protection, UI, roadmap, and
   slice documentation.
7. Run focused tests, full verification, production build, scans, integrity checks, localhost
   inspection, and P0/P1 self-review; fix all P0/P1 findings.
8. Commit only intended files, push the dedicated branch, open an unmerged PR against current
   `main`, and require green CI on the exact remote head.

## 12. Completion criteria

- Actual committed saved-workflow executions replace representative execution rows in every
  affected API and UI surface with exact lineage and explicit local simulation provenance.
- Protected and missing-protection results render correctly, including the critical local alert and
  risk block for missing protection.
- Restart and repeated reads return byte-equivalent deterministic API records without appends or
  duplicates.
- Any invalid or unavailable execution evidence exposes no partial projected record.
- Existing no-live, no-broker, no-secret, manual-approval, risk, and audit boundaries remain intact.
- Full verification and production build pass, localhost inspection is recorded, and exact-head PR
  CI is green without merging the PR.

## 13. Risks and assumptions

- The JSONL journal remains the audit source of truth; SQLite remains an integrity-bound lookup and
  cannot independently establish projection trust.
- The current local store has no workflow deletion, so all-workflow evidence listing is the safest
  way to avoid silently skipping orphaned or corrupt rows.
- Replacing, rather than mixing, representative rows avoids misleading per-envelope provenance.
- Audit projections will include only manifest events attributable to committed executions; they do
  not claim to replace a general journal explorer.
- Existing legacy record schemas remain version 1 and gain a nullable attribution field, so clients
  can distinguish representative from durable records without an endpoint migration.
