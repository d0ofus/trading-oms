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

Durable execution positions link alerts and audit records through exact execution and position
attribution. The monitor displays workflow/run/execution, protection, risk-block, and journal facts.
It does not infer linkage from a shared symbol when durable attribution is available.

The dashboard is inspection-only. It cannot reconcile positions, acknowledge alerts, deliver alerts,
connect to a broker, amend orders, or change protection state.

Secret-shaped text is redacted before rendering in dashboard-derived rows.

## Saved-Workflow Execution

The deliberate saved-workflow simulation execution command consumes a proposal that already has a
persisted protective-order plan. After the deterministic fake fill, it records either
`expected_protection_present` or `missing_expected_protection` in the position and execution
evidence. Missing expected protection creates one critical local alert with no-op dispatch and
sets `risk_increasing_actions_blocked=true`.

This is a deterministic simulation observation. It does not place, inspect, or reconcile any real
protective order.

## Current Limitations

- Exception references are derived from current read-model state until explicit protection-exception
  records exist.
- Representative alert linkage uses `source_event_reference`; durable execution linkage uses exact
  projected position attribution.
- Richer protection lifecycle history remains future work.
