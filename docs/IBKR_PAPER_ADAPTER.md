# IBKR Paper Adapter

Slice 016 introduces the first IBKR paper adapter foundation. Slice 047 adds a local-only TCP
reachability probe for validated paper TWS/Gateway endpoints. Slice 048 adds adapter-bound paper
contract lookup records for sanitized stock metadata. Slice 049 adds guarded adapter-bound paper
order submission records.

It does not add live trading, live IBKR account mode, real broker credentials, account IDs,
certificates, private keys, passwords, tokens, public IBKR exposure, an IBKR SDK dependency,
authenticated TWS/Gateway sessions by default, live order submission, order cancellation, order
modification, market-data subscriptions, OMS orchestration, approval workflow orchestration, order
status callbacks, fill callbacks, paper trading UI, or production rollout.

## Purpose

The adapter gives future IBKR work a broker-specific boundary without letting core OMS or risk code
import IBKR-specific behavior directly.

The current implementation is local only. It can:

- validate paper-only adapter configuration;
- probe local TWS/Gateway paper TCP reachability without sending application data;
- resolve supported paper stock contract metadata through an injected adapter-bound connector;
- record local IBKR paper connection-state observations;
- represent unknown IBKR state as requiring reconciliation;
- build a local, non-transmitting paper order plan from an already validated
  `BrokerOrderRequest`;
- record a guarded paper order submission attempt through an injected adapter-bound connector after
  risk, approval, OMS, contract, idempotency, reconciliation, and protection checks pass;
- append connectivity-probe, contract-lookup, connection-state, order-plan, and paper submission
  records to the event journal.

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

## Contract Lookup

`IbkrPaperAdapter.lookup_contract` accepts a validated `IbkrPaperContractLookupRequest`, requires a
known local paper endpoint configuration, journals the attempt, and uses an injected
`ContractLookupConnector` to resolve supported stock contract metadata.

The lookup does not authenticate, import an IBKR SDK, subscribe to market data, request account
state, or place orders. It does not create order intents, OMS transitions, approval tickets, paper
orders, order callbacks, or fill callbacks.

Contract lookup event types:

```text
ibkr.paper.contract_lookup.attempted
ibkr.paper.contract_lookup.recorded
```

Lookup outcomes include:

- `resolved`;
- `not_found`;
- `ambiguous`;
- `unsupported_instrument`;
- `blocked_disconnected`;
- `blocked_reconciliation_required`;
- `stale_result_rejected`;
- `unknown_requires_reconciliation`.

Stale results, timeout, OS errors, unexpected connector errors, and existing unknown state are
represented as reconciliation-required. Reconciliation-required state continues to block local paper
order-plan creation.

Lookup payloads intentionally omit host, port, account, credential, route, submit, transmit, order,
token, password, certificate, private key, and secret fields.

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

## Paper Order Submission

`IbkrPaperAdapter.record_paper_order_submission` accepts an
`IbkrPaperOrderSubmissionRequest` that references:

- an existing `IbkrPaperOrderPlan`;
- fresh sanitized `IbkrPaperResolvedContract` metadata;
- an OMS transition reference;
- an idempotency key;
- a protective-order plan reference or approved protective exception for risk-increasing buys.

The adapter journals every submission attempt with:

```text
ibkr.paper.order_submission.attempted
```

and every outcome with:

```text
ibkr.paper.order_submission.recorded
```

The method uses an injected `PaperOrderSubmissionConnector` only after all safety gates pass. The
default connector is unavailable and returns an `unknown_requires_reconciliation` outcome rather
than silently accepting work.

Submission outcomes include:

- `accepted_paper_submission`;
- `duplicate_accepted`;
- `blocked_duplicate_conflict`;
- `blocked_disconnected`;
- `blocked_reconciliation_required`;
- `blocked_stale_contract`;
- `blocked_contract_mismatch`;
- `blocked_missing_protection`;
- `unknown_requires_reconciliation`.

Duplicate idempotency keys are accepted only when the canonical submission payload matches the
previous accepted payload. Reused keys with different payloads are rejected and journaled as
`blocked_duplicate_conflict`.

Disconnected, unknown, stale, or reconciliation-required state blocks connector use. Stale or
unknown submission outcomes record adapter state as `unknown_requires_reconciliation`.

Submission payloads intentionally omit host, port, account, credential, route, submit, transmit,
broker order identifier, order status callback, fill callback, token, password, certificate,
private key, and secret fields.

## Guarantees

- No IBKR SDK dependency.
- No authenticated TWS or IB Gateway session.
- No built-in IBKR protocol transport.
- Local TCP reachability probe only; it sends no application data.
- No live submit, place, transmit, cancel, or modify methods.
- Contract lookup is connector-driven and does not create an order-capable transport.
- Paper submission is connector-driven, paper-only, and blocked unless risk, approval, OMS,
  contract, idempotency, reconciliation, and protection gates pass.
- No real account IDs, credentials, certificates, passwords, private keys, tokens, or secrets.
- No public IBKR host or port exposure.
- Unknown state is explicit and blocks local paper order-plan creation and paper submission.
- Core OMS and risk code remain broker-agnostic.

## Current Limitations

- No actual IBKR session.
- No market data.
- No SDK-backed contract lookup.
- No built-in SDK-backed paper order transport.
- No order status or fill callbacks.
- No OMS/fake broker/approval orchestration.
- Reconnect and reconciliation are covered only by the local resilience/chaos harness; there is no
  real IBKR session reconciliation.
- No persistence beyond the event journal records written by callers.
