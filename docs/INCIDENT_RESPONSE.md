# Incident Response

Slice 057 expands the incident-response runbook and exposes safe read-only incident posture through
`GET /api/operational-controls`.

This is local operating guidance and inspection only.

Live trading remains disabled.

No live broker order path may be introduced.

No broker-side liquidation, live cancel, live flatten, live route, live submit, live transmit,
credential storage, external incident platform, or production rollout behavior is added.

## Critical Incidents

Critical incidents include:

- unexpected order;
- duplicate order;
- position without expected protection;
- unknown broker state;
- stale data used for a decision;
- missing audit event;
- redaction failure or secret leakage suspicion;
- IBKR port exposure;
- reconciliation failure;
- emergency stop bypass suspicion;
- authorization bypass suspicion.

## Initial Response

1. Activate or preserve the local emergency stop when risk-increasing work may continue.
2. Stop new risk-increasing decisions.
3. Preserve logs, journal records, workflow definitions, simulation runs, paper callback records,
   and audit export indexes.
4. Alert the operator through the local alert/audit surface.
5. Reconcile orders, positions, callbacks, and broker state before any further risk increase.
6. Document the incident timeline without recording credentials, account identifiers, tokens,
   passwords, certificates, private keys, or secrets.
7. Fix the root cause.
8. Add regression tests before returning to the prior operating state.

## Read-Only Incident Posture

Slice 057 exposes:

- active incident state;
- severity floor for operator review;
- emergency-stop requirement for critical incidents;
- post-incident review requirement;
- local runbook status;
- last review timestamp.

The read model is inspection data only. It does not file tickets, send messages, connect to brokers,
cancel orders, flatten positions, transmit orders, upload evidence, or start production rollout.

## Recovery Requirements

Recovery must preserve:

- append-only audit records;
- risk, approval, OMS, and reconciliation gates;
- local authorization checks;
- emergency-stop block behavior;
- paper-only IBKR boundaries;
- readiness gates;
- redacted audit export behavior.

Unknown broker state, reconciliation-required state, stale data, missing expected protection, and
missing audit evidence remain blockers for risk-increasing steps until explicitly resolved.

## Current Limitations

- Incident status is local read-model posture only.
- No external incident-response system is integrated.
- No automated production rollback, backup restore, or broker-side emergency action is implemented.
