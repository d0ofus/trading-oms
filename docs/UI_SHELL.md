# UI Shell

Slice 013 introduces the first frontend operations shell.

It does not add live trading, broker integration, real broker credentials, Telegram delivery,
order submission, cancellation, approval actions, backend API integration, authentication,
database persistence, Strategy DSL editing, or the visual workflow builder.

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
- Approval tickets
- Orders
- Positions
- Audit events
- Alerts

Each section uses local display records. There are no forms, action buttons, or mutation controls.

## Guarantees

- The UI is read-only in this slice.
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
- There is no backend read API integration yet.
- There is no authentication or authorization model yet.
- There are no user-customizable views yet.
- The UI is not yet wired to approval decisions, OMS state transitions, alert delivery, or audit
  event queries.
