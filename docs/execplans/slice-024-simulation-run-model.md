# ExecPlan: Slice 024 simulation run model

## 1. Goal

Create a deterministic simulation run model that records run identity, replay input reference,
lifecycle status, timestamps, and append-only journal references.

## 2. Non-goals

- No strategy execution.
- No simulation run HTTP endpoints.
- No approval mutation endpoints.
- No fake broker orchestration.
- No broker connectivity.
- No IBKR transport.
- No live trading.

## 3. Safety constraints

- Simulation runs are local records only.
- Every accepted create or lifecycle transition must be journaled.
- Duplicate create and transition IDs must be idempotent only when payloads match.
- Invalid transitions must fail without journaling.
- Replay input references must not be URLs, broker routes, credentials, or live data sources.
- No order submission, broker transport, external network client, or live-trading path is added.

## 4. Current state

The repo has deterministic replay records, append-only event journaling, read models, and a
backend-connected read-only UI. There is no simulation run model yet.

## 5. Proposed design

Add `trading_oms_backend.simulation_runs` with frozen dataclasses for create and transition
requests plus a `SimulationRunBook` in-memory lifecycle manager. The book validates run IDs,
timestamps, replay input references, allowed status transitions, idempotency keys, and journal-safe
payloads. It appends journal events for accepted run creation and lifecycle transitions.

## 6. Data model changes

New in-memory Python records only:

- `SimulationRunRecord`
- `SimulationRunCreateRequest`
- `SimulationRunTransitionRequest`

No database schema or persistence layer is added.

## 7. API changes

None. No HTTP, CLI, config, broker, or frontend API is added in this slice.

## 8. Test plan

- Unit tests for creating a simulation run and journaling it.
- Unit tests for valid deterministic lifecycle transitions.
- Unit tests for duplicate create and transition idempotency.
- Unit tests for invalid transitions and invalid replay references failing without journaling.
- Source/payload safety tests proving no broker, network, order-submission, credential, or live
  trading affordances are added.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 024 commit to remove the simulation run module, tests, docs, and slice status
updates.

## 11. Implementation steps

1. Add focused simulation run tests.
2. Implement the simulation run model and book.
3. Add simulation run documentation.
4. Update README and `docs/SLICES.md`.
5. Run verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Simulation run records include run ID, status, timestamps, replay input reference, and journal
  references.
- Accepted create and transition operations append journal records.
- Duplicate create and transition requests are idempotent only when payloads match.
- Invalid lifecycle transitions fail without journaling.
- Verification passes.
- No live trading, broker transport, order submission, HTTP mutation endpoint, or credentials are
  added.

## 13. Risks and assumptions

- The model is intentionally in-memory until later persistence work.
- Status names are local simulation lifecycle states, not broker or OMS order states.
- Slice 025 and later slices will consume this model for orchestration.
