# Simulation Execution

Slice 029 adds approved-order execution through local OMS and the simulation-only fake broker.

This slice does not add IBKR transport, paper account orders, live broker connectivity, real account
actions, HTTP order-execution endpoints, order submission to external systems, or live trading.

## Flow

The execution path starts only from a local order already in `PENDING_APPROVAL`:

```text
approval.ticket.decided: approved
-> OMS APPROVED
-> OMS SUBMITTED
-> fake broker acknowledgement/reject
-> OMS ACKNOWLEDGED or REJECTED
-> optional fake broker fill/cancel
-> OMS FILLED or CANCELLED
```

## Supported Fake Broker Outcomes

`ApprovedOrderExecutionRequest.broker_outcome` supports:

- `acknowledge_only`
- `fill`
- `cancel`
- `reject`

All outcomes are local fake broker behavior. No network transport exists.

## Journal Coverage

The execution path journals:

- approval decisions;
- OMS approval/submission/outcome transitions;
- fake broker acknowledgement, fill, cancel, and reject transitions.

## Safety Guarantees

- Execution requires existing risk-passed pending-approval simulation context.
- Approval is local and explicit.
- Fake broker requests are built from stored non-routable proposal context and passed risk context.
- Duplicate execution IDs are idempotent when payloads match.
- Terminal order states block new execution attempts.
- No IBKR SDK, socket, network client, external broker route, account ID, credential, submit, or
  transmit behavior is added.

## Current Limitations

- Execution state is in-memory only.
- No HTTP endpoint starts execution.
- No position tracking exists yet.
- Protection monitoring and alerts are deferred to Slice 030.
