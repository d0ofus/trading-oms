# IBKR Adapter Design

## Status

Not implemented.

## Rules

- IBKR integration must be paper-only when first introduced.
- Broker-specific behavior must live behind an adapter interface.
- Core OMS and risk logic must not import IBKR libraries directly.
- Reconnect and reconciliation must be designed before any production rollout.
- Live trading must remain disabled by default.

## Expected adapter responsibilities

- Connect to TWS or IB Gateway.
- Subscribe to market data.
- Resolve contracts.
- Submit paper orders only.
- Receive order status updates.
- Receive fills.
- Reconcile open orders and positions.
- Emit structured events to the event journal.
