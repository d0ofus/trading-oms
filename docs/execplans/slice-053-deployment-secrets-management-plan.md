# ExecPlan: Slice 053 Deployment And Secrets Management Plan

## 1. Goal

Document production-like paper operation deployment options, secret-handling requirements, network
exposure rules, rollback expectations, and backup/restore planning while live trading remains
disabled and no rollout work starts.

## 2. Non-goals

- Production rollout.
- Production deployment automation.
- Authentication or authorization implementation.
- Operator role enforcement.
- Emergency stop implementation.
- Observability implementation.
- Backup tooling implementation.
- IBKR live trading.
- Live account mode.
- Broker-order transmit, submit-live, route-live, cancel, modify, or market-data subscription
  controls.
- Real broker credentials, account identifiers, passwords, certificates, private keys, tokens, or
  secrets.
- Slice 054 or later implementation.

## 3. Safety constraints

- Live trading must remain disabled.
- Default app posture remains paper or simulation.
- No live broker order path may be introduced.
- No secrets, credentials, account identifiers, certificates, private keys, passwords, or tokens may
  be committed, logged, displayed, exported, or documented as real values.
- IBKR TWS or Gateway API ports must never be exposed to the public internet.
- IBKR connectivity remains paper-only and localhost-preferred.
- Production-like paper operation requires explicit human approval, external review, readiness
  evidence, authentication/authorization, emergency stop, observability, backup/restore, and
  incident-response work in later approved slices.
- The live-readiness checklist remains an audit artifact and cannot enable trading.

## 4. Current state

The repository has a safe simulation and paper foundation through Slice 052:

- safe configuration defaults with live trading disabled;
- append-only event journaling;
- deterministic replay, strategy, risk, OMS, fake broker, approvals, alerts, audit export, and
  visual workflow simulation layers;
- paper-only IBKR adapter boundaries, local connectivity probing, contract lookup, guarded paper
  submission modeling, status/fill callback handling, chaos tests, and read-only operator UI;
- no production rollout tooling, no authentication/authorization, no emergency stop, no deployment
  architecture, and no real secret storage integration.

`docs/SLICES.md` has Slice 052 ready for human review and Slice 053 not started. Gate F has now
been explicitly approved for Slice 053 planning only.

## 5. Proposed design

Add a planning document that defines:

- allowed deployment architecture options for production-like paper operation;
- hard deployment preconditions before any rollout can start;
- secrets-management requirements and prohibited secret handling;
- network exposure rules, including no public IBKR ports and no arbitrary broker host fields;
- data retention, audit, backup, restore, and rollback planning requirements;
- future-slice boundaries for authentication, roles, emergency stop, observability, readiness
  evidence, and controlled paper rollout.

Update existing security and slice documentation to reference the new planning boundary. Add focused
tests that verify the planning docs keep the hard stops explicit and do not mark Slice 054 or later
as implemented.

## 6. Data model changes

None.

## 7. API changes

None.

No endpoints, CLI commands, config keys, workflow nodes, UI controls, broker surfaces, or deployment
commands are added.

## 8. Test plan

- Add backend documentation tests verifying the Slice 053 deployment plan exists and includes the
  required hard stops.
- Verify `docs/SLICES.md` marks Slice 053 ready for human review after the docs are complete while
  leaving Slice 054 and later not started.
- Verify the new planning docs explicitly block production rollout, live trading, real secrets,
  live account mode, public IBKR ports, and broker-control surfaces.
- Verify the planning docs include network exposure, secrets management, rollback, and
  backup/restore requirements.
- Run full repository verification.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 053 documentation and test changes. No runtime behavior, external resources,
credentials, database migrations, deployment resources, or broker sessions are introduced.

## 11. Implementation steps

1. Add documentation tests for Slice 053 safety boundaries.
2. Add the deployment and secrets-management planning document.
3. Update `docs/SECURITY_BASELINE.md` with a short production-like paper operation boundary.
4. Update `docs/SLICES.md` to mark Slice 053 ready for human review and keep Slice 054+ not
   started.
5. Run full verification.
6. Self-review for live-order prevention, secret leakage, public-port exposure, rollout scope
   creep, and accidental Slice 054+ implementation.
7. Commit and push if local git permissions allow it; otherwise report the blocker and exact manual
   commands.

## 12. Completion criteria

- Slice 053 ExecPlan exists.
- Deployment and secrets-management planning documentation exists.
- The plan defines production-like paper deployment options without starting rollout.
- The plan defines secret handling, network exposure, rollback, and backup/restore requirements.
- Documentation preserves hard stops: no live trading, no live account mode, no production rollout,
  no public IBKR ports, no real secrets, no account identifiers, and no broker-control surfaces.
- `docs/SLICES.md` marks Slice 053 ready for human review and leaves Slice 054 and later not
  started.
- Tests or verification checks cover the documentation safety boundaries.
- Full verification passes.

## 13. Risks and assumptions

- This slice may be mistaken for production approval. The docs must state that it is planning only.
- Future production-like paper operation depends on later approved slices for authentication,
  authorization, roles, emergency stop, observability, backup/restore tooling, and controlled paper
  rollout checklist.
- A hosted deployment must not be allowed to reach public IBKR ports; broker access stays
  localhost-only or private-network-only after separate review.
- Secret management is documented as a requirement here, not implemented.
