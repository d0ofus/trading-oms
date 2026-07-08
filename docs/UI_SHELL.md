# UI Shell

Slice 013 introduced the first frontend operations shell.

It does not add live trading, broker integration, real broker credentials, Telegram delivery,
order submission, cancellation, approval actions, backend API integration, authentication,
database persistence, or backend Strategy DSL mutation.

## Purpose

The UI shell is a read-only inspection surface for the local trading workflow. It gives operators a
single place to see the current safety posture and the workflow areas that later slices can connect
to real read APIs.

The current shell renders static/local demo data only.

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

The shell includes static sections for:

- Signals
- Visual builder
- Approval tickets
- Orders
- Positions
- Audit events
- Alerts

Each section uses local display records. Slice 015 adds a local visual builder with safe inputs for
the replay-only Strategy DSL preview. There are no forms, action buttons, API mutation controls,
broker controls, or order submission controls.

## Guarantees

- The operational workflow sections are read-only.
- The visual builder edits local state only.
- No backend API client is added.
- No live trading controls are added.
- No broker connection controls are added.
- No order submission controls are added.
- No Telegram send controls are added.
- No credential, token, account, or secret inputs are added.

## Tests

Frontend tests render the shell to static markup and assert:

- expected workflow sections are present;
- safety posture labels are present;
- forbidden live-action affordances are absent;
- the baseline safety posture remains paper mode with live trading disabled and no broker
  connectivity.

## Current Limitations

- Demo records are static and local.
- The visual builder is local state only.
- There is no backend read API integration yet.
- There is no authentication or authorization model yet.
- User-customizable behavior is limited to local visual-builder DSL preview fields.
- The UI is not yet wired to approval decisions, OMS state transitions, alert delivery, or audit
  event queries.
