# ExecPlan: Slice 051 Paper Transport Chaos Tests

## 1. Goal

Add deterministic paper-transport chaos coverage for the IBKR paper adapter boundary. The slice must
prove that disconnects, reconnects, duplicate callbacks, stale callbacks, out-of-order callbacks,
conflicting callbacks, and unknown/reconciliation-required state keep paper transport conservative
and block risk-increasing paper behavior.

## 2. Non-goals

- Live trading.
- Live IBKR account mode.
- Real broker credentials, account identifiers, passwords, certificates, private keys, tokens, or
  secrets.
- Public IBKR host or port exposure.
- Arbitrary broker host fields.
- IBKR SDK dependency.
- Network callback listener registration.
- Market-data subscriptions.
- New paper order submission behavior.
- New order status or fill callback behavior beyond deterministic test coverage.
- Cancel or modify operations.
- Paper trading UI.
- HTTP API, workflow, or DSL execution controls for paper transport.
- Production-readiness work.
- Production rollout.
- Slice 052 or later behavior.

## 3. Safety constraints

- IBKR configuration remains paper-only.
- Live trading remains disabled by config and code.
- Chaos coverage must remain deterministic and local.
- Tests must not open broker, market-data, public-network, or callback-listener connections.
- All IBKR-specific behavior remains isolated in `trading_oms_backend.ibkr_paper_adapter`.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.
- Disconnected adapter state must block connector-backed contract lookup, paper submission, and
  callback acceptance.
- Unknown/reconciliation-required adapter state must block local paper order planning,
  connector-backed contract lookup, paper submission, and callback acceptance.
- Reconnect must require an explicit safe local paper observation before paper submission can be
  accepted again.
- Duplicate callbacks must remain idempotent only for matching canonical payloads.
- Conflicting duplicate callbacks, stale callbacks, out-of-order callbacks, mismatches, and invalid
  callback data must require reconciliation.
- Journal payloads must remain free of account identifiers, credentials, arbitrary hosts, route-live
  fields, submit-live fields, transmit-live fields, broker order identifiers, market-data payloads,
  and secret-shaped fields.

## 4. Current state

The repository has:

- safe settings that reject live trading, live IBKR account mode, public IBKR hosts, and non-paper
  IBKR ports;
- `IbkrPaperAdapterConfig` for paper-only localhost-only adapter configuration;
- adapter-bound connectivity probing, contract lookup, order-plan creation, paper submission, and
  paper status/fill callback recording;
- event journaling for connection state, probe, contract lookup, order plan, paper submission,
  status callback, and fill callback records;
- callback idempotency, stale timestamp checks, ordering checks, and reconciliation-required
  outcomes;
- no IBKR SDK dependency, no authenticated session, no market data, no network callback listener,
  no paper trading UI, and no production rollout.

## 5. Proposed design

Add deterministic chaos tests that compose existing adapter APIs into adverse paper-transport
stories:

- disconnect -> connected -> accepted paper submission;
- unknown/reconciliation-required state blocking contract lookup, order planning, submission, and
  callbacks;
- duplicate status and fill callbacks remaining idempotent for matching canonical payloads;
- conflicting duplicate callback IDs requiring reconciliation;
- stale and out-of-order callback observations requiring reconciliation;
- a negative surface test that proves the chaos slice did not add SDK, listener, market-data,
  public host, credential/account, live-mode, submit-live, transmit-live, route-live, or UI
  affordances.

This slice should not add runtime behavior unless a gap is discovered while writing the tests. The
preferred implementation is tests and documentation only because the Slice 047-050 adapter behavior
already provides the required safety responses.

## 6. Data model changes

None.

## 7. API changes

None.

No HTTP endpoints, CLI commands, config keys, dependency files, workflow nodes, or UI controls are
added.

## 8. Test plan

- Add deterministic paper transport chaos tests for disconnect/reconnect blocking and recovery.
- Add deterministic paper transport chaos tests for unknown/reconciliation-required state blocking
  risk-increasing paper behavior.
- Add duplicate status callback and duplicate fill callback chaos tests.
- Add conflicting callback, stale callback, and out-of-order callback chaos tests.
- Add forbidden-surface tests proving no live, account, credential, public host, market-data,
  SDK/listener, production, or UI affordances were added.
- Run the targeted chaos tests.
- Run full repository verification.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider -q backend/tests/test_ibkr_paper_transport_chaos.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 051 branch. No external state, credentials, dependencies, database migrations, UI
controls, broker session state, network listeners, SDK callbacks, or persistent broker state are
introduced.

## 11. Implementation steps

1. Add deterministic chaos tests that compose the existing IBKR paper adapter APIs.
2. Fix any genuine safety gaps discovered by those tests, keeping changes inside the adapter
   boundary.
3. Add Slice 051 documentation for deterministic paper transport chaos guarantees.
4. Update `docs/SLICES.md` with Slice 051 branch, acceptance criteria, and review status.
5. Run targeted tests and full verification.
6. Self-review for live-order prevention, secret leakage, public-port exposure, account leakage,
   scope creep, callback idempotency, reconciliation blocking, stale/out-of-order handling, and
   accidental Slice 052+ behavior.
7. Commit and push the branch when GitHub auth allows it; otherwise provide manual push and PR
   creation instructions.

## 12. Completion criteria

- Slice 051 ExecPlan exists.
- Deterministic chaos tests cover disconnect and reconnect behavior.
- Deterministic chaos tests cover unknown/reconciliation-required state blocking risk-increasing
  paper behavior.
- Deterministic chaos tests cover duplicate status and fill callback idempotency.
- Deterministic chaos tests cover conflicting, stale, and out-of-order callback reconciliation
  requirements.
- Tests prove the slice adds no live trading, live account mode, credentials, account IDs, public
  IBKR host exposure, SDK/network callback listener registration, market-data subscription,
  production-readiness work, production rollout, or paper trading UI.
- `docs/SLICES.md` and IBKR docs describe the Slice 051 behavior and hard stops.
- Verification passes.
- Slice 052 and later remain not started behind separate approval.

## 13. Risks and assumptions

- This slice is test-focused; the main risk is mistaking deterministic callback records for a real
  broker reconciliation system. Documentation must say there is still no authenticated IBKR session
  reconciliation.
- Existing in-memory callback idempotency is process-local until a later persistence or
  reconciliation slice.
- The chaos tests should exercise adverse sequencing without adding real network dependencies or
  broader broker behavior.
