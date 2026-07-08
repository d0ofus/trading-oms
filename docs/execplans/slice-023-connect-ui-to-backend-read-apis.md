# ExecPlan: Slice 023 connect UI shell to backend read APIs

## 1. Goal

Replace the static frontend operations records with backend-derived read API data while preserving
the existing read-only safety posture and local replay-only visual builder.

## 2. Non-goals

- No simulation run creation.
- No approval actions.
- No broker actions.
- No workflow persistence.
- No order submission or cancellation controls.
- No live trading.

## 3. Safety constraints

- The UI must consume read API data through `GET`-only client calls.
- The visual builder remains local and replay-only.
- The UI must not render submit, approve, reject, cancel, connect, transmit, credential, token,
  password, account, host, port, route, socket, or secret affordances.
- Backend-unavailable state must preserve paper mode, live trading disabled, and no broker
  connectivity.
- No mutation calls, broker SDK, socket code, or live-action behavior is added.

## 4. Current state

The frontend shell renders static local workflow rows. Slice 022 added a typed read API client and
safe loading/error states, but `App` does not consume them yet.

## 5. Proposed design

Update `App` to load the aggregate read API snapshot on mount, render safety posture from the
current read state, derive summary panels and workflow rows from backend data, and show clear
loading/error/empty states without adding action controls. Keep the existing visual builder state
and DSL preview local.

## 6. Data model changes

No backend or persistence model changes. Frontend display mapping only.

## 7. API changes

No new backend API endpoints. The UI consumes the existing read-only endpoints from Slice 021 via
the Slice 022 client.

## 8. Test plan

- Frontend tests rendering loaded backend-derived data through an injected initial read state.
- Frontend tests for backend-unavailable fallback state.
- Frontend tests proving visual builder controls remain local/replay-only.
- Frontend tests proving no live-action or credential affordances are rendered.
- Full verification and browser check at `http://localhost:5173`.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 023 commit to restore the static UI shell and remove the UI API wiring docs/status
updates.

## 11. Implementation steps

1. Update frontend tests around loaded/error read API states.
2. Wire `App` to the read API client and derive visible rows from snapshots.
3. Update UI shell documentation and slice queue.
4. Run verification.
5. Start local backend/frontend servers and browser-check `http://localhost:5173`.
6. Self-review safety boundaries.

## 12. Completion criteria

- UI shell renders backend-derived safety, signals, approvals, orders, positions, audit events, and
  alerts when read data is available.
- Backend-unavailable state shows a safe fallback and no live-action affordances.
- Visual builder remains local and replay-only.
- Verification passes.
- Browser check confirms the local UI loads at `http://localhost:5173`.

## 13. Risks and assumptions

- The backend read API still serves safe demo read data until later persistence/orchestration work.
- Frontend wiring does not imply approval for Gate B simulation mutation endpoints.
- Browser check may be blocked if local server startup or browser automation is unavailable; any
  blocker must be reported with exact command output.
