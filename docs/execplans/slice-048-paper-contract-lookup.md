# ExecPlan: Slice 048 Paper Contract Lookup

## 1. Goal

Add a safe IBKR paper contract lookup surface behind the existing adapter boundary. The slice should
validate paper-only localhost-only configuration, journal lookup attempts and outcomes, return
sanitized contract metadata when an adapter-bound paper lookup connector resolves a contract, and
represent disconnected, stale, or unknown lookup state conservatively.

## 2. Non-goals

- Live trading.
- Live IBKR account mode.
- Real broker credentials, account identifiers, passwords, certificates, private keys, tokens, or
  secrets.
- Public IBKR host or port exposure.
- Arbitrary broker host fields.
- Paper order submission.
- Order placement, routing, transmission, cancellation, or modification.
- Market orders or any other order type handling.
- Market-data subscriptions.
- Order status callbacks.
- Fill callbacks.
- Paper trading UI.
- Workflow, DSL, or API execution controls.
- Production-readiness work.
- Production rollout.

## 3. Safety constraints

- IBKR configuration remains paper-only.
- Live trading remains disabled by config and code.
- Contract lookup hosts remain localhost-only through `IbkrPaperAdapterConfig`.
- Contract lookup ports remain known paper ports only: TWS paper `7497` or IB Gateway paper `4002`.
- Contract lookup behavior remains isolated in `trading_oms_backend.ibkr_paper_adapter`.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.
- No order method, market-data subscription method, callback method, credential field, account field,
  live-mode field, arbitrary host field, or public network exposure is added.
- Unknown, stale, or connector-error lookup state must be represented as reconciliation-required.
- Reconciliation-required state must continue to block local paper order-plan creation.
- Lookup attempt and outcome payloads must not include host, port, account identifiers,
  credentials, route, submit, transmit, order, token, password, certificate, private key, or secret
  fields.
- Unsupported instruments must be rejected without connector calls and must be journaled safely.

## 4. Current state

The repository has:

- safe settings that reject live trading, live IBKR account mode, public IBKR hosts, and non-paper
  IBKR ports;
- `IbkrPaperAdapterConfig` for paper-only localhost-only adapter configuration;
- `IbkrPaperAdapter.probe_local_connectivity`, which journals local TCP reachability and updates
  adapter connection state;
- `IbkrPaperAdapter.record_connection_state`, which journals local connection observations;
- local order-plan records that are explicitly non-transmitting and blocked during
  reconciliation-required state;
- no IBKR SDK dependency, no authenticated TWS/Gateway session, no contract lookup, no market data,
  no callbacks, and no order transport.

## 5. Proposed design

Extend `trading_oms_backend.ibkr_paper_adapter` with a small contract lookup surface:

- `IbkrPaperContractLookupRequest`, a safe request record for stock contract metadata lookup.
- `IbkrPaperResolvedContract`, a sanitized metadata record with contract identifiers and descriptive
  fields only.
- `IbkrPaperContractLookupResult`, a safe journal payload for resolved, not-found, ambiguous,
  unsupported, disconnected, stale, and unknown/reconciliation-required outcomes.
- `IbkrPaperAdapter.lookup_contract`, which journals every attempt, checks current adapter state,
  rejects unsupported instruments before connector calls, and uses an injected
  `ContractLookupConnector` for deterministic paper lookup behavior.

This slice intentionally does not add an IBKR SDK dependency. The connector seam keeps future SDK
or protocol work behind the adapter boundary while letting this slice validate models, journaling,
state handling, and safety boundaries first.

Lookup outcomes:

- `resolved` returns sanitized contract metadata and does not require reconciliation.
- `not_found` and `ambiguous` return no contract and do not require reconciliation.
- `unsupported_instrument` returns no contract and does not call the connector.
- `blocked_disconnected` returns no contract and does not call the connector.
- `stale_result_rejected`, connector timeout, connector OS errors, or unexpected connector errors
  return no contract, require reconciliation, and record adapter connection state as
  `unknown_requires_reconciliation`.
- Existing `unknown_requires_reconciliation` adapter state blocks lookup before the connector and
  journals a reconciliation-required outcome.

## 6. Data model changes

No database tables or migrations.

New domain records:

- `IbkrPaperContractLookupRequest`
- `IbkrPaperResolvedContract`
- `IbkrPaperContractLookupResult`

New event types:

- `ibkr.paper.contract_lookup.attempted`
- `ibkr.paper.contract_lookup.recorded`

## 7. API changes

No HTTP endpoints, CLI commands, config keys, dependency files, workflow nodes, or UI controls are
added.

New Python API behind the adapter boundary:

- `IbkrPaperAdapter.lookup_contract(...)`

## 8. Test plan

- Unit test resolved stock contract lookup with an injected connector and verify attempt/result
  journal records.
- Unit test not-found and ambiguous outcomes with injected connector responses.
- Unit test unsupported instruments are journaled and do not call the connector.
- Unit test disconnected and reconciliation-required states block lookup before connector calls.
- Unit test stale connector metadata is rejected, journaled, and records
  `unknown_requires_reconciliation`.
- Unit test timeout/OS/unexpected connector errors become reconciliation-required outcomes.
- Unit test unsafe config still rejects public hosts, live mode, and non-paper ports before lookup.
- Unit test lookup payloads exclude account, credential, host, port, route, submit, transmit, order,
  token, password, certificate, private key, and secret fields.
- Unit test source surface contains no IBKR SDK imports, no order placement methods, no market-data
  subscription methods, and no callback methods.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 048 branch. No external state, credentials, dependencies, database migrations, UI
controls, broker session state, or persistent broker state are introduced.

## 11. Implementation steps

1. Add tests for contract lookup resolution, blocked states, stale/unknown outcomes, safe payloads,
   and forbidden surfaces.
2. Implement adapter-bound contract lookup models and method.
3. Update IBKR docs and slice status.
4. Run full verification.
5. Self-review for live-order prevention, secret leakage, public-port exposure, account leakage,
   and accidental Slice 049+ scope.
6. Commit and push the branch when GitHub auth allows it, otherwise provide manual push and PR
   creation instructions.

## 12. Completion criteria

- Slice 048 ExecPlan exists.
- Paper contract lookup exists behind the adapter boundary.
- Lookup validates paper-only localhost-only known-paper-port configuration before connector use.
- Lookup journals every attempt and outcome.
- Unknown, stale, timeout, OS, or unexpected connector state requires reconciliation.
- Reconciliation-required state blocks local paper order-plan creation.
- Unsupported instruments are handled without connector calls.
- Lookup payloads exclude host, port, account, credential, route, submit, transmit, order, and
  secret-shaped fields.
- Tests cover resolved, not-found, ambiguous, unsupported, disconnected, reconciliation-required,
  stale, connector-error, safe payload, and forbidden-surface behavior.
- `docs/SLICES.md` and IBKR docs describe the Slice 048 behavior and hard stops.
- Verification passes.
- Slice 049 and later remain not started behind separate approval.

## 13. Risks and assumptions

- This slice does not add an IBKR SDK dependency. The injected connector is an intentional boundary
  that lets tests prove lookup semantics without introducing protocol/session risk.
- Contract lookup metadata is not proof that an account exists, market data is fresh, or orders can
  be placed.
- Contract metadata can still become stale or ambiguous; stale and unknown outcomes are treated as
  reconciliation-required.
- A later Slice 049+ design must still separately handle paper order transport, idempotency,
  callbacks, reconciliation, and protective-order requirements.
