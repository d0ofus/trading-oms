# Audit Export Bundle

Slice 045 adds a deterministic local audit export bundle for review.

It does not upload exports, deliver exports externally, connect to a broker, add IBKR transport,
enable live trading, add production rollout behavior, or store credentials or secrets.

## Backend Endpoint

```text
GET /api/audit-export-bundle
```

The endpoint returns a JSON bundle with:

- manifest metadata;
- operations read-model snapshot;
- workflow definitions;
- workflow simulation run records;
- journal records.

The manifest includes workflow IDs, run IDs, journal sequence references, record counts, and a
passed safety-scan summary.

## Secret-Shaped Content Scan

The export builder recursively scans the bundle before returning or writing it. It rejects:

- secret-shaped keys and values;
- live-enabled booleans;
- broker host, account, submit, transmit, route, and place-order affordances;
- arbitrary-code and JavaScript-shaped text.

The exported bundle uses a `safety_scan` manifest entry and does not include findings when the scan
passes.

## Local File Export

Backend code can write a bundle to a local JSON file with stable key ordering. This is local file
output only and does not upload, email, send, or otherwise deliver the bundle.

## Current Limitations

- The API endpoint exports the current in-process workflow/run stores and current read-model
  snapshot.
- Local SQLite-backed export orchestration remains future work.
- Export signing, compression, retention policy, and external review transport remain future work.
