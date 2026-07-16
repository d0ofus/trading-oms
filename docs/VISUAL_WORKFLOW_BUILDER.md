# Visual Workflow Builder

Slice 015 introduced the safe visual workflow builder foundation, and Slices 032-039 added the
typed React Flow graph, validation, preview DSL compilation, local workflow persistence APIs, and
simulation-only workflow APIs. The current non-broker editor candidate changes the fixed graph
preview into an interactive frontend-local graph editor.

This editor does not add live trading, broker integration, order submission, real market-data
ingestion, backend mutation, persistence, workflow execution, arbitrary expressions, custom
scripts, code execution, file import/export, credentials, tokens, or secrets.

## Purpose

The visual builder is a frontend-only editing and inspection surface for a typed simulation
workflow and the existing replay-only Strategy DSL controls. It lets operators arrange the safe
simulation node catalog, connect or remove workflow edges, see continuous graph validation, and
inspect the generated JSON-compatible simulation workflow DSL document.

The edited graph remains React state only. It does not save, run, submit, transmit, connect to a
broker, import, export, or call a backend mutation API.

## Visual Flow

The original Strategy DSL preview graph is fixed to:

```text
Replay bars -> Close source -> Simple moving average -> Bias signal -> Strategy DSL
```

Each node is descriptive only. Nodes do not execute orders, call brokers, fetch live market data, or
run arbitrary code.

The initial React Flow graph is:

```text
Replay source -> Bar builder -> Strategy trigger -> Risk check -> Approval ticket -> Fake broker -> Position update -> Alert -> Audit sink
```

The graph remains non-executing. Operators can:

- select and move nodes;
- remove nodes and add them back from the typed palette;
- connect nodes with typed workflow edges;
- select and remove edges;
- reset the graph to its deterministic initial state.

Only one instance of each supported node type is allowed. Unsupported node and edge types cannot
be introduced through the editor.

## Continuous Validation

Every edit is checked locally for:

- required risk-check, manual-approval, and audit nodes;
- duplicate node IDs and duplicate node types;
- unsupported and explicitly unsafe action-node types;
- unsupported edge types and unknown edge endpoints;
- graph cycles;
- the complete ordered simulation safety path from replay source through audit sink.

Compilation returns no DSL document while any check fails. A valid graph compiles only to
`mode: simulation`, `runtime: preview_only`, and `broker: fake_broker_only`, with live trading,
broker transport, and arbitrary code explicitly disabled.

## Safe Controls

The Strategy DSL panel still exposes only these local controls:

- `symbol`
- `lookback_bars`
- `bar_timeframe_seconds`

The generated DSL always uses:

- `schema_version: 1`
- `strategy_id: visual-close-above-sma`
- `strategy_type: close_above_sma`
- `mode: replay`
- `parameters.price_source: close`

## Safety Posture

The UI explicitly displays:

- `Replay only`
- `No broker connectivity`
- `No order actions`
- `No credential fields`

The builder contains no save or run buttons, order submission controls, broker connection controls,
Telegram delivery controls, credential fields, import/export controls, or code execution controls.

## Current Limitations

- Frontend-only, page-lifetime graph state.
- One fixed typed node catalog; no custom node definitions.
- No drag-from-palette gesture; palette buttons add removed catalog nodes and canvas dragging moves
  existing nodes.
- No connection ports with custom data schemas beyond the single `workflow` edge type.
- Existing backend workflow APIs are intentionally not called by this editor.
- No workflow save, update, or run behavior.
- No file import or export.
- No backend validation call in this slice; compilation uses the typed frontend validator.
- No custom strategy types, arbitrary expressions, scripts, or code execution.
