# Protection Monitoring

Slice 044 adds a read-only protection monitoring dashboard to the frontend operations shell.

It does not add live broker reconciliation, real alert delivery, broker connectivity, IBKR
transport, live trading, production rollout, credentials, or secrets.

## Dashboard Scope

The dashboard derives its state from existing read API records:

- positions;
- local alert records;
- audit events.

It shows:

- expected-protection position counts;
- missing-protection position counts;
- exception and review-required references;
- critical and emergency local alerts;
- operator-visible emergency conditions.

## Safety Behavior

Missing expected protection is rendered as a critical operator-visible condition. Critical and
emergency local alerts remain visible with their source event reference.

The dashboard is inspection-only. It cannot reconcile positions, acknowledge alerts, deliver alerts,
connect to a broker, amend orders, or change protection state.

Secret-shaped text is redacted before rendering in dashboard-derived rows.

## Current Limitations

- Exception references are derived from current read-model state until explicit protection-exception
  records exist.
- Alert linkage uses `source_event_reference` matching a position ID when available.
- Richer protection lifecycle history remains future work.
