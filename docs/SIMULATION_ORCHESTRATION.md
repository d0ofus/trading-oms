# Simulation Orchestration

Slice 027 adds the first deterministic replay-to-approval orchestration path.

This slice does not add approval decision endpoints, automatic approval, fake broker execution,
simulated fills, position tracking, broker connectivity, IBKR transport, order submission, HTTP
mutation endpoints, or live trading.

## Flow

The orchestration path is:

```text
simulation run
-> replay events
-> local 5-minute bars
-> first 5-minute breakout plus volume-filter strategy signal
-> non-routable order-intent proposal
-> risk decision
-> local OMS CREATED and PENDING_APPROVAL context
-> pending approval ticket
```

OMS is used only to produce the pending-approval context required by approval tickets. No approved
order is submitted to a broker or fake broker in this slice.

## Safety Blocks

Approval-ticket creation is blocked when risk blocks, including:

- stale market data;
- duplicate risk request IDs;
- unknown broker state for risk-increasing proposals.

Duplicate order-intent proposal IDs fail safely. The simulation run is marked failed and no second
proposal is journaled.

## Journal Coverage

The orchestrator relies on existing domain modules to journal accepted state changes:

- `simulation_run.created`
- `simulation_run.status_changed`
- `strategy.signal.generated`
- `order_intent.proposed`
- `risk.decision.evaluated`
- `oms.order.transitioned`
- `approval.ticket.created`

No `fake_broker.order.transitioned` events are emitted in this slice.

## Current Limitations

- Orchestration is in-memory only.
- Replay inputs are passed as local `MarketDataReplayEvent` records.
- No HTTP API exists for starting simulation runs yet.
- Approval decisions are not applied in this slice.
- Fake broker execution, fills, positions, and protection alerts are deferred to later Gate B
  slices.
