# React Flow Visual Canvas

Slice 032 adds the first React Flow canvas scaffold for the Gate C visual simulation workflow
builder.

The canvas remains a simulation workflow surface. It does not run, execute, submit, transmit,
connect, route, call a broker, import files, export files, or evaluate custom code.

## Scaffold Nodes

The first React Flow graph shows:

```text
Replay source -> Bar builder -> Strategy trigger -> Risk check -> Approval ticket -> Fake broker -> Position update -> Alert -> Audit sink
```

The graph intentionally keeps the required safe path visible:

- deterministic replay input;
- local bar construction;
- simulation strategy trigger;
- risk check;
- manual approval ticket;
- fake broker simulation;
- local position update;
- local alert record;
- append-only audit sink.

## Local Layout Editing

Slice 032 introduced a locked, non-executing scaffold. Slice 033 allows local node movement so the
operator can arrange the visual layout.

- node movement changes frontend-local canvas positions only;
- nodes remain the fixed simulation scaffold;
- edges remain fixed;
- nodes are not connectable;
- React Flow Controls are not rendered;
- no save, run, import, export, submit, transmit, connect, route, or credential controls are
  rendered.

Validation and DSL compilation are now present. Canvas layout persistence, simulation run
orchestration, and visual run inspection remain reserved for later Gate C slices.

## Graph Validation

Slice 035 adds frontend graph validation. The default catalog graph must pass:

- required risk check node;
- required approval ticket node;
- required audit sink node;
- supported node types only;
- no unsafe action nodes;
- no cycles;
- no unknown edge endpoints.

Invalid graphs are represented by explicit validation errors. The validator still does not save,
run, submit, transmit, connect, route, call a broker, or call a backend mutation endpoint.

## Workflow DSL Preview

Slice 036 compiles the validated graph to a JSON-compatible simulation workflow DSL preview and
adds a backend parser/validator for that generated shape. The compiler refuses invalid graphs and
the default document uses:

- `schema_version: 1`
- `workflow_id: visual-simulation-workflow`
- `mode: simulation`
- `runtime: preview_only`
- `broker: fake_broker_only`
- `safety_gates.broker_transport_allowed: false`
- `safety_gates.live_trading_enabled: false`
- `safety_gates.arbitrary_code_allowed: false`

The preview is local and non-executing. It does not create, save, run, submit, transmit, connect, or
route anything.

## Workflow Definition Persistence

Slice 037 adds local backend persistence for validated simulation workflow definitions:

- `GET /api/workflows`
- `POST /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `PUT /api/workflows/{workflow_id}`

Saved definitions are versioned local records. Every create or update request must pass the backend
workflow DSL parser before persistence. The endpoints do not run workflows, create simulation runs,
submit orders, connect to a broker, or expose live-mode, credential, account, route, import, script,
or eval fields.

## Saved Workflow Simulation Runs

Slice 038 adds a simulation-only run endpoint for saved workflow definitions:

- `POST /api/workflows/{workflow_id}/simulation-runs`

The endpoint reloads and validates the saved workflow DSL, runs the deterministic local replay path
through strategy, risk, OMS pending approval, and manual approval-ticket creation, and journals
per-node statuses. It stops at manual approval wait. Fake broker, position update, and alert nodes
are marked blocked until approval; they are not executed by this endpoint.

## Visual Run Inspection

Slice 039 shows run inspection state on the graph and node ledger. Each node displays:

- current simulation status;
- short inspection detail;
- append-only journal reference.

The first inspection view shows the deterministic approval-wait run from Slice 038. Risk checks pass,
the approval ticket waits for manual review, and fake broker, position update, and alert nodes remain
blocked. The status model can represent future risk blocks, fake fills, and alert records without
adding execution controls. The UI also shows those supported statuses in a read-only legend so fills
and alerts are inspectable status types, not action affordances.

## Safety Boundary

The canvas must not introduce:

- live trading;
- IBKR transport;
- real broker connectivity;
- broker host fields;
- account IDs;
- credentials or secrets;
- live-mode fields;
- arbitrary JavaScript, scripts, imports, or eval-like fields.

Automatic approval, fake broker execution from saved workflow runs, and live trading remain
unavailable.
