# ExecPlan: interactive visual workflow editor

## 1. Goal

Turn the fixed React Flow simulation preview into a usable local visual editor where an operator can
add safe typed nodes, select and move them, remove nodes and edges, connect nodes, see continuous
validation, and inspect a DSL preview compiled from the edited graph.

## 2. Non-goals

- No workflow create, update, save, load, or persistence control.
- No simulation-run start or execution control.
- No approval, OMS, fake-broker, position, alert, or journal behavior change.
- No backend mutation or parser behavior change.
- No arbitrary or user-defined node types, expressions, scripts, imports, or code.
- No Candidate 063 implementation, IBKR dependency, broker connection, socket, paper session,
  credential, account identifier, contract lookup, market-data request, or order transport.
- No deployment, rollout, production operation, or live trading.

## 3. Safety constraints

- The node palette is derived only from the existing typed simulation node catalog.
- Editor state and layout remain frontend-local and disappear on refresh.
- Compilation must validate the current graph first and produce no document for invalid graphs.
- Validation must reject missing risk, approval, and audit gates; duplicate node identities or node
  types; unsupported node or edge types; unknown edge endpoints; cycles; and an incomplete required
  simulation path.
- Node and edge creation must reject unknown endpoints, self-links, duplicate links, and unsupported
  types before they enter editor state.
- The generated DSL remains `simulation`, `preview_only`, and `fake_broker_only`, with broker
  transport, live trading, and arbitrary code explicitly disabled.
- No broker host/port, account, credential, submit, transmit, route, live-mode, script, import,
  JavaScript, or eval field or action may appear.
- Existing risk, manual approval, audit, emergency-stop, and no-live-trading boundaries remain
  unchanged.

## 4. Current state

The merged simulation-run-inspector tree passes full verification with 587 backend tests and 65
frontend tests. The current React Flow canvas renders every catalog node, allows position changes,
keeps edges fixed, and compiles the DSL preview from constant catalog arrays. Nodes cannot be added
or removed through application controls, edges cannot be connected or removed, and graph edits do
not drive validation or compilation.

An authenticated fetch confirmed the inspector squash merge as authoritative `origin/main` commit
`1feb6edab814ca92b1c381a3067dcc8744c466cd`. Its tree
`5bc59aedbd93fde9317b721c49d716166b99a0f0` exactly matches the reviewed inspector head tree. The
editor branch is rebased directly onto that commit.

Implementation result: the local editor, validation hardening, dynamic DSL preview, responsive
styles, tests, and documentation are complete. Focused tests, all 72 frontend tests, lint, type
checking, production build, and full verification with 587 backend tests pass. The backend and Vite
services answer locally with paper mode, live trading disabled, and broker connectivity not
configured. Browser discovery returned no available browser instance, so no visual screenshot claim
is made.

## 5. Proposed design

Add a pure frontend editor-state module that owns cloned catalog nodes, safe workflow edges, current
selection, deterministic add/remove/connect/move operations, and rejection of duplicate or
unsupported mutations. Keep React Flow rendering in the canvas component, but make `App` own the
editor state so the current graph feeds both continuous validation and the generated DSL preview.

Render a compact palette beside a stable canvas. Palette buttons add only missing catalog node
types. React Flow handles node movement and connection gestures; explicit local remove and reset
commands operate on the selected node or edge. The canvas renders validation errors from the edited
graph and does not display representative run statuses.

## 6. Data model changes

Frontend-only TypeScript state is added for:

- editor nodes cloned from `VisualWorkflowNodeDefinition`;
- safe domain edges with `type: "workflow"`;
- selected node or edge identity;
- deterministic mutation results and rejection reasons.

No backend, persistence, journal, risk, approval, order, position, alert, broker, or configuration
data model changes are made.

## 7. API changes

None. No HTTP endpoint, request, response, configuration key, CLI command, persistence interface, or
broker adapter changes in this slice.

## 8. Test plan

- Failing-first editor-state tests for deterministic initial state, typed node addition after
  removal, selection, movement, node removal with incident-edge cleanup, edge connection/removal,
  reset, duplicate prevention, unsupported mutation rejection, unknown endpoints, and self-links.
- Validation tests for duplicate node IDs/types, unsupported edge types, missing safety gates,
  cycles, unknown endpoints, and incomplete required paths.
- Compiler tests proving the edited valid graph compiles and every invalid graph produces no DSL
  document.
- Rendering tests for palette controls, selectable/removable state, continuous validation output,
  edited-graph DSL wiring, stable canvas classes, responsive-safe layout, and absent save/run/broker/
  live/secret affordances.
- Existing frontend and backend safety tests remain green.

## 9. Verification commands

```powershell
npm.cmd run test --prefix frontend -- visualWorkflowEditor.test.ts visualWorkflowValidation.test.ts visualWorkflowDsl.test.ts visualSimulationWorkflowCanvas.test.ts App.test.tsx
npm.cmd run lint --prefix frontend
npm.cmd run typecheck --prefix frontend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Start the backend and frontend, inspect `http://localhost:5173` at desktop and mobile widths where a
browser surface is available, and record any browser limitation honestly.

## 10. Rollback plan

Revert this candidate commit. The previous fixed local canvas and constant safe DSL preview return;
backend APIs and all trading-safety behavior remain unchanged.

## 11. Implementation steps

1. Add failing editor-state, validation, compiler, canvas, and App rendering tests.
2. Add the pure deterministic local graph editor model.
3. Harden graph validation for duplicates, safe edge types, and the required simulation path.
4. Make the React Flow canvas controlled by the local editor state and add palette/connect/remove/
   reset interactions.
5. Compile the App's DSL preview from current editor state and remove representative run status from
   the editing surface.
6. Add stable responsive styling and update product/slice documentation.
7. Run focused checks, full verification, local runtime inspection, and a P0/P1 self-review.
8. Authenticate GitHub, fetch `origin/main`, confirm the inspector merge, rebase the branch onto
   current main, rerun verification, commit/push as needed, and prepare the PR.

## 12. Completion criteria

- Every existing safe simulation node type is available from a compact palette.
- Nodes can be added, selected, moved, removed, and restored without duplicate identities.
- Safe edges can be connected, selected, and removed; unsafe or duplicate mutations are rejected.
- Validation updates from the edited graph and blocks missing gates, unsupported content, cycles,
  duplicate identities/types, unknown endpoints, and incomplete required paths.
- The DSL preview updates from the edited graph and is absent as a document when validation fails.
- The canvas has stable responsive dimensions and usable desktop/mobile composition.
- No save, load, run, backend mutation, IBKR, broker, credential/account, transport, deployment,
  rollout, production, or live-trading behavior is added.
- Focused and full verification pass after rebasing onto authoritative merged `origin/main`.

## 13. Risks and assumptions

- The palette intentionally permits at most one instance of each current catalog node type; this
  avoids ambiguous required-path compilation until a future typed multi-instance design exists.
- Invalid intermediate graphs are allowed for editing but never compile to a DSL document.
- React Flow keyboard deletion must flow through the same pure cleanup logic as explicit removal.
- Layout is intentionally not durable in this slice.
- The inspector squash merge changed commit identity while preserving the exact reviewed tree; the
  authenticated fetch and tree comparison resolve that provenance assumption.
- `npm audit` reports five existing Vitest/Vite development-tool advisories. The critical advisory
  applies to the unused Vitest UI server; this slice does not start that server or broaden network
  exposure. A toolchain-major upgrade remains separate dependency-hardening work.
