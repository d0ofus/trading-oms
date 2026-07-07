# ExecPlan: Slice 010 OMS state machine

## 1. Goal

Add a deterministic backend OMS state machine that represents order lifecycle states explicitly,
validates allowed transitions, supports transition idempotency, and journals every accepted order
lifecycle transition.

## 2. Non-goals

- Live broker integration.
- IBKR connectivity.
- Network access.
- Real broker credentials, account IDs, tokens, certificates, or secrets.
- Automatic order submission from strategies.
- Approval ticket implementation.
- Fake broker execution orchestration.
- Alerts, UI, database migrations, or position tracking.

## 3. Safety constraints

- No live trading.
- No live broker order-transmission path.
- No secrets.
- Default behavior remains paper/simulation.
- Every accepted order lifecycle transition must be journaled.
- Every order must carry risk-decision context before moving toward approval/submission states.
- Approval references are required before the order can become approved.
- Unknown broker state must be representable and must block new risk-increasing decisions.
- Duplicate transition IDs must be idempotent only when the replayed transition payload matches.

## 4. Current state

- `event_journal.py` provides append-only JSONL records.
- `risk_engine.py` evaluates risk decisions and journals them.
- `fake_broker.py` provides a simulation-only fake broker adapter and journals fake broker
  transitions.
- `docs/OMS_STATE_MACHINE.md` lists conceptual lifecycle states but no implementation exists.
- Slice 010 is approved in `docs/SLICES.md`.

## 5. Proposed design

Add `backend/src/trading_oms_backend/oms_state_machine.py` with:

- explicit OMS state constants;
- an allowed-transition table;
- `OrderSnapshot` for current OMS order state;
- `OrderTransitionRequest` for requested state changes;
- `OrderTransitionRecord` for accepted transition records;
- `OrderStateMachine` for deterministic in-memory transition application;
- idempotency tracking by `transition_id`;
- event journal append for every newly accepted transition.

The state machine will be local and broker-agnostic. It will not call the fake broker, submit
orders, or connect to any external service.

## 6. Data model changes

No database changes.

New in-memory and journal payload shapes:

- `OrderSnapshot`: order ID, client order ID, symbol, side, quantity, risk intent, current state,
  created timestamp, updated timestamp, risk-decision ID, optional approval reference, optional
  broker transition reference, cumulative filled quantity, leaves quantity, and reconciliation flag.
- `OrderTransitionRequest`: transition ID, order identifiers, target state, occurred timestamp,
  reason, risk-decision ID, optional approval reference, optional broker transition reference,
  optional fill quantities.
- `OrderTransitionRecord`: accepted transition with prior state, new state, reason, timestamp,
  and resulting snapshot.

## 7. API changes

No HTTP API, CLI, config, or public network API changes.

New Python interface:

- `OrderStateMachine.apply_transition`
- `OrderStateMachine.current_snapshot`
- `OrderStateMachine.risk_increasing_decisions_blocked`

## 8. Test plan

- Unit tests for created-to-pending-approval-to-approved-to-submitted-to-acknowledged-to-filled.
- Unit tests for cancellation path.
- Unit tests for risk-rejected and approval-rejected terminal paths.
- Unit tests for invalid transitions.
- Unit tests for idempotent duplicate transition IDs and conflicting duplicate rejections.
- Unit tests for unknown broker state requiring reconciliation and blocking risk-increasing
  decisions.
- Unit tests for validation failures on identifiers, symbols, sides, quantities, timestamps,
  risk intents, approval references, broker transition references, and fill quantities.
- Unit tests proving journal records are appended for every newly accepted transition and no new
  journal record is appended for idempotent replay.
- Unit tests proving payloads contain no live broker routing, network, account, credential, or
  transmission fields.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 010 commit or remove the new OMS state machine module, tests, docs, and
`docs/SLICES.md` updates. No migrations or external resources are introduced.

## 11. Implementation steps

1. Add focused OMS state machine tests first.
2. Implement the OMS state machine module.
3. Update OMS documentation and overview docs.
4. Update `docs/SLICES.md` acceptance criteria.
5. Run verification.
6. Self-review and red-team for live trading, secret leakage, invalid state transitions, missing
   journaling, idempotency gaps, and scope creep.
7. Fix P0/P1 findings and run final verification.

## 12. Completion criteria

- OMS state machine module exists.
- Initial lifecycle states are represented explicitly.
- Allowed transitions are explicit and invalid transitions fail validation.
- Every newly accepted order lifecycle transition is journaled.
- Duplicate transition IDs are idempotent when payloads match and rejected when payloads conflict.
- Unknown broker state can be represented and blocks new risk-increasing decisions.
- Tests cover valid transitions, invalid transitions, idempotency, unknown state, journaling,
  validation, and payload safety.
- Verification passes.
- No live broker connectivity, live order submission path, or secrets are introduced.

## 13. Risks and assumptions

- This slice is an in-memory state machine only; persistence remains future work.
- Approval tickets are represented by a required reference string, but the approval service is not
  implemented yet.
- Fake broker transitions are represented by references, but this slice does not orchestrate fake
  broker calls.
- Position tracking and reconciliation workflows remain future slices.
