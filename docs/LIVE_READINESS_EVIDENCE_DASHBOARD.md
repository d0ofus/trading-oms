# Live-Readiness Evidence Dashboard

Slice 058 adds a read-only evidence dashboard for live-readiness final-review posture.

This dashboard does not approve live trading.

Live trading remains disabled.

## Purpose

The dashboard makes checklist evidence visible to an operator before any later final-review process.
It shows:

- readiness result;
- missing evidence count;
- external review requirement;
- explicit human approval requirement;
- paper-trading evidence;
- emergency-stop evidence;
- audit-retention evidence;
- backup/restore evidence;
- incident-response evidence;
- readiness blockers.

## Backend View

The backend exposes:

```text
GET /api/live-readiness-evidence
```

The endpoint is read-only and requires the same local `view_operations` permission as the other
inspection endpoints.

The response may report only:

- `not_ready`;
- `ready_for_final_review`.

`ready_for_final_review` means only that evidence is complete enough for separate review. It does
not authorize live trading, paper-production rollout, broker connectivity, or order routing.

## Safety Guarantees

- `live_trading_enabled` is always `false`.
- `live_trading_authorized` is always `false`.
- Missing evidence remains visible.
- External review and explicit human approval remain visible requirements.
- No mutation endpoint is added.
- No broker adapter, network client, external delivery, rollout executor, or action URL is added.
- No private values or broker identifiers are displayed.

## Current Status

The demo evidence dashboard reports `not_ready`.

The current blockers are missing paper-trading history evidence, missing independent review
evidence, missing redaction review evidence, missing explicit human approval evidence, and blocked
network-exposure evidence.

Slice 059 adds a separate controlled paper-production rollout checklist. The checklist remains
`not_ready`, cannot mutate this dashboard, cannot authorize rollout or live trading, and requires a
separate future approval before any rollout work.
