# Order And Position Details

Slice 043 adds read-only order and position detail sections to the frontend operations shell.

It does not add broker amendments, live position reconciliation, broker connectivity, IBKR
transport, live trading, production rollout, credentials, or secrets.

## Order Detail

The order detail section renders the first order read model currently available from the backend
snapshot. It shows:

- client order ID and order ID;
- current OMS state;
- risk decision reference;
- approval reference when available;
- cumulative filled quantity and leaves quantity;
- reconciliation visibility;
- linked audit records by exact order ID.

The section is inspection-only. It has no submit, route, transmit, cancel, amend, or broker-connect
controls.

## Position Detail

The position detail section renders the first position read model currently available from the
backend snapshot. It shows:

- position ID;
- symbol;
- quantity;
- average price;
- source;
- protection state;
- linked audit records by symbol.

Missing expected protection is rendered as a critical operator-visible state.

## Current Limitations

- The first detail views select the first available order and position from the read snapshot.
- Richer historical OMS transition lists and position-specific audit IDs remain future work.
- Detail sections use existing read APIs only; no new backend mutation endpoints are added.
