# Visual Workflow Builder

Slice 015 introduced the safe visual workflow builder foundation, Slices 032-039 added the typed
React Flow graph and local workflow APIs, and the non-broker editor candidates added interactive
editing followed by validated workflow-definition persistence.

The builder still does not add live trading, broker integration, order submission, real
market-data ingestion, automatic execution, arbitrary expressions, custom scripts, code execution,
file import/export, credentials, tokens, account identifiers, or secrets.

## Purpose

The visual builder is an editing and inspection surface for a typed simulation workflow and the
existing replay-only Strategy DSL controls. Operators can arrange the safe simulation node
catalog, connect or remove workflow edges, see continuous graph validation, inspect generated
JSON-compatible DSL, deliberately create or update a backend-validated local definition, and start
that exact unchanged saved version against the fixed deterministic local replay.

Editing and persistence never start a workflow. The separate run-start panel requires a two-step
operator confirmation and the backend still enforces authorization, emergency stop, saved-version
validation, risk, journaling, and manual approval wait. Nothing submits or transmits an order,
connects to a broker, imports code, or bypasses a required safety node.

## Visual Flow

The original Strategy DSL preview graph is fixed to:

```text
Replay bars -> Close source -> Simple moving average -> Bias signal -> Strategy DSL
```

The interactive React Flow graph is:

```text
Replay source -> Bar builder -> Strategy trigger -> Risk check -> Approval ticket -> Fake broker -> Position update -> Alert -> Audit sink
```

Operators can:

- select and move nodes;
- remove nodes and add them back from the typed palette;
- connect nodes with typed workflow edges;
- select and remove edges;
- reset the graph to its deterministic initial state.

Only one instance of each supported node type and one instance of each edge are allowed.
Unsupported node and edge types cannot be introduced through the editor.

## Continuous Validation

Every edit is checked locally for:

- required risk-check, manual-approval, and audit nodes;
- duplicate node IDs, duplicate node types, and duplicate edges;
- unsupported and explicitly unsafe action-node types;
- unsupported edge types and unknown edge endpoints;
- graph cycles;
- the complete ordered simulation safety path from replay source through audit sink.

Compilation returns no DSL document while any check fails. A valid graph compiles only to
`mode: simulation`, `runtime: preview_only`, and `broker: fake_broker_only`, with live trading,
broker transport, and arbitrary code explicitly disabled.

The backend applies the same duplicate, shape, node, edge, cycle, required-gate, complete-path,
forbidden-content, and safety-posture checks before any workflow definition is written. Frontend
validation improves feedback; it is never the authoritative write boundary.

## Persistence

The workflow library uses the existing endpoints only:

- `GET /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `POST /api/workflows`
- `PUT /api/workflows/{workflow_id}`

Saved API records are treated as untrusted and are exposed to the editor only after strict local
shape, metadata, timestamp, version, DSL, graph, and safety validation. Loading reconstructs node
positions from the deterministic typed catalog because positions are not part of the persisted
DSL.

Create and update are deliberate commands; there is no autosave. Update requests carry the loaded
record's positive `expected_version`. A changed stale update returns HTTP 409 and leaves both the
stored record and current editor draft unchanged. An exact retry may remain idempotent only for the
current or immediately prior successful version. Loading or starting a new draft cannot replace
dirty work unless the operator checks the discard confirmation.

The UI renders explicit loading, empty, loading-definition, saving, success, validation-error,
version-conflict, and unavailable states. API exception text and response payload details are not
rendered.

## Deliberate Simulation Run Start

The run-start panel uses the existing endpoint only:

- `POST /api/workflows/{workflow_id}/simulation-runs`

Start eligibility requires a loaded saved definition, a matching selected workflow, no unsaved
editor changes, successful graph compilation, a positive saved version, loaded safety state, local
admin authorization, and an inactive emergency stop. The request contains the saved
`expected_workflow_version`, one generated run ID, one timestamp set, and only
`fixtures/replay/aapl-session.jsonl`. A stale version returns HTTP 409 before run orchestration or
run journaling. Lifecycle and approval times use the deliberate attempt's wall clock; market-data
freshness uses the fixed replay profile's deterministic clock. Direct API requests for any other
replay reference are rejected.

The operator first chooses review, then sees workflow ID, saved version, replay reference, and
`SIMULATION ONLY`, and must check a confirmation before start is enabled. There is no automatic
start or retry. An unavailable attempt retains the exact request for a deliberate idempotent retry.
On success the UI reloads API-backed run history and selects the exact new
`waiting_for_approval` record. Validation, authorization, emergency-stop, conflict, and
unavailable failures preserve both the draft and saved definition and never display backend
exception details.

## Durable Manual Decision

The selected-run inspector now exposes separate `Review approval` and `Review rejection` commands
only for a persisted `waiting_for_approval` run and an operator with the dedicated approver
permission. The operator provides a bounded reason, reviews workflow/run/ticket identity, and must
check a second confirmation before recording the decision.

The UI calls only:

- `POST /api/workflows/{workflow_id}/simulation-runs/{run_id}/approve`
- `POST /api/workflows/{workflow_id}/simulation-runs/{run_id}/reject`

Approval is visibly `SIMULATION ONLY` and returns `approved_not_executed`. It does not start an
execution step. Rejection returns `rejected`. An active emergency stop blocks approval but leaves
rejection available. Successful decisions reload the API-backed inspector; unavailable or
conflicting responses never assume local success.

The local-development operator section has an explicit Admin/Approver segmented control. Changing
it reloads the API-backed operator session and sends the same selected identity and role on read,
workflow, and decision requests. Admin can save and start but cannot decide; Approver can inspect
and decide but cannot administer or start. Production rejects this local-header auth model.

## Durable Approved Simulation Execution

For a selected durable `approved_not_executed` run, the inspector exposes a separate Admin-only
`SIMULATION ONLY` review action. It shows the run's persisted saved version and exact approval,
order-intent, risk, OMS order, and protection facts. The operator reviews first and then checks a
second confirmation before one explicit execution request is sent.

The request uses the run's persisted version, not the current editable workflow version. Success
reloads the inspector and shows durable deterministic OMS, fake-fill, position, protection, local-
alert, and journal evidence. Conflict, emergency-stop, unavailable, critical protection, and
restart-recovery states remain explicit. Approval never triggers execution automatically, and an
Approver cannot use the Admin execution action.

No builder node or control can select a broker, account, host, port, credential, external alert,
live mode, production rollout, or arbitrary execution outcome.

## Safe Controls

The Strategy DSL panel still exposes only:

- `symbol`
- `lookback_bars`
- `bar_timeframe_seconds`

The generated Strategy DSL always uses:

- `schema_version: 1`
- `strategy_id: visual-close-above-sma`
- `strategy_type: close_above_sma`
- `mode: replay`
- `parameters.price_source: close`

The workflow library exposes saved-definition selection, load, new, metadata, discard confirmation,
create, update, and the separate confirmed fixed-replay simulation start. It has no delete, broker,
order, credential, account, arbitrary JSON, import/export, script, or live-mode control.

## Safety Posture

The UI explicitly displays:

- `Replay only`
- `No broker connectivity`
- `No order actions`
- `No credential fields`

Persistence stores simulation definitions only. It does not execute nodes, contact a broker,
deliver external alerts, or establish paper-session or live-readiness evidence. Confirmed run start
uses only the deterministic local pipeline and stops at manual approval; downstream fake-broker,
position, and alert nodes remain blocked.

## Current Limitations

- One fixed typed node catalog; no custom node definitions.
- No drag-from-palette gesture; palette buttons add removed catalog nodes and canvas dragging moves
  existing nodes.
- No connection ports with custom data schemas beyond the single `workflow` edge type.
- Node positions are page-local and reset to deterministic catalog positions when loading.
- Saved-workflow simulation-run records and their journal manifests survive backend restart in the
  bounded local state directory. Invalid durable evidence fails closed and is not partially shown.
- Saved-workflow approval/rejection and explicit simulation-execution evidence survive restart.
  Approval remains deliberately separate and non-executing.
- No file import or export.
- No custom strategy types, arbitrary expressions, scripts, or code execution.
- Local workflow storage is suitable for this bounded self-hosted development surface; production
  deployment and rollout remain separately gated.
