# Approval Inbox

Slice 042 adds a simulation-only approval inbox to the frontend operations shell.

It does not add broker transmission, IBKR transport, live trading, OMS advancement, fake broker
execution, production rollout, credentials, or secrets.

## UI Scope

The inbox shows pending simulation approval tickets from the read API and renders a review form for
each pending ticket.

Each form captures:

- actor;
- reason.

Each form exposes simulation-only controls:

- Approve simulation;
- Reject simulation.

These controls call the existing simulation approval endpoints. They do not submit, route, transmit,
cancel, or modify broker orders.

## Idempotency

Decision request IDs are deterministic for each ticket and action:

```text
<ticket_id>-approve-decision
<ticket_id>-reject-decision
```

The UI shows the idempotency key so an operator can understand repeated matching requests. Backend
decision handling remains idempotent for repeated matching payloads.

## Current Limitations

- The inbox uses current read-model tickets for display.
- Runtime data refresh after a decision remains future work.
- Approval responses are local simulation approval records only.
