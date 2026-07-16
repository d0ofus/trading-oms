# Simulation Run Inspector

Slice 031 added the first static, read-only simulation run detail section. The non-broker
simulation-run-inspector candidate replaces those representative completion records with saved
workflow simulation runs loaded from the backend.

The saved-workflow run-start candidate adds a separate deliberate simulation-only control next to
the editor. It refreshes this inspector and selects the exact newly created run only after the
backend returns a validated manual-approval-wait record. This inspector itself remains read-only.

## What The UI Shows

The `Simulation run detail` section shows:

- saved workflow simulation run history, newest first;
- the selected workflow ID, display name, and definition version;
- run ID, status, timestamps, deterministic replay input reference, and approval ticket ID;
- the backend-recorded node-status timeline;
- each node's append-only journal reference;
- explicit loading, empty, and unavailable states.

The inspector uses only:

- `GET /api/workflows`
- `GET /api/workflows/{workflow_id}/simulation-runs`

It does not infer that approval, fake-broker execution, fills, positions, or alerts occurred. A
workflow run that stopped at manual approval shows the approval node waiting and downstream nodes
blocked exactly as returned by the backend.

## Safety Guarantees

- The view is read-only.
- The run selector changes local display state only.
- The view does not start, submit, transmit, connect, cancel, approve, reject, or execute anything.
- The view does not expose credential fields or live-trading controls.
- API failures discard partial data and render a generic unavailable state without exception text.
- Empty and failed responses never fall back to a fabricated successful run.
- A successful saved-workflow start must be present in a fresh API read before the inspector selects
  it; a failed refresh remains unavailable and retains the exact idempotent request for explicit
  retry.

## Current Limitations

- Workflow simulation run records are process-local in the current backend runner and do not survive
  a backend restart.
- The inspector does not compare runs or aggregate run metrics.
- Workflow creation and run start remain separate controls; this inspector provides no mutation
  control.
- Candidate 063 IBKR connector work remains deferred.
