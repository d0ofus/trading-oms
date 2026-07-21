# Emergency Stop

Slice 056 adds a local emergency stop for simulation and paper-mode operation.

This is a local application safety gate only. It does not connect to a broker, cancel live orders,
flatten positions, liquidate positions, transmit orders, or enable live trading.

## Behavior

- Emergency stop state starts inactive.
- Admin operators can activate or deactivate the local emergency stop.
- Activation and deactivation are appended to the local event journal.
- While active, risk-increasing simulation and paper-mode work is blocked before approval
  execution, saved workflow simulation run start, OMS advancement, fake broker transitions, fills,
  position updates, or alert work can advance.
- The explicit saved-workflow simulation execution command checks the stop before durable
  execution reservation. A blocked attempt appends the dedicated emergency-stop audit event.
- Rejecting a pending simulation approval ticket remains allowed because rejection does not
  increase risk.
- Every blocked risk-increasing attempt is journaled.

## API

Safe read endpoint:

```text
GET /api/emergency-stop
```

Local admin-only mutation endpoints:

```text
POST /api/emergency-stop/activate
POST /api/emergency-stop/deactivate
```

Request bodies include only:

- `event_id`;
- `requested_at`;
- `actor`;
- `reason`;
- `schema_version`.

The body `actor` must match the authenticated local operator. The endpoints reject secret-shaped
operator or event values.

## Safety Boundaries

- Live trading remains disabled.
- No broker transport is added.
- No broker-side liquidation, flatten, live cancel, live route, live submit, or live transmit
  behavior is added.
- No credentials, account identifiers, tokens, passwords, certificates, private keys, or secrets are
  stored or displayed.
- The frontend panel is read-only inspection. It does not expose emergency stop action buttons or
  broker controls.

## Current Limitations

- Emergency stop state is in-memory local process state for this slice.
- Persistence, observability, incident response workflows, backup/restore, and production-like
  operating procedures remain future approved slices.
