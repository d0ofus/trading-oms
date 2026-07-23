# Backend Read Models

Slice 020 introduces typed backend read models for safe inspection views.

This slice does not add HTTP endpoints, frontend integration, mutation endpoints, simulation
orchestration, persistence, broker connectivity, IBKR transport, order submission, or live trading.

## Purpose

The read models are stable, JSON-compatible summaries for read-only API endpoints and UI sections.
They make the current safety posture and local workflow state inspectable without adding action
controls.

The backend module is:

```text
trading_oms_backend.read_models
```

## Included Views

The module provides frozen dataclasses for:

- emergency stop state;
- safety posture;
- audit events;
- strategy signals;
- risk decisions;
- approval tickets;
- orders;
- positions;
- alerts;
- live-readiness status;
- live-readiness evidence dashboard;
- paper trading operator visibility;
- operations controls for observability, retention, backup/restore, and incident response;
- aggregate operations view.

Every read model exposes `to_json_dict()` for deterministic JSON-compatible output.

Audit event read models include optional filter metadata for the audit explorer:

- `run_id`
- `symbol`
- `order_id`
- `ticket_id`
- `severity`

## Demo Assembler

`build_demo_operations_read_model()` returns a safe local aggregate view for the current read-only
API slice. It uses static inspection records only. It does not read from a database, write to the
event journal, submit orders, approve tickets, connect to brokers, or call external services.

## Durable Simulation Lifecycle Projection

The signal, risk-decision, approval-ticket, audit-event, order, position, and alert endpoints
replace their representative rows when at least one committed saved-workflow simulation run
exists. The projection consumes only records returned by
`WorkflowSimulationRunner.list_projection_sources()`. The runner reconstructs every SQLite
schema-v4 row and verifies its SHA-256-bound manifest against the append-only JSONL journal before
any row reaches the read-model projector.

Signals, risk decisions, approval tickets, and audit events carry a strict
`decision_attribution` object. It preserves the exact workflow/version/run state, persisted signal
reference, order-intent ID, risk-decision ID, approval-ticket ID, optional decision ID/value/actor/
reason/timestamp, event references, and complete manifest references. Its fixed classifications
are `simulated`, `local_only`, and `externally_unverified`; `broker_derived` and
`externally_verified` remain false.

Each durable row contains one strict `execution_attribution` object with the exact workflow and
version, run, execution, order intent, risk decision, approval ticket and decision, OMS order,
fake-fill reference, position, protection status, local alert, complete run manifest references,
and execution-specific journal references. Its fixed classifications are `simulated`, `local_only`,
`fake_broker_derived`, and `externally_unverified`; `broker_derived` and `externally_verified`
remain false.

The projector is all-or-nothing across all seven lifecycle resources. Pending persistence,
partial, malformed, digest-invalid, source-mismatched, contradictory, duplicate, or otherwise
unavailable evidence returns generic HTTP 503 without partial data. A committed run waiting for a
manual decision is valid lifecycle evidence; its order, position, and alert resources are empty
with explicit durable provenance. Unaffected safety and readiness endpoints remain available. If
there is no committed run, the existing representative rows and provenance remain visibly
unchanged.

## Saved-Run Comparison Snapshot

`trading_oms_backend.simulation_run_comparison` builds a frozen read-only snapshot for exactly two
explicit committed workflow/run selectors. It reuses the strict lifecycle validator and compares
workflow, run, signal, order intent, risk, ticket, decision, execution, protection, alerts, and
journal provenance in a fixed order.

Each section and field difference is deterministically classified as added, removed, changed, or
unchanged. The snapshot binds every manifest sequence to its canonical record SHA-256 and includes
a deterministic comparison SHA-256. A same-run selection is valid and produces eleven unchanged
sections. There is no representative fallback when committed sources exist.

Selected audit-export evidence binds one exact committed run to its source-manifest digest and
either the complete manifest or one exact sequence already contained in that manifest. These are
in-memory/API records only; no database or journal schema is changed.

## Safety Guarantees

- Read models are frozen dataclasses.
- Live trading remains disabled in the safety and readiness views.
- Readiness views always report `live_trading_enabled: false` and
  `live_trading_authorized: false`.
- Live-readiness evidence dashboard views always report `live_trading_enabled: false` and
  `live_trading_authorized: false`, and may report only `not_ready` or
  `ready_for_final_review`.
- `ready_for_final_review` is evidence posture only and does not authorize live trading.
- Paper trading operator views always require `paper_mode: paper` and
  `live_trading_enabled: false`.
- Operational controls always report `live_trading_enabled: false`,
  `production_rollout_authorized: false`, destructive retention disabled, append-only journal
  preservation required, and external backup storage unconfigured.
- Emergency stop views expose local stop status and blocking posture only. They contain no broker
  controls or action URLs.
- The module contains no network, socket, IBKR SDK, broker transport, or order-submission behavior.
- The module exposes no submit, approve, reject, cancel, connect, transmit, credential, token,
  password, account, route, host, port, socket, or secret affordance keys.

## Current Limitations

- The base aggregate assembler is local demo data; validated committed runs replace all seven
  lifecycle resources atomically.
- Slice 021 exposes these models through read-only `GET /api/...` endpoints.
- Frontend screens consume these models for read-only inspection.
- The paper trading operator read model is representative read-only visibility, not a live IBKR
  session.
- The live-readiness evidence dashboard is representative read-only visibility, not approval for
  live trading or controlled paper rollout.
- The operations controls read model is representative read-only visibility, not external
  observability, backup execution, restore execution, audit deletion, or production rollout.
- Durable projection remains local simulation evidence. It is not broker-derived or externally
  verified and does not authorize automatic approval, automatic execution, broker transport, or
  live trading.
- Saved-run comparison validates every committed source before selection. One corrupt source
  quarantines comparison/export availability rather than allowing a misleading partial view.
