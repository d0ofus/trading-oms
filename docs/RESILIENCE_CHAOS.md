# Resilience and Chaos Tests

Slice 017 adds the first deterministic local resilience and chaos-test foundation.

It does not add live trading, real broker credentials, account IDs, certificates, private keys,
passwords, tokens, IBKR SDK dependencies, socket or network transport, TWS/Gateway connectivity,
market-data subscriptions, production reconciliation, order submission, order placement, order
transmission, order cancellation, order modification, or UI changes.

## Purpose

The resilience module creates local audit records for disconnect, reconnect, unknown broker state,
and reconciliation behavior. It also provides a deterministic chaos scenario that proves the
existing risk engine blocks stale market data and unknown broker state during reconnect recovery.

## Event Types

The local resilience event types are:

```text
resilience.connection.disconnected
resilience.connection.reconnected
resilience.broker_state.unknown
resilience.reconciliation.started
resilience.reconciliation.completed
resilience.chaos.scenario.completed
```

Disconnect, reconnect, unknown-state, and reconciliation-start events set:

```text
requires_reconciliation: true
blocks_risk_increasing: true
```

Reconciliation completion clears those flags only when the provided local snapshot says broker
state is known and no operator review is required.

## Duplicate Handling

`ResilienceMonitor` tracks resilience event IDs. A repeated event ID is idempotently replayed only
when the payload matches exactly. A repeated event ID with different payload content is rejected and
does not append another journal record.

## Chaos Scenario

`run_reconnect_reconciliation_chaos_scenario` runs a fixed local sequence:

1. record disconnect;
2. record reconnect;
3. record unknown broker state;
4. start reconciliation;
5. evaluate a stale-market-data risk request;
6. evaluate an unknown-broker-state risk request;
7. complete reconciliation from a known local snapshot;
8. journal the scenario summary.

The scenario uses the existing risk engine rather than adding a parallel risk path.

## Guarantees

- No IBKR SDK dependency.
- No socket or network transport.
- No TWS or IB Gateway connection attempt.
- No live broker connectivity.
- No order submission, placement, transmission, cancellation, or modification path.
- No real account IDs, credentials, certificates, passwords, private keys, tokens, or secrets.
- Reconnect leaves risk-increasing work blocked until reconciliation completes.
- Stale market data remains blocked by the risk engine.
- Unknown broker state remains blocked for risk-increasing decisions.
- Resilience and scenario records are appended to the event journal.

## Current Limitations

- Reconciliation snapshots are local summaries only.
- No comparison against a real broker, TWS, IB Gateway, or external account state exists.
- No position protection reconciliation exists yet.
- No alert escalation is triggered by these events yet.
- No UI inspection view is wired to these events yet.
- Real paper-connectivity reconciliation still requires a separately approved future slice.
