# Simulation Approval API

Slice 028 added generic simulation-only approval decision endpoints. The durable saved-workflow
approval candidate adds separate workflow/run-scoped endpoints for persisted approval-wait runs.

Approval remains non-executing. A later, separate Admin-only simulation command may consume a
committed approval; it does not change the approval endpoint's behavior and cannot contact a real
broker.

## Endpoints

Generic demo-ticket endpoints:

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

Persisted saved-workflow endpoints:

```text
POST /api/workflows/{workflow_id}/simulation-runs/{run_id}/approve
POST /api/workflows/{workflow_id}/simulation-runs/{run_id}/reject
```

The strict request adds `schema_version`, `expected_workflow_version`, and
`approval_ticket_id` to the decision fields shown above. Success returns the complete updated
saved-workflow run record. Approval produces `approved_not_executed`; rejection produces
`rejected`.

## Safety Guarantees

- Endpoints apply decisions to simulation approval tickets only.
- Approval does not submit, route, transmit, cancel, or modify any order.
- Approval does not advance OMS state or call the fake broker. Execution requires a distinct
  `/execute` request by an authenticated Admin after approval is durably committed.
- Persisted decisions require the dedicated `approve_simulation` permission, and the body actor
  must match the authenticated operator.
- The local UI requires an explicit switch from Admin to Approver review. It sends one consistent
  local-development identity/role across reads and mutations; it does not silently elevate an
  Admin decision request.
- Persisted decisions bind workflow, version, run, ticket, order, order intent, risk decision, and
  prior OMS evidence before reservation.
- Active emergency stop blocks approval but permits rejection as a risk-reducing action.
- Decision evidence is reserved before journal append and committed with the updated run and
  digest-bound manifest. Interrupted pending evidence fails closed.
- Decision IDs remain idempotent when payloads match.
- A ticket cannot be decided twice with different decision IDs.
- Unknown ticket IDs fail with HTTP 400.
- Responses do not expose broker route, account ID, credential, submit, or transmit fields.

## Current Limitations

- The generic demo-ticket service remains in-memory and separate from saved-workflow runs.
- The frontend approval inbox still calls the generic endpoints. The saved-run inspector uses only
  the workflow/run-scoped endpoints.
- Persisted approval is durable but intentionally does not execute. The separate saved-workflow
  execution endpoint consumes only exact committed approved evidence and preserves Admin/Approver
  role separation.
