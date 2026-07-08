# React Flow Visual Canvas

Slice 032 adds the first React Flow canvas scaffold for the Gate C visual simulation workflow
builder.

The canvas is frontend-only and static. It does not save, run, execute, submit, transmit, connect,
route, call a backend mutation API, call a broker, import files, export files, or evaluate custom
code.

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

Validation, DSL compilation, persistence, simulation run orchestration, and visual run inspection
are reserved for later Gate C slices.

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

Simulation-only execution remains unavailable until the later approved Gate C run slice.
