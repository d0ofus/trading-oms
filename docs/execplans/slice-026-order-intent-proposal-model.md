# ExecPlan: Slice 026 order-intent proposal model

## 1. Goal

Represent strategy output as typed, non-executable order-intent proposals.

## 2. Non-goals

- No risk evaluation orchestration.
- No approval decisions.
- No OMS transitions.
- No fake broker execution.
- No broker connectivity.
- No IBKR transport.
- No live trading.

## 3. Safety constraints

- Proposals must remain explicitly non-routable.
- A proposal is not a risk pass, human approval, OMS transition, broker request, or executable
  order.
- Duplicate proposal IDs and duplicate source signal references must be prevented.
- Risk-increasing proposals must include a protective-order plan or approved exception reference.
- Every accepted proposal must be journaled.
- Proposal payloads must not contain broker routes, account IDs, credentials, approval references,
  risk-decision IDs, submit, or transmit fields.
- No network client, broker SDK, HTTP mutation endpoint, or live-trading path is added.

## 4. Current state

The repo has replay-only product strategy signals, risk checks, approval tickets, OMS, and fake
broker models, but no typed model that safely represents strategy output as an order-intent
proposal.

## 5. Proposed design

Add `trading_oms_backend.order_intents` with frozen dataclasses for protective plans, proposal
requests, and proposal records plus an in-memory `OrderIntentProposalBook`. The book validates
proposal fields, enforces non-routable status, prevents duplicate proposal/source-signal creation,
journals accepted proposals, and returns readback records.

## 6. Data model changes

New in-memory Python records only:

- `OrderIntentProtectivePlan`
- `OrderIntentProposalRequest`
- `OrderIntentProposal`

No database schema or persistence layer is added.

## 7. API changes

None. No HTTP, CLI, config, broker, or frontend API is added in this slice.

## 8. Test plan

- Unit tests for creating and journaling non-routable proposals.
- Unit tests for duplicate proposal ID idempotency and conflict rejection.
- Unit tests for duplicate source signal rejection.
- Unit tests for risk-increasing protection requirements.
- Validation tests for sides, quantities, order types, timestamps, limit prices, and executable
  statuses.
- Source/payload safety tests proving no broker, network, approval, submission, credential, or live
  trading affordances are added.

## 9. Verification commands

```powershell
python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\trading-oms-pytest-slice026" backend\tests\test_order_intents.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 026 commit to remove the order-intent module, tests, docs, and slice status
updates.

## 11. Implementation steps

1. Add focused order-intent proposal tests.
2. Implement the non-routable proposal model and proposal book.
3. Add order-intent proposal documentation.
4. Update README and `docs/SLICES.md`.
5. Run focused and full verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Typed order-intent proposal records exist.
- Proposal status is explicitly non-routable.
- Risk-increasing proposals require a protective plan or approved exception reference.
- Duplicate proposal IDs and duplicate source signals are prevented.
- Every accepted proposal is journaled.
- Verification passes.
- No risk evaluation orchestration, approval decision, OMS transition, broker transport, order
  submission, HTTP mutation endpoint, credentials, or live-trading path is added.

## 13. Risks and assumptions

- Proposal records intentionally include order-intent fields such as side and quantity, but they do
  not contain broker routing or execution authority.
- Slice 027 will be responsible for converting proposals into risk-evaluation requests inside a
  deterministic simulation orchestration path.
