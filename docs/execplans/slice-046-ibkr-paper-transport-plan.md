# ExecPlan: Slice 046 IBKR Paper Transport Plan

## 1. Goal

Create a planning-only Gate D package for future IBKR paper transport work. The package must define
the required safety controls, external review checklist, and hard stops before any Gate E
implementation can begin.

## 2. Non-goals

- Implementing IBKR transport.
- Installing or importing an IBKR SDK.
- Connecting to TWS or IB Gateway.
- Adding connectivity probes.
- Adding market-data subscriptions.
- Adding contract lookup.
- Placing, submitting, transmitting, cancelling, or modifying any order.
- Adding real broker credentials, account identifiers, tokens, passwords, certificates, private
  keys, or secrets.
- Adding configurable broker host fields, live-mode fields, submit controls, transmit controls, or
  route-live controls.
- Starting production-readiness work.
- Starting production rollout.
- Enabling live trading.

## 3. Safety constraints

- Live trading remains disabled.
- No code path may transmit a live order.
- No code path may transmit a paper order in this slice.
- Default mode remains simulation or paper.
- IBKR work remains paper-only.
- IBKR access must remain local-only and must never expose TWS or IB Gateway ports publicly.
- Broker-specific behavior must remain behind the adapter boundary.
- Core OMS, risk, approval, workflow, and strategy modules must remain broker-agnostic.
- Future paper transport must preserve risk-before-approval-before-OMS-before-transport ordering.
- Future paper transport must block on stale market data, duplicate order IDs, unknown broker state,
  disconnects, and reconciliation-required state.
- Every future paper connection event, reconnect event, reconciliation event, order transition, fill,
  cancel, reject, and emergency event must be journaled.
- Future risk-increasing entries must have a protective-order plan or an explicitly approved
  exception.
- Audit logs, exports, docs, tests, screenshots, and alerts must contain no secrets.

## 4. Current state

The repository has:

- safe configuration defaults with live trading disabled;
- an append-only event journal;
- risk, approval, OMS, fake broker, simulated position, alert, and audit foundations;
- simulation-only workflow execution;
- read APIs and UI inspection surfaces;
- an IBKR paper adapter boundary from Slice 016 that is local only and non-transmitting;
- resilience tests for local deterministic disconnect, reconnect, stale data, unknown state,
  duplicates, and reconciliation behavior;
- no IBKR SDK dependency, no TWS/Gateway connectivity, no network transport, no order placement, no
  credentials, and no account identifiers.

## 5. Proposed design

This slice adds documentation only:

- `docs/IBKR_PAPER_TRANSPORT_EXTERNAL_REVIEW.md` for the external Gate E review checklist.
- This ExecPlan for paper transport planning scope, safety constraints, implementation prerequisites,
  and rollback.
- A Slice 046 status update in `docs/SLICES.md`.

The design intentionally keeps all implementation work out of scope. Gate E must be separately
approved before any SDK, connection, contract, market-data, callback, paper order, or operator UI
implementation starts.

## 6. Data model changes

None.

## 7. API changes

None.

No HTTP endpoints, CLI commands, config keys, SDK dependencies, network clients, host fields,
credential fields, account fields, order actions, workflow nodes, or UI controls are added.

## 8. Test plan

This is a documentation-only planning slice. Verification is limited to repository verification and
self-review:

- Run the full repository verifier.
- Confirm no implementation files changed.
- Confirm no dependency files changed.
- Confirm no SDK, connectivity, account, credential, order-placement, live-mode, submit, transmit,
  or route-live affordances were added.
- Confirm Slice 047 and later remain not started behind Gate E.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 046 documentation commit. No runtime behavior, dependencies, external state,
configuration, database schema, secrets, or network access are introduced.

## 11. Implementation steps

1. Add the external IBKR paper transport review checklist.
2. Add this Slice 046 ExecPlan.
3. Update `docs/SLICES.md` with Slice 046 branch, acceptance criteria, and review status.
4. Run full verification.
5. Self-review for safety boundaries and accidental Gate E scope.
6. Commit and push the planning-only branch.

## 12. Completion criteria

- Slice 046 ExecPlan exists.
- External paper-only IBKR transport review checklist exists.
- Checklist explicitly blocks live trading, real credentials, account identifiers, public IBKR port
  exposure, production rollout, and order placement.
- Docs require separate Gate E approval before any SDK, connectivity probe, contract lookup, paper
  order transport, callback handling, or paper trading UI.
- `docs/SLICES.md` reflects Slice 046 as ready for human review.
- Verification passes.
- No implementation files, dependency files, SDKs, connectivity probes, order-placement paths,
  secrets, account identifiers, host fields, live-mode fields, production-readiness work, or live
  trading paths are added.

## 13. Risks and assumptions

- Planning docs can create a false sense that paper transport is approved; the checklist therefore
  repeats that Gate E requires separate explicit approval.
- Future IBKR transport design must treat paper order placement as safety-critical even though it is
  not live trading.
- External review must happen before Gate E implementation starts.
- The existing local-only adapter foundation is the boundary for any future IBKR SDK integration.

