# ExecPlan: Slice 059 controlled paper-production rollout checklist

## 1. Goal

Add a durable, fail-closed checklist for reviewing a possible controlled production-like paper
operation without authorizing or executing a rollout, enabling live trading, or changing broker
transport behavior.

## 2. Non-goals

- Actual deployment or rollout.
- Production operation.
- Live trading or live account mode.
- Live or paper order-path changes.
- Broker transport, market-data, callback, or reconciliation behavior changes.
- Deployment automation, cloud resources, external integrations, or public services.
- Credential, account identifier, token, password, certificate, private key, or secret handling.
- Backend or frontend behavior.

## 3. Safety constraints

- Live trading remains disabled and unauthorized.
- Default mode remains simulation or paper.
- The checklist may report only `not_ready` or `ready_for_final_review`.
- Checklist completion cannot authorize rollout, deployment, production operation, or live trading.
- Missing, unverified, expired, or contradictory evidence must block a go decision.
- External review, paper-trading history, live-readiness evidence, secret-management review,
  network-exposure review, and operator approval must never be fabricated or inferred.
- Public IBKR TWS or Gateway API exposure remains prohibited.
- Existing risk, approval, OMS, audit, emergency-stop, authorization, reconciliation, incident
  response, paper-only, and readiness gates remain intact.
- No secrets or private broker/account values may appear in repository files, logs, docs, tests,
  screenshots, exports, or alert payloads.

## 4. Current state

Slice 053 documents deployment and secret-management planning boundaries. Slices 054 through 057
add local authorization, role separation, emergency-stop behavior, and read-only operating-control
evidence. Slice 058 displays read-only live-readiness evidence and currently reports `not_ready`.

The current evidence explicitly lacks reviewed paper-trading history, independent external review,
redaction review, explicit human approval evidence, and an approved network-exposure review. The
repository has no durable Slice 059 go/no-go checklist tying these prerequisites to rollback and
incident-response evidence.

## 5. Proposed design

Add `docs/CONTROLLED_PAPER_PRODUCTION_ROLLOUT_CHECKLIST.md` as a planning and review artifact. It
will define:

- evidence-state vocabulary and fail-closed evaluation rules;
- paper-only entry criteria;
- external review and operator sign-off requirements;
- secret-management and network-exposure review requirements;
- authentication, authorization, emergency-stop, observability, retention, backup/restore,
  reconciliation, rollback, and incident-response evidence;
- explicit go/no-go rules and stop conditions;
- a current evidence register that records every unverified prerequisite as blocking;
- a post-checklist boundary that requires a separate future approval before any rollout work.

Update directly relevant planning and safety docs to reference the checklist and preserve the hard
stop. Add documentation tests that require the checklist sections, current blocking posture, and
forbidden-enablement protections.

## 6. Data model changes

None.

## 7. API changes

None.

## 8. Test plan

- Extend deployment-planning documentation tests to require the Slice 059 checklist and ExecPlan.
- Assert every required evidence category is present.
- Assert the current checklist result remains `not_ready` and missing evidence remains blocking.
- Assert the checklist cannot authorize rollout or live trading.
- Assert Slice 059 becomes `ready_for_human_review` only after the documentation is complete.
- Preserve forbidden configuration and secret-shaped content checks.

## 9. Verification commands

```powershell
python -m pytest backend\tests\test_deployment_planning_docs.py
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 059 commit. No runtime behavior, data model, API, deployment resource, broker
transport, or external system requires rollback.

## 11. Implementation steps

1. Add failing documentation tests for required evidence, fail-closed status, and hard stops.
2. Add the controlled paper-production rollout checklist.
3. Update directly relevant safety, readiness, deployment, operations, and slice-queue docs.
4. Run focused tests and full verification.
5. Self-review every explicit requirement and forbidden capability.
6. Commit and push the Slice 059 branch if authentication permits.

## 12. Completion criteria

- A durable controlled paper-production rollout checklist exists.
- Paper-only entry, go/no-go, rollback, and incident-response criteria are explicit.
- Every required evidence category is represented.
- Missing or unverified evidence is blocking and the current result remains `not_ready`.
- Checklist completion is explicitly not rollout approval or live-trading approval.
- No backend, frontend, transport, deployment, secret-handling, or external integration behavior is
  added.
- Slice 059 is marked `ready_for_human_review` and verification passes.

## 13. Risks and assumptions

- The human approval for Gate F authorizes checklist planning only, not rollout execution.
- External review and operational evidence are not currently available and must remain blockers.
- The root Git metadata is read-only to this process, so implementation uses a writable temporary
  worktree rooted at the verified Slice 058 commit.
- GitHub authentication may still require manual push and PR commands.
