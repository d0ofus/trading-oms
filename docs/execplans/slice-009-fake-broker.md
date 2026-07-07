# ExecPlan: Slice 009 fake broker

## 1. Goal

Add a deterministic, simulation-only fake broker adapter that can acknowledge, fill,
cancel, and reject fake orders while journaling every fake broker order transition.

## 2. Non-goals

- Live broker integration.
- IBKR connectivity.
- Network access.
- Real broker credentials or account identifiers.
- Automatic order submission from strategies.
- Approval ticket implementation.
- Full OMS state machine implementation.
- Alerts, UI, or database migrations.

## 3. Safety constraints

- No live trading.
- No live broker order-transmission path.
- No secrets, credentials, tokens, account IDs, certificates, or private keys.
- Default behavior is simulation-only.
- Broker-specific code must remain behind an adapter-shaped interface.
- Fake broker requests must include explicit risk-decision and approval references; this slice
  validates those references exist but does not implement approval tickets.
- Duplicate client order IDs must be blocked.
- Every fake broker order transition must be appended to the event journal.
- No network, socket, broker SDK, or IBKR code may be added.

## 4. Current state

- `backend/src/trading_oms_backend/event_journal.py` provides append-only JSONL records.
- `backend/src/trading_oms_backend/risk_engine.py` provides structured risk decisions.
- There is no broker adapter protocol, fake broker, OMS integration, approval service, or order
  lifecycle implementation yet.
- `docs/SLICES.md` marks Slice 009 as the approved autonomous slice.

## 5. Proposed design

Add `backend/src/trading_oms_backend/fake_broker.py` with:

- a `SimulationBrokerAdapter` protocol;
- a validated `BrokerOrderRequest` record for simulation order requests;
- a validated `FakeBrokerConfig` record controlling deterministic fill behavior;
- a validated `BrokerOrderTransition` record for fake broker state transitions;
- an in-memory `FakeBroker` implementation that records orders by `client_order_id`;
- methods to accept, fill, cancel, and explicitly reject fake orders;
- JSON-compatible journal payloads for every transition.

The fake broker will not connect to any external process, broker API, network endpoint, or live
market-data source.

## 6. Data model changes

No database changes.

New in-memory and journal payload shapes:

- `BrokerOrderRequest`: schema version, client order ID, symbol, side, quantity, order type,
  reference price, optional limit price, requested timestamp, risk decision ID, approval reference.
- `BrokerOrderTransition`: schema version, client order ID, fake broker order ID, symbol, side,
  quantity, state, occurred timestamp, reason, cumulative filled quantity, leaves quantity, and
  optional fill price.

## 7. API changes

No HTTP API, CLI, config, or public network API changes.

New Python interface:

- `SimulationBrokerAdapter.accept_order`
- `SimulationBrokerAdapter.fill_order`
- `SimulationBrokerAdapter.cancel_order`
- `SimulationBrokerAdapter.reject_order`

## 8. Test plan

- Unit tests for accepting and journaling an acknowledged fake order.
- Unit tests for deterministic immediate fills when configured.
- Unit tests for manual fills and cancel transitions.
- Unit tests for explicit rejections.
- Unit tests proving duplicate client order IDs are blocked.
- Unit tests for invalid request, config, timestamp, side, symbol, quantity, price, and state
  validation failures.
- Unit tests proving fake broker payloads contain no live broker routing, account, host, port,
  transmit, socket, credential, or secret fields.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 009 commit or remove the new fake broker module, tests, docs, and `docs/SLICES.md`
updates. No persistence or migrations are introduced.

## 11. Implementation steps

1. Add focused fake broker tests first.
2. Add the fake broker module and adapter protocol.
3. Add fake broker documentation.
4. Update `docs/SLICES.md` acceptance criteria.
5. Run verification.
6. Self-review and red-team for live trading, secret leakage, missing journaling, and duplicate
   order issues.
7. Fix P0/P1 findings and run final verification.

## 12. Completion criteria

- Fake broker module exists.
- Simulation-only adapter protocol exists and is broker-agnostic.
- Accepted fake orders are acknowledged deterministically.
- Configured fill behavior produces deterministic fills.
- Open fake orders can be cancelled deterministically.
- Explicit fake rejections are deterministic.
- Duplicate client order IDs are blocked.
- Every fake broker order transition is journaled.
- Tests cover accepted, filled, cancelled, rejected, duplicate, journaling, validation, and safety
  payload behavior.
- Verification passes.
- No live broker connectivity, live order submission, or secrets are introduced.

## 13. Risks and assumptions

- This slice uses an in-memory fake broker only; process restarts lose fake broker state.
- This slice validates caller-supplied risk-decision and approval references but does not check a
  persisted risk or approval service because those integrations do not exist yet.
- OMS ownership of final order lifecycle states remains future work in Slice 010.
- Numeric values use Python floats to match earlier replay, bar, strategy, and risk-engine slices.
