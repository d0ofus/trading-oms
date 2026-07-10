# ExecPlan: Slice 057 Observability, Retention, Backup, And Incident Response

## 1. Goal

Add safe local operating-control visibility for production-readiness review: observability events and
metrics, audit-retention metadata, backup/restore verification posture, and incident-response
status.

## 2. Non-goals

- Live trading.
- Production rollout.
- Broker transport changes.
- Broker-side cancel, flatten, liquidation, route, submit, or transmit behavior.
- Real credentials, account identifiers, tokens, passwords, certificates, private keys, or secrets.
- External log shipping, external backup storage, alert delivery, cloud resources, or deployment
  automation.
- Deleting, truncating, compacting, or rewriting audit records.

## 3. Safety constraints

- Live trading remains disabled and unauthorized.
- Default mode remains paper or simulation.
- All Slice 057 surfaces are inspection/read-only.
- Audit retention must not delete records by default.
- Backup/restore hooks are local verification metadata only and must not store external targets or
  credentials.
- Incident response must preserve the emergency stop, risk, approval, OMS, audit, authorization,
  paper-only, and readiness gates.
- No secret-shaped, broker-routing-shaped, account-shaped, or network-control-shaped fields may
  appear in API responses, UI, docs, logs, or audit export payloads.

## 4. Current state

The repo has local auth/authorization, role separation, emergency stop controls, read-only
inspection APIs, audit exports, paper-only IBKR adapter boundaries, and a read-only UI shell. Slice
053 documented deployment, rollback, and backup planning requirements. Slice 056 left persistence,
observability, incident response, backup/restore, and production-like operating procedures as future
work.

## 5. Proposed design

- Add typed read models for operational controls:
  - observability metric summaries;
  - observability event summaries;
  - audit-retention policy metadata;
  - backup/restore verification posture;
  - incident-response status.
- Add those models to the aggregate operations read model.
- Expose `GET /api/operational-controls` as a read-only inspection endpoint guarded by
  `view_operations`.
- Add frontend client support and a read-only UI section for the operating controls.
- Expand docs to describe the local-only observability, retention, backup/restore, and incident
  workflow boundaries.

## 6. Data model changes

- Add frozen dataclasses in `trading_oms_backend.read_models` for Slice 057 operating controls.
- Add `operational_controls` to `OperationsReadModel`.
- No database migrations.
- No deletion/retention executor state.

## 7. API changes

- `GET /api/operational-controls`

No mutation endpoints, external log sinks, backup writers, restore commands, broker controls, or
production rollout toggles are added.

## 8. Test plan

- Backend read-model tests for JSON shape, safe defaults, validation failures, and forbidden keys.
- API tests for `GET /api/operational-controls`, read-only HTTP methods, view authorization, and
  absence of secret/broker/network affordances.
- Frontend client tests proving `GET` usage and safe fallback.
- Frontend render tests proving visible observability, retention, backup/restore, and incident
  posture without live/broker/credential controls.
- Documentation tests for Slice 057 status and hard stops.

## 9. Verification commands

```powershell
.\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 057 commit. This removes the read-only operating-control surface and restores the
Slice 056 state while preserving prior safety gates.

## 11. Implementation steps

1. Add backend tests and documentation expectations for Slice 057.
2. Add operating-control read models and demo assembler data.
3. Expose the read-only API endpoint and update API docs.
4. Add frontend client types/fallbacks and UI rendering.
5. Update slice docs and safety docs.
6. Run verification and self-review.

## 12. Completion criteria

- Operating-control read models expose local observability, retention, backup/restore, and incident
  status.
- `GET /api/operational-controls` returns the safe read model and does not implement mutation
  methods.
- UI renders the operating-control posture without action buttons or unsafe affordances.
- Audit-retention metadata keeps destructive retention disabled.
- Backup/restore metadata is local verification only with no external storage configured.
- Incident response status requires emergency-stop/risk/approval/audit preservation.
- No live trading, production rollout, broker transport, credentials, account IDs, secrets, or
  destructive audit behavior is introduced.
- Verification passes.

## 13. Risks and assumptions

- Slice 057 is still a local readiness/control surface, not production observability tooling.
- Retention and backup/restore execution remain future approved work; this slice defines safe
  metadata and verification posture only.
- External review is still required before controlled paper-production rollout planning can proceed.
