# ExecPlan: Slice 044 protection monitoring dashboard

## 1. Goal

Add a read-only protection monitoring dashboard that makes protected positions, protection
exceptions, missing-protection conditions, linked local alerts, and emergency-condition visibility
easy to inspect.

## 2. Non-goals

- No live broker reconciliation.
- No real alert delivery.
- No broker connectivity.
- No IBKR transport.
- No live trading.
- No new mutation endpoints.
- No secrets or credentials.

## 3. Safety constraints

- The dashboard is read-only and uses existing read API positions, alerts, and audit events.
- Missing expected protection must be surfaced as critical operator-visible state.
- Critical and emergency alerts must remain visible and linked to the related position when possible.
- The UI must not expose broker host, account ID, credential, route, submit-order, transmit-order,
  live-mode, script, import, eval, or alert-delivery controls.
- Secret-shaped text must be redacted before rendering.

## 4. Current state

Slice 043 added read-only order and position detail sections. The read API already exposes positions,
alerts, and audit events with enough metadata to classify protection state and link local alerts.

## 5. Proposed design

Add a frontend helper that builds a protection monitoring view from the existing read snapshot.
Render a dashboard section with summary counts, missing-protection conditions, exception/reference
rows, and critical/emergency local alert rows.

## 6. Data model changes

None.

## 7. API changes

None.

## 8. Test plan

- Frontend helper tests for protected, missing-protection, review-required, not-required, alert
  linkage, emergency-condition summary, and redaction.
- App render tests for the dashboard section and absence of unsafe controls.
- Existing full verification remains the release gate.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 044 commit to remove the dashboard helper, UI, tests, and docs.

## 11. Implementation steps

1. Add protection monitoring helper tests.
2. Implement the helper view model and redaction.
3. Render the read-only dashboard in the frontend shell.
4. Update docs and slice queue.
5. Run full verification and browser inspect `http://localhost:5173`.

## 12. Completion criteria

- UI shows protected/unprotected/review/exception counts.
- UI shows missing expected protection as critical.
- UI shows exception references for positions that do not have expected protection present.
- UI shows linked critical/emergency local alerts.
- Verification passes.
- No broker connectivity, IBKR transport, live trading, secrets, real alert delivery, or production
  rollout are added.

## 13. Risks and assumptions

- Exception references are derived from current read-model state until richer explicit exception
  records exist.
- Alert linkage uses `source_event_reference` matching the position ID when available.
