# IBKR Paper Order Submission

Slice 049 adds a guarded paper order submission record surface behind the existing IBKR paper
adapter boundary.

The submission surface is paper-only. It does not enable live trading, live account mode, real
broker credentials, account identifiers, public IBKR exposure, market-data subscriptions, order
status callbacks, fill callbacks, paper trading UI, production rollout, or live order transmission.

## Scope

The adapter can:

- validate the existing paper-only adapter configuration;
- require adapter state `connected_paper` before connector use;
- reject reconciliation-required state before connector use;
- require a local `IbkrPaperOrderPlan` built from a passed risk decision and explicit approval;
- require fresh sanitized `IbkrPaperResolvedContract` metadata from contract lookup;
- require an OMS transition reference;
- require an idempotency key;
- require protective-order evidence or an approved exception for risk-increasing buys;
- call an injected adapter-bound paper submission connector only after all safety checks pass;
- journal every attempt and outcome;
- mark stale, timeout, OS, unexpected, unavailable, or existing unknown state as
  reconciliation-required.

The adapter cannot:

- authenticate by itself;
- store account identifiers;
- use credentials, tokens, passwords, certificates, private keys, or secrets;
- import or use an IBKR SDK directly;
- subscribe to market data;
- request account state;
- route live orders;
- receive order status callbacks;
- receive fill callbacks;
- expose public IBKR ports;
- enable live trading.

## Required Evidence

`IbkrPaperAdapter.record_paper_order_submission` requires an
`IbkrPaperOrderSubmissionRequest` with:

- `order_plan`: an `IbkrPaperOrderPlan` created from a validated `BrokerOrderRequest`;
- `contract`: fresh sanitized contract metadata;
- `oms_transition_reference`: the caller's OMS-ready transition reference;
- `idempotency_key`: deterministic duplicate-prevention key;
- `protective_order_plan_reference` or `approved_protective_exception_reference` for
  risk-increasing buys.

The order plan already carries:

- `client_order_id`;
- symbol, side, quantity, and order type;
- passed risk decision ID;
- explicit approval reference.

## Connector Boundary

The method accepts an injected `PaperOrderSubmissionConnector`. This keeps future SDK or protocol
work inside the IBKR adapter boundary and lets tests prove guard ordering without requiring a
running TWS or IB Gateway process.

The default connector is unavailable and records `unknown_requires_reconciliation`. It does not
silently accept work.

## Journal Events

Each request appends:

```text
ibkr.paper.order_submission.attempted
```

and then appends:

```text
ibkr.paper.order_submission.recorded
```

Outcomes include:

- `accepted_paper_submission`;
- `duplicate_accepted`;
- `blocked_duplicate_conflict`;
- `blocked_disconnected`;
- `blocked_reconciliation_required`;
- `blocked_stale_contract`;
- `blocked_contract_mismatch`;
- `blocked_missing_protection`;
- `unknown_requires_reconciliation`.

Payloads include only local identifiers, order-plan facts, contract ID, safety references, status,
reconciliation flag, and optional failure category. Payloads intentionally exclude host, port,
account, credential, route, submit, transmit, broker order identifier, order status callback, fill
callback, token, password, certificate, private key, and secret fields.

## Idempotency

The adapter stores a canonical payload hash per idempotency key in memory.

- Matching duplicate payloads produce `duplicate_accepted` without calling the connector again.
- Reused idempotency keys with different canonical payloads produce
  `blocked_duplicate_conflict`.

## Safety Guarantees

- Live trading remains disabled.
- IBKR account mode remains paper-only.
- TWS or Gateway connectivity remains localhost-only on known paper ports.
- Unknown or reconciliation-required state blocks connector use.
- Stale contract metadata blocks connector use and requires reconciliation.
- Risk, approval, OMS, contract, idempotency, and protection evidence are required before connector
  use.
- No order status or fill callback behavior is added.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.

## Current Limitations

- No authenticated IBKR session is created by this module.
- No SDK-backed paper transport is included by default.
- Accepted records are local adapter outcomes, not status or fill confirmations.
- No order status callbacks.
- No fill callbacks.
- No paper trading UI.
- In-memory idempotency state is process-local until a later persistence/reconciliation slice.
