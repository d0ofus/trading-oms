# Local Persistence

Slice 040 added a local SQLite persistence foundation for simulation and inspection data. The
durable saved-workflow simulation-run candidate added schema version 2, and durable manual
decisions add schema version 3.

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
version `3`. Existing version-1 and version-2 databases migrate additively and retain their legacy
tables and records.

## Tables

The schema contains:

- `schema_migrations`
- `workflow_definitions`
- `workflow_simulation_runs`
- `workflow_simulation_run_evidence`
- `read_model_snapshots`
- `journal_index`

The journal index is a queryable index of append-only journal records. It is not the source of truth
for audit history and does not replace the JSONL event journal.

`workflow_simulation_run_evidence` is the authoritative lookup and idempotency record for saved
workflow simulation runs. It stores the canonical accepted request and digest, workflow/version
attribution, `pending` or `committed` state, typed run record, approval-ticket reference, node
statuses, canonical journal manifest, and manifest digest. Schema version 3 adds nullable
decision identity, request digest, request JSON, evidence state, typed decision record, and update
timestamp columns plus a unique partial decision-ID index.

## Write And Recovery Contract

A new saved-workflow simulation run is written in this order:

1. authorization, emergency stop, saved-DSL validation, and expected-version checks pass;
2. SQLite atomically reserves the exact canonical request as `pending` before run journaling;
3. the existing deterministic replay-to-risk-to-manual-approval path appends JSONL records;
4. the node-status records are appended in the same in-process journal write session; and
5. SQLite atomically finalizes the run as `committed` with its typed record and journal manifest.

SQLite and JSONL do not share one transaction. An interruption before finalization therefore leaves
an explicit `pending` row. The service preserves that row and fails list, get, and retry closed. It
does not fabricate completion, rerun automatically, delete evidence, or present a partial success.

Committed reads reconstruct strict domain records and compare every manifest record with the
append-only JSONL source by sequence and canonical content. Missing, malformed, incomplete,
non-contiguous, digest-invalid, or contradictory evidence returns only a generic unavailable API
state. Exact committed retries return the existing record without another orchestration or journal
append. A different payload using the same run ID is rejected.

Manual decisions follow the same reserve/finalize boundary. Domain, attribution, expiry,
authorization, and emergency-stop validation complete before SQLite reserves the exact decision as
`pending`. The approval-domain decision and changed node-status records are then appended, and
SQLite atomically commits the typed decision, updated run, expanded manifest, and digest. A pending
or corrupt decision makes the run unavailable; it is never displayed as approved or retried
automatically.

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

The running local API keeps saved workflow definitions, workflow simulation JSONL, and SQLite run
evidence under `.tmp/trading-oms-local-state`. Saved workflow run list/get and the UI inspector
recover after backend reconstruction or process restart. The JSONL journal remains the audit source
of truth; the SQLite manifest is an integrity binding and lookup record, not a replacement journal.

Committed saved-workflow approval/rejection evidence recovers through the same list/get APIs.
Approval remains `approved_not_executed`; persistence does not route or execute it.

This is bounded local development storage. It is not a production database, backup/restore design,
multi-host writer, deployment approval, broker-session record, or paper/live trading history.
