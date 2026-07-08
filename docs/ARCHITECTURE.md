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
- Strategy DSL.
- Visual workflow builder.
- IBKR paper adapter foundation.
- Local resilience and chaos-test harness.

## Later components

- React Flow drag-and-drop visual builder.
- IBKR paper transport.
- Production reconciliation engine.
- Live-readiness gate.
