# ExecPlan: Slice 040 local persistence foundation

## 1. Goal

Add a deterministic local SQLite persistence foundation for workflow definitions, workflow
simulation runs, operations read-model snapshots, and journal indexes.

## 2. Non-goals

- No production database deployment.
- No broker transport.
- No IBKR connectivity.
- No live trading.
- No secrets or credential storage.
- No replacement of the existing API runtime storage in this slice.

## 3. Safety constraints

- SQLite storage is local-only and file based.
- Persisted JSON payloads must reject secret-shaped keys or values.
- Persisted payloads must not enable live trading, broker transport, arbitrary code, submit,
  transmit, broker host, account ID, or route-live fields.
- Event journals remain append-only; SQLite stores an index of journal records, not a mutable source
  of truth.
- Default mode remains paper or simulation.

## 4. Current state

Workflow definitions use local JSON file persistence. Workflow simulation runs are stored in memory
with append-only JSONL journal records. Backend read APIs return typed demo read models. Journal
records can be read from JSONL but do not yet have a queryable local index.

## 5. Proposed design

Add a `LocalSqlitePersistenceStore` in `trading_oms_backend.local_persistence` that initializes a
versioned SQLite schema and can persist validated JSON snapshots for:

- workflow definitions;
- workflow simulation runs;
- operations read-model snapshots;
- journal index records with common filter columns.

Add a deterministic CLI setup command:

```powershell
$env:PYTHONPATH = "backend/src"
python -m trading_oms_backend.local_persistence init --database .tmp/trading-oms.sqlite3
```

The store validates payloads before writing and exposes read methods for tests and later slices.

## 6. Data model changes

New local SQLite tables:

- `schema_migrations`
- `workflow_definitions`
- `workflow_simulation_runs`
- `read_model_snapshots`
- `journal_index`

No production migration or external database is introduced.

## 7. API changes

No HTTP API changes.

New local setup command:

```powershell
$env:PYTHONPATH = "backend/src"
python -m trading_oms_backend.local_persistence init --database <path>
```

## 8. Test plan

- Unit tests for idempotent schema initialization.
- Unit tests for workflow definition, simulation run, read-model snapshot, and journal-index
  persistence.
- Unit tests for journal-index filtering fields.
- Unit tests proving secret-shaped, live-enabled, or broker-transmission-shaped payloads are
  rejected before persistence.
- Unit tests for the deterministic setup command.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 040 commit to remove the SQLite module, tests, docs, and slice status update. This
does not affect existing JSON/JSONL persistence.

## 11. Implementation steps

1. Add persistence tests.
2. Implement the local SQLite store and CLI init command.
3. Add docs for local persistence setup and safety boundaries.
4. Update `docs/SLICES.md`.
5. Run full verification.

## 12. Completion criteria

- SQLite schema setup is deterministic and idempotent.
- Workflow definitions, workflow simulation runs, operations read-model snapshots, and journal
  indexes can be stored and read locally.
- Journal indexes expose common filter columns for later audit explorer work.
- Secret-shaped and unsafe live/broker/action payloads are rejected.
- Verification passes.

## 13. Risks and assumptions

- This slice intentionally does not switch the app runtime to SQLite yet; later slices can wire the
  store into API services after the persistence foundation is verified.
- SQLite is selected as the local default because it is deterministic, file based, and available in
  Python's standard library.
