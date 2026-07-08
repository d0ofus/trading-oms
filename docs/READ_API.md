# Backend Read-Only API

Slice 021 exposes the backend read models through FastAPI inspection endpoints.

This slice does not add mutation endpoints, approval actions, simulation runs, persistence, broker
connectivity, IBKR transport, order submission, or live trading.

## Endpoints

The backend exposes:

- `GET /api/safety`
- `GET /api/audit-events`
- `GET /api/signals`
- `GET /api/risk-decisions`
- `GET /api/approval-tickets`
- `GET /api/orders`
- `GET /api/positions`
- `GET /api/alerts`
- `GET /api/readiness`

Each route returns the matching section from `build_demo_operations_read_model()`.

## Safety Guarantees

- Only `GET` handlers are implemented for these API views.
- `POST`, `PUT`, `PATCH`, and `DELETE` are not implemented for these routes.
- Responses expose inspection data only.
- Responses do not expose submit, approve, reject, cancel, connect, transmit, credential, token,
  password, account, host, port, route, socket, or secret affordance keys.
- Readiness responses keep `live_trading_enabled: false` and
  `live_trading_authorized: false`.
- No broker SDK, socket, network client, or transport behavior is introduced.

## Current Limitations

- The endpoints use safe static demo read-model data.
- No database-backed read model persistence exists yet.
- No frontend screen consumes these endpoints yet.
- Approval tickets are visible for inspection only; no approval action endpoint exists.
- Orders are visible for inspection only; no order submission, cancellation, or broker route exists.
