# Simulation Approval API

Slice 028 adds simulation-only approval decision endpoints.

This slice does not add broker order transmission, real account actions, OMS advancement after
approval, fake broker execution, IBKR transport, order submission, or live trading.

## Endpoints

```text
POST /api/approval-tickets/{ticket_id}/approve
POST /api/approval-tickets/{ticket_id}/reject
```

Request body:

```json
{
  "decision_id": "approval-decision-001",
  "decided_at": "2026-07-08T13:46:00Z",
  "actor": "human-operator-001",
  "decision_reference": "manual-simulation-approval-001",
  "reason": "operator_reviewed_simulation_ticket"
}
```

The response is the approval-ticket decision record from the local approval domain model.

## Safety Guarantees

- Endpoints apply decisions to simulation approval tickets only.
- Approval does not submit, route, transmit, cancel, or modify any order.
- Approval does not advance OMS state in this slice.
- Approval does not call the fake broker in this slice.
- Decision IDs remain idempotent when payloads match.
- A ticket cannot be decided twice with different decision IDs.
- Unknown ticket IDs fail with HTTP 400.
- Responses do not expose broker route, account ID, credential, submit, or transmit fields.

## Current Limitations

- The service is in-memory and seeded with the demo pending ticket.
- Decisions are not persisted beyond the local temporary JSONL journal.
- The frontend does not yet provide an approval inbox.
- Approved simulation orders are not executed until a later Gate B slice.
