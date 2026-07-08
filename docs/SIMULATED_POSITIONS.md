# Simulated Positions And Protection Monitoring

Slice 030 adds local simulated position tracking and protection monitoring.

This slice does not add real portfolio reconciliation, real alert delivery, broker connectivity,
IBKR transport, HTTP position endpoints, external order submission, or live trading.

## Position Updates

`SimulatedPositionBook` consumes filled fake broker transitions and records local position state:

- position ID;
- symbol;
- quantity;
- average fill price;
- protection status;
- expected protection kind;
- source fake broker fill reference;
- journal references.

Accepted position updates append:

```text
position.updated
```

## Protection Monitoring

Protection status is explicit:

- `expected_protection_present`
- `missing_expected_protection`

When expected protection is missing, the book creates a critical local alert intent and records a
local no-op dispatch. This makes the safety issue visible without sending any real alert.

Alert journal events:

```text
alert.intent.created
alert.dispatch.recorded
```

## Safety Guarantees

- Only simulated filled fake broker transitions can create position updates.
- Missing expected protection creates a critical local alert.
- Alert dispatch is local no-op only.
- Position and alert payloads reject broker route, account, credential, submit, and transmit
  affordances.
- Duplicate position update IDs are idempotent when payloads match.
- Conflicting duplicate update IDs fail without new journal records.

## Current Limitations

- State is in-memory only.
- Positions are not yet exposed through a dedicated simulation run detail API.
- No real broker reconciliation exists.
- No real alert delivery exists.
- The frontend does not yet show run-specific protection monitoring details.
