# ExecPlan: Slice 058 live-readiness evidence dashboard

## 1. Goal

Add a read-only live-readiness evidence dashboard that makes final-review evidence visible without
enabling live trading or production-like behavior.

## 2. Non-goals

- Live trading.
- Live broker transport.
- Live order routing.
- Production rollout.
- External review automation.
- Runtime configuration changes.
- Private-value storage or display.

## 3. Safety constraints

- Live trading remains disabled.
- Default mode remains simulation or paper.
- Readiness may report only `not_ready` or `ready_for_final_review`.
- `ready_for_final_review` is evidence posture only and cannot authorize live trading.
- No broker adapter, network, socket, order, or external alert behavior is added.
- No private values, broker identifiers, external tokens, account identifiers, or action URLs may be
  exposed.
- Existing risk, approval, OMS, audit, emergency stop, authorization, observability, retention,
  incident response, and paper-only gates remain intact.

## 4. Current state

Slice 057 exposes safe local operating-control visibility through backend read models,
`GET /api/operational-controls`, and the frontend operations shell. Existing readiness data is a
compact status read model and does not show evidence item detail, missing evidence, or external
review blockers.

## 5. Proposed design

Add typed read models for readiness evidence items and an aggregate evidence dashboard. Include the
dashboard in the operations read-model snapshot and expose it through a new read-only endpoint:
`GET /api/live-readiness-evidence`.

Render a frontend section that shows:

- evidence result;
- missing evidence count;
- external review requirement;
- explicit human approval requirement;
- paper evidence;
- emergency-stop evidence;
- audit retention, backup/restore, and incident-response evidence;
- readiness blockers.

All UI is informational. No buttons, mutation endpoints, broker controls, or rollout controls are
added.

## 6. Data model changes

Add:

- `LiveReadinessEvidenceItemReadModel`;
- `LiveReadinessEvidenceDashboardReadModel`;
- `OperationsReadModel.live_readiness_evidence`.

No database migrations are added.

## 7. API changes

Add:

```text
GET /api/live-readiness-evidence
```

No mutation endpoint is added.

## 8. Test plan

- Backend unit tests for readiness evidence validation and unsafe state rejection.
- Backend read API tests proving the new endpoint returns the aggregate section and rejects
  mutation methods.
- Frontend read API client tests for the new endpoint, snapshot, and safe fallback.
- Frontend rendering tests for visible evidence, missing blockers, disabled live posture, and
  absence of unsafe affordances.
- Documentation tests updated for Slice 058 status.

## 9. Verification commands

```powershell
python -m pytest backend\tests\test_live_readiness_evidence.py backend\tests\test_read_api.py backend\tests\test_read_models.py backend\tests\test_deployment_planning_docs.py
npm.cmd test -- --run src/readApiClient.test.ts src/App.test.tsx
.\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 058 commit. The previous Slice 057 operating-control read API and UI remain safe
and independent.

## 11. Implementation steps

1. Add tests for the backend read models and read endpoint.
2. Add tests for frontend client and dashboard rendering.
3. Implement backend read models, demo data, and endpoint.
4. Wire frontend types, client, fallback snapshot, and dashboard section.
5. Update docs and Slice 058 status.
6. Run verification and fix failures.
7. Self-review safety and scope.

## 12. Completion criteria

- Dashboard evidence is visible through backend and frontend.
- Missing evidence and review requirements are explicit.
- Live-trading fields remain false.
- Readiness result cannot become anything beyond `not_ready` or `ready_for_final_review`.
- No unsafe affordance keys, action URLs, broker network fields, private values, or mutation methods
  are introduced.
- Verification passes or any blocker is documented with exact output.

## 13. Risks and assumptions

- Local `origin/main` may remain stale because GitHub auth/TLS is failing in this environment.
- The implementation proceeds from the clean Slice 057 worktree, which is the expected merged
  baseline according to the active goal.
- External review and controlled paper rollout remain later gates.
