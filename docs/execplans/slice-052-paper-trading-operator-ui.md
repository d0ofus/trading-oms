# ExecPlan: Slice 052 Paper Trading Operator UI

## 1. Goal

Add a paper-only operator visibility panel to the existing UI. The panel should show IBKR paper
mode, live trading disabled, adapter connection state, order status, callback status/fill state,
and reconciliation warnings using read-only backend data.

## 2. Non-goals

- Live trading.
- Live IBKR account mode.
- Real broker credentials, account identifiers, passwords, certificates, private keys, tokens, or
  secrets.
- Public broker host configuration.
- Credential inputs.
- Live trading controls.
- Broker-order transmit, submit-live, route-live, cancel, modify, or market-data subscription
  controls.
- IBKR SDK dependency.
- Network callback listener registration.
- New paper order submission, status callback, fill callback, contract lookup, or connectivity
  behavior.
- Production-readiness work.
- Production rollout.
- Slice 053 or later behavior.

## 3. Safety constraints

- UI must remain paper-only and inspection-focused.
- Live trading must remain disabled and visibly shown as disabled.
- IBKR account mode must remain paper-only.
- No UI, API, DSL, workflow, or config surface may expose credentials, account identifiers, public
  broker host fields, submit/transmit/route controls, live-mode controls, market-data subscription
  controls, cancel/modify controls, or broker SDK controls.
- Any paper transport status shown in the UI must be read-only and derived from safe read models.
- Reconciliation-required and unknown states must be clearly visible.
- The implementation must not bypass risk, approval, OMS, audit, reconciliation, idempotency, or
  protective-order requirements.
- Slice 053 Gate F production-readiness work must remain not started.

## 4. Current state

The repository has:

- safe configuration defaults with live trading disabled and IBKR account mode constrained to
  paper;
- read-only backend endpoints for safety, audit events, signals, risk decisions, approval tickets,
  orders, positions, alerts, and readiness;
- a connected React UI shell that renders backend-derived operational records;
- read-only order, position, protection, audit, approval, and simulation inspection panels;
- adapter-bound IBKR paper connectivity, contract lookup, order submission, status/fill callback,
  and chaos-test behavior;
- no paper trading operator UI, no public host controls, no credential inputs, and no live controls.

## 5. Proposed design

Add a small read-only paper operator view:

- Backend:
  - Add `PaperTradingOperatorReadModel` to `read_models.py`.
  - Add `paper_trading` to `OperationsReadModel`.
  - Populate demo/read API data from existing safe settings and representative paper adapter
    status/order/callback facts.
  - Add a read-only `GET /api/paper-trading` endpoint.
- Frontend:
  - Extend `readApiClient.ts` with `PaperTradingApiView` and `/api/paper-trading`.
  - Add a "Paper trading" section to `App.tsx` using the loaded snapshot.
  - Render paper-only labeling, connection state, order status, callback/fill state,
    reconciliation warning, and disabled live-trading posture.
  - Add tests proving the panel renders required visibility and does not expose unsafe controls.
- Docs:
  - Add a paper operator UI doc.
  - Mark Slice 052 ready for human review while leaving Slice 053 and later not started.

This design intentionally keeps all paper UI behavior read-only. No mutation endpoints or operator
actions are added.

## 6. Data model changes

New read model only:

- `PaperTradingOperatorReadModel`

No database tables or migrations.

## 7. API changes

New read-only endpoint:

```text
GET /api/paper-trading
```

No mutation endpoints, CLI commands, config keys, dependency files, workflow nodes, or action
controls are added.

## 8. Test plan

- Backend read-model tests for valid paper operator views, unsafe live/account values, and forbidden
  secret/live-routing fields.
- Backend read API tests for `GET /api/paper-trading` and read-only endpoint coverage.
- Frontend API client tests for `/api/paper-trading`.
- Frontend UI tests proving paper-only labeling, connection state, order status, callback/fill
  state, reconciliation warnings, disabled live-trading posture, and absence of unsafe controls.
- Run local UI and inspect `http://localhost:5173` if practical.
- Run full repository verification.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 052 branch. No external state, credentials, dependencies, broker sessions,
database migrations, or production resources are introduced.

## 11. Implementation steps

1. Add backend read-model and read API tests.
2. Implement the read-only paper operator model and endpoint.
3. Add frontend API client and UI tests.
4. Implement the read-only paper trading UI panel.
5. Update docs and `docs/SLICES.md`.
6. Run full verification.
7. Run and inspect the local UI if practical.
8. Self-review for trading safety, secret leakage, live-order prevention, public-port exposure,
   account ID leakage, unsafe controls, paper-only labeling, reconciliation visibility, and
   accidental Slice 053+ work.
9. Commit and push the branch when GitHub auth allows it; otherwise provide manual push and PR
   creation instructions.

## 12. Completion criteria

- Slice 052 ExecPlan exists.
- Paper-only operator UI visibility exists.
- UI shows paper-only labeling, live trading disabled, adapter connection state, order status,
  callback/fill state, and reconciliation warnings.
- Backend exposes only safe read-only paper operator data.
- Tests prove paper-only labeling, reconciliation warnings, order/status visibility, and absence of
  unsafe controls.
- No live trading, live account mode, credentials, account IDs, public broker host configuration,
  live trading controls, credential inputs, submit-live, transmit-live, route-live, cancel, modify,
  market-data subscription controls, production-readiness work, production rollout, or Slice 053+
  behavior is added.
- `docs/SLICES.md` and IBKR paper docs describe the Slice 052 behavior and hard stops.
- Verification passes.
- Slice 053 and later remain not started behind separate approval.

## 13. Risks and assumptions

- The view is based on safe read models and demo/read API records, not a live authenticated IBKR
  session.
- The panel could be mistaken for an execution console; labels and tests must keep it explicitly
  read-only and paper-only.
- Full production broker reconciliation remains future work and requires separate approval.
