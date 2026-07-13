# Deployment And Secrets Management Plan

Slice 053 is a production-readiness planning slice for production-like paper operation.

Planning only: this document does not approve production rollout.

Live trading remains disabled.

No live broker order path may be introduced.

Production-like paper operation requires separate explicit human approval and external review.

## Current Boundary

The application currently supports simulation and paper-oriented inspection workflows. It has safe
configuration defaults, journaling, replay, risk checks, approvals, OMS behavior, fake broker
simulation, audit export, paper-only IBKR adapter boundaries, local paper transport modeling, chaos
coverage, and a read-only paper operator UI.

This document does not add deployment automation, authentication, authorization, roles, emergency
stop behavior, production observability, backup tooling, secret manager integration, real IBKR
credentials, account identifiers, live account mode, market-data subscriptions, or broker control
surfaces.

## Deployment Architecture Options

### Option A: Local Single-Operator Paper Environment

This is the preferred next production-like paper architecture after later security slices are
approved.

- Frontend and backend run on the operator workstation or a private local host.
- SQLite, journal files, exports, and logs stay on local encrypted storage.
- TWS or IB Gateway runs on the same host where possible.
- IBKR connectivity is paper-only and bound to localhost.
- The app is reachable only by the local operator until authentication and authorization are
  implemented.
- Secrets live outside the repository in a local secret store, operating-system credential vault, or
  ignored local environment file.

This option is still not a rollout approval. It needs the later authentication, authorization,
emergency stop, observability, backup/restore, and controlled paper rollout slices before use as an
operational deployment.

### Option B: Private Network Paper Operations

This is a later option for a private office or VPN-only paper environment.

- Frontend and backend run on a private subnet or behind VPN access.
- TWS or IB Gateway remains on localhost or a tightly controlled private host.
- Firewalls deny inbound access to IBKR API ports from the public internet.
- Only the application UI/API may be exposed to approved operators after authentication and
  authorization are implemented.
- Host and network changes require a recorded network-exposure review.

This option must not create arbitrary broker host fields in the UI, workflow builder, API payloads,
or configuration docs.

### Option C: Hosted Control Plane With Local Broker Boundary

This is a future architecture candidate only.

- A hosted UI or control plane may provide operator visibility after authentication,
  authorization, observability, and incident-response work exists.
- Broker connectivity remains local to an operator-controlled environment.
- Any bridge between hosted services and a local broker boundary must be separately designed,
  reviewed, and approved before implementation.
- The hosted service must not directly expose or require public IBKR API access.

This option is not approved for implementation in Slice 053.

## Disallowed Deployment Shapes

- Public internet exposure for IBKR TWS or Gateway API ports.
- Production rollout before explicit human approval and external review.
- Live account mode.
- Live trading.
- Public broker host configuration.
- UI/API/workflow fields that collect broker credentials, account identifiers, hostnames, ports,
  passwords, certificates, private keys, tokens, or secrets.
- Deployment scripts that create real cloud resources or route traffic to broker services.
- Any deployment that bypasses risk, approval, OMS, audit, reconciliation, or protective-order
  requirements.

## Network Exposure Rules

IBKR TWS or Gateway API ports must never be exposed to the public internet.

Required rules for any future production-like paper environment:

- Prefer localhost-only broker connectivity.
- If a private-network host is later approved, restrict access with deny-by-default firewall rules.
- Permit only known paper IBKR ports for paper mode after separate review.
- Do not add public broker host fields to the UI, API, workflow builder, DSL, logs, docs, or exports.
- Do not allow deployment configuration to override live-trading hard stops.
- Do not open callback listeners, SDK listeners, or market-data network subscriptions without a
  separate approved slice.
- Treat unknown broker state, reconnect state, reconciliation-required state, and stale data as
  blockers for risk-increasing steps.

Network exposure review must be recorded before any controlled paper rollout plan can start.

## Secrets Management Requirements

No real broker credentials, account identifiers, passwords, certificates, private keys, tokens, or
secrets may be committed, logged, displayed, exported, or stored in repository files.

Future production-like paper operation must use a secret-handling design that provides:

- secret storage outside git, screenshots, docs, tests, logs, audit exports, and alert payloads;
- per-environment separation between local development, paper operation, and any later reviewed
  environment;
- least-privilege access for operators and services;
- startup validation that rejects missing, malformed, live-mode, or unsafe secret configuration;
- rotation and revocation procedures;
- audit records for secret access and configuration changes without recording secret values;
- redaction for logs, errors, exports, UI views, and incident bundles;
- placeholder-only examples in `.env.example`;
- ignored local files or managed secret stores for private values.

Secret storage implementation is future work. Slice 053 documents requirements only.

## Data, Backup, And Restore Requirements

Backup and restore planning must protect journal and persistence data without exporting secrets.

Future production-like paper operation needs a backup plan for:

- append-only journal records;
- SQLite or later persistence databases;
- workflow definitions;
- simulation and paper run summaries;
- audit export indexes;
- configuration snapshots that exclude secret values.

Minimum expectations:

- backups are encrypted at rest;
- restore procedures are documented and periodically tested;
- restored data preserves audit ordering and event immutability;
- backup jobs do not include secret files or local credential stores;
- audit exports remain redacted and secret-scanned before review sharing;
- data retention rules are reviewed before controlled paper rollout.

## Rollback Requirements

Rollback planning must preserve the append-only audit trail.

Future production-like paper rollback must include:

- disabling paper transport by configuration or feature flag;
- stopping schedulers, workers, or adapters before redeploying older application artifacts;
- preserving journals, order state, approval records, reconciliation records, and audit exports;
- rotating or revoking secrets if a deployment or operator device is suspected compromised;
- recording rollback decisions and outcomes in the event journal or incident record;
- avoiding destructive data rollback unless an audited backup/restore procedure has been approved.

Rollback is not a substitute for reconciliation. Unknown broker state must remain blocking until
reconciled.

## Future Slice Boundaries

Slice 054 adds a local operator authentication and authorization foundation. Slice 055 hardens local
operator roles and approval permissions. Neither is production authentication or rollout approval.

Slice 056 adds a local emergency stop that blocks risk-increasing simulation and paper-mode work
while active. It does not add broker-side liquidation, live cancel, live flatten, broker transport,
or production rollout.

Slice 057 adds read-only local operating-control visibility for observability, audit-retention
metadata, backup/restore posture, and incident response. It does not add external observability,
backup execution, restore execution, audit deletion, external storage, production rollout, or live
trading.

Slice 058 adds read-only live-readiness evidence visibility. It does not complete external review,
approve controlled rollout, authorize live trading, or change disabled live-trading configuration.

Controlled paper-production rollout checklist work remains future Slice 059 work.

No future slice may enable live trading unless a separate live-readiness review, external review,
and explicit human approval process later approves it. The current repository must continue to treat
live trading as disabled and unauthorized.
