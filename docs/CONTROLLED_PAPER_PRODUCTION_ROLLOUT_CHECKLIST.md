# Controlled Paper-Production Rollout Checklist

Planning and evidence checklist only.

Current result: `not_ready`.

Checklist completion does not authorize rollout.

Live trading remains disabled and unauthorized.

Missing, unverified, expired, or contradictory evidence is blocking.

## Purpose And Boundary

This checklist prepares evidence for a possible future review of production-like paper operation.
It does not start a rollout, deploy infrastructure, connect a broker, transmit an order, change
configuration, provision a service, or authorize production operation.

Gate F approval for Slice 059 authorizes preparation of this checklist only. Any future rollout
work requires a Separate future approval after independent review of the completed evidence packet.

No checklist result can enable live trading. No checklist result can override configuration, risk,
approval, OMS, audit, emergency-stop, authorization, reconciliation, incident-response, paper-only,
or readiness gates.

IBKR TWS or Gateway API ports must never be exposed to the public internet.

## Evidence Vocabulary

Every mandatory evidence item has one of these states:

- `verified`: a named review role has inspected current, scoped, non-secret evidence and recorded a
  safe reference, review date, and outcome;
- `missing`: the required evidence artifact does not exist;
- `unverified`: an artifact or local foundation exists, but the required independent or
  environment-specific review has not occurred;
- `expired`: the review is older than its approved validity period or the reviewed system changed;
- `contradictory`: evidence conflicts with another artifact or observed system state.

Mandatory evidence cannot use a not-applicable state. Evidence must return to `unverified` after a
material code, configuration, dependency, network, authorization, broker-adapter, operating-system,
or deployment-design change.

The aggregate result may be only:

- `not_ready`: at least one mandatory item is not `verified`;
- `ready_for_final_review`: all mandatory items are `verified`, but a separate final review and
  explicit human decision are still required.

`ready_for_final_review` is not a go decision and cannot trigger any action.

## Current Evidence Register

The planning authorization recorded for this slice applies only to checklist preparation. It is not
rollout sign-off and is excluded from the go/no-go evidence count.

| Required evidence | Current state | Current blocking reason |
| --- | --- | --- |
| External review evidence | `missing` | No independent scoped review record is attached. |
| Paper-trading history evidence | `missing` | No reviewed duration, scenario coverage, incident summary, or acceptance record is attached. |
| Live-readiness evidence | `unverified` | The dashboard reports `not_ready` and required evidence remains missing. |
| Secret-management review | `unverified` | Requirements are documented, but no environment-specific handling review is attached. |
| Network-exposure review | `missing` | No approved deny-by-default, localhost-only exposure review is attached. |
| Authentication and authorization evidence | `unverified` | Local role controls exist, but production-like identity and access suitability is not established. |
| Emergency-stop evidence | `unverified` | Local implementation and tests exist, but no target-environment rehearsal record is attached. |
| Observability evidence | `unverified` | Local read-only posture exists, but no operating-environment observation review is attached. |
| Audit-retention evidence | `unverified` | Append-only requirements exist, but no approved operational retention review is attached. |
| Backup and restore evidence | `unverified` | Local planning exists, but no target-environment backup and restore rehearsal is attached. |
| Reconciliation evidence | `unverified` | Deterministic local tests exist, but no reviewed production-like paper session evidence is attached. |
| Rollback evidence | `missing` | No reviewed rollback rehearsal and data-preservation record is attached. |
| Incident-response evidence | `missing` | No reviewed exercise, escalation record, or post-exercise findings are attached. |
| Operator sign-off evidence | `missing` | No scoped operations, risk, security, and final human sign-offs are attached. |

Current go/no-go decision: `no_go`.

## Paper-Only Entry Criteria

All paper-only entry criteria are mandatory:

- application mode is paper or simulation and live trading remains disabled;
- IBKR account mode is paper-only;
- broker connectivity is localhost-only and limited to reviewed paper endpoints;
- no public broker API port, public broker host field, or internet-routable broker listener exists;
- no live account, live route, or live-order capability exists in configuration, API, UI, workflow,
  adapter, deployment, or operator procedure;
- every order has a passed risk decision, explicit human approval, valid OMS state, duplicate
  protection, and a protective-order plan or approved exception;
- stale market data blocks decisions;
- unknown broker state, disconnect, reconnect, callback conflict, and reconciliation-required state
  block new risk-increasing work;
- every safety-relevant event is appended to the journal;
- a position without expected protection produces a critical alert;
- operator access preserves role separation and does not treat local development headers as
  production authentication;
- emergency-stop behavior is tested for the reviewed artifact and target environment;
- the evidence packet contains no credentials, account identifiers, tokens, passwords,
  certificates, private keys, secret values, or private operator data.

Failure of any entry criterion is an immediate `no_go`.

## Required Review Evidence

### External Review Evidence

The evidence packet must include an independent review record covering trading safety, secret
leakage, live-order prevention, paper-only enforcement, risk and approval gates, OMS correctness,
journaling, authorization, emergency stop, reconciliation, rollback, and incident response.

Open P0 or P1 findings are blocking. Unscoped, self-authored, expired, or unsigned review notes are
`unverified`.

### Paper-Trading History Evidence

The history review must define the reviewed build, date range, session count, strategy/workflow
scope, symbols represented without account identifiers, disconnect/reconnect scenarios, stale-data
blocks, duplicate prevention, reconciliation outcomes, missing-protection alerts, operator approval
outcomes, emergency-stop exercises, and all incidents or anomalies.

Missing duration criteria, unexplained gaps, unresolved anomalies, or evidence from a different
build is blocking.

### Live-Readiness Evidence

The live-readiness dashboard must be reviewed as evidence posture only. Its result must never be
used to enable live trading. A `not_ready` result is blocking; `ready_for_final_review` still
requires independent review and an explicit human decision.

### Secret-Management Review

Secret-management review must prove that private values remain outside git, docs, tests, logs,
screenshots, exports, alerts, workflow definitions, and UI/API payloads. It must cover least
privilege, environment separation, redaction, rotation, revocation, startup failure behavior, and
incident handling without recording secret values.

### Network-Exposure Review

Network review must prove deny-by-default exposure, localhost-only broker connectivity, no public
IBKR API port, no public broker callback listener, and no UI/API/workflow field that can redirect
broker traffic. Any unknown route, public listener, or undocumented exception is blocking.

### Authentication And Authorization Evidence

Review must prove operator identity, least privilege, role separation, privileged-action audit,
session handling, access revocation, and denial behavior. Local development header authentication
is insufficient for production-like paper operation.

### Emergency-Stop Evidence

Evidence must identify the reviewed build and show activation, risk-increasing work blocking,
allowed risk-reducing rejection behavior, journal coverage, authorized deactivation, recovery, and
post-event review. Broker-side liquidation, live cancel, live flatten, and live transmission remain
out of scope.

### Observability Evidence

Evidence must show that system health, safety posture, emergency-stop state, journal health,
reconciliation state, backup posture, and incident state can be observed without leaking secrets or
adding external control paths.

### Audit-Retention Evidence

Evidence must show append-only preservation, reviewed retention periods, access controls, integrity
checks, and non-destructive handling. Deletion, truncation, compaction, or rewrite capability is not
approved by this checklist.

### Backup And Restore Evidence

Evidence must show encrypted local backup scope, secret exclusion, integrity checking, a reviewed
restore rehearsal, audit ordering preservation, and reconciliation before risk-increasing work.
External storage and automated restore execution are not approved by this checklist.

### Reconciliation Evidence

Evidence must cover disconnect, reconnect, unknown state, stale data, duplicate callbacks,
conflicting callbacks, out-of-order callbacks, and explicit reconciliation completion. Unknown or
unreconciled state remains blocking.

## Rollback And Incident Evidence

### Rollback Evidence

A reviewed rollback plan and rehearsal record must demonstrate:

- paper transport can be disabled without enabling another transport;
- workers and adapters can be stopped before artifact rollback;
- journals, approvals, OMS state, fills, callbacks, and reconciliation records remain preserved;
- restored or rolled-back state remains blocked until reconciliation is complete;
- suspected private-value exposure follows revocation and incident procedures without recording
  the values;
- rollback decisions and outcomes are journaled or attached to the incident record;
- destructive data rollback is prohibited unless a separately reviewed restore procedure permits
  it.

An untested rollback plan is `unverified`.

### Incident-Response Evidence

A reviewed exercise must cover detection, severity, authorized emergency-stop use, containment,
operator escalation, evidence preservation, reconciliation, recovery criteria, rollback decision,
post-incident review, and unresolved finding ownership.

No incident procedure may bypass risk, approval, OMS, audit, authorization, emergency stop,
paper-only enforcement, reconciliation, or readiness checks. The checklist adds no broker-side
emergency action or external incident integration.

## Operator Sign-Off Evidence

Separate sign-offs are required from the scoped operations, risk, security, independent review, and
final human approval roles. Each record must contain a safe evidence reference, reviewed build,
scope, decision, date, expiry or re-review trigger, and unresolved findings. It must not contain
private identity data, credentials, account identifiers, or signatures containing secret material.

No sign-off role may infer another role's decision. Missing sign-off is blocking.

## Explicit Go/No-Go Rules

A checklist may advance to `ready_for_final_review` only when every mandatory item is `verified`,
all evidence refers to the same reviewed build and environment, no P0/P1 finding is open, and no
evidence is expired or contradictory.

The decision remains `no_go` when any item is `missing`, `unverified`, `expired`, or
`contradictory`; when paper-only posture cannot be proven; when broker state is unknown; when data
is stale; when reconciliation is incomplete; when expected protection is absent; or when emergency
stop, authorization, audit, rollback, backup/restore, or incident-response evidence is inadequate.

Even after `ready_for_final_review`, a separate future approval and a new approved ExecPlan are
required before any rollout implementation or operational action. There is no automatic promotion,
deployment, configuration change, connector action, or order action.

## Evidence Handling

Evidence references may contain only safe identifiers, document names, non-secret checksums,
review dates, status, scope, and finding references. Evidence must be redacted and secret-scanned
before sharing. Evidence records must not embed credentials, account identifiers, tokens,
passwords, certificates, private keys, secret values, broker hosts, broker ports, or private
operator data.

## Current Decision

Current result: `not_ready`.

Current decision: `no_go`.

External review, paper-trading history, environment-specific secret and network reviews, target-
environment operating evidence, rollback rehearsal, incident exercise, and operator sign-offs are
missing or unverified. No rollout may start from this checklist state.
