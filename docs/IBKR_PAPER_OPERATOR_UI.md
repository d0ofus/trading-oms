# IBKR Paper Operator UI

Slice 052 adds a read-only paper trading operator section to the frontend shell.

It does not add live trading, live account mode, real broker credentials, account identifiers,
public IBKR exposure, market-data subscriptions, SDK or network callback listener registration,
order submission controls, order cancellation controls, order modification controls, production
readiness work, production rollout, or live order transmission.

## Scope

The UI shows operator-visible paper transport state from safe backend read models:

- paper-only adapter labeling;
- live-trading disabled posture;
- adapter connection state;
- reconciliation-required warnings;
- latest representative paper order status;
- latest representative status callback state;
- latest representative fill callback state;
- cumulative filled and leaves quantity.

The backend exposes this through:

```text
GET /api/paper-trading
```

The endpoint returns the `paper_trading` section from `build_demo_operations_read_model()`. It is
inspection data only.

## Safety Guarantees

- The UI renders no broker connection controls.
- The UI renders no credential, token, password, account identifier, host, or port fields.
- The UI renders no submit, place, transmit, route, cancel, or modify controls.
- The endpoint is `GET`-only.
- The read model requires `paper_mode: paper` and `live_trading_enabled: false`.
- Reconciliation-required state is visible and clearly blocking for risk-increasing steps.
- The panel depends on backend read data or the safe frontend fallback only.

## Current Limitations

- The operator section is read-only visibility only.
- The displayed data is demo/read-model state, not a live IBKR session.
- There is still no SDK-backed paper transport by default.
- There is still no authenticated TWS or IB Gateway session in the app.
- There is no persistent broker reconciliation store.
- Slice 053 production-readiness planning remains not started and requires separate explicit
  approval.
