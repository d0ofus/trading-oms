# Backend Read Models

Slice 020 introduces typed backend read models for safe inspection views.

This slice does not add HTTP endpoints, frontend integration, mutation endpoints, simulation
orchestration, persistence, broker connectivity, IBKR transport, order submission, or live trading.

## Purpose

The read models are stable, JSON-compatible summaries for future read-only API endpoints and UI
sections. They make the current safety posture and local workflow state inspectable without adding
action controls.

The backend module is:

```text
trading_oms_backend.read_models
```

## Included Views

The module provides frozen dataclasses for:

- safety posture;
- audit events;
- strategy signals;
- risk decisions;
- approval tickets;
- orders;
- positions;
- alerts;
- live-readiness status;
- aggregate operations view.

Every read model exposes `to_json_dict()` for deterministic JSON-compatible output.

## Demo Assembler

`build_demo_operations_read_model()` returns a safe local aggregate view for the next read-only API
slice. It uses static inspection records only. It does not read from a database, write to the event
journal, submit orders, approve tickets, connect to brokers, or call external services.

## Safety Guarantees

- Read models are frozen dataclasses.
- Live trading remains disabled in the safety and readiness views.
- Readiness views always report `live_trading_enabled: false` and
  `live_trading_authorized: false`.
- The module contains no network, socket, IBKR SDK, broker transport, or order-submission behavior.
- The module exposes no submit, approve, reject, cancel, connect, transmit, credential, token,
  password, account, route, host, port, socket, or secret affordance keys.

## Current Limitations

- The aggregate assembler is local demo data only.
- No HTTP endpoints expose these models yet.
- No frontend screen consumes these models yet.
- No database-backed read model persistence exists yet.
- Position records are inspection summaries only; full simulated position tracking remains a later
  slice.
