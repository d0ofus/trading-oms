# ExecPlan: Slice 041 audit explorer UI

## 1. Goal

Add a read-only audit explorer UI that lets an operator filter and inspect audit events by common
simulation and safety fields.

## 2. Non-goals

- No audit deletion or mutation.
- No mutable event history.
- No broker transport.
- No live trading.
- No production rollout.
- No secret rendering.

## 3. Safety constraints

- Audit explorer controls are filters only; they must not submit, approve, transmit, route, or
  execute orders.
- Audit data remains read-only and backend-derived or safe fallback data.
- Secret-shaped audit text must be redacted before display.
- No broker host, account ID, credential, route, submit, transmit, script, eval, import, or live-mode
  controls may be added.

## 4. Current state

The UI has an `Audit events` read-only list, but no filters or detail view. Backend audit read models
only expose sequence, event type, timestamp, and summary.

## 5. Proposed design

Extend the audit read model with optional local index fields: run ID, symbol, order ID, ticket ID,
and severity. Add frontend helper functions for filtering and redacting unsafe audit text. Add a
new `Audit explorer` section with filter inputs and a detail panel that displays the first matching
event.

## 6. Data model changes

`AuditEventReadModel` and `AuditEventApiView` gain optional fields:

- `run_id`
- `symbol`
- `order_id`
- `ticket_id`
- `severity`

## 7. API changes

Existing `GET /api/audit-events` responses include the optional filter fields. No new endpoint or
mutation route is added.

## 8. Test plan

- Backend tests for the extended audit read-model shape.
- Frontend unit tests for filtering by run, event type, symbol, order ID, ticket ID, severity, and
  timestamp.
- Frontend unit tests for secret-shaped audit text redaction.
- App rendering tests for the audit explorer controls and detail view.
- Existing safety tests must continue proving no live-action controls render.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 041 commit to remove the audit explorer UI, helper functions, read-model optional
fields, tests, and docs.

## 11. Implementation steps

1. Extend audit read-model tests and frontend helper tests.
2. Add optional audit index fields to backend/frontend types.
3. Render read-only audit explorer filters and detail panel.
4. Add docs and update slice status.
5. Run full verification and browser inspect `http://localhost:5173`.

## 12. Completion criteria

- UI shows filters for run, event type, symbol, order ID, ticket ID, severity, and timestamp.
- UI shows an audit event detail panel.
- Filtering helper covers each required field.
- Secret-shaped audit text is redacted before display.
- No execution, broker, credential, route, submit, transmit, or live controls are added.
- Verification passes.

## 13. Risks and assumptions

- This slice uses current read API data and optional index fields. Slice 040's SQLite journal index
  can feed these fields in a later backend wiring slice.
