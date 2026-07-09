# IBKR Paper Adapter

Slice 016 introduces the first IBKR paper adapter foundation. Slice 047 adds a local-only TCP
reachability probe for validated paper TWS/Gateway endpoints.

It does not add live trading, live IBKR account mode, real broker credentials, account IDs,
certificates, private keys, passwords, tokens, public IBKR exposure, an IBKR SDK dependency,
authenticated TWS/Gateway sessions, IBKR protocol transport, order submission, order placement,
order transmission, order cancellation, order modification, market-data subscriptions, contract
resolution, OMS orchestration, approval workflow orchestration, callback handling, paper trading UI,
or production rollout.

## Purpose

The adapter gives future IBKR work a broker-specific boundary without letting core OMS or risk code
import IBKR-specific behavior directly.

The current implementation is local only. It can:

- validate paper-only adapter configuration;
- probe local TWS/Gateway paper TCP reachability without sending application data;
- record local IBKR paper connection-state observations;
- represent unknown IBKR state as requiring reconciliation;
- build a local, non-transmitting paper order plan from an already validated
  `BrokerOrderRequest`;
- append connectivity-probe, connection-state, and order-plan records to the event journal.

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

## Connectivity Probe

`IbkrPaperAdapter.probe_local_connectivity` checks whether the validated localhost paper endpoint is
reachable by opening and closing a short TCP connection. It does not authenticate, send IBKR
protocol data, subscribe to market data, perform contract lookup, request account state, or place
orders.

The probe journals event type:

```text
ibkr.paper.connectivity_probe.recorded
```

Probe outcomes map to adapter state:

- reachable local paper endpoint -> `connected_paper`;
- refused local paper endpoint -> `disconnected`;
- timeout or unexpected OS error -> `unknown_requires_reconciliation`.

Probe payloads intentionally omit host, port, account, credential, route, submit, transmit, and
secret fields.

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
- No authenticated TWS or IB Gateway session.
- No IBKR protocol transport.
- Local TCP reachability probe only; it sends no application data.
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
- Reconnect and reconciliation are covered only by the local resilience/chaos harness; there is no
  real IBKR session reconciliation.
- No persistence beyond the event journal records written by callers.
