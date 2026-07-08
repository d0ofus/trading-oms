# ExecPlan: Slice 042 approval inbox UI

## 1. Goal

Create a simulation-only operator approval inbox with pending ticket rows, approve/reject forms,
actor and reason capture, and idempotency feedback.

## 2. Non-goals

- No broker transmission.
- No live trading.
- No IBKR transport.
- No OMS advancement or fake broker execution from the UI.
- No production rollout.
- No secrets or credentials.

## 3. Safety constraints

- Approval actions call only the existing simulation approval endpoints.
- Approval forms must not expose broker host, account ID, credential, route, submit-order,
  transmit-order, live-mode, script, import, or eval controls.
- Approval does not submit, route, transmit, cancel, or modify a broker order.
- Decision requests must include actor, reason, decision reference, and deterministic decision ID.
- Idempotency feedback must be visible.

## 4. Current state

Backend simulation approval endpoints already support approve/reject decisions for simulation
tickets and are idempotent for repeated matching payloads. The frontend only lists approval tickets
as read-only records.

## 5. Proposed design

Add a frontend approval inbox section that lists pending read-model tickets. Each ticket renders a
simulation-only approval form with actor and reason fields plus approve/reject buttons. Add a small
API client for the existing simulation approval endpoints and a helper that builds stable decision
request payloads from ticket/action/form state.

## 6. Data model changes

No backend data model changes. New frontend request/response types mirror the existing simulation
approval API.

## 7. API changes

No new HTTP endpoints.

Frontend client methods:

- `approveTicket(ticketId, request)`
- `rejectTicket(ticketId, request)`

## 8. Test plan

- Frontend unit tests for deterministic decision payload construction.
- Frontend client tests proving only simulation approval/reject endpoints are called.
- App render tests for pending tickets, actor/reason capture, approve/reject controls, and
  idempotency feedback.
- Existing safety tests updated to allow simulation approval forms while still blocking live/broker
  order controls.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 042 commit to remove the approval inbox UI, frontend client/helper, tests, and
docs.

## 11. Implementation steps

1. Add approval inbox helper/client tests.
2. Implement frontend helper and API client.
3. Render approval inbox forms in the app shell.
4. Update docs and slice status.
5. Run verification and browser inspect `http://localhost:5173`.

## 12. Completion criteria

- UI lists pending simulation approval tickets.
- UI captures actor and reason.
- UI exposes approve/reject controls labeled simulation-only.
- UI shows idempotency feedback.
- Client posts only to simulation approval endpoints.
- Verification passes.

## 13. Risks and assumptions

- The UI uses read-model tickets for display; backend mutation responses are local simulation
  approval decision records.
- Runtime data refresh after a decision remains a later slice.
