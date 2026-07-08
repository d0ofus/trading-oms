# ExecPlan: Slice 020 backend read models

## 1. Goal

Create typed backend read models for safe inspection views that future read-only APIs and frontend
screens can use without adding mutation behavior, broker transport, or live trading.

## 2. Non-goals

- No HTTP endpoints.
- No frontend integration.
- No mutation endpoints.
- No simulation run orchestration.
- No persistence layer.
- No broker connectivity.
- No IBKR transport.
- No order submission.
- No live trading.

## 3. Safety constraints

- Read models must be inspection-only data containers.
- Read models must not expose submit, approve, reject, cancel, connect, transmit, credential, token,
  password, host, account, route, or secret affordances.
- Default posture remains paper/simulation with live trading disabled.
- No network access, socket usage, broker SDK import, or live-order path is introduced.
- Future order paths remain required to pass risk before approval or submission.
- Future risk-increasing workflows remain required to have manual approval and audit records.

## 4. Current state

The backend has standalone domain modules for configuration, event journal records, replay strategy
signals, risk decisions, approval tickets, OMS order snapshots, fake broker transitions, alerts,
and live-readiness decisions. The frontend currently uses static local display data. There is no
backend read-model module and no HTTP API for these views yet.

## 5. Proposed design

Add a `trading_oms_backend.read_models` module containing frozen dataclasses for:

- safety posture;
- audit event read records;
- signal read records;
- risk decision read records;
- approval ticket read records;
- order read records;
- position read records;
- alert read records;
- readiness read records;
- an aggregate `OperationsReadModel`.

Each model exposes a deterministic `to_json_dict()` method. The module also exposes a local
`build_demo_operations_read_model()` assembler that creates safe, static inspection data from the
current domain concepts. This assembler is a temporary bridge for Slice 021 read-only APIs and must
not create mutation behavior.

## 6. Data model changes

No database or persistence changes. New in-memory Python dataclasses only.

## 7. API changes

No HTTP, CLI, config, or public network API changes.

## 8. Test plan

- Unit tests for stable JSON shapes across all read-model categories.
- Unit tests proving the aggregate model contains all expected sections.
- Unit tests proving read-model payloads contain no forbidden action, broker, credential, network,
  or secret-shaped keys.
- Source inspection test proving the module does not import network/broker transport or define
  mutation/action methods.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 020 commit to remove the read-model module, tests, docs, and slice status updates.

## 11. Implementation steps

1. Add focused read-model tests first.
2. Implement the read-model dataclasses and safe demo assembler.
3. Add read-model documentation and README reference.
4. Update `docs/SLICES.md` with Slice 020 completion evidence.
5. Run verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Backend read-model module exists.
- Safety, audit, signal, risk, approval, order, position, alert, and readiness read models exist.
- Aggregate local read-model assembler exists.
- Tests prove stable JSON shape and forbidden affordances are absent.
- Verification passes.
- No endpoints, mutation behavior, broker transport, secrets, or live-trading path are added.

## 13. Risks and assumptions

- The demo assembler is intentionally static and temporary until Slice 021 exposes read-only APIs
  and later slices add real run/read-model data sources.
- Position read models are inspection records only; full position tracking remains a later slice.
- This slice does not imply approval for Gate B mutation endpoints.
