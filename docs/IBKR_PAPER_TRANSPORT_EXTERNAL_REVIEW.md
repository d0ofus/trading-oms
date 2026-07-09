# IBKR Paper Transport External Review Checklist

Slice 046 defines the review evidence required before any IBKR paper transport implementation can
begin. This checklist is not approval to implement transport, connect to TWS or IB Gateway, place
orders, add credentials, start production rollout, or enable live trading.

## Gate

- Gate D covers planning only.
- Gate E is required before any connectivity probe, SDK integration, contract lookup, paper order
  transport, callback handling, or paper trading UI.
- Live trading remains disabled and out of scope.
- Production rollout remains out of scope.

## Reviewer Evidence

An external reviewer must confirm all items before Gate E implementation can be considered:

- The proposed work is paper-only and cannot select live account mode.
- No real broker credentials, account identifiers, tokens, passwords, certificates, private keys, or
  other secrets are required in repository files, logs, docs, screenshots, tests, or alert payloads.
- TWS or IB Gateway API access is local-only and is not exposed to the public internet.
- The existing safe configuration rules remain the source of truth for paper mode, live trading
  disabled, local-only connectivity, and known paper ports.
- Broker-specific code remains isolated behind the IBKR adapter boundary.
- Core OMS, risk, approval, workflow, and strategy modules do not import IBKR SDK types directly.
- No workflow, UI, API, DSL, or config surface introduces broker account fields, credential fields,
  arbitrary host fields, live-mode controls, or live routing controls.
- Any future paper order path must require a passed risk decision, explicit human approval, OMS
  readiness, reconciliation-safe state, and journaled state transitions.
- Unknown broker state, disconnects, stale market data, duplicate callbacks, or reconciliation gaps
  must block new risk-increasing work.
- Every connection event, reconnect event, reconciliation event, order submission attempt, status
  update, fill, cancel, reject, and emergency condition must be journaled.
- Any risk-increasing paper entry must include an expected protective-order plan or an explicitly
  approved exception before transport.
- A position without expected protection must raise a critical alert.
- Audit export and log paths must continue to reject secret-shaped and live-routing-shaped content.

## Required Design Review Topics

The Gate E implementation plan must address these topics before code starts:

- SDK choice and adapter-boundary containment.
- Local TWS/Gateway connection lifecycle.
- Paper-only configuration enforcement.
- Readiness checks before any paper order can be considered.
- Contract lookup validation and unsupported-instrument handling.
- Order ID and idempotency strategy.
- Duplicate status and fill callback handling.
- Disconnect, reconnect, and reconciliation flow.
- Unknown-state blocking behavior.
- Market-data freshness requirements.
- Emergency-stop interaction.
- Audit event schema additions.
- Operator-visible paper-only labeling.
- Rollback and disablement path.

## Required Test Evidence

Gate E must include tests for:

- paper-only mode enforcement;
- live mode rejection;
- local-only connectivity validation;
- absence of secrets and account identifiers;
- rejection of broker credential, live-mode, transmit, submit, and route affordances;
- stale data blocking;
- unknown broker state blocking;
- duplicate order and duplicate callback handling;
- disconnect and reconnect behavior;
- reconciliation-required state;
- risk-before-approval-before-OMS-before-paper-transport ordering;
- protective-order plan or approved exception requirements;
- audit journal coverage for every state transition.

## Explicit Non-Approvals

This checklist does not approve:

- IBKR SDK installation;
- connectivity probes;
- market-data subscriptions;
- contract lookup;
- paper order submission;
- order status callbacks;
- fill callbacks;
- real credentials;
- account identifiers;
- production deployment;
- production rollout;
- live trading;
- live-readiness implementation.

