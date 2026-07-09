# ExecPlan: Slice 050 Paper Order Status And Fill Callbacks

## 1. Goal

Add safety-first IBKR paper order status and fill callback handling behind the existing IBKR paper
adapter boundary. The slice should accept only callbacks that correlate to an existing accepted
Slice 049 paper submission record, journal every receipt and outcome, enforce callback
idempotency, map accepted updates to OMS-compatible state names, and represent stale,
out-of-order, mismatched, conflicting, or unknown callback data as reconciliation-required.

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
- Cancel or modify operations.
- Paper transport chaos tests.
- Paper trading UI.
- HTTP API, workflow, or DSL execution controls for paper transport.
- Production-readiness work.
- Production rollout.
- Slice 051 or later behavior.

## 3. Safety constraints

- IBKR configuration remains paper-only.
- Live trading remains disabled by config and code.
- Callback handling remains isolated in `trading_oms_backend.ibkr_paper_adapter`.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.
- Callback hosts and ports remain constrained by the existing `IbkrPaperAdapterConfig`:
  localhost-only and known paper ports `7497` or `4002`.
- A callback can be accepted only after:
  - an accepted `IbkrPaperOrderSubmissionRecord` exists;
  - the callback client order ID matches the submission client order ID;
  - the callback correlation reference matches the submission local acknowledgement reference;
  - callback IDs are idempotent for identical payloads and rejected for conflicts;
  - callback timestamps are not stale or out of order;
  - callback cumulative quantities are OMS-compatible and never exceed the submitted quantity.
- Unknown, mismatched, stale, out-of-order, or conflicting callback data must require
  reconciliation.
- Every callback receipt, accepted update, duplicate callback, rejected/conflicting callback,
  unknown-state observation, and reconciliation-required outcome must be journaled.
- Payloads must not include account identifiers, credentials, arbitrary host fields, route-live
  fields, submit-live fields, transmit-live fields, broker order identifiers, market-data payloads,
  or secret-shaped fields.

## 4. Current state

The repository has:

- safe settings that reject live trading, live IBKR account mode, public IBKR hosts, and non-paper
  IBKR ports;
- `IbkrPaperAdapterConfig` for paper-only localhost-only adapter configuration;
- `IbkrPaperAdapter.record_connection_state`, `probe_local_connectivity`, `lookup_contract`,
  `create_order_plan`, and `record_paper_order_submission`;
- `IbkrPaperOrderSubmissionRecord` from Slice 049, including accepted local paper submission
  records and local acknowledgement references;
- append-only event journaling;
- explicit OMS states including `ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`, `REJECTED`, and
  `UNKNOWN_REQUIRES_RECONCILIATION`;
- no IBKR SDK dependency, no market data, no callback listener, no UI, and no production rollout.

## 5. Proposed design

Extend `trading_oms_backend.ibkr_paper_adapter` with deterministic adapter-bound callback records:

- `IbkrPaperOrderStatusCallback`, a safe callback request for paper order status observations.
- `IbkrPaperOrderStatusCallbackRecord`, a safe journal payload for accepted, duplicate, blocked,
  and reconciliation-required order status callback outcomes.
- `IbkrPaperFillCallback`, a safe callback request for paper fill observations.
- `IbkrPaperFillCallbackRecord`, a safe journal payload for accepted, duplicate, blocked, and
  reconciliation-required fill callback outcomes.
- `IbkrPaperAdapter.record_paper_order_status_callback(...)`, which journals callback receipt,
  validates the accepted submission correlation, enforces callback idempotency, rejects
  stale/out-of-order/conflicting data, and returns an OMS-compatible state.
- `IbkrPaperAdapter.record_paper_fill_callback(...)`, which applies the same safety gates for fill
  observations and maps cumulative fill quantity to `PARTIALLY_FILLED` or `FILLED`.

This slice intentionally does not add an IBKR SDK dependency or callback listener. Tests pass
callback records directly into the adapter to prove validation, journal coverage, idempotency, and
safety boundaries.

Order status outcomes:

- `accepted_status_update`;
- `duplicate_status_update`;
- `blocked_submission_not_accepted`;
- `blocked_correlation_mismatch`;
- `blocked_duplicate_conflict`;
- `blocked_stale_callback`;
- `blocked_out_of_order_callback`;
- `blocked_invalid_status`;
- `unknown_requires_reconciliation`.

Fill outcomes:

- `accepted_fill_update`;
- `duplicate_fill_update`;
- `blocked_submission_not_accepted`;
- `blocked_correlation_mismatch`;
- `blocked_duplicate_conflict`;
- `blocked_stale_callback`;
- `blocked_out_of_order_callback`;
- `blocked_invalid_fill`;
- `unknown_requires_reconciliation`.

## 6. Data model changes

No database tables or migrations.

New domain records:

- `IbkrPaperOrderStatusCallback`
- `IbkrPaperOrderStatusCallbackRecord`
- `IbkrPaperFillCallback`
- `IbkrPaperFillCallbackRecord`

New event types:

- `ibkr.paper.order_status_callback.received`
- `ibkr.paper.order_status_callback.recorded`
- `ibkr.paper.fill_callback.received`
- `ibkr.paper.fill_callback.recorded`

## 7. API changes

No HTTP endpoints, CLI commands, config keys, dependency files, workflow nodes, or UI controls are
added.

New Python APIs behind the adapter boundary:

- `IbkrPaperAdapter.record_paper_order_status_callback(...)`
- `IbkrPaperAdapter.record_paper_fill_callback(...)`

## 8. Test plan

- Unit test accepted order status callback maps to `ACKNOWLEDGED` and journals receipt/result.
- Unit test rejected order status callback maps to `REJECTED`.
- Unit test accepted fill callback maps partial quantity to `PARTIALLY_FILLED` and full quantity to
  `FILLED`.
- Unit test callbacks require an accepted Slice 049 submission record.
- Unit test callback client order ID and correlation reference mismatches require reconciliation.
- Unit test duplicate callback IDs are idempotent for identical payloads and rejected for conflicts.
- Unit test stale and out-of-order callback timestamps require reconciliation.
- Unit test invalid status values and invalid fill quantities are blocked and journaled.
- Unit test callback payloads exclude account identifiers, credentials, host, port, route, submit,
  transmit, broker order identifiers, market-data payloads, and secret fields.
- Unit test source surface still contains no IBKR SDK imports, market-data subscriptions,
  credential/account fields, live-routing methods, or network callback listener.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 050 branch. No external state, credentials, dependencies, database migrations, UI
controls, broker listener registration, SDK callbacks, or persistent broker state are introduced.

## 11. Implementation steps

1. Add tests for accepted status and fill callbacks, duplicate idempotency, conflicts,
   stale/out-of-order data, mismatches, invalid payloads, safe payloads, and forbidden surfaces.
2. Implement adapter-bound status and fill callback request/result models and methods.
3. Update IBKR docs and slice status.
4. Run full verification.
5. Self-review for live-order prevention, secret leakage, public-port exposure, account leakage,
   callback idempotency, stale/out-of-order blocking, reconciliation behavior, and accidental Slice
   051+ scope.
6. Commit and push the branch when GitHub auth allows it; otherwise provide manual push and PR
   creation instructions.

## 12. Completion criteria

- Slice 050 ExecPlan exists.
- Paper order status and fill callback handling exists behind the IBKR paper adapter boundary.
- Callback handling validates paper-only localhost-only known-paper-port configuration through
  existing config models.
- Callback handling requires an accepted Slice 049 paper submission record.
- Callback client order ID and correlation reference must match the accepted submission.
- Duplicate callback IDs are accepted only for matching canonical payloads and rejected for
  conflicts.
- Accepted status/fill callbacks map to OMS-compatible states.
- Unknown, mismatched, stale, out-of-order, invalid, conflicting, or unavailable callback data
  requires reconciliation as appropriate.
- Every receipt and outcome is journaled.
- Payloads exclude host, port, account, credential, route, submit, transmit, broker order
  identifier, market-data payload, and secret-shaped fields.
- `docs/SLICES.md` and IBKR docs describe the Slice 050 behavior and hard stops.
- Verification passes.
- Slice 051 and later remain not started behind separate approval.

## 13. Risks and assumptions

- Callback records are adapter-bound deterministic inputs, not a live SDK callback listener.
- Accepted callback records are local observations and still require caller-side OMS application in
  a later orchestration path.
- In-memory callback idempotency and ordering state is process-local until a later persistence or
  reconciliation slice.
- A later Slice 051 must separately test disconnect/reconnect, duplicate callback chaos, and
  reconciliation behavior under adverse paper transport scenarios.
