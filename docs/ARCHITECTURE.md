# Architecture

## Principles

- Core domain code must be broker-agnostic.
- Broker integrations must be adapters.
- Simulation and replay must be deterministic.
- Safety state must be explicit.
- Audit history must be append-only for critical events.
- Unknown broker state blocks risk-increasing actions.

## Initial components

- Config.
- Event journal.
- Market-data replay.
- Bar builder.
- Strategy engine.
- Risk engine.
- Approval service.
- Broker adapter interface.
- Fake broker.
- OMS.
- Alerts.
- API.
- UI.

## Later components

- Strategy DSL.
- React Flow visual builder.
- IBKR paper adapter.
- Reconciliation engine.
- Chaos test harness.
- Live-readiness gate.
