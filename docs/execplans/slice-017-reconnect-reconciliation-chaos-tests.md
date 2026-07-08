# ExecPlan: Slice 017 Reconnect Reconciliation Chaos Tests

## 1. Goal

Add a deterministic local resilience and chaos-test foundation that journals disconnect, reconnect,
unknown-state, reconciliation, stale-data, and duplicate-event behavior without adding broker
connectivity or order transmission.

## 2. Non-goals

- Live trading.
- Real broker credentials, account IDs, certificates, private keys, passwords, tokens, or secrets.
- IBKR SDK dependency.
- Socket or network transport.
- Connecting to TWS, IB Gateway, or any broker.
- Submitting, placing, transmitting, cancelling, or modifying real or paper broker orders.
- Market-data subscriptions.
- Production reconciliation against real broker state.
- UI changes.
- Dependency installs.

## 3. Safety constraints

- Do not enable live trading.
- Do not add any code path that can transmit a live or paper broker order.
- Do not add credentials, account IDs, passwords, certificates, private keys, tokens, or secrets.
- Disconnect, reconnect, reconciliation, and emergency-like resilience events must be journaled.
- Reconnect must leave risk-increasing work blocked until reconciliation completes.
- Unknown broker state must block risk-increasing decisions.
- Stale market data must block trading decisions.
- Duplicate safety events must not create divergent audit history.
- All behavior must be deterministic and local.

## 4. Current state

The backend already has:

- an append-only `JsonlEventJournal`;
- a risk engine that blocks stale market data, duplicate request IDs, missing protective orders, and
  unknown broker state for risk-increasing requests;
- an OMS state machine that can represent `UNKNOWN_REQUIRES_RECONCILIATION`;
- a local-only IBKR paper adapter that records `unknown_requires_reconciliation` but intentionally
  does not implement reconnect or reconciliation workflows.

`docs/ROADMAP.md` Phase 8 calls for testing disconnect, reconnect, stale data, unknown broker
state, duplicate events, and reconciliation.

## 5. Proposed design

Add `trading_oms_backend.resilience` with:

- `ResilienceEvent` for local deterministic resilience audit records;
- `ReconciliationSnapshot` for local snapshot summaries captured during reconciliation;
- `ResilienceMonitor` to record disconnect, reconnect, unknown-state, reconciliation-start, and
  reconciliation-completed events;
- idempotency handling that replays duplicate event IDs only when the event payload matches exactly
  and rejects conflicting duplicate event IDs;
- a `run_reconnect_reconciliation_chaos_scenario` helper that runs a fixed local scenario and
  verifies risk behavior through the existing risk engine.

The monitor will expose `blocks_risk_increasing` and `requires_reconciliation` flags. Reconnect and
unknown-state events keep risk-increasing work blocked; reconciliation completion clears the block
only when the snapshot says broker state is known and no manual review is required.

## 6. Data model changes

No database tables or migrations.

New in-memory/domain records:

- `ResilienceEvent`
- `ReconciliationSnapshot`
- `ReconnectReconciliationChaosResult`

## 7. API changes

No HTTP API, CLI command, config key, dependency, network endpoint, or persistence change.

The new backend module exposes local Python types and helper methods only.

## 8. Test plan

- Unit tests for disconnect, reconnect, reconciliation-start, and reconciliation-completed
  journaling.
- Unit tests proving reconnect keeps `blocks_risk_increasing` true until reconciliation completes.
- Unit tests proving reconciliation completion with known broker state clears the block.
- Unit tests proving duplicate event IDs are idempotent when payloads match and rejected when they
  conflict.
- Unit tests proving a deterministic chaos scenario blocks stale market data and unknown broker
  state through the existing risk engine.
- Unit tests proving resilience payloads and source do not include account, credential, socket,
  submit, or transmit behavior.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the slice branch changes to remove the resilience module, tests, docs, ExecPlan, and Slice
017 status updates. No persistent data or external state is introduced.

## 11. Implementation steps

1. Add focused resilience and chaos tests.
2. Implement the local resilience module.
3. Add docs for resilience/chaos behavior and update roadmap/status docs.
4. Run verification and repair failures.
5. Self-review and red-team the local resilience boundary.

## 12. Completion criteria

- Resilience/chaos module exists.
- Disconnect, reconnect, reconciliation start, and reconciliation completion events are journaled.
- Reconnect leaves risk-increasing work blocked until reconciliation completes.
- Unknown broker state blocks risk-increasing work.
- Stale market data blocks risk-increasing work in the chaos test coverage.
- Duplicate resilience event IDs are blocked or idempotently replayed when payloads match.
- Tests cover deterministic reconnect/reconciliation scenarios and safety edge cases.
- Verification passes.
- No IBKR SDK, socket, network transport, live broker connectivity, or order submission path is
  added.
- No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets are
  introduced.

## 13. Risks and assumptions

- This slice creates a local resilience and test harness, not real broker reconciliation.
- Real paper-connectivity reconciliation must still be separately designed and approved before any
  IBKR transport is introduced.
- Future reconciliation against broker state must keep unknown state risk-blocking until durable
  evidence proves local and broker state match.
