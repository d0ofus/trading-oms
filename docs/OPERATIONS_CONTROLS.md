# Operations Controls

Slice 057 adds read-only local operating-control visibility for observability, audit retention,
backup/restore posture, and incident response.

This is not production rollout.

Live trading remains disabled.

No live broker order path may be introduced.

No external log shipping, external backup target, cloud resource, broker control, credential field,
account identifier, token, password, certificate, private key, or secret is added.

## Read Model

The backend exposes `OperationalControlsReadModel` through:

```text
GET /api/operational-controls
```

The response includes:

- local observability metric summaries for system health, safety posture, emergency stop state,
  audit journal health, backup status, and incident response;
- local observability event summaries with journal references;
- audit-retention metadata;
- backup/restore verification posture;
- incident-response status.

All fields are inspection data only. The endpoint has no mutation methods and does not connect,
upload, download, delete, restore, submit, transmit, route, or deliver anything.

The API provenance envelope labels this view `local_only` and `externally_unverified`. An `ok`
local metric or a documented local plan describes local state only; it is not independently
reviewed controlled-rollout evidence.

## Observability

Slice 057 observability is local status visibility only.

It does not add external metrics sinks, log collectors, alert delivery, tracing exporters, cloud
resources, broker listeners, market-data subscriptions, or network clients.

Expected local observations include:

- system health;
- safety posture;
- emergency stop state;
- audit journal health;
- backup status;
- incident response state.

Observability text rejects credential-shaped, broker-routing-shaped, live-order-shaped, and
arbitrary-code-shaped values.

## Audit Retention

Audit retention is metadata only in this slice.

Destructive retention is disabled.

Append-only journal preservation remains required.

No audit record deletion, truncation, compaction, rewrite, or migration executor is added.

Future retention execution requires separate explicit approval, external review where appropriate,
and tests proving append-only audit guarantees are preserved.

## Backup And Restore

Backup/restore status is local verification posture only.

The current state is:

- backup plan documented locally;
- restore verification documented locally;
- local encrypted storage required;
- external storage not configured;
- redaction required before review sharing.

Slice 057 does not add external storage, upload/download jobs, cloud buckets, credentials, account
identifiers, backup schedulers, restore commands, or production rollout automation.

## Incident Response

Incident response status is read-only local playbook visibility.

Critical incidents require operator review and emergency-stop preservation. Response work must keep
risk, approval, OMS, audit, authorization, paper-only, reconciliation, and readiness gates intact.

Incident response does not add broker-side liquidation, live cancel, live flatten, live submit, live
transmit, live account mode, or production rollout behavior.

## Current Limitations

- Operating controls use safe local read-model data.
- Emergency-stop, observability, retention, backup/restore, and reconciliation artifacts remain
  `unverified` in the live-readiness dashboard until separate external evidence is reviewed.
- There is no external observability integration.
- There is no backup executor or restore executor.
- There is no audit-retention deletion executor.
- Slice 059 documents a fail-closed production-like paper rollout checklist, but its current result
  is `not_ready`; external review, target-environment evidence, and separate explicit human approval
  remain blocking.
