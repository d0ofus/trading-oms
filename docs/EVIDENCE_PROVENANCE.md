# Evidence Provenance

Slice 060 makes the origin and assurance level of operations read data explicit. The labels prevent
representative local data, simulation output, test doubles, and adapter-only state from being
mistaken for authenticated broker evidence or externally verified rollout evidence.

This work does not add broker connectivity, order transport, deployment behavior, production
rollout, or live trading.

## Read API Envelope

Each operations inspection endpoint returns:

```json
{
  "schema_version": 1,
  "resource": "paper_trading",
  "provenance": {
    "schema_version": 1,
    "resource": "paper_trading",
    "source": "build_demo_operations_read_model",
    "classifications": [
      "representative",
      "demo",
      "local_only",
      "test_double",
      "adapter_only",
      "externally_unverified"
    ],
    "broker_derived": false,
    "externally_verified": false,
    "summary": "Representative local paper-adapter state; not an authenticated IBKR paper session."
  },
  "data": {}
}
```

The frontend validates the envelope before displaying `data`. An unknown resource, unknown or
duplicate classification, missing `externally_unverified` label, `broker_derived: true`, or
`externally_verified: true` causes the complete operations snapshot to fall back to the safe local
fallback.

## Classifications

- `representative`: shaped to demonstrate the product view, not proof of a real operating event.
- `demo`: produced by the deterministic demo read-model builder.
- `simulated`: produced by local simulation or replay behavior.
- `local_only`: observed or recorded only in the local process or local artifacts.
- `test_double`: supplied by an injected fake or test connector.
- `adapter_only`: demonstrates an adapter boundary without an authenticated external session.
- `externally_unverified`: not reviewed and accepted as external evidence.

All current operations resources are explicitly not broker-derived and externally unverified. The
paper-trading view is adapter-only/test-double data and is not an authenticated IBKR paper session.

## Readiness Evidence

Readiness evidence uses only these states:

- `verified`;
- `missing`;
- `unverified`;
- `expired`;
- `contradictory`.

Every mandatory item whose state is not `verified` is blocking. In particular, locally implemented
emergency-stop behavior and locally documented observability, retention, backup/restore, and
reconciliation controls remain `unverified`; their existence does not satisfy controlled-rollout
evidence requirements.

The current demo dashboard has zero verified items and remains `not_ready`. A
`ready_for_final_review` result is valid only when every item is verified and external review and
explicit human approval are no longer outstanding. Even that result would not authorize rollout or
live trading.

## Hard Stops

- No current read-model record is authenticated broker evidence.
- No current local artifact is externally verified rollout evidence.
- Provenance metadata cannot authorize an action.
- Missing, unverified, expired, and contradictory mandatory evidence all block readiness.
- `live_trading_enabled` and `live_trading_authorized` remain false.
- No credentials, account identifiers, hosts, ports, tokens, private values, or external integration
  controls may appear in provenance metadata.
