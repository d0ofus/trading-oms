# Simulation Run Detail UI

Slice 031 adds a read-only simulation run detail section to the frontend shell.

This slice does not add visual workflow editing, workflow persistence, IBKR transport, broker
connectivity, execution controls, credentials, or live trading.

## What The UI Shows

The `Simulation run detail` section shows:

- run timeline;
- signal record;
- risk decision;
- approval decision;
- OMS state path;
- fake broker record;
- simulated fill;
- simulated position;
- protection alert;
- audit summary.

## Safety Guarantees

- The view is read-only.
- The view renders no forms or buttons.
- The view does not submit, transmit, connect, cancel, approve, reject, or execute anything.
- The view does not expose credential fields or live-trading controls.
- The fake broker details shown are simulation-only records.

## Current Limitations

- The first version is static UI content that reflects the Gate B simulation path.
- No backend simulation run detail endpoint exists yet.
- No run selector exists yet.
- No visual workflow graph exists yet; Gate C has not started.
