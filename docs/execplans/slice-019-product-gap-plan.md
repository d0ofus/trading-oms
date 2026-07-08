# ExecPlan: Slice 019 product gap plan

## 1. Goal

Create the post-Slice-018 product gap analysis and implementation queue so the repository can move
from safety foundation work into connected simulation, visual workflow building, paper-only IBKR
planning, and production-readiness planning through explicit human gates.

## 2. Non-goals

- No backend implementation changes.
- No frontend implementation changes.
- No API endpoints.
- No simulation mutation endpoints.
- No persistence layer.
- No React Flow dependency.
- No IBKR transport.
- No live trading.
- No production rollout.

## 3. Safety constraints

- Live trading remains disabled.
- No broker order-transmission path is introduced.
- No real credentials, account IDs, tokens, passwords, certificates, private keys, or secrets are
  introduced.
- IBKR transport requires separate explicit approval.
- Production rollout requires separate explicit approval, external review, and readiness evidence.
- Future order paths must pass risk before approval or execution.
- Future risk-increasing workflows must require human approval and append-only audit records.

## 4. Current state

Slices 001 through 018 are complete. The repository has local domain foundations for config,
journaling, replay, bar building, strategy signals, risk, fake broker behavior, OMS states,
approval tickets, alerts, UI shell, Strategy DSL, local visual builder preview, IBKR paper adapter
boundary, resilience checks, and live-readiness evaluation.

The app does not yet have connected backend read APIs, end-to-end simulation orchestration,
workflow persistence, Make.com-style graph editing, IBKR paper transport, production deployment, or
live trading.

## 5. Proposed design

- Add `docs/PRODUCT_GAP_ANALYSIS.md` to map stated goals to current gaps.
- Add Slice 019 through Slice 059 to `docs/SLICES.md`.
- Mark Slice 019 complete once this documentation slice is implemented and verified.
- Keep all future slices `not_started` unless separately approved by the human.
- Update README to include the gap analysis in the important files list.

## 6. Data model changes

None.

## 7. API changes

None.

## 8. Test plan

No code tests are required for this documentation-only slice. Run the repository verification gate
to prove the docs-only change does not break existing checks.

## 9. Verification commands

```powershell
.\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 019 commit to remove the product gap analysis, queue updates, README link, and
this ExecPlan.

## 11. Implementation steps

1. Add the product gap analysis.
2. Add the post-Slice-018 queue entries to `docs/SLICES.md`.
3. Add this ExecPlan.
4. Update README references.
5. Run verification.
6. Self-review safety boundaries.

## 12. Completion criteria

- Product gap analysis exists.
- Slice 019 through Slice 059 are represented in `docs/SLICES.md`.
- Future gates are explicit.
- No implementation behavior changes are made.
- Verification passes.

## 13. Risks and assumptions

- The plan is intentionally broad, so each future slice still needs a focused ExecPlan before
  implementation.
- The user has approved Gate A only through the request to implement this plan.
- Gates B through G remain blocked until separate explicit approval.
