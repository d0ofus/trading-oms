# ExecPlan: Slice 013 UI shell

## 1. Goal

Create the first frontend UI shell for safely inspecting local trading workflow state, with clear
paper/simulation safety posture and static sections for the core operations areas.

## 2. Non-goals

- Live trading.
- Broker integration.
- Real broker credentials.
- Telegram tokens or alert delivery.
- Order submission, cancellation, approval, or execution controls.
- Backend API integration.
- Authentication or authorization.
- Database persistence.
- Strategy DSL editing.
- Visual workflow builder.

## 3. Safety constraints

- Do not enable live trading.
- Do not add any path that can transmit a live order.
- Do not add broker connectivity.
- Do not add Telegram tokens, broker credentials, account IDs, passwords, certificates, private
  keys, or secrets.
- Default posture must remain paper/simulation with live trading disabled.
- The UI must be read-only/static in this slice.
- No button, form, or control may imply live trading, broker connection, Telegram delivery, or
  order submission.

## 4. Current state

The frontend is a minimal Vite React app with `App.tsx`, `styles.css`, and a `safetyPosture`
constant. It currently renders a simple heading and safety definition list. The backend has local
domain modules through alerts, but no frontend operations shell yet.

## 5. Proposed design

Replace the minimal frontend screen with a restrained operations dashboard:

- persistent header showing app name and safety status;
- left navigation for signals, approval tickets, orders, positions, audit events, and alerts;
- summary panels backed by static/local demo data;
- detail sections for each core workflow area;
- safety banner showing paper mode, live trading disabled, no broker connectivity, manual approval,
  append-only journal, and no real alert delivery.

The shell will not call APIs or expose action buttons. Tests will render the app to static markup
and assert the expected shell sections and forbidden live-action affordances.

## 6. Data model changes

None.

Frontend-only TypeScript constants will hold local demo display data.

## 7. API changes

None.

No backend endpoints, frontend API clients, config keys, or external integrations are added.

## 8. Test plan

- Unit test safety posture remains paper mode with live trading disabled and no broker
  connectivity.
- Render test confirms the shell includes signals, approval tickets, orders, positions, audit
  events, and alerts.
- Render test confirms safety status labels are visible.
- Render test confirms forbidden live-action affordances are absent.
- Existing backend and frontend verification still pass.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

If a dev server is used for visual inspection:

```powershell
npm.cmd run dev -- --host 127.0.0.1 -w frontend
```

## 10. Rollback plan

Revert the slice branch changes to restore the previous minimal frontend and remove the Slice 013
docs/status updates. No persistent state or external integration is introduced.

## 11. Implementation steps

1. Add frontend render tests for the UI shell and safety constraints.
2. Implement the static read-only UI shell.
3. Update CSS for a dense operational dashboard layout.
4. Add UI shell documentation and README references.
5. Run verification and repair failures.
6. Run a local visual check if practical.
7. Mark Slice 013 ready for human review only after checks pass.

## 12. Completion criteria

- Frontend UI shell exists.
- Shell shows app mode, live trading disabled, and broker connectivity status.
- Shell includes sections for signals, approval tickets, orders, positions, audit events, and
  alerts.
- UI uses static/local demo data only.
- UI contains no enabled order submission, broker, live trading, Telegram, or credential controls.
- Tests cover shell rendering, safety posture, expected sections, and forbidden live-action
  affordances.
- Verification passes.
- No live broker connectivity or order submission path is added.
- No real Telegram tokens or secrets are introduced.

## 13. Risks and assumptions

- The UI currently uses local demo data, so it must not be mistaken for real trading state.
- Future slices must add backend read APIs separately and preserve read-only defaults until
  explicit approval workflow integration exists.
- Visual polish is intentionally scoped to a durable shell, not the full production UI.
