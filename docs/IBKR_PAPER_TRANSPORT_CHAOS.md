# IBKR Paper Transport Chaos Tests

Slice 051 adds deterministic paper-transport chaos coverage for the IBKR paper adapter boundary.

This is test coverage only. It does not add live trading, live account mode, real broker
credentials, account identifiers, public IBKR exposure, market-data subscriptions, SDK or network
callback listener registration, paper trading UI, production-readiness work, production rollout, or
live order transmission.

## Scope

The chaos tests prove:

- disconnected state blocks paper submission before connector use;
- a fresh successful local paper connectivity observation is required before a previously
  disconnected adapter can accept paper submission;
- unknown or reconciliation-required state blocks order planning, contract lookup, paper submission,
  and callback acceptance;
- duplicate status callbacks and fill callbacks are idempotent only for matching canonical
  payloads;
- conflicting duplicate callbacks require reconciliation;
- stale callback data requires reconciliation and blocks later paper submission;
- out-of-order callback data requires reconciliation;
- adapter payloads remain free of secret-shaped, account-shaped, public-host, market-data,
  submit/transmit/route, live-mode, and broker-order-identifier fields;
- the adapter still exposes no SDK import, market-data subscription, network callback listener,
  paper trading UI, or live-order surface.

## Deterministic Boundaries

The tests use injected local connector callables and direct deterministic callback records. They do
not require TWS, IB Gateway, an IBKR SDK, a broker account, credentials, market-data access, or any
external broker process.

The tests do not claim real IBKR session reconciliation exists. The current repository still has no
authenticated IBKR session, no SDK-backed transport, no network callback listener registration, and
no persistent broker reconciliation store.

## Safety Guarantees

- Live trading remains disabled.
- IBKR account mode remains paper-only.
- TWS or Gateway connectivity remains localhost-only on known paper ports.
- Disconnected state blocks connector-backed paper submission.
- Unknown or reconciliation-required state blocks risk-increasing paper transport behavior.
- Unsafe callback observations move the adapter into `unknown_requires_reconciliation`.
- Reconnection requires an explicit safe local paper connectivity observation before paper
  submission can be accepted again.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.

## Current Limitations

- Chaos coverage is local and deterministic, not a production broker-reconciliation system.
- Callback idempotency and ordering state remains process-local until a later persistence or
  reconciliation slice.
- No paper trading operator UI is included in this slice.
