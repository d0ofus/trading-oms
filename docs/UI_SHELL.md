# UI Shell

Slice 013 introduced the first frontend operations shell. Slice 023 connects the operations
sections to the backend read API.

It does not add live trading, broker integration, real broker credentials, Telegram delivery,
order submission, cancellation, approval actions, authentication, database persistence, or backend
Strategy DSL mutation.

## Purpose

The UI shell is a read-only inspection surface for the local trading workflow. It gives operators a
single place to see the current safety posture and workflow records from the backend read API.

The backend read API serves safe representative records until committed saved-workflow simulation
evidence exists. Signals, risk decisions, approval tickets, audit events, orders, positions, and
alerts then switch atomically to validated durable local projections. If the backend or evidence is
unavailable, the frontend shows a conservative fallback with live trading disabled and no broker
connectivity.

## Safety Posture

The shell displays:

- `Paper mode`
- `Live trading disabled`
- `Broker connectivity none`
- `Manual approval required`
- `Append-only journal`
- `Alert delivery local-noop`

These labels are intentionally visible in the first viewport. They are not connected to any live
broker, Telegram, or execution integration.

## Sections

The shell includes read API-backed sections for:

- Signals
- Risk decisions
- Visual builder
- Approval tickets
- Orders
- Positions
- Audit events
- Alerts
- Run comparison

Each section uses backend read-model data when available. Slice 015 adds a local visual builder with
safe inputs for the replay-only Strategy DSL preview. There are no forms, action buttons, API
mutation controls, broker controls, or order submission controls.

Durable lifecycle rows show exact workflow/run drill-down in the signals, risk decisions, approval
tickets, audit explorer, orders, positions, and protection monitor. Pending decisions route only to
the existing saved-run inspector. Approved, rejected, expired, cancelled, and executed tickets are
visible and non-actionable. The client rejects mixed durable/representative provenance, incomplete
manifest audit rows, or any partial decision/execution identity set.

The run-comparison workspace has two independent committed-run selectors and an explicit Compare
command. It renders exact selectors, lifecycle evidence sections, change counts, digests, manifest
references, and local-only provenance. Audit controls appear only after a validated comparison and
prepare either a complete-manifest or one-event local JSON bundle. Changing any selector or scope
invalidates stale results.

## Guarantees

- The operational workflow sections are read-only.
- The visual builder edits local state only.
- The backend API client uses read-only `GET` requests only.
- No live trading controls are added.
- No broker connection controls are added.
- No order submission controls are added.
- No Telegram send controls are added.
- No credential, token, account, or secret inputs are added.
- Run comparison and selected audit preparation use read-only GET requests and expose no approval,
  execution, retry, repair, delete, connect, deploy, or live-mode action.

## Tests

Frontend tests render the shell to static markup and assert:

- expected workflow sections are present;
- backend-derived workflow records render through an injected read state;
- backend-unavailable fallback remains safe;
- safety posture labels are present;
- forbidden live-action affordances are absent;
- the baseline safety posture remains paper mode with live trading disabled and no broker
  connectivity.

## Current Limitations

- Representative lifecycle data remains only when no committed saved-workflow run exists.
- The visual builder is local state only.
- Local development authentication and separated Admin/Approver roles are not production identity.
- User-customizable behavior is limited to local visual-builder DSL preview fields.
- The UI can inspect durable simulation OMS, position, protection, local-alert, and journal evidence;
  it cannot deliver alerts externally or control a broker.
- Saved-run comparison is limited to committed local simulation evidence and local JSON download.
