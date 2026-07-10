# Backend Inspection API

Slice 021 exposes the backend read models through FastAPI inspection endpoints.

Slice 021 did not add mutation endpoints, approval actions, simulation runs, persistence, broker
connectivity, IBKR transport, order submission, or live trading. Slice 028 later added separate
simulation-only approval decision endpoints documented in `docs/SIMULATION_APPROVAL_API.md`.

## Endpoints

The backend exposes:

- `GET /api/emergency-stop`
- `GET /api/safety`
- `GET /api/audit-events`
- `GET /api/signals`
- `GET /api/risk-decisions`
- `GET /api/approval-tickets`
- `GET /api/orders`
- `GET /api/positions`
- `GET /api/alerts`
- `GET /api/readiness`
- `GET /api/paper-trading`
- `GET /api/audit-export-bundle`

The section routes from `/api/emergency-stop` through `/api/paper-trading` return the matching
section from `build_demo_operations_read_model()` or current local in-process state.

`GET /api/audit-export-bundle` returns a deterministic local review bundle built from the current
read-model snapshot, workflow definitions, workflow simulation run records, and journal records. It
recursively scans the bundle and fails closed if secret-shaped or live-routing-shaped content is
present.

`GET /api/audit-events` includes optional audit filter metadata fields:

- `run_id`
- `symbol`
- `order_id`
- `ticket_id`
- `severity`

## Safety Guarantees

- Only `GET` handlers are implemented for these API views.
- `POST`, `PUT`, `PATCH`, and `DELETE` are not implemented for these routes.
- Responses expose inspection data only.
- `GET /api/emergency-stop` exposes local emergency stop state only; admin-only activation and
  deactivation endpoints are documented in `docs/EMERGENCY_STOP.md`.
- `GET /api/paper-trading` exposes paper-only operator visibility only, with no broker controls.
- Responses do not expose submit, approve, reject, cancel, connect, transmit, credential, token,
  password, account, host, port, route, socket, or secret affordance keys.
- Readiness responses keep `live_trading_enabled: false` and
  `live_trading_authorized: false`.
- Audit export responses include local JSON review data only and do not upload, deliver, submit,
  transmit, route, or connect anything.
- No broker SDK, socket, network client, or transport behavior is introduced.

## Current Limitations

- The endpoints use safe static demo read-model data.
- SQLite persistence exists as a local foundation, but these endpoints still use safe static demo
  read-model data.
- Frontend screens consume these endpoints for read-only inspection and safe fallback rendering.
- Approval ticket read models are visible for inspection; simulation-only approval decision
  endpoints are documented separately in `docs/SIMULATION_APPROVAL_API.md`.
- Orders are visible for inspection only; no order submission, cancellation, or broker route exists.
- The audit export endpoint uses current in-process stores; SQLite-backed export orchestration is
  future work.
