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

## Safety Guarantees

- Read models are frozen dataclasses.
- Live trading remains disabled in the safety and readiness views.
- Readiness views always report `live_trading_enabled: false` and
  `live_trading_authorized: false`.
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

- The aggregate assembler is local demo data only.
- Slice 021 exposes these models through read-only `GET /api/...` endpoints.
- Frontend screens consume these models for read-only inspection.
- The paper trading operator read model is representative read-only visibility, not a live IBKR
  session.
- The operations controls read model is representative read-only visibility, not external
  observability, backup execution, restore execution, audit deletion, or production rollout.
- SQLite persistence exists as a local foundation, but these read models are not yet backed by it at
  runtime.
- Position records are inspection summaries only; full simulated position tracking remains a later
  slice.
