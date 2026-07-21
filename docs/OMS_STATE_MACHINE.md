# OMS State Machine

Slice 010 introduces a deterministic backend OMS state machine.

It does not add live broker integration, IBKR connectivity, network access, real broker
credentials, fake broker execution orchestration, approval ticket orchestration, alerts, UI,
database migrations, position tracking, or live trading.

## Purpose

The OMS state machine represents order lifecycle transitions explicitly and auditably.

It is a local in-memory domain component. It validates transitions, applies accepted transitions,
and appends each newly accepted transition to the event journal.

It does not submit orders to any broker.

## States

- CREATED
- RISK_REJECTED
- PENDING_APPROVAL
- APPROVAL_REJECTED
- APPROVED
- SUBMITTED
- ACKNOWLEDGED
- PARTIALLY_FILLED
- FILLED
- CANCEL_REQUESTED
- CANCELLED
- REJECTED
- FAILED
- UNKNOWN_REQUIRES_RECONCILIATION

## Allowed Transitions

Initial transition:

- no prior state -> CREATED

Standard path:

- CREATED -> PENDING_APPROVAL
- PENDING_APPROVAL -> APPROVED
- APPROVED -> SUBMITTED
- SUBMITTED -> ACKNOWLEDGED
- ACKNOWLEDGED -> PARTIALLY_FILLED
- PARTIALLY_FILLED -> PARTIALLY_FILLED
- ACKNOWLEDGED or PARTIALLY_FILLED -> FILLED

Rejection and failure paths:

- CREATED -> RISK_REJECTED
- PENDING_APPROVAL -> APPROVAL_REJECTED
- SUBMITTED or ACKNOWLEDGED -> REJECTED
- SUBMITTED, ACKNOWLEDGED, PARTIALLY_FILLED, or CANCEL_REQUESTED -> FAILED

Cancel path:

- ACKNOWLEDGED or PARTIALLY_FILLED -> CANCEL_REQUESTED
- CANCEL_REQUESTED -> CANCELLED

Unknown broker state:

- SUBMITTED, ACKNOWLEDGED, PARTIALLY_FILLED, or CANCEL_REQUESTED ->
  UNKNOWN_REQUIRES_RECONCILIATION

Terminal states do not allow further transitions in this slice.

## Transition Event

Every newly accepted OMS transition is appended to the event journal with event type:

```text
oms.order.transitioned
```

The payload contains:

- transition ID;
- order ID;
- previous state;
- new state;
- occurred timestamp;
- reason;
- validated transition request snapshot;
- resulting order snapshot.

## Idempotency

`transition_id` is the idempotency key.

If the same transition ID is replayed with the same payload, the state machine returns the original
transition record and does not append another journal entry.

If the same transition ID is replayed with a different payload, the transition is rejected.

## Required Context

Every transition request includes:

- order ID and client order ID;
- symbol;
- side;
- quantity;
- risk intent;
- target state;
- occurred timestamp;
- reason;
- risk decision ID.

Moving to `APPROVED` or later states requires an approval reference.

Broker-observed states such as `ACKNOWLEDGED`, `FILLED`, `CANCELLED`, `REJECTED`, `FAILED`, and
`UNKNOWN_REQUIRES_RECONCILIATION` require a broker transition reference. In this slice that
reference is just an identifier supplied by the caller; the OMS does not call the fake broker.

## Safety Rule

Unknown state must block new risk-increasing trading decisions until reconciliation completes.

The state machine exposes:

```text
risk_increasing_decisions_blocked(order_id)
```

This returns `true` when the current order state is `UNKNOWN_REQUIRES_RECONCILIATION`.

## Guarantees

- OMS behavior is local and deterministic.
- Allowed transitions are explicit.
- Invalid transitions fail before changing state or writing to the journal.
- Every newly accepted transition is journaled.
- Duplicate transition IDs are idempotent only when the payload matches exactly.
- Unknown broker state is represented explicitly and blocks risk-increasing decisions.
- No network, live broker, account routing, credential, or live order-submission path is added.

## Current Integration And Limitations

- The standalone state machine remains in memory. Saved-workflow execution reconstructs and
  recomputes its exact persisted `CREATED` and `PENDING_APPROVAL` history, then captures the new
  `APPROVED`, `SUBMITTED`, `ACKNOWLEDGED`, and `FILLED` records in durable run evidence.
- Historical restoration never re-appends prior journal records and fails on malformed,
  out-of-order, conflicting, or snapshot-inconsistent history.
- The bounded saved-workflow path uses the local fake broker and simulated position domains only.
- No real broker reconciliation workflow exists.
- No partial-fill cancel accounting exists beyond explicit cumulative filled quantity validation.
- Callers must not put secrets in request, reason, reference, or snapshot fields.
