# ExecPlan: Candidate Slice 063 entry-gate audit

## 1. Goal

Audit the Candidate 063 entry criteria against the exact authoritative `main` tree after PR 54 and
publish a durable, fail-closed gate decision. If any prerequisite is absent, stop before adding an
IBKR dependency, connector, socket, session, callback listener, request path, or paper lab.

## 2. Non-goals

- Candidate 063 implementation.
- Installing or vendoring the IBKR SDK.
- Contacting TWS, IB Gateway, IBKR, or any broker endpoint.
- Adding credentials, account identifiers, host or port controls, or private values.
- Authorizing a paper lab, deployment, production rollout, or live trading.
- Waiving, fabricating, or self-approving independent review evidence.

## 3. Safety constraints

- Live trading remains disabled and unauthorized.
- The Candidate 062 review packet is immutable and must be assessed against its recorded digest.
- A missing, pending, ambiguous, unattributed, stale, or internally generated review remains
  insufficient evidence.
- Every open P0 or P1 finding keeps Candidate 063 blocked.
- The audit may add documentation and documentation tests only.

## 4. Current state

GitHub reports PR 54 squash-merged into `main` as
`197009c2af0146d96faad95468785a422a0aa5fe`. Its tree
`06a174b7b9109c6662e0147dea8fce308d3a9663` exactly matches the verified local candidate tree used
for this audit.

The Candidate 062 handoff says external review is missing, readiness is `not_ready`, the decision is
`no_go`, all fourteen rollout evidence categories are blocking, and zero are verified. The review
directory contains only the immutable packet, digest, guide, specification, and an uncompleted
response template.

## 5. Proposed design

Add `docs/CANDIDATE_063_GATE_AUDIT.md` with:

- immutable baseline and packet identities;
- a requirement-by-requirement gate matrix;
- the eight open P0/P1 findings and fourteen unresolved evidence categories;
- an explicit `blocked` / `no_go` decision;
- confirmation that no connector work was authorized or added; and
- the smallest legitimate next action: three attributable independent reviews against the
  unchanged packet, followed by accepted finding dispositions and a separate implementation-only
  human approval.

Add a focused documentation test that parses the report and proves the fail-closed decision and
prohibited implementation boundary remain explicit.

## 6. Data model changes

None. No runtime model, persistence schema, journal schema, configuration model, or API payload
changes.

## 7. API changes

None. No HTTP, WebSocket, CLI, broker, SDK, callback, or UI surface changes.

## 8. Test plan

- First add a focused test that requires the gate report and its fail-closed markers.
- Confirm the test fails while the report is absent.
- Add the report and rerun the focused test.
- Verify the immutable packet digest and recorded source identities.
- Run the full repository verification command.
- Scan the diff for SDK, socket, credential, account, live, transport, and implementation changes.

## 9. Verification commands

```powershell
$env:PYTHONPATH = (Resolve-Path .\backend\src).Path
python -m pytest backend\tests\test_candidate_063_gate_audit.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
git diff --check
```

## 10. Rollback plan

Revert the documentation-only candidate commit. No runtime state, persistence, broker state,
external session, or dependency is created.

## 11. Implementation steps

1. Bind the audit to the authoritative PR 54 merge commit and exact tree.
2. Read the repository guidance, Candidate 062 ExecPlan, review guide, packet, digest, and response
   template.
3. Add the focused failing documentation test.
4. Add the gate report with exact pass, fail, and missing evidence.
5. Run focused and full verification.
6. Perform P0/P1 trading-safety, secret-leakage, false-attribution, and scope review.
7. Commit and publish only the documentation/test branch, open an unmerged PR, and verify CI on the
   exact remote head.
8. Stop before Candidate 063 implementation.

## 12. Completion criteria

- The report covers every explicit Candidate 063 entry criterion.
- Missing review evidence and all open P0/P1 findings remain blocking.
- The next action is concrete and does not imply self-review can satisfy independence.
- Focused and full verification pass.
- No IBKR dependency, connector, socket, session, request, callback listener, private value,
  deployment, rollout, or live capability is added.
- The exact candidate branch is published through an unmerged PR with green CI.

Verification evidence:

- The new focused test first failed four tests because the report and queue entry did not exist.
- The completed focused gate-audit test passes four tests.
- The Candidate 062 packet digest matches its checked-in digest and the independent-review packet
  verifier returns `verified_local_artifact_identity`.
- The combined handoff and gate-audit suite passes fourteen tests.
- Full verification passes 695 backend tests, 171 frontend tests, and four resilience tests, plus
  formatting, lint, type, repository, and security checks.
- P0/P1 self-review found no runtime, dependency, configuration, immutable-packet, secret,
  false-attribution, broker-contact, paper-lab, rollout, or live-capability change.

## 13. Risks and assumptions

- The Git sandbox cannot authenticate Git transport, so the authoritative commit and tree are
  obtained through authenticated GitHub API calls. The local baseline tree must match the remote
  tree exactly before editing.
- A merged plan, green CI, internal self-review, or completed template is not independent review.
- This audit does not decide the technical merits of the proposed connector. It only tests whether
  the repository's own entry gate is satisfied.
