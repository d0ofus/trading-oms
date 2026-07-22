# Audit Explorer

Slice 041 adds a read-only audit explorer to the frontend operations shell.

It does not add audit mutation, deletion, event-history rewriting, broker transport, IBKR
connectivity, order submission, live trading, production rollout, credentials, or secrets.

## UI Scope

The audit explorer shows:

- filters for workflow, run, execution, event type, symbol, order ID, ticket ID, severity, and
  timestamp;
- a matching event list;
- a read-only event detail panel.

The controls are local UI filters only. There are no buttons, forms, approval actions, broker
actions, route fields, submit/transmit controls, or live-mode controls.

## Read Model Fields

Audit event read models now include optional fields for filtering:

- `run_id`
- `symbol`
- `order_id`
- `ticket_id`
- `severity`

The fields are inspection metadata only. They do not create order actions or mutable event history.

Durable saved-workflow simulation events also carry a strict execution attribution object. The
event detail exposes workflow/version, run, execution, intent, risk, manual approval, order, fill,
position, protection, local alert, and journal references. The event list is deterministic by JSONL
sequence and remains read-only.

## Secret Rendering Boundary

The frontend audit explorer redacts secret-shaped audit text before rendering. This is defense in
depth; upstream code must still avoid putting secrets into journal records, read models, logs, docs,
screenshots, tests, or alert payloads.

## Current Limitations

- The explorer uses representative data until committed saved-workflow execution evidence exists;
  it then uses only the validated durable projection for execution-backed events.
- The filters are client-side.
- Slice 040's SQLite journal index is not yet wired as the backend data source.
