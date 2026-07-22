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

Durable saved-workflow simulation orders show the exact workflow/version, run, execution, intent,
risk, manual approval, OMS order, fake-fill, position, protection, local alert, and journal lineage.
This is local fake-broker evidence, not broker-derived or externally verified evidence.

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
Durable position audit linkage uses the exact projected position identity rather than symbol-only
matching, so concurrent runs of the same symbol cannot be mixed.

## Current Limitations

- The first detail views select the first available order and position from the read snapshot.
- Full historical OMS transition payload inspection remains future work; the current audit list
  exposes validated event identities and exact execution attribution.
- Detail sections use existing read APIs only; no new backend mutation endpoints are added.
