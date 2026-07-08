# ExecPlan: Slice 021 backend read-only API endpoints

## 1. Goal

Expose the Slice 020 inspection read models through read-only FastAPI endpoints so the frontend can
consume safe backend-derived data in the next slices.

## 2. Non-goals

- No POST, PUT, PATCH, or DELETE endpoints.
- No approval actions.
- No simulation run creation.
- No persistence layer.
- No broker connectivity.
- No IBKR transport.
- No order submission.
- No live trading.

## 3. Safety constraints

- API routes must expose inspection data only.
- Endpoints must not return submit, approve, reject, cancel, connect, transmit, credential, token,
  password, account, host, port, route, socket, or secret affordances.
- Default posture remains paper/simulation with live trading disabled.
- Readiness responses must not authorize or enable live trading.
- No network client, socket, broker SDK, or transport behavior is introduced.

## 4. Current state

The backend has a minimal FastAPI app with `/healthz`. Slice 020 added immutable read models and a
safe `build_demo_operations_read_model()` assembler, but no HTTP routes expose those views.

## 5. Proposed design

Add read-only `GET /api/...` route handlers to the existing FastAPI app. Each handler builds the
current aggregate operations read model and returns the matching JSON-compatible section. Keep the
temporary data source local and static until later slices add persistence and orchestration.

## 6. Data model changes

None. This slice reuses the Slice 020 read-model dataclasses.

## 7. API changes

Add:

- `GET /api/safety`
- `GET /api/audit-events`
- `GET /api/signals`
- `GET /api/risk-decisions`
- `GET /api/approval-tickets`
- `GET /api/orders`
- `GET /api/positions`
- `GET /api/alerts`
- `GET /api/readiness`

## 8. Test plan

- API tests for all read-only endpoints and stable response shapes.
- API tests proving unsupported mutation methods return method-not-allowed.
- API tests proving responses exclude action, broker-network, credential, and secret affordance
  keys.
- Source inspection test proving the app does not add submit/order/broker transport behavior.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 021 commit to remove the API routes, tests, docs, and slice status updates.

## 11. Implementation steps

1. Add focused API endpoint tests.
2. Add the read-only FastAPI route handlers.
3. Document the read-only API behavior.
4. Update the slice queue with completion evidence.
5. Run verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- All nine read-only endpoints return the matching read-model section.
- Mutation HTTP methods are not implemented for these routes.
- Responses expose no unsafe action, broker, network, credential, or secret affordances.
- Verification passes.
- No live trading, broker transport, order submission, persistence, or mutation behavior is added.

## 13. Risks and assumptions

- Responses use safe static demo read-model data until later slices connect real read sources.
- Returning a pending approval ticket for inspection must not imply any approval action is available.
- Gate B remains required before any simulation mutation endpoint is implemented.
