# Fake Broker

Slice 009 introduces a deterministic, simulation-only fake broker adapter.

It does not add live broker integration, IBKR connectivity, network access, real broker
credentials, approval tickets, OMS orchestration, alerts, UI, database migrations, or live trading.

## Purpose

The fake broker gives later replay, approval, and OMS slices a local adapter-shaped component for
simulated order transitions.

It accepts only validated `BrokerOrderRequest` records. Requests must include:

- a unique `client_order_id`;
- uppercase `symbol`;
- `side`: `buy` or `sell`;
- positive integer `quantity`;
- `order_type`: `market` or `limit`;
- positive finite `reference_price`;
- timezone-aware `requested_at`;
- `risk_decision_id`;
- `risk_decision_result`: `passed`;
- `approval_reference`.

The fake broker validates that risk and approval references exist as request fields. It does not
verify them against a persisted risk or approval service because those integrations do not exist
yet.

## Adapter Interface

The Python interface is simulation-only:

- `SimulationBrokerAdapter.accept_order`
- `SimulationBrokerAdapter.fill_order`
- `SimulationBrokerAdapter.cancel_order`
- `SimulationBrokerAdapter.reject_order`

The concrete implementation is `FakeBroker`.

There is no socket, network host, port, broker SDK, live account, or external transmission path.

## Fill Modes

`FakeBrokerConfig.fill_mode` controls deterministic fill behavior:

- `acknowledge_only`: accepting an order creates one `acknowledged` transition.
- `fill_immediately`: accepting an order creates `acknowledged` and then `filled` transitions at
  the request timestamp.

For immediate fills, market orders use `reference_price`, and limit orders use `limit_price`.

Manual fills can be created only after an order is acknowledged.

## Transition Event

Every fake broker order transition is appended to the event journal with event type:

```text
fake_broker.order.transitioned
```

The transition payload contains:

- `client_order_id`;
- `fake_broker_order_id`;
- `symbol`;
- `side`;
- `quantity`;
- `state`: `acknowledged`, `filled`, `cancelled`, or `rejected`;
- `occurred_at`;
- `reason`;
- `cumulative_filled_quantity`;
- `leaves_quantity`;
- optional `fill_price`;
- the original validated order request snapshot.

## Guarantees

- Fake broker behavior is local and deterministic.
- Duplicate client order IDs are blocked.
- Accepted fake orders are journaled as acknowledged.
- Configured immediate fills are journaled deterministically.
- Manual fills and cancels are allowed only for acknowledged fake orders.
- Explicit rejections are journaled without first acknowledging the order.
- Invalid requests, configs, transitions, and state changes fail validation.
- No live broker connectivity, account routing, network access, credentials, or live trading path is
  introduced.

## Current Limitations

- State is in memory only.
- No partial fills.
- No order amendments.
- OMS state transition validation exists separately in `docs/OMS_STATE_MACHINE.md`, but this fake
  broker does not orchestrate OMS transitions.
- No approval ticket lookup yet.
- No portfolio or position reconciliation yet.
- Numeric values currently use Python floats because earlier replay, bar, strategy, and risk slices
  use Python floats.
- Callers must not put secrets in request or transition fields.
