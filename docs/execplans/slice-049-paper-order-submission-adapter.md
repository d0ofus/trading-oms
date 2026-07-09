# ExecPlan: Slice 049 Paper Order Submission Adapter

## 1. Goal

Add a safety-first IBKR paper order submission adapter surface behind the existing IBKR paper
adapter boundary. The slice should accept only already risk-passed, human-approved, OMS-ready,
contract-resolved paper order plans; journal every attempt and outcome; enforce idempotency; and
represent stale, disconnected, unknown, or reconciliation-required state conservatively.

## 2. Non-goals

- Live trading.
- Live IBKR account mode.
- Real broker credentials, account identifiers, passwords, certificates, private keys, tokens, or
  secrets.
- Public IBKR host or port exposure.
- Arbitrary broker host fields.
- IBKR SDK dependency.
- Market-data subscriptions.
- Order status callbacks.
- Fill callbacks.
- Cancel or modify operations.
- Paper trading UI.
- HTTP API, workflow, or DSL execution controls for paper transport.
- Production-readiness work.
- Production rollout.
- Slice 050 or later behavior.

## 3. Safety constraints

- IBKR configuration remains paper-only.
- Live trading remains disabled by config and code.
- Submission hosts remain localhost-only through `IbkrPaperAdapterConfig`.
- Submission ports remain known paper ports only: TWS paper `7497` or IB Gateway paper `4002`.
- Paper submission behavior remains isolated in `trading_oms_backend.ibkr_paper_adapter`.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.
- A submission can be considered only after:
  - a local order plan exists from a validated `BrokerOrderRequest`;
  - the order plan carries a passed risk decision and approval reference;
  - the caller provides an OMS transition reference proving OMS readiness;
  - the caller provides fresh sanitized contract metadata from Slice 048;
  - the adapter is `connected_paper`;
  - the adapter does not require reconciliation;
  - a deterministic idempotency key is present;
  - a risk-increasing entry has a protective-order plan reference or approved exception reference.
- Disconnected, unknown, stale, or reconciliation-required state blocks connector use.
- Duplicate idempotency keys are accepted only when the canonical request payload matches; conflicts
  are rejected and journaled.
- Attempt, accepted, duplicate, blocked, unknown, and reconciliation-required outcomes are journaled.
- Payloads must not include account identifiers, credentials, arbitrary host fields, route-live
  fields, submit-live fields, transmit-live fields, broker order identifiers, status callbacks, fill
  callback data, or secret-shaped fields.

## 4. Current state

The repository has:

- safe settings that reject live trading, live IBKR account mode, public IBKR hosts, and non-paper
  IBKR ports;
- `IbkrPaperAdapterConfig` for paper-only localhost-only adapter configuration;
- `IbkrPaperAdapter.probe_local_connectivity`, which journals local TCP reachability and updates
  adapter connection state;
- `IbkrPaperAdapter.lookup_contract`, which resolves sanitized stock contract metadata through an
  injected adapter-bound connector and marks stale/unknown state as reconciliation-required;
- `IbkrPaperAdapter.create_order_plan`, which creates local non-transmitting order plans from
  validated risk-passed and approval-referenced `BrokerOrderRequest` records;
- append-only event journaling;
- no IBKR SDK dependency, no authenticated session, no market data, no callbacks, no order status
  handling, no fill handling, and no paper trading UI.

Baseline verification was attempted before this slice and failed because ignored old `.tmp`
worktrees were scanned by `scripts/verify_repo.py`; the delete command was blocked by the execution
environment policy. This slice will harden the verifier to skip the generated `.tmp` directory so
ignored temporary worktrees cannot create false repository-secret failures.

## 5. Proposed design

Extend `trading_oms_backend.ibkr_paper_adapter` with a small, adapter-bound paper submission
surface:

- `IbkrPaperOrderSubmissionRequest`, a safe request record that references the existing local order
  plan, sanitized resolved contract metadata, OMS transition reference, idempotency key, and
  protective-order evidence.
- `IbkrPaperOrderSubmissionRecord`, a safe journal payload for accepted, duplicate, blocked, stale,
  and unknown/reconciliation-required outcomes.
- `IbkrPaperAdapter.record_paper_order_submission`, which journals the attempt, validates current
  adapter state and request evidence, enforces idempotency, rejects stale or mismatched contract
  metadata, and invokes an injected `PaperOrderSubmissionConnector` only after all guards pass.

This slice intentionally does not add an IBKR SDK dependency. The injected connector is the adapter
boundary for deterministic tests and future SDK containment. The default connector is unavailable
and produces an unknown/reconciliation-required outcome rather than silently succeeding.

Submission outcomes:

- `accepted_paper_submission` records a local accepted paper submission outcome.
- `duplicate_accepted` returns the prior accepted record for a matching idempotency key and payload.
- `blocked_duplicate_conflict` rejects a reused idempotency key with a different canonical payload.
- `blocked_disconnected` rejects before connector use when the adapter is not connected.
- `blocked_reconciliation_required` rejects before connector use when the adapter requires
  reconciliation.
- `blocked_stale_contract` rejects stale contract metadata and records unknown/reconciliation state.
- `blocked_contract_mismatch` rejects contract/order-plan mismatches.
- `blocked_missing_protection` rejects risk-increasing entries without protective-order evidence.
- `unknown_requires_reconciliation` records timeout, OS, unexpected connector errors, or unavailable
  connector outcomes and marks adapter state unknown/reconciliation-required.

## 6. Data model changes

No database tables or migrations.

New domain records:

- `IbkrPaperOrderSubmissionRequest`
- `IbkrPaperOrderSubmissionRecord`

New event types:

- `ibkr.paper.order_submission.attempted`
- `ibkr.paper.order_submission.recorded`

## 7. API changes

No HTTP endpoints, CLI commands, config keys, dependency files, workflow nodes, or UI controls are
added.

New Python API behind the adapter boundary:

- `IbkrPaperAdapter.record_paper_order_submission(...)`

## 8. Test plan

- Unit test accepted paper submission with an injected connector and verify attempt/result journal
  records.
- Unit test disconnected and reconciliation-required states block connector use.
- Unit test stale contract metadata blocks connector use, journals the outcome, and records unknown
  reconciliation-required state.
- Unit test order-plan/contract mismatches block connector use.
- Unit test risk-increasing buys require a protective-order plan reference or an approved exception.
- Unit test idempotent duplicate requests return `duplicate_accepted` and conflicting idempotency
  payloads return `blocked_duplicate_conflict`.
- Unit test timeout/OS/unexpected/default-unavailable connector errors become
  reconciliation-required outcomes.
- Unit test unsafe config still rejects public hosts, live mode, and non-paper ports before
  submission.
- Unit test submission payloads exclude account identifiers, credentials, host, port, route,
  submit, transmit, broker order identifiers, status callbacks, fill callbacks, and secret fields.
- Unit test source surface contains no IBKR SDK imports, no market-data subscription methods, no
  status/fill callback methods, and no live/order-routing methods.
- Unit test `scripts/verify_repo.py` ignores generated `.tmp` directories while still scanning
  tracked source files.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 049 branch. No external state, credentials, dependencies, database migrations, UI
controls, broker session state, status callbacks, fill callbacks, or persistent broker state are
introduced.

## 11. Implementation steps

1. Add verifier coverage for skipping ignored generated `.tmp` directories.
2. Add tests for paper submission accepted, blocked, idempotent, stale, unknown, and safe-payload
   outcomes.
3. Implement adapter-bound paper submission request/result models and method.
4. Update IBKR docs and slice status.
5. Run full verification.
6. Self-review for live-order prevention, secret leakage, public-port exposure, account leakage,
   idempotency, reconciliation blocking, protective-order enforcement, and accidental Slice 050+
   scope.
7. Commit and push the branch when GitHub auth allows it; otherwise provide manual push and PR
   creation instructions.

## 12. Completion criteria

- Slice 049 ExecPlan exists.
- Paper order submission behavior exists behind the IBKR paper adapter boundary.
- Submission validates paper-only localhost-only known-paper-port configuration through existing
  config models.
- Submission requires connected/reconciliation-safe adapter state.
- Submission requires resolved fresh contract metadata that matches the local order plan.
- Submission requires passed risk, explicit approval, OMS transition reference, idempotency key, and
  protective-order evidence for risk-increasing entries.
- Every attempt and outcome is journaled.
- Duplicate idempotency keys are accepted only for matching canonical payloads and rejected for
  conflicts.
- Unknown, timeout, OS, unexpected, unavailable, and stale outcomes require reconciliation and block
  later risk-increasing work.
- Payloads exclude host, port, account, credential, route, submit, transmit, broker order
  identifier, status callback, fill callback, and secret-shaped fields.
- `docs/SLICES.md` and IBKR docs describe the Slice 049 behavior and hard stops.
- Verification passes.
- Slice 050 and later remain not started behind separate approval.

## 13. Risks and assumptions

- This slice is the first paper submission surface; even though it remains paper-only, it must be
  treated as safety-critical.
- The implementation uses an injected connector rather than an SDK dependency so tests can prove
  safety gates before future protocol work.
- The accepted record is a local adapter record and is not an order-status or fill confirmation.
- Contract metadata is not proof that an account, market data, or order status stream is ready.
- A later Slice 050 must separately handle paper order status, fill callbacks, duplicate callbacks,
  and reconciliation.
