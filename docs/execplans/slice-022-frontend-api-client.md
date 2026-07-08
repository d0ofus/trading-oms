# ExecPlan: Slice 022 frontend API client and safe loading states

## 1. Goal

Add a typed frontend client for the read-only backend API endpoints, plus safe loading and backend
error states that keep the UI in a non-actionable paper/simulation posture.

## 2. Non-goals

- No main UI shell wiring yet.
- No mutation calls.
- No approval action UI.
- No order submission UI.
- No broker connection UI.
- No credential fields.
- No live trading.

## 3. Safety constraints

- The client must use `GET` requests only.
- The client must not expose submit, approve, reject, cancel, connect, transmit, credential, token,
  password, account, host, port, route, socket, or secret affordance fields.
- Backend-unavailable fallback must show live trading disabled and no broker connectivity.
- Error messages must not echo arbitrary secret-bearing exception text.
- No broker SDK, socket, network transport beyond browser `fetch`, or live-action behavior is added.

## 4. Current state

The frontend renders static local data. Slice 021 added read-only backend endpoints but the frontend
has no client for them and no typed backend-unavailable state.

## 5. Proposed design

Add a `readApiClient` module with TypeScript types matching the backend read API JSON shapes,
injectable `fetch` support for tests, endpoint-specific `GET` methods, an aggregate snapshot loader,
and explicit `loading`, `loaded`, and `error` states. The error state uses a safe local fallback
snapshot rather than backend data or exception text.

## 6. Data model changes

No database or backend model changes. New frontend TypeScript types only.

## 7. API changes

No backend API changes. Add frontend client functions for:

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

- Frontend unit tests proving every client method uses `GET` and the expected endpoint.
- Frontend unit tests proving aggregate load succeeds with typed data.
- Frontend unit tests proving failed backend calls return a safe fallback snapshot.
- Frontend unit tests proving client state exposes no forbidden action, broker, credential, or
  secret-shaped keys.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 022 commit to remove the frontend API client, tests, docs, and slice status
updates.

## 11. Implementation steps

1. Add focused frontend API-client tests.
2. Implement the typed read API client and safe states.
3. Document the frontend client boundary.
4. Update the slice queue with completion evidence.
5. Run verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Typed client functions exist for all nine read-only endpoints.
- Aggregate loader returns explicit loading/loaded/error states.
- Backend failure falls back to a safe no-live-trading posture.
- Tests prove no mutation calls or unsafe affordance keys are exposed.
- Verification passes.

## 13. Risks and assumptions

- Main UI wiring remains Slice 023.
- The fallback state is intentionally conservative and local-only.
- Gate B remains required before any simulation mutation endpoint is implemented.
