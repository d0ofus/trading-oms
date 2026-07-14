# ExecPlan: Candidate Slice 060 evidence provenance hardening

## 1. Goal

Make every operations read model, read-only API response, frontend fallback, and API-backed
operator view state where its data came from and what that data can prove. Align the
live-readiness dashboard with the controlled paper-production checklist so local implementation,
tests, plans, or representative records can never be reported as externally verified evidence.

## 2. Non-goals

- IBKR connectivity, connectivity probes, authentication, contract lookup, order submission,
  callback handling, or broker reconciliation.
- Broker credentials, account identifiers, passwords, tokens, certificates, private keys, or any
  other secret or private value.
- External identity, alert, observability, backup, storage, review, or evidence integration.
- Deployment, controlled rollout, production operation, evidence campaigns, or paper sessions.
- Live trading, live account mode, live order transmission, or readiness authorization.
- Candidate Slice 061 or any later candidate.
- Changes to risk decisions, approvals, OMS transitions, fake-broker behavior, protection rules,
  emergency-stop behavior, or append-only journaling.

## 3. Safety constraints

- Live trading remains disabled and unauthorized.
- Application mode remains paper or simulation.
- All current operations provenance must state broker_derived=false and
  externally_verified=false.
- Representative, demo, simulated, local-only, test-double, adapter-only, and externally
  unverified classifications must be explicit and machine-validated.
- Missing, unverified, expired, or contradictory mandatory evidence must count as blocking.
- Only evidence explicitly marked verified may be non-blocking; no local artifact may infer that
  state.
- ready_for_final_review requires every mandatory evidence item to be verified, no blocking
  evidence, no outstanding external review, and no outstanding explicit human approval.
- ready_for_final_review still cannot enable or authorize live trading or rollout.
- Read API provenance must fail closed in the frontend if metadata is missing, malformed,
  broker-derived, or externally verified contrary to the current product boundary.
- Existing risk, manual approval, OMS, duplicate prevention, stale-data, unknown-state,
  reconciliation, protection, emergency-stop, authorization, and audit gates remain unchanged.
- No IBKR TWS or Gateway port may be exposed or contacted.
- No secret or private broker/account value may appear in code, docs, tests, logs, screenshots,
  exports, API payloads, or UI text.

## 4. Current state

The post-Slice-059 closeout review is merged into origin/main as squash commit eeda184; its tree
matches the reviewed closeout branch. Candidate Slice 060 starts from that commit.

build_demo_operations_read_model currently constructs representative records for signals, risk,
approvals, orders, positions, alerts, readiness, paper adapter state, and operating controls.
Most records have no explicit provenance. Operations endpoints return bare models or arrays, so an
API consumer cannot reliably distinguish representative data from actual local state.

The paper operator view shows a representative partial fill built in memory. It is not derived from
an authenticated IBKR session, but the API payload has no machine-readable statement of that fact.
Frontend fallbacks likewise identify their source in ad hoc fields rather than a shared provenance
contract.

The live-readiness dashboard currently accepts satisfied, missing, requires_external_review, and
blocked. Its demo data marks local emergency-stop, audit-retention, and backup/restore artifacts
satisfied, while the controlled rollout checklist correctly records them as unverified. Its
blocking count includes only blocked, not all non-satisfied evidence.

Implementation outcome (2026-07-14): the proposed provenance envelope, frontend fail-closed
validation, visible labels, and checklist-aligned evidence aggregation are implemented. Local HTTP
inspection confirmed the UI and API were available, paper data was not broker-derived or externally
verified, and readiness remained `not_ready` with zero verified and 14 blocking items. The in-app
browser was unavailable, so interactive visual inspection was not claimed; frontend render tests
verified the labels and absence of unsafe controls. Full verification passed with 555 backend tests
and 60 frontend tests.

## 5. Proposed design

Add a typed ReadModelProvenance model with:

- resource name;
- source identifier;
- an ordered set of classifications drawn only from representative, demo, simulated,
  local_only, test_double, adapter_only, and externally_unverified;
- broker_derived=false;
- externally_verified=false;
- a concise safe summary.

Store one provenance record for every resource in OperationsReadModel. Require an exact,
duplicate-free resource catalog and expose a resource lookup method. Include the catalog in
persisted and audit-exported operations snapshots.

Return every operations read endpoint as a versioned envelope containing resource, provenance, and
data. Arrays remain arrays inside data, so even an empty resource still has provenance. Do not
alter health, workflow mutation, approval mutation, emergency-stop mutation, or audit-export
interfaces.

Add equivalent frontend envelope and provenance types. Validate provenance at runtime before
accepting an API response. Reject malformed metadata, resource mismatches, unsupported
classifications, broker_derived=true, externally_verified=true, or missing
externally_unverified; fall back to the safe local snapshot on any failure. Preserve a provenance
catalog in OperationsApiSnapshot.

Display a clear provenance band and per-section provenance notices for all API-backed operations
views. Paper trading must explicitly say that the view is representative, adapter/test-double
evidence only, not broker-derived, externally unverified, and not an authenticated IBKR session.
Static workflow and run views retain their existing simulation-only labels.

Replace live-readiness evidence statuses with the controlled-checklist vocabulary: verified,
missing, unverified, expired, and contradictory. Track counts for every status and define
blocking_evidence_count as all non-verified mandatory items. Align demo dashboard categories with
all fourteen checklist evidence rows. Current local implementation and plan artifacts remain
unverified; absent external or exercise artifacts remain missing.

Document the provenance contract, fail-closed aggregation rule, and distinction between local
implementation evidence and external operational evidence.

## 6. Data model changes

- Add ReadModelProvenance to the backend.
- Add a required, complete provenance catalog to OperationsReadModel.
- Add unverified_evidence_count, expired_evidence_count, contradictory_evidence_count, and
  verified_evidence_count to LiveReadinessEvidenceDashboardReadModel.
- Change evidence status vocabulary to verified, missing, unverified, expired, and contradictory.
- Align evidence categories to the fourteen controlled paper-production checklist categories.
- Add matching frontend provenance, envelope, evidence-status, evidence-category, and count types.
- Add provenance metadata to OperationsApiSnapshot and the safe frontend fallback.

No database migration is required. Persisted local read-model JSON gains additive provenance and
readiness-count fields; no production database or external storage exists.

## 7. API changes

The following read-only endpoints change from bare data to a shared envelope with schema_version,
resource, provenance, and data:

- GET /api/emergency-stop
- GET /api/operator-session
- GET /api/safety
- GET /api/audit-events
- GET /api/signals
- GET /api/risk-decisions
- GET /api/approval-tickets
- GET /api/orders
- GET /api/positions
- GET /api/alerts
- GET /api/readiness
- GET /api/paper-trading
- GET /api/operational-controls
- GET /api/live-readiness-evidence

No endpoint, method, credential field, broker control, external action, or rollout control is added.

## 8. Test plan

Backend:

- prove the provenance catalog covers every operations resource exactly once;
- prove every current resource is not broker-derived and not externally verified;
- prove representative simulation resources carry representative/demo/simulated/local-only and
  externally-unverified classifications;
- prove paper trading additionally carries test-double and adapter-only classifications;
- prove actual in-process local state is labeled local-only and externally unverified without
  being called broker evidence;
- reject unknown or duplicate classifications, unsafe flags, missing or duplicate resources, and
  resource mismatches;
- prove every operations endpoint returns a matching provenance envelope, including empty lists;
- prove current local emergency-stop, retention, backup/restore, authentication, observability,
  reconciliation, and live-readiness artifacts are unverified, not verified;
- parameterize missing, unverified, expired, and contradictory evidence to prove each blocks
  ready_for_final_review;
- prove only an all-verified evidence set can reach ready_for_final_review while live-trading flags
  remain false;
- preserve API read-only and authorization tests, persistence tests, export tests, and secret/live
  surface guards.

Frontend:

- parse and retain matching provenance envelopes for every operations endpoint;
- reject missing, mismatched, unsafe, or unsupported provenance and use the safe fallback;
- prove the fallback itself is explicit local-only, representative where applicable, not
  broker-derived, and externally unverified;
- render representative, demo, simulated, local-only, test-double, adapter-only, not
  broker-derived, and externally-unverified labels;
- render the paper warning that no authenticated IBKR session is represented;
- render missing and unverified readiness items and all blocking counts without satisfied claims;
- preserve the absence of broker, credential, rollout, and live-trading controls.

No broker, external, deployment, or live test is permitted.

## 9. Verification commands

    python -m pytest backend\tests\test_evidence_provenance.py backend\tests\test_read_models.py backend\tests\test_read_api.py backend\tests\test_live_readiness_evidence.py backend\tests\test_operational_controls.py
    npm.cmd --prefix frontend test -- --run src/readApiClient.test.ts src/App.test.tsx
    powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1

Run the backend and frontend locally only. Inspect http://localhost:5173 and safe read-only APIs
without invoking any IBKR adapter operation.

## 10. Rollback plan

Revert the Candidate Slice 060 commit. The API response shape, frontend client, and UI must be
reverted together. Local persisted read-model snapshots are versioned JSON and require no
destructive migration. No broker, external system, deployment, secret store, or production data
requires rollback.

## 11. Implementation steps

1. Add failing backend tests for provenance validation, complete API envelopes, and fail-closed
   readiness aggregation.
2. Add failing frontend tests for envelope validation, safe fallback, and visible provenance.
3. Implement backend provenance models, catalog validation, endpoint envelopes, checklist-aligned
   evidence states, and all-status blocking counts.
4. Implement frontend types, runtime envelope validation, fallback provenance, snapshot catalog,
   and per-view provenance notices.
5. Update provenance, readiness, operating-control, API, README, and slice-queue documentation.
6. Run focused backend/frontend tests and fix failures.
7. Run local backend/frontend inspection using only safe read endpoints.
8. Run full verification and self-review all explicit safety and non-goal boundaries.
9. Commit and push the dedicated branch and prepare a PR if authentication permits.
10. Stop without beginning Candidate Slice 061 or any external, broker, or rollout work.

## 12. Completion criteria

- Every operations read-model resource has typed, safe provenance.
- Every operations read endpoint carries provenance even when its data list is empty.
- Every current API provenance record says not broker-derived and externally unverified.
- Representative, demo, simulation, test-double, adapter-only, and local-only classifications are
  applied where true and not applied where false.
- Frontend API ingestion fails closed on absent or unsafe provenance.
- Every API-backed operator view visibly distinguishes representative, local, or simulated data
  from broker-derived or externally verified evidence.
- Paper UI cannot reasonably be mistaken for a real IBKR session or paper-order history.
- Local emergency-stop, retention, backup/restore, authentication, observability, reconciliation,
  and readiness artifacts are unverified, never verified.
- Missing, unverified, expired, and contradictory evidence all block readiness.
- Only all-verified evidence can produce ready_for_final_review; that result still leaves live
  trading disabled and unauthorized.
- No broker operation, credential, external integration, deployment, rollout, production behavior,
  live-order path, or safety-gate bypass is introduced.
- Focused and full verification pass.

## 13. Risks and assumptions

- The envelope is an intentional breaking change to local read-only APIs; backend and frontend ship
  in the same slice.
- Provenance labels describe origin and evidentiary strength, not correctness of every underlying
  trading algorithm.
- Current runtime records are built by build_demo_operations_read_model; in-process emergency stop
  and operator identity are actual local state alongside representative records and therefore need
  resource-specific provenance.
- Test-double classification applies to representative paper-adapter capability evidence, not an
  actual broker callback or session.
- No external evidence is available. verified is tested as a validation state but is not assigned
  to current demo or runtime evidence.
- The in-app browser may be unavailable; if so, record the limitation and use local HTTP
  observations plus frontend tests without claiming visual inspection.
- GitHub CLI authentication may require exact manual PR commands after the branch is pushed.
