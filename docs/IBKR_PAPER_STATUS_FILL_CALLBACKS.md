# IBKR Paper Status And Fill Callbacks

Slice 050 adds deterministic paper order status and fill callback records behind the existing
IBKR paper adapter boundary.

This does not add live trading, live account mode, real broker credentials, account identifiers,
public IBKR exposure, market-data subscriptions, SDK or network callback listener registration,
paper trading UI, production-readiness work, production rollout, or live order transmission.

## Scope

The adapter can:

- record a paper order status callback observation;
- record a paper fill callback observation;
- require an accepted Slice 049 paper order submission record;
- require matching client order ID and local acknowledgement/correlation reference;
- enforce callback ID idempotency;
- reject conflicting duplicate callback IDs;
- reject mismatched, stale, out-of-order, disconnected, reconciliation-required, invalid, or
  unknown callback data;
- map accepted callback observations to OMS-compatible target states;
- mark unsafe callback outcomes as reconciliation-required;
- journal callback receipts, callback outcomes, duplicate observations, rejected observations, and
  reconciliation-required state observations.

The adapter cannot:

- authenticate by itself;
- store account identifiers;
- use credentials, tokens, passwords, certificates, private keys, or secrets;
- import or use an IBKR SDK directly;
- open a network callback listener;
- subscribe to market data;
- request account state;
- route live orders;
- expose public IBKR ports;
- enable live trading.

## Required Evidence

`IbkrPaperAdapter.record_paper_order_status_callback` requires:

- an `IbkrPaperOrderStatusCallback`;
- an existing accepted `IbkrPaperOrderSubmissionRecord`;
- paper-only localhost-only adapter configuration;
- connected or reconciliation-safe adapter state;
- matching `client_order_id`;
- matching local acknowledgement/correlation reference;
- fresh and in-order observation timestamps.

`IbkrPaperAdapter.record_paper_fill_callback` requires the same evidence, plus positive fill
quantity and cumulative quantity checks that cannot move past the submitted order quantity.

## Journal Events

Status callback handling appends:

```text
ibkr.paper.order_status_callback.received
ibkr.paper.order_status_callback.recorded
```

Fill callback handling appends:

```text
ibkr.paper.fill_callback.received
ibkr.paper.fill_callback.recorded
```

Unsafe callback data can also append:

```text
ibkr.paper.connection_state.recorded
```

when the adapter must move into `unknown_requires_reconciliation`.

## OMS Mapping

Accepted status callbacks map to OMS-compatible target states:

- `acknowledged` maps to `ACKNOWLEDGED`;
- `partially_filled` maps to `PARTIALLY_FILLED`;
- `filled` maps to `FILLED`;
- `rejected` maps to `REJECTED`.

Accepted fill callbacks map cumulative fill quantity to either `PARTIALLY_FILLED` or `FILLED`.

Invalid mappings are journaled and require reconciliation. Examples include a filled status whose
cumulative quantity does not equal the submitted quantity, a partial fill with zero cumulative
quantity, cumulative fill quantity moving backward, or cumulative fill quantity exceeding the
submitted order quantity.

## Idempotency

Callback IDs are idempotent per callback type.

- Matching duplicate callback payloads produce duplicate outcomes without changing adapter state.
- Reused callback IDs with different canonical payloads produce `blocked_duplicate_conflict` and
  require reconciliation.

## Safety Guarantees

- Live trading remains disabled.
- IBKR account mode remains paper-only.
- TWS or Gateway connectivity remains localhost-only on known paper ports.
- Unknown or reconciliation-required state blocks callback acceptance.
- Accepted Slice 049 submission correlation is required before callback acceptance.
- Mismatched, stale, out-of-order, invalid, conflicting, disconnected, or reconciliation-required
  callback data is journaled and requires reconciliation.
- Callback payloads intentionally exclude host, port, account, credential, route, submit, transmit,
  broker order identifier, market-data payload, token, password, certificate, private key, and
  secret fields.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.

## Current Limitations

- No authenticated IBKR session is created by this module.
- No SDK-backed paper transport is included by default.
- No SDK/network callback listener registration.
- No order cancellation or order modification callbacks.
- No paper trading UI.
- In-memory callback idempotency and ordering state is process-local until a later persistence or
  reconciliation slice.
