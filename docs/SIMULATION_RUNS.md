# Simulation Runs

Slice 024 introduces a deterministic simulation run model.

This slice does not run strategies, create HTTP endpoints, approve tickets, orchestrate fake broker
execution, connect to brokers, add IBKR transport, submit orders, or enable live trading.

## Purpose

Simulation run records provide a local lifecycle spine for later Gate B orchestration. A run tracks:

- run ID;
- lifecycle status;
- creation and update timestamps;
- replay input reference;
- append-only journal references.

The backend module is:

```text
trading_oms_backend.simulation_runs
```

## Lifecycle

The initial status is `created`.

Allowed transitions:

- `created` -> `running`
- `created` -> `completed`
- `created` -> `failed`
- `created` -> `cancelled`
- `running` -> `completed`
- `running` -> `failed`
- `running` -> `cancelled`

Terminal statuses are `completed`, `failed`, and `cancelled`. Terminal runs cannot transition.

## Journaling

`SimulationRunBook` appends journal records for accepted operations:

- `simulation_run.created`
- `simulation_run.status_changed`

The returned run record stores journal references as `journal_sequence:<sequence>`.

## Idempotency

- Repeating the same create payload for the same `run_id` returns the existing run and does not
  append another journal record.
- Repeating the same transition payload for the same `transition_id` returns the prior result and
  does not append another journal record.
- Conflicting duplicate IDs fail without journaling.

## Safety Guarantees

- Replay input references must be local references, not URLs or broker routes.
- Replay input references reject credential-, broker-, socket-, token-, and transmit-shaped text.
- Invalid transitions fail before journal append.
- The module contains no HTTP routes, network clients, socket code, broker SDK imports, order
  submission behavior, or live-trading behavior.

## Current Limitations

- Run records are in-memory only.
- No simulation run API endpoint exists yet.
- No strategy, risk, approval, OMS, fake broker, position, alert, or UI orchestration is performed
  in this slice.
