# ExecPlan: Candidate Slice 061 independent review packet

## 1. Goal

Produce a deterministic, secret-scanned independent-review packet for an external reviewer. Bind
the packet to the exact merged Candidate Slice 060 baseline commit
`2db249f7b7c239a7f09885d17f30cc8ba587afc0` and tree
`ae4caa823c99cf50a5a6f6cad744886d310b4c5e`. Include reproducible source, dependency, test,
verification, and evidence manifests; reviewed-document inventory; safety-control traceability;
pre-review findings; unresolved evidence; machine-readable metadata; and a human-readable guide.

The packet prepares material for independent review. It does not perform, commission, impersonate,
or claim completion of an independent review.

## 2. Non-goals

- Contacting, selecting, naming, or impersonating an external reviewer.
- Marking external-review or any other controlled-rollout evidence `verified`.
- IBKR connectivity, probes, protocol/SDK selection, authentication, contract lookup, orders,
  callbacks, paper sessions, or reconciliation against broker truth.
- Credentials, account identifiers, private operator information, tokens, passwords, certificates,
  private keys, or other private values.
- External integrations, uploads, downloads, remote evidence stores, deployment, controlled
  rollout, production operation, or evidence campaigns.
- Live trading, live account mode, live-order transport, or readiness promotion.
- Candidate Slice 062 or any later candidate.

## 3. Safety constraints

- Live trading remains disabled and unauthorized; readiness remains `not_ready` and the decision
  remains `no_go`.
- External-review evidence remains `missing`. Every missing, unverified, expired, or contradictory
  mandatory item remains blocking.
- The packet must say `not_independently_reviewed` and must not imply that self-recorded source,
  test, simulation, adapter, documentation, or runtime evidence is external evidence.
- Packet generation and verification are local filesystem/Git-object operations only. They must not
  open sockets, invoke broker adapters, call external services, or add an API endpoint.
- Packet output and its input specification must reject secret-shaped keys or assignments, account
  identifiers, private-value fields, unsafe URLs, broker-routing fields, live-order affordances,
  and any true live/transport authorization boolean.
- Source data included in the machine packet is limited to safe paths, sizes, classifications, and
  SHA-256 digests. Source contents and private environment values are not embedded.
- Existing risk, approval, OMS, duplicate prevention, stale-data, unknown-state, protection,
  reconciliation, emergency-stop, authorization, append-only journal, and paper-only gates remain
  unchanged.
- No IBKR TWS or Gateway API port may be contacted or exposed.

## 4. Current state

PR #41 is squash-merged into `origin/main` as commit
`2db249f7b7c239a7f09885d17f30cc8ba587afc0`; its tree exactly matches the reviewed Candidate Slice
060 branch. The worktree was clean when Candidate Slice 061 branched from that commit.

The untouched baseline passed `scripts/verify.ps1` on 2026-07-14: repository checks, formatting,
lint, compilation, 555 backend tests, frontend lint/typecheck and 60 tests, and four resilience
tests passed. The script still labels integration, replay-engine, and end-to-end commands as
placeholders; the packet must preserve that limitation.

The repository already has deterministic JSON and recursive unsafe-content scanning in
`audit_export.py`, but it has no Git-bound source/dependency/test/evidence manifest or independent
review packet. `POST_SLICE_059_REVIEW.md` defines Candidate 061 and the evidence gaps. Slice 060
corrected provenance and readiness contradictions, leaving zero verified evidence items, six
missing items, eight unverified items, and fourteen blockers.

## 5. Proposed design

Add a backend-local `independent_review_packet` module with no FastAPI integration. It will:

1. resolve an exact full baseline commit and tree through local `git` commands;
2. read tracked blobs from that commit rather than from the mutable working tree;
3. build a source manifest containing path, byte size, Git blob identity, and SHA-256 digest;
4. derive dependency, test, and reviewed-document inventories from baseline blobs;
5. combine those inventories with a checked-in packet specification containing the approved review
   scope, self-recorded baseline verification result, traceability matrix, pre-review findings, and
   fourteen unresolved checklist items;
6. calculate a SHA-256 digest for each manifest/ledger and produce stable, sorted JSON;
7. recursively scan the specification and packet for unsafe keys, values, URLs, booleans, and
   affordances before writing;
8. write a SHA-256 sidecar for the complete packet; and
9. independently verify the sidecar, baseline identity, every baseline blob digest, every nested
   manifest digest, safety scan result, review status, readiness posture, and unresolved evidence.

The checked-in packet specification is transparent reviewer input, not external evidence. A
human-readable guide explains how to reproduce and inspect the packet and states that an external
reviewer has not yet accepted it.

## 6. Data model changes

Add versioned local JSON schemas represented by validated Python data:

- packet metadata and baseline identity;
- source manifest;
- dependency manifest with declared constraints and lockfile-derived package versions;
- test manifest with test-file digests and definition counts;
- verification manifest with exact commands, observed pass counts, limitations, and self-recorded
  evidence classification;
- evidence/document manifest;
- safety-control traceability matrix;
- open pre-review findings ledger;
- unresolved controlled-rollout evidence register; and
- packet safety-scan record.

No database, journal, API read model, broker model, order state, or runtime configuration changes.

## 7. API changes

No HTTP API changes.

Add local CLI interfaces:

    python -m trading_oms_backend.independent_review_packet generate --repository . --spec review/candidate-061/spec.json --output review/candidate-061/packet.json --digest-output review/candidate-061/packet.sha256
    python -m trading_oms_backend.independent_review_packet verify --repository . --packet review/candidate-061/packet.json --digest review/candidate-061/packet.sha256

The CLI performs no network, broker, external-delivery, deployment, or mutation operation outside
writing the explicitly requested local packet files during `generate`.

## 8. Test plan

- Prove the baseline commit/tree must exactly match the specification.
- Prove source entries are sorted, complete, and hashed from baseline Git blobs, not working files.
- Prove dependency inventory covers Python declaration files and npm package/lock files without
  copying resolved URLs or integrity/private metadata.
- Prove test inventory covers backend and frontend test files and records definition counts.
- Prove reviewed documents exist in the baseline and retain documented/unverified classifications.
- Prove every nested manifest, traceability matrix, findings ledger, unresolved register, generator
  source, specification, complete packet, and sidecar has a reproducible SHA-256 digest.
- Prove the packet has all eight approved review-scope areas.
- Prove the findings ledger has severity, owner status, evidence references, blocking state, and
  resolution state without pretending to be an independent finding disposition.
- Prove all fourteen checklist categories are present, zero are verified, external review is
  missing, readiness is `not_ready`, and all fourteen remain blocking.
- Parameterize secret-shaped data, account identifiers, private-value fields, unsafe URLs,
  broker-routing fields, order affordances, and unsafe booleans and prove generation fails closed.
- Prove tampered packet bytes, sidecar, baseline blobs, nested digests, and review/readiness status
  fail verification.
- Prove CLI generate/verify behavior is local and deterministic.
- Preserve full existing verification.

## 9. Verification commands

    python -m pytest backend\tests\test_independent_review_packet.py -q
    $env:PYTHONPATH = "backend/src"
    python -m trading_oms_backend.independent_review_packet verify --repository . --packet review/candidate-061/packet.json --digest review/candidate-061/packet.sha256
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1

## 10. Rollback plan

Revert the single Candidate Slice 061 commit. This removes only local packet tooling, tests,
specification, generated packet/sidecar, guide, ExecPlan, and documentation references. No runtime
state, database, external system, broker session, deployment, account, private value, or production
artifact requires rollback.

## 11. Implementation steps

1. Add failing tests for exact baseline identity, deterministic manifests/digests, required packet
   sections, fail-closed scanner behavior, unresolved evidence, and tamper detection.
2. Implement local Git-object reading, canonical JSON/digest helpers, packet validation, generation,
   verification, and CLI parsing.
3. Add the Candidate 061 specification with the approved scope, baseline verification result,
   reviewed-document inventory, traceability, pre-review findings, and unresolved evidence.
4. Generate and verify the machine packet and SHA-256 sidecar.
5. Add the human review guide and update README/SLICES/security documentation.
6. Run focused tests and full verification; fix failures.
7. Self-review every changed file for secret leakage, evidence overclaim, mutable identities,
   readiness promotion, broker/rollout behavior, authorization bypass, and scope creep.
8. Commit and push the dedicated branch; create a PR if authenticated, otherwise report exact
   manual commands and URL.
9. Stop without beginning Candidate Slice 062 or any external, broker, deployment, campaign,
   rollout, production, or live work.

## 12. Completion criteria

- A machine-readable packet and human-readable guide exist and are tied to commit `2db249f...` and
  tree `ae4caa...`.
- Source, dependency, test, verification, and evidence manifests are complete for their documented
  scope, deterministically ordered, and protected by SHA-256 digests.
- The reviewed-document inventory, eight-area traceability matrix, open findings ledger, and all
  fourteen unresolved checklist items are explicit and reproducible.
- The sidecar and verifier detect packet, manifest, baseline, or digest tampering.
- The packet and guide say no independent review has yet occurred or been accepted.
- Readiness remains `not_ready`; external-review evidence remains `missing`; zero items are
  verified; all fourteen mandatory items remain blocking.
- The packet passes its secret/unsafe-content scan and contains no private values or action paths.
- Focused and full verification pass.
- No HTTP endpoint, broker operation, external integration, deployment, rollout, production
  operation, evidence campaign, live-order path, credential, account identifier, or safety-gate
  bypass is introduced.

## 13. Risks and assumptions

- SHA-256 manifests establish artifact identity, not correctness or independent acceptance.
- The baseline verification result is a local self-recorded observation from the clean baseline;
  an external reviewer must reproduce it and may reach a different result.
- Python dependencies declare bounded ranges but are not fully locked; the dependency manifest must
  expose that limitation rather than imply a reproducible resolved Python environment.
- npm lock data is useful supply-chain inventory but does not constitute a vulnerability review.
- Test-definition counts are structural inventory and differ from executed case counts because of
  parameterization; both values must be labeled accurately.
- The packet generator is added after the frozen baseline. Its own source/specification hashes and
  Candidate Slice 061 review are required before relying on it.
- Existing Git objects are assumed available locally. Missing objects or a commit/tree mismatch
  must fail closed rather than falling back to the working tree or network.
- The post-Slice-059 review contains a historical contradiction that Slice 060 corrected; the
  generated packet must use current Slice 060 provenance/readiness semantics.
- GitHub CLI authentication may still be unavailable after a successful Git push.
