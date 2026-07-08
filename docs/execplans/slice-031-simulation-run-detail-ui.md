# ExecPlan: Slice 031 simulation run detail UI

## 1. Goal

Show an end-to-end simulation run detail view in the frontend UI.

## 2. Non-goals

- No visual workflow editing.
- No workflow persistence.
- No IBKR transport.
- No broker connectivity.
- No execution controls.
- No live trading.

## 3. Safety constraints

- The UI is read-only.
- The UI must not render submit, transmit, broker connect, credential, Telegram delivery, or live
  trading controls.
- The detail view may show simulation/fake broker records but cannot trigger execution.
- No secrets or credential-shaped values may be rendered.

## 4. Current state

The frontend shell shows read-model sections for signals, tickets, orders, positions, audit events,
and alerts. It does not yet show a single end-to-end simulation run timeline.

## 5. Proposed design

Add a `Simulation run detail` section to the existing shell navigation and console. The section
shows a compact timeline and grouped read-only records for signal, risk, approval, OMS, fake broker,
fill, position, alert, and audit details. Keep styling aligned with the existing dashboard cards and
status pills.

## 6. Data model changes

None.

## 7. API changes

None. No HTTP, CLI, config, broker, or persistence API is added in this slice.

## 8. Test plan

- Frontend render test for the new section.
- Frontend render test for timeline and required detail groups.
- Existing safety test proving no live-action affordances, forms, or buttons are rendered.
- Browser verification at `http://localhost:5173`.

## 9. Verification commands

```powershell
npm run test --prefix frontend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 031 commit to remove the frontend run detail UI, tests, docs, and slice status
updates.

## 11. Implementation steps

1. Add frontend tests for the run detail UI.
2. Add read-only run detail markup.
3. Add responsive styles.
4. Update docs and slice queue.
5. Run focused frontend tests and full verification.
6. Browser-check the local UI.
7. Self-review safety boundaries.

## 12. Completion criteria

- UI shows a simulation run timeline.
- UI shows signal, risk, approval, OMS, fake broker, fill, position, alert, and audit sections.
- UI remains read-only with no execution controls.
- Verification passes.
- Browser check at `http://localhost:5173` passes.
- No visual workflow editing, IBKR transport, broker connectivity, credentials, or live-trading
  path is added.

## 13. Risks and assumptions

- This first UI is a read-only static detail view until later persistence/run-detail APIs exist.
- Gate C visual workflow work remains unstarted.
