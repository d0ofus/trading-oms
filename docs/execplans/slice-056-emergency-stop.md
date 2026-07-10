# ExecPlan: Slice 056 Emergency Stop

## 1. Goal

Add a local emergency stop that operators can inspect, activate, and deactivate in simulation/paper
mode, with append-only audit evidence and blocking for risk-increasing simulation work while active.

## 2. Non-goals

- Live trading.
- Broker-side liquidation.
- Live cancel, live flatten, live route, live submit, or live transmit behavior.
- Broker credentials, account identifiers, tokens, passwords, certificates, private keys, or
  secrets.
- Production rollout.
- External incident-response tooling.

## 3. Safety constraints

- Live trading remains disabled.
- Default app posture remains paper or simulation.
- Emergency stop is local application state only.
- Activation and deactivation must be journaled.
- Risk-increasing work must be blocked while the emergency stop is active.
- Blocking must happen before approval execution, workflow simulation run start, OMS advancement,
  fake broker transitions, fills, or position/alert work can advance.
- Rejection or inspection paths may remain available because they do not increase risk.
- No secret, broker host, broker port, account id, route, submit, transmit, live-mode, liquidation,
  or credential affordances may be introduced.

## 4. Current state

The repo has local operator auth, separated approver/admin roles, simulation approval endpoints,
saved workflow simulation runs, fake broker and OMS simulation services, read models, and frontend
operator visibility. There is no emergency stop state, no emergency stop read model, no
activation/deactivation journal event, and no central guard for risk-increasing simulation actions.

## 5. Proposed design

- Add `EmergencyStopService` with deterministic in-memory state and append-only JSONL events.
- Add validated activation/deactivation request models and state/change records.
- Add `emergency_stop.activated`, `emergency_stop.deactivated`, and
  `emergency_stop.risk_increasing_action_blocked` journal events.
- Add safe read model fields for active status, reason, actor, timestamps, and blocking posture.
- Add read endpoint `GET /api/emergency-stop`.
- Add local admin-only mutation endpoints:
  - `POST /api/emergency-stop/activate`
  - `POST /api/emergency-stop/deactivate`
- Bind emergency-stop mutation body actor to the authenticated operator.
- Block risk-increasing approval approve, saved workflow simulation run start, and approved-order
  execution through orchestration before OMS/fake-broker advancement.
- Add frontend read API and a visible emergency stop panel. The panel is inspection-only in this
  slice and contains no live broker controls.

## 6. Data model changes

- Add local emergency-stop state and journal record models.
- Add `EmergencyStopReadModel`.
- Add `emergency_stop` to `OperationsReadModel`.
- No database migrations.

## 7. API changes

- `GET /api/emergency-stop`
- `POST /api/emergency-stop/activate`
- `POST /api/emergency-stop/deactivate`

All endpoints remain local app controls only. They do not connect to a broker, cancel live orders,
flatten positions, or transmit any live order.

## 8. Test plan

- Unit tests for emergency stop activation/deactivation, idempotency, unsafe payload rejection, and
  block-event journaling.
- API tests for read visibility, admin-only activation/deactivation, actor binding, and blocking of
  approval approve and workflow simulation run start while active.
- Orchestration tests proving an active emergency stop blocks approved execution before OMS/fake
  broker transitions.
- Read-model and frontend tests proving safe visibility and absence of live/broker/secret controls.
- Documentation tests for Slice 056 status and hard stops.

## 9. Verification commands

```powershell
.\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 056 commit. That removes emergency-stop state and restores Slice 055 behavior,
while preserving prior no-live-trading and no-secret safety gates.

## 11. Implementation steps

1. Add the emergency-stop domain service and focused tests.
2. Add read model/API visibility and mutation endpoints.
3. Wire blocking into approval approve, workflow simulation start, and approved-order execution.
4. Add frontend visibility and tests.
5. Update docs and slice status.
6. Run full verification and self-review.

## 12. Completion criteria

- Local emergency stop can be activated and deactivated by an admin operator.
- Activation and deactivation are journaled.
- Active emergency stop is visible through backend read API and frontend UI.
- Approval approve, saved workflow simulation run start, and approved-order execution are blocked
  while active.
- Blocking is journaled before risk-increasing work can advance.
- No live trading, broker-side liquidation, broker transport, credentials, account IDs, secrets, or
  production rollout behavior is introduced.
- Verification passes.

## 13. Risks and assumptions

- Emergency stop is in-memory local application state for this slice. Persistence and incident
  response operations remain Slice 057+ work.
- Rejecting a pending simulation ticket remains allowed while active because it does not increase
  risk.
- UI mutation controls are intentionally deferred; this slice exposes state visibly without adding
  operator-facing emergency action buttons.
