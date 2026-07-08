# ExecPlan: Slice 030 simulated positions, protection monitoring, and alerts

## 1. Goal

Track simulated positions from fake broker fills and raise critical local alerts when expected
protection is missing.

## 2. Non-goals

- No real portfolio reconciliation.
- No real alert delivery.
- No broker connectivity.
- No IBKR transport.
- No HTTP position endpoint.
- No live trading.

## 3. Safety constraints

- Position updates must come from simulated filled fake broker transitions only.
- Every accepted position update must be journaled.
- A position missing expected protection must create a critical local alert intent and local no-op
  dispatch record.
- Alert payloads must contain no broker routes, account IDs, credentials, submit, or transmit
  fields.
- Duplicate position update IDs must be idempotent only when payloads match.
- No network client, broker SDK, real alert transport, or live-trading path is added.

## 4. Current state

The repo can execute approved simulation orders through OMS and fake broker. It does not yet track
simulated positions or raise alerts for missing expected protection.

## 5. Proposed design

Add `trading_oms_backend.simulated_positions` with typed position update requests, simulated
position records, and a `SimulatedPositionBook`. The book consumes fake broker filled transitions,
records a local position, journals it, and uses the existing `AlertBook` plus `NoopAlertDispatcher`
to create and record critical alerts when expected protection is missing.

## 6. Data model changes

New in-memory Python records only:

- `PositionUpdateRequest`
- `SimulatedPosition`
- `ProtectionMonitoringResult`

No database schema or persistence layer is added.

## 7. API changes

None. No HTTP, CLI, config, broker, or frontend API is added in this slice.

## 8. Test plan

- Unit test for recording a filled position with expected protection present.
- Unit test for creating a critical alert and no-op dispatch when protection is missing.
- Unit tests for idempotency and conflicting duplicate update IDs.
- Validation test rejecting non-filled fake broker transitions.
- Payload/source safety tests proving no broker, network, order-submission, credential, or live
  trading affordances are added.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\trading-oms-pytest-slice030" backend\tests\test_simulated_positions.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 030 commit to remove simulated position tracking, tests, docs, and slice status
updates.

## 11. Implementation steps

1. Add focused simulated position/protection tests.
2. Implement the simulated position book.
3. Add position/protection documentation.
4. Update README and `docs/SLICES.md`.
5. Run focused and full verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Simulated filled fake broker transitions can update local positions.
- Protection status is explicit.
- Missing expected protection creates a critical local alert and no-op dispatch.
- Every position update and alert is journaled.
- Verification passes.
- No real broker reconciliation, real alert delivery, broker transport, credentials, or
  live-trading path is added.

## 13. Risks and assumptions

- Position state is in-memory until later persistence work.
- The first implementation records a local position from each fill update request.
- Later slices can aggregate fills into richer portfolio views.
