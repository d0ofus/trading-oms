# Live Trading Readiness Checklist

Live trading is not approved.

This checklist is a future gate, not permission to implement live trading.

## Required before considering live trading

- Paper trading history reviewed.
- Risk engine complete.
- OMS state machine complete.
- Event journal complete.
- Approval flow complete.
- Reconnect/reconciliation tested.
- Chaos tests passing.
- Duplicate order prevention tested.
- Stale data blocking tested.
- Emergency stop implemented.
- Secrets management reviewed.
- Network exposure reviewed.
- External code review completed.
- Explicit human approval recorded.

## Current status

Not ready.

## Backend readiness gate

Slice 018 adds `trading_oms_backend.live_readiness` as a typed, local readiness evaluator.

The evaluator:

- records one check per required readiness item;
- returns `not_ready` while any evidence item is missing;
- can return `ready_for_final_review` only when all evidence is present;
- always reports `live_trading_enabled: false`;
- always reports `live_trading_authorized: false`;
- appends every evaluation to the event journal with event type:

```text
live_readiness.evaluated
```

`ready_for_final_review` is not permission to trade live. It means the checklist evidence is ready
for external review and explicit rollout approval. The configuration layer still rejects
truthy `LIVE_TRADING_ENABLED` values.

## Current gaps

The checklist remains not ready until the required evidence exists. In particular, emergency stop
implementation, external code review, paper-trading history review, secrets-management review,
network-exposure review, and explicit human approval must be documented before any future
consideration.

Slice 053 adds `docs/DEPLOYMENT_AND_SECRETS_MANAGEMENT_PLAN.md` as planning input for future
secrets-management and network-exposure review. It is not a completed review, production rollout
approval, or live-trading approval.

Slice 054 adds local operator authentication and authorization models. This is not production
authentication, not a completed external review, and not live-trading approval.

Slice 058 adds `GET /api/live-readiness-evidence` and the frontend live-readiness evidence
dashboard. The dashboard is read-only evidence visibility. It reports `not_ready` while evidence is
missing, keeps `live_trading_enabled: false`, keeps `live_trading_authorized: false`, and cannot
approve live trading or controlled paper rollout.
