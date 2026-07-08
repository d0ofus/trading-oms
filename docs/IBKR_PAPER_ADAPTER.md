# IBKR Paper Adapter

Slice 016 introduces the first IBKR paper adapter foundation.

It does not add live trading, live IBKR account mode, real broker credentials, account IDs,
certificates, private keys, passwords, tokens, public IBKR exposure, an IBKR SDK dependency, socket
or network transport, TWS/Gateway connectivity, order submission, order placement, order
transmission, order cancellation, order modification, market-data subscriptions, contract
resolution, OMS orchestration, approval workflow orchestration, reconnect/chaos behavior, or UI.

## Purpose

The adapter gives future IBKR work a broker-specific boundary without letting core OMS or risk code
import IBKR-specific behavior directly.

The current implementation is local only. It can:

- validate paper-only adapter configuration;
- record local IBKR paper connection-state observations;
- represent unknown IBKR state as requiring reconciliation;
- build a local, non-transmitting paper order plan from an already validated
  `BrokerOrderRequest`;
- append connection-state and order-plan records to the event journal.

## Configuration Boundary

`IbkrPaperAdapterConfig` requires:

- `account_mode: paper`
- `live_trading_enabled: false`
- `host`: `127.0.0.1`, `localhost`, or `::1`
- `port`: `7497` for TWS paper or `4002` for IB Gateway paper

The adapter configuration can be built from the existing safe `Settings` object. It rejects live
account mode, enabled live trading, non-localhost hosts, and non-paper ports.

## Connection State

The local connection-state model is:

- `disconnected`
- `connected_paper`
- `unknown_requires_reconciliation`

Unknown state sets `requires_reconciliation: true` and blocks local paper order-plan creation.

Connection-state records are journaled with event type:

```text
ibkr.paper.connection_state.recorded
```

## Paper Order Plans

`IbkrPaperAdapter.create_order_plan` accepts only an existing validated `BrokerOrderRequest`. That
request already requires:

- positive order quantity;
- valid side and order type;
- passed risk-decision context;
- explicit approval reference.

The resulting `IbkrPaperOrderPlan` is a local record with `status: planned_local_only` and
`local_only: true`. It is not sent anywhere.

Order plans are journaled with event type:

```text
ibkr.paper.order_plan.created
```

## Guarantees

- No IBKR SDK dependency.
- No socket or network transport.
- No TWS or IB Gateway connection attempt.
- No submit, place, transmit, cancel, or modify methods.
- No real account IDs, credentials, certificates, passwords, private keys, tokens, or secrets.
- No public IBKR host or port exposure.
- Unknown state is explicit and blocks local paper order-plan creation.
- Core OMS and risk code remain broker-agnostic.

## Current Limitations

- No actual IBKR session.
- No market data.
- No contract lookup.
- No paper order transport.
- No order status or fill callbacks.
- No OMS/fake broker/approval orchestration.
- No reconnect or reconciliation implementation beyond local state representation.
- No persistence beyond the event journal records written by callers.
