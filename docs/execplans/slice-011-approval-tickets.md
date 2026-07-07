# ExecPlan: Slice 011 approval tickets

## 1. Goal

Add a deterministic backend approval-ticket domain component that creates pending human approval
tickets from passed risk decisions and OMS pending-approval context, records explicit human or
system decisions, applies idempotency, and journals every ticket creation and decision.

## 2. Non-goals

- Live broker integration.
- IBKR connectivity.
- Network access.
- Real broker credentials, account IDs, tokens, certificates, or secrets.
- Automatic execution after approval.
- UI approval screens.
- Alert delivery or Telegram integration.
- Database migrations.
- Position tracking.
- Full OMS or fake broker orchestration.

## 3. Safety constraints

- No live trading.
- No live broker order-transmission path.
- No secrets.
- Default behavior remains paper/simulation.
- Tickets can be created only from passed risk-decision context.
- Tickets require OMS pending-approval context.
- Every ticket creation and decision must be journaled.
- Approval must be explicit and attributed to a non-empty actor and reference.
- Approved tickets must not submit orders, call brokers, or advance OMS state.
- Duplicate ticket IDs and decision IDs must be idempotent only when payloads match.

## 4. Current state

- `event_journal.py` provides append-only JSONL records.
- `risk_engine.py` creates passed or blocked risk decisions and journals them.
- `oms_state_machine.py` represents order lifecycle states and requires an approval reference before
  approved/submitted states.
- `fake_broker.py` is a simulation-only adapter and does not orchestrate OMS or approval flow.
- Slice 011 is approved in `docs/SLICES.md`.

## 5. Proposed design

Add `backend/src/trading_oms_backend/approval_tickets.py` with:

- explicit approval ticket statuses;
- `ApprovalTicketCreateRequest` for creating pending tickets;
- `ApprovalDecisionRequest` for applying approve/reject/expire/cancel decisions;
- `ApprovalTicket` snapshot records;
- `ApprovalDecisionRecord` journal payload records;
- `ApprovalTicketBook` in-memory component that creates tickets and applies decisions;
- idempotency tracking by ticket ID for creates and decision ID for decisions;
- event journal append for every newly accepted ticket creation and decision.

The component will not call the OMS, fake broker, external network, or any live order-submission
path.

## 6. Data model changes

No database changes.

New in-memory and journal payload shapes:

- `ApprovalTicket`: ticket ID, order IDs, symbol, side, quantity, risk intent, risk decision ID,
  OMS transition reference, status, created timestamp, expiry timestamp, optional decided timestamp,
  optional decision actor/reference/reason, and source request snapshot.
- `ApprovalDecisionRecord`: decision ID, ticket ID, previous status, new status, decided timestamp,
  decision actor, decision reference, reason, request snapshot, and resulting ticket snapshot.

## 7. API changes

No HTTP API, CLI, config, or public network API changes.

New Python interface:

- `ApprovalTicketBook.create_ticket`
- `ApprovalTicketBook.apply_decision`
- `ApprovalTicketBook.current_ticket`

## 8. Test plan

- Unit tests for creating pending tickets from passed risk and pending-approval OMS context.
- Unit tests for approved, rejected, expired, and cancelled ticket decisions.
- Unit tests for create and decision idempotency with matching payloads and conflict rejection.
- Unit tests proving every newly accepted ticket creation and decision is journaled.
- Unit tests proving approved tickets do not emit OMS, broker, submit, transmit, route, account, or
  credential-shaped payload fields.
- Unit tests for validation failures on ticket IDs, order IDs, symbols, sides, quantities, risk
  intents, risk-decision result, OMS state, timestamps, expiry ordering, actors, references, and
  reasons.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 011 commit or remove the new approval ticket module, tests, docs, and
`docs/SLICES.md` updates. No migrations or external resources are introduced.

## 11. Implementation steps

1. Add focused approval-ticket tests first.
2. Implement the approval ticket module.
3. Add approval ticket documentation and update overview docs.
4. Update `docs/SLICES.md` acceptance criteria.
5. Run verification.
6. Self-review and red-team for live trading, secret leakage, automatic execution, missing
   journaling, idempotency gaps, and scope creep.
7. Fix P0/P1 findings and run final verification.

## 12. Completion criteria

- Approval ticket module exists.
- Tickets can be created only with passed risk-decision context.
- Tickets represent pending, approved, rejected, expired, and cancelled states explicitly.
- Approval decisions require an explicit actor and reference.
- Approval decisions are idempotent when payloads match and rejected when payloads conflict.
- Every ticket creation and decision is journaled.
- Approved tickets do not automatically submit orders.
- Tests cover create, approve, reject, expire, cancel, idempotency, journaling, validation, and
  payload safety.
- Verification passes.
- No live broker connectivity, live order submission path, or secrets are introduced.

## 13. Risks and assumptions

- This slice is in-memory only; persistence remains future work.
- OMS integration is by reference only. This slice does not advance OMS state.
- Human identity is represented by caller-supplied actor/reference strings; authentication and UI
  workflow remain future work.
- Expiry is applied by an explicit decision request rather than a scheduler.
