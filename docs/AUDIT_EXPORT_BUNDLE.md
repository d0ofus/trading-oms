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

The endpoint also supports exact saved-run selection. All four fields are required together:
`workflow_id`, `run_id`, `expected_manifest_sha256`, and `journal_scope`. Complete-manifest scope
includes every source record. Single-event scope additionally requires `journal_sequence` and
includes only that exact source-manifest event.

Selected manifests include the expected workflow version, run lifecycle status, complete source
manifest digest and references, selected references and record digests, provenance, and a
deterministic selection SHA-256. Stale digests and out-of-manifest sequences fail closed.

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
  snapshot when no selection is supplied.
- Exact selected-run mode uses restart-safe committed SQLite and digest-bound JSONL evidence.
- Arbitrary ranges and mixed-run exports are not supported by selected mode.
- Export signing, compression, retention policy, and external review transport remain future work.
