# Local Persistence

Slice 040 adds a local SQLite persistence foundation for simulation and inspection data.

It is a local-only persistence layer. It does not add production database deployment, broker
transport, IBKR connectivity, live trading, real alert delivery, credentials, account IDs, or order
transmission.

## Setup Command

Initialize the local SQLite schema with:

```powershell
$env:PYTHONPATH = "backend/src"
python -m trading_oms_backend.local_persistence init --database .tmp/trading-oms.sqlite3
```

The command is deterministic and idempotent. It creates the schema if needed and records migration
version `1`.

## Tables

The schema contains:

- `schema_migrations`
- `workflow_definitions`
- `workflow_simulation_runs`
- `read_model_snapshots`
- `journal_index`

The journal index is a queryable index of append-only journal records. It is not the source of truth
for audit history and does not replace the JSONL event journal.

## Safety Boundary

Before writing JSON payloads, the persistence store rejects:

- secret-shaped fields such as API keys, tokens, passwords, private keys, credentials, certificates,
  and authorization material;
- broker routing fields such as broker host, account ID, submit URL, transmit URL, place-order URL,
  or route URL;
- payloads that set live trading, live authorization, broker transport, or arbitrary code execution
  to true;
- text shaped like order submission, order transmission, JavaScript, eval, private keys, or secret
  assignments.

The store may persist safety-negative fields such as `live_trading_enabled: false` and
`broker_transport_allowed: false` because those fields prove the disabled posture.

## Current Use

This slice introduces the foundation module and tests. The running API still uses the existing
JSON/JSONL and in-memory services until later slices wire the SQLite store into operator workflows.
