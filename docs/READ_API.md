# Backend Inspection API

Slice 021 exposes the backend read models through FastAPI inspection endpoints.

Slice 021 did not add mutation endpoints, approval actions, simulation runs, persistence, broker
connectivity, IBKR transport, order submission, or live trading. Slice 028 later added separate
simulation-only approval decision endpoints documented in `docs/SIMULATION_APPROVAL_API.md`.

## Endpoints

The backend exposes:

- `GET /api/emergency-stop`
- `GET /api/safety`
- `GET /api/audit-events`
- `GET /api/signals`
- `GET /api/risk-decisions`
- `GET /api/approval-tickets`
- `GET /api/orders`
- `GET /api/positions`
- `GET /api/alerts`
- `GET /api/readiness`
- `GET /api/live-readiness-evidence`
- `GET /api/paper-trading`
- `GET /api/operational-controls`
- `GET /api/simulation-run-comparison`
- `GET /api/audit-export-bundle`

The operations section routes from `/api/emergency-stop` through
`/api/live-readiness-evidence` return a versioned envelope containing `resource`, `provenance`, and
`data`. The `data` field contains the matching section from `build_demo_operations_read_model()` or
current local in-process state. The provenance field identifies representative, demo, simulated,
local-only, test-double, adapter-only, and externally unverified data as applicable. See
`docs/EVIDENCE_PROVENANCE.md`.

When committed saved-workflow simulation runs exist, `/api/audit-events`, `/api/signals`,
`/api/risk-decisions`, `/api/approval-tickets`, `/api/orders`, `/api/positions`, and `/api/alerts`
atomically replace representative rows with validated schema-v4 SQLite plus digest-bound JSONL
projections. Upstream records remain simulated, local-only, externally unverified, and explicitly
not broker-derived. Downstream records add `fake_broker_derived` only for an actual local execution.
Any pending persistence, corrupt, source-mismatched, duplicate, or contradictory evidence returns
generic HTTP 503 from all seven views without partial data.

`GET /api/audit-export-bundle` returns a deterministic local review bundle built from the current
read-model snapshot, workflow definitions, workflow simulation run records, and journal records. It
recursively scans the bundle and fails closed if secret-shaped or live-routing-shaped content is
present.

`GET /api/simulation-run-comparison` requires exact left and right workflow/run query selectors.
It returns eleven ordered durable evidence sections, deterministic change classifications,
complete journal provenance, and a comparison SHA-256. Missing, corrupt, duplicate, mixed-source,
cross-run, contradictory, or otherwise unavailable evidence returns a generic failure without
partial records or representative fallback.

`GET /api/audit-export-bundle` also accepts an all-or-none selected-run query containing
`workflow_id`, `run_id`, `expected_manifest_sha256`, and `journal_scope`. Scope is either
`complete_run_manifest` or `single_journal_event`; the latter also requires `journal_sequence`.
The selected bundle contains exactly one committed run and the exact requested manifest records.
A stale manifest digest returns generic HTTP 409.

`GET /api/audit-events` includes optional audit filter metadata fields:

- `run_id`
- `symbol`
- `order_id`
- `ticket_id`
- `severity`

## Safety Guarantees

- Only `GET` handlers are implemented for these API views.
- `POST`, `PUT`, `PATCH`, and `DELETE` are not implemented for these routes.
- Responses expose inspection data only.
- Every operations response says whether its data is broker-derived and externally verified. Both
  values are false for the current local/demo implementation.
- `GET /api/emergency-stop` exposes local emergency stop state only; admin-only activation and
  deactivation endpoints are documented in `docs/EMERGENCY_STOP.md`.
- `GET /api/paper-trading` exposes representative adapter/test-double visibility only, with no
  broker controls; it is not evidence of an authenticated IBKR paper session.
- `GET /api/operational-controls` exposes local observability, retention, backup/restore, and
  incident-response posture only, with no external sinks, deletion executors, backup executors,
  restore commands, rollout controls, or broker controls.
- `GET /api/live-readiness-evidence` exposes evidence posture only. Missing, unverified, expired,
  and contradictory mandatory evidence all block final review. It cannot authorize live trading or
  controlled paper rollout.
- Responses do not expose submit, approve, reject, cancel, connect, transmit, credential, token,
  password, account, host, port, route, socket, or secret affordance keys.
- Readiness responses keep `live_trading_enabled: false` and
  `live_trading_authorized: false`.
- Audit export responses include local JSON review data only and do not upload, deliver, submit,
  transmit, route, or connect anything.
- Saved-run comparison and selected audit export are `GET`-only and add no approval, execution,
  retry, repair, deletion, or journal-rewrite action.
- No broker SDK, socket, network client, or transport behavior is introduced.

## Current Limitations

- Signals, risk decisions, approval tickets, audit events, orders, positions, and alerts use one
  validated durable lifecycle projection when any committed run exists. Unreached downstream
  stages are empty, not representative.
- The provenance envelope is metadata only and cannot make representative or local-only data into
  broker-derived or externally verified evidence.
- The lifecycle projector reads local SQLite and JSONL evidence only; it does not write, repair,
  retry, delete, route, or transmit anything.
- Frontend screens consume these endpoints for read-only inspection and safe fallback rendering.
- Approval ticket read models are visible for inspection; simulation-only approval decision
  endpoints are documented separately in `docs/SIMULATION_APPROVAL_API.md`.
- Orders are visible for inspection only; no order submission, cancellation, or broker route exists.
- Parameterless audit export uses current in-process stores. Exact selected-run export uses
  committed SQLite plus digest-bound JSONL evidence and never falls back to representative rows.
- Operational controls are safe local read-model data only; production observability, backup
  execution, restore execution, audit-retention execution, and controlled paper rollout remain
  future approved work.
