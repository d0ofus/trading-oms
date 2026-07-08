# ExecPlan: Slice 043 order and position detail pages

## 1. Goal

Add read-only order and position detail sections that show OMS state, fill quantities, position
protection state, and linked audit records from existing backend read-model data.

## 2. Non-goals

- No broker order amendments.
- No live position reconciliation.
- No broker connectivity.
- No IBKR transport.
- No live trading.
- No new mutation endpoints.
- No secrets or credentials.

## 3. Safety constraints

- Detail pages are read-only and use existing read API records.
- The UI must not expose broker host, account ID, credential, route, submit-order, transmit-order,
  live-mode, script, import, or eval controls.
- Unknown, stale, or reconciliation-required states remain visible rather than hidden.
- Linked audit records must be redacted for secret-shaped text before rendering.

## 4. Current state

The frontend shell lists orders and positions as summary rows. It has read API types for orders,
positions, alerts, and audit events. The audit explorer already filters and redacts audit text.

## 5. Proposed design

Add a small frontend helper that builds order and position detail view models from the existing
read API snapshot. Render two read-only sections:

- order detail with OMS state, risk/approval references, cumulative filled/leaves quantities, and
  linked audit events;
- position detail with protection status, source, quantity/average price, and linked audit events.

## 6. Data model changes

None.

## 7. API changes

None.

## 8. Test plan

- Frontend helper tests for order audit linking, position audit linking, fill/protection summaries,
  and unsafe text redaction.
- App render tests for the order detail and position detail sections.
- Existing safety render tests continue blocking live/broker/secret affordances.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 043 commit to remove the helper, detail UI, docs, and tests.

## 11. Implementation steps

1. Add order/position detail helper tests.
2. Implement helper view-model builders and redaction.
3. Render read-only detail sections in the frontend shell.
4. Update docs and slice queue.
5. Run full verification and browser inspect `http://localhost:5173`.

## 12. Completion criteria

- UI shows order detail with OMS state, fills, risk/approval references, and linked audit records.
- UI shows position detail with protection state, quantity/average price, source, and linked audit
  records.
- Unsafe text is redacted before rendering.
- Verification passes.
- No broker connectivity, IBKR transport, live trading, secrets, or production rollout are added.

## 13. Risks and assumptions

- The first detail sections show the first available order and position from the read snapshot.
- Historical transition richness is limited to the currently available read models and linked audit
  events; richer persisted transition lists remain future work.
