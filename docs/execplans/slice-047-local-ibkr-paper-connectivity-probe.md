# ExecPlan: Slice 047 Local IBKR Paper Connectivity Probe

## 1. Goal

Add a localhost-only IBKR paper connectivity probe that can observe whether the configured local TWS
or IB Gateway paper endpoint is reachable, journal the observation, and update adapter connection
state without authenticating, subscribing, resolving contracts, or placing orders.

## 2. Non-goals

- Live trading.
- Live IBKR account mode.
- Real broker credentials, account identifiers, passwords, certificates, private keys, tokens, or
  secrets.
- Public IBKR host or port exposure.
- Arbitrary broker host fields.
- IBKR SDK dependency.
- IBKR protocol login or authentication.
- Market-data subscriptions.
- Contract lookup.
- Paper order submission.
- Order placement, routing, transmission, cancellation, or modification.
- Order status callbacks.
- Fill callbacks.
- Paper trading UI.
- Production-readiness work.
- Production rollout.

## 3. Safety constraints

- IBKR configuration remains paper-only.
- Live trading remains disabled by config and code.
- Probe hosts must remain localhost-only through `IbkrPaperAdapterConfig`.
- Probe ports must remain known paper ports only: TWS paper `7497` or IB Gateway paper `4002`.
- The probe may open a short TCP connection only to the validated local endpoint.
- The probe must not send bytes, authenticate, subscribe to data, request account state, resolve
  contracts, or place orders.
- Probe payloads and journal records must not include account identifiers, credentials, secrets,
  arbitrary hosts, or route/transmit/submit affordances.
- Unknown probe state must be represented as reconciliation-required.
- Connection probe attempts and resulting adapter connection-state observations must be journaled.
- Unknown broker state must continue to block risk-increasing work.
- Core OMS, risk, approval, workflow, and strategy modules must remain broker-agnostic.

## 4. Current state

The repository has:

- safe settings that reject live trading, live IBKR account mode, public IBKR hosts, and non-paper
  IBKR ports;
- `IbkrPaperAdapterConfig` for paper-only localhost-only adapter configuration;
- `IbkrPaperAdapter.record_connection_state`, which journals local paper connection observations;
- local order-plan records that are explicitly non-transmitting and blocked during
  reconciliation-required state;
- no IBKR SDK dependency, no TWS/Gateway session, no contract lookup, no market data, no callbacks,
  and no order transport.

## 5. Proposed design

Extend `trading_oms_backend.ibkr_paper_adapter` with a small connectivity probe surface:

- `IbkrPaperConnectivityProbeResult`, a safe journal payload that records probe status, adapter
  state, endpoint kind, timestamp, reason, and optional failure category without host, port,
  account, credential, or order-routing fields.
- `IbkrPaperAdapter.probe_local_connectivity`, which accepts an optional connector callable for
  deterministic tests and otherwise uses a local TCP reachability check against the already
  validated adapter config.
- A default connector that opens and closes a TCP connection to the local paper endpoint without
  sending or receiving application data.

Probe outcomes:

- successful local TCP reachability records `reachable_local_paper_endpoint` and adapter state
  `connected_paper`;
- clear local refusal records `unreachable_local_paper_endpoint` and adapter state `disconnected`;
- timeout or unexpected OS errors record `unknown_requires_reconciliation` and adapter state
  `unknown_requires_reconciliation`.

## 6. Data model changes

No database tables or migrations.

New domain record:

- `IbkrPaperConnectivityProbeResult`

New event type:

- `ibkr.paper.connectivity_probe.recorded`

## 7. API changes

No HTTP endpoints, CLI commands, config keys, dependency files, workflow nodes, or UI controls are
added.

New Python API behind the adapter boundary:

- `IbkrPaperAdapter.probe_local_connectivity(...)`

## 8. Test plan

- Unit test successful probe with an injected connector and verify probe and connection-state
  journal records.
- Unit test refused endpoint with an injected connector and verify disconnected state.
- Unit test timeout/unknown state with an injected connector and verify reconciliation-required
  state.
- Unit test unsafe config still rejects public hosts, live mode, and non-paper ports before probing.
- Unit test probe payloads exclude account, credential, host, port, route, submit, transmit, and
  secret fields.
- Unit test source surface contains no IBKR SDK imports, no order placement methods, no send/receive
  behavior, and no contract/market-data/callback methods.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 047 branch. No external state, credentials, dependencies, database migrations, UI
controls, or persistent broker state are introduced.

## 11. Implementation steps

1. Add tests for connectivity probe success, refusal, unknown state, safe payloads, and forbidden
   surfaces.
2. Implement the adapter-bound local connectivity probe.
3. Update IBKR docs and slice status.
4. Run full verification.
5. Self-review for live-order prevention, secret leakage, public-port exposure, account leakage,
   and accidental Slice 048+ scope.
6. Commit and push the branch.

## 12. Completion criteria

- Slice 047 ExecPlan exists.
- Local IBKR paper connectivity probe exists behind the adapter boundary.
- Probe validates paper-only localhost-only known-paper-port configuration before attempting
  reachability.
- Probe journals every attempt/result and adapter connection-state observation.
- Unknown probe state requires reconciliation.
- Probe sends no data, authenticates with no credentials, stores no account identifiers, performs
  no contract lookup, subscribes to no market data, and places no orders.
- Tests cover success, refusal, unknown state, unsafe config rejection, safe payload shape, and
  forbidden surfaces.
- `docs/SLICES.md` and IBKR docs describe the Slice 047 behavior and hard stops.
- Verification passes.
- Slice 048 and later remain not started behind separate approval.

## 13. Risks and assumptions

- TCP reachability is not proof of a valid paper trading session; docs and payload names must avoid
  claiming account or order readiness.
- Local TWS/Gateway may be absent during tests, so tests use injected connectors and do not depend
  on a real broker process.
- A later Slice 048+ design must still separately handle SDK integration, contract lookup,
  callbacks, reconciliation, and paper order transport.
