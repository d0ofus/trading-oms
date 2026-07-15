# ExecPlan: Candidate Slice 062 external design-review handoff

## 1. Goal

Produce a deterministic, secret-scanned handoff for independent architecture, trading-safety, and
security review of the merged Candidate Slice 062 IBKR paper connector design. Bind the handoff to
merged commit `eafc3939f2c5cdc2a7fe09280381395e648bc28d`, tree
`d1074dd86dc6b03ce6683cf90d9f2bce7a2da723`, and the exact Candidate Slice 062 ExecPlan source.

The handoff will give reviewers reproducible provenance, explicit blocking questions, a findings
ledger, response fields, and an objective Candidate 063 entry gate. It will not claim that an
external review has occurred or authorize Candidate 063.

## 2. Non-goals

- Implementing Candidate 063 or changing application, broker-adapter, OMS, risk, approval,
  workflow, API, frontend, configuration, persistence, deployment, or runtime behavior.
- Adding or installing an IBKR SDK, dependency, connector, socket, callback listener, session,
  worker, endpoint, or UI control.
- Starting or contacting TWS or IB Gateway, authenticating, selecting an account, resolving a
  contract, requesting market data, transmitting or cancelling an order, or receiving a callback.
- Collecting paper-session evidence, running a bounded paper lab, deploying infrastructure,
  starting a controlled rollout, promoting readiness, or enabling live trading.
- Recording credentials, account identifiers, private operator values, tokens, passwords,
  certificates, private keys, raw broker messages, or other secrets.
- Treating an internally generated packet, passing tests, or a completed response template as
  independent acceptance.

## 3. Safety constraints

- Live trading remains disabled and unauthorized; no live route or live-order path may be added.
- Readiness remains `not_ready`, the decision remains `no_go`, external-review evidence remains
  `missing`, zero controlled-rollout evidence categories are verified, and all 14 categories remain
  blocking.
- Candidate 063 remains blocked until separate explicit human approval and attributable independent
  architecture, trading-safety, and security review of the exact merged Candidate 062 design.
- Every P0/P1 pre-review item remains open and blocking. Only a genuine reviewer response and a
  separately reviewed resolution may change that state.
- The handoff must contain no secret-shaped content, account identifiers, broker destinations,
  order-routing affordances, private values, or external-delivery mechanism.
- Review artifacts must distinguish internal preparation from independent review and must not
  overstate code, test, simulated, adapter-only, documented, or external evidence.
- Reproduction and verification must be local-only and must not open a network connection or read
  private environment values.
- The immutable Candidate Slice 062 source identities are:
  - commit `eafc3939f2c5cdc2a7fe09280381395e648bc28d`;
  - tree `d1074dd86dc6b03ce6683cf90d9f2bce7a2da723`;
  - plan path `docs/execplans/candidate-slice-062-ibkr-paper-connector-execplan.md`;
  - Git blob `e72d53b9ca85744809e91a3fdff97c42e41bfa7a`;
  - plan SHA-256 `b76575eaf048c13b91bc18ecb778c767b11d66da428d42ec9710ddfc1fade145`.

## 4. Current state

- Candidate Slice 062 was squash-merged as commit
  `eafc3939f2c5cdc2a7fe09280381395e648bc28d`; its merged tree exactly matches the reviewed branch
  tree.
- The Candidate Slice 062 ExecPlan selects the official native Python TWS API Latest 10.48 classic
  asynchronous architecture as a proposal, but no artifact, dependency, connector, or runtime
  integration exists.
- Candidate Slice 061 provides deterministic packet tooling that inventories an exact Git tree,
  dependencies, tests, verification evidence, documents, traceability, open findings, and all 14
  unresolved evidence categories. It writes canonical JSON plus a SHA-256 sidecar and rejects unsafe
  packet content.
- The Candidate Slice 061 packet is internally prepared and is not independently reviewed. Its
  baseline predates Candidate Slice 062 and therefore cannot serve as Candidate 062 design-review
  evidence.
- `docs/IBKR_PAPER_TRANSPORT_EXTERNAL_REVIEW.md` defines the external-review boundary, but no
  reviewer identity, dated disposition, accepted findings, or residual-risk record exists.
- No IBKR application-protocol connector, authenticated paper session, broker-originated callback,
  or real paper-order evidence exists.

## 5. Proposed design

Create `review/candidate-062/` as a self-contained handoff:

- `spec.json` will use the proven Candidate 061 packet schema while binding the complete manifest to
  the merged Candidate 062 commit and tree. Its traceability and findings will focus on the concrete
  connector design.
- `packet.json` will be generated deterministically by
  `trading_oms_backend.independent_review_packet`; `packet.sha256` will identify its exact canonical
  bytes.
- `REVIEW_GUIDE.md` will state the authorization boundary, exact plan path/blob/content digest,
  reviewer workflow, discipline-specific instructions, required questions, Candidate 063 gate, and
  reproducible commands.
- `REVIEW_RESPONSE_TEMPLATE.md` will provide explicit uncompleted fields for reviewer identity,
  role, review date, reviewed scope, disposition, residual risk, evidence examined, and finding
  dispositions. Empty or pending fields will remain visibly non-evidence.

The packet findings ledger will contain open blocking P0/P1 pre-review items for:

- exact official API 10.48 artifact filename, origin, version, SHA-256, license, redistribution,
  transitive dependencies, Python compatibility, and compatible TWS/Gateway build;
- authoritative paper-session proof, exactly-one-account handling, and private-value containment;
- dedicated client identity, order-ID ownership and persistence, opaque order references, durable
  outbox, dispatch ambiguity, restart recovery, and idempotency;
- callback ordering, duplication, conflict, fill/status correlation, protection state, local no-op
  alert limitations, disconnect/reconnect, and reconciliation gaps;
- local-only destination enforcement, public-exposure evidence, and emergency-stop interaction;
- independent architecture, trading-safety, and security acceptance of the complete design.

The review guide will require reviewers to record findings outside the immutable generated packet.
Review responses are attributable human records, not generated proof. Any P0/P1 finding, missing
discipline, incomplete identity/date/scope/disposition, or unaccepted residual risk keeps Candidate
063 blocked.

## 6. Data model changes

None. Review JSON and Markdown files are repository artifacts only; no runtime table, schema,
record, state transition, or persistence model changes.

## 7. API changes

None. No endpoint, CLI surface beyond the existing local packet generator, config key, network
interface, broker interface, workflow node, frontend control, or public runtime contract changes.

## 8. Test plan

- Add focused documentation/artifact tests that verify the exact merged commit, tree, plan path,
  Git blob, and plan SHA-256.
- Rebuild the packet twice and assert identical canonical bytes and SHA-256 output.
- Verify the checked-in packet with the local deterministic verifier and reject tampering.
- Assert all required architecture, trading-safety, and security review topics are represented.
- Assert the findings ledger has open blocking P0/P1 items covering SDK provenance, paper proof,
  private-value/account ambiguity, client/order identity, durable outbox/idempotency, callbacks,
  protection, reconnect, and reconciliation.
- Assert reviewer identity, role, date, scope, disposition, residual-risk, and evidence fields are
  explicitly pending and cannot be mistaken for a completed review.
- Assert Candidate 063 remains blocked on separate approval, three independent review disciplines,
  and resolution of every P0/P1 finding.
- Assert readiness is `not_ready`, external review is `missing`, all 14 evidence categories block,
  and zero are verified.
- Recursively scan the handoff for secret/account/private-value shapes, unsupported external URLs,
  broker destinations, live affordances, and order-routing fields.
- Assert the change adds no IBKR dependency, connector, socket, TWS/Gateway operation, broker
  request, callback listener, runtime configuration, deployment, rollout, or live capability.
- Run the existing Candidate 061 packet tests to ensure its immutable packet remains reproducible.

## 9. Verification commands

```powershell
$env:PYTHONPATH = (Resolve-Path .\backend\src).Path
python -m pytest backend\tests\test_candidate_slice_062_external_review_handoff.py -q
python -m pytest backend\tests\test_independent_review_packet.py -q
python -m trading_oms_backend.independent_review_packet verify --repository . --packet review/candidate-062/packet.json --digest review/candidate-062/packet.sha256
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
git diff --check
git diff --name-status eafc3939f2c5cdc2a7fe09280381395e648bc28d...HEAD
```

No command may install or import an IBKR SDK, open a broker socket, contact TWS/Gateway, read a
private value, submit a request, collect broker evidence, deploy, or start a rollout.

## 10. Rollback plan

Revert the single handoff commit. This removes the Candidate 062 review directory, focused tests,
this ExecPlan, and documentation references only. It does not alter the merged Candidate 062 design
or any runtime behavior.

If a private value, account identifier, external transmission, broker interaction, or unsupported
readiness claim is discovered, stop work, preserve relevant local evidence without reproducing the
sensitive value, remove the unsafe artifact through an explicitly reviewed incident response, and
keep Candidate 063 blocked.

## 11. Implementation steps

1. Add this ExecPlan as the first handoff file change.
2. Add failing-first focused tests for provenance, deterministic generation, review topics, response
   fields, blocking findings, safety scanning, and the Candidate 063 gate.
3. Add the Candidate 062 packet specification, review guide, and response template.
4. Generate canonical `packet.json` and `packet.sha256` using the existing local packet tooling.
5. Update `docs/SLICES.md`, `docs/SECURITY_BASELINE.md`, and README discoverability without changing
   runtime behavior or marking external review complete.
6. Run focused tests, repair documentation/artifact failures, and verify Candidate 061 remains
   unchanged and reproducible.
7. Run the full repository verifier and diff checks.
8. Self-review for trading safety, secret leakage, live-order prevention, provenance overclaim,
   determinism, scope creep, and maintainability; fix every P0/P1 finding.
9. Commit and push the dedicated handoff branch and create a PR when authentication permits.
10. Stop. Do not begin Candidate 063 or contact IBKR.

## 12. Completion criteria

- The handoff ExecPlan is the first file edit.
- A deterministic packet binds the complete source manifest to exact merged Candidate 062 commit
  `eafc3939f2c5cdc2a7fe09280381395e648bc28d` and tree
  `d1074dd86dc6b03ce6683cf90d9f2bce7a2da723`.
- The exact Candidate 062 plan path, Git blob, SHA-256, and source references are visible and tested.
- Official API 10.48 artifact/version/license/hash, architecture, trading-safety, security,
  paper-proof, private-value/account, client/order-ID, durable outbox/idempotency, callback,
  protection, reconnect, and reconciliation questions are explicit.
- The findings ledger contains open blocking P0/P1 pre-review items and cannot represent them as
  independently accepted.
- Reviewer identity, role, date, scope, disposition, residual risk, evidence, and finding-response
  fields are explicit and pending.
- Candidate 063 is objectively blocked on separate explicit approval, completed independent review
  by all three disciplines, and accepted resolution of all P0/P1 findings.
- Reproducible local commands and recursive safety scans are documented and tested.
- Readiness remains `not_ready`; external review remains `missing`; all 14 controlled-rollout
  evidence categories remain blocking; zero are verified.
- Focused and full verification pass.
- No dependency, connector, socket, TWS/Gateway operation, credential/account field, contract or
  market-data request, order path, callback listener, session, deployment, rollout, or live
  capability is added.
- Work stops before Candidate 063.

## 13. Risks and assumptions

- The Candidate 061 packet schema was designed for a broad baseline review. Reusing it is safe only
  if the Candidate 062 specification and human guide make the narrower design-review scope and
  source identities unmistakable.
- A deterministic packet proves artifact identity, not review independence, reviewer competence,
  source correctness, operational safety, or readiness.
- Official IBKR packaging, versions, licenses, and compatibility can change. Reviewers must assess
  the exact proposed 10.48 artifact; no automatic substitution or floating version is acceptable.
- A paper port or operator assertion may be insufficient paper-session proof. Any ambiguity remains
  blocking and prevents order-capable state.
- Broker callback and retrieval behavior can be incomplete, delayed, duplicated, out of order, or
  ambiguous. Design acceptance cannot replace future deterministic tests or separately approved
  bounded paper-lab evidence.
- Markdown response fields are intentionally mutable external-review working records. They must be
  signed or otherwise attributed through an approved process before they can become evidence, and
  any change in the reviewed source invalidates the baseline binding.
- The current local/no-op alert path and in-memory adapter idempotency are not sufficient for a
  concrete connector and remain explicit Candidate 063 blockers.
- Completion of this handoff does not constitute external review, Candidate 063 approval,
  production readiness, controlled rollout approval, paper-session evidence, or live-trading
  authorization.
