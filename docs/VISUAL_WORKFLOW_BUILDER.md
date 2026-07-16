# Visual Workflow Builder

Slice 015 introduced the safe visual workflow builder foundation, Slices 032-039 added the typed
React Flow graph and local workflow APIs, and the non-broker editor candidates added interactive
editing followed by validated workflow-definition persistence.

The builder still does not add live trading, broker integration, order submission, real
market-data ingestion, workflow execution, arbitrary expressions, custom scripts, code execution,
file import/export, credentials, tokens, account identifiers, or secrets.

## Purpose

The visual builder is an editing and inspection surface for a typed simulation workflow and the
existing replay-only Strategy DSL controls. Operators can arrange the safe simulation node
catalog, connect or remove workflow edges, see continuous graph validation, inspect generated
JSON-compatible DSL, and deliberately create or update a backend-validated local definition.

The editor never starts a workflow, submits or transmits an order, connects to a broker, imports
code, or bypasses risk, manual approval, fake-broker, alert, or audit nodes.

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

The workflow library exposes only saved-definition selection, load, new, metadata, discard
confirmation, create, and update controls. It has no run, delete, broker, order, credential,
account, arbitrary JSON, import/export, script, or live-mode control.

## Safety Posture

The UI explicitly displays:

- `Replay only`
- `No broker connectivity`
- `No order actions`
- `No credential fields`

Persistence stores simulation definitions only. It does not execute nodes, contact a broker,
deliver external alerts, or establish paper-session or live-readiness evidence.

## Current Limitations

- One fixed typed node catalog; no custom node definitions.
- No drag-from-palette gesture; palette buttons add removed catalog nodes and canvas dragging moves
  existing nodes.
- No connection ports with custom data schemas beyond the single `workflow` edge type.
- Node positions are page-local and reset to deterministic catalog positions when loading.
- No workflow run-start control in this slice.
- No file import or export.
- No custom strategy types, arbitrary expressions, scripts, or code execution.
- Local workflow storage is suitable for this bounded self-hosted development surface; production
  deployment and rollout remain separately gated.
