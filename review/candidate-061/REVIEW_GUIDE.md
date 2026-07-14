# Candidate Slice 061 Independent Review Guide

## Review boundary

This internally prepared packet is **not independently reviewed**. External-review evidence remains missing. Current result: `not_ready`. Current decision: `no_go`.

The packet is bound to immutable Slice 060 baseline commit `2db249f7b7c239a7f09885d17f30cc8ba587afc0` and tree `ae4caa823c99cf50a5a6f6cad744886d310b4c5e`. It inventories that complete Git tree; it does not claim that the current working tree or a later revision was reviewed.

The packet does not authorize paper-production operation, deployment, rollout, broker connectivity, order transmission, or live trading. It contains no broker routing, account values, credentials, external delivery, or network integration. All 14 controlled-rollout evidence categories remain blocking.

## Reviewer entry point

1. Confirm the baseline commit and tree independently with the commands listed in `packet.json`.
2. Verify `packet.sha256`, then run the local packet verifier to reproduce every manifest from the baseline Git objects.
3. Review the eight entries in `review_scope`, using `traceability.controls` to locate implementation and test evidence.
4. Assess every open item in `findings.items`; these are internal pre-review findings, not independent conclusions.
5. Assess every item in `unresolved_evidence.items`. Missing or unverified evidence remains blocking and must not be inferred from documentation or local tests.
6. Record findings outside this immutable packet with reviewer identity, evidence examined, severity, and disposition.

## Artifact inventory

- `spec.json`: human-maintained, safety-validated input describing scope, traceability, known findings, and unresolved evidence.
- `packet.json`: deterministic machine-readable packet generated from the spec and exact baseline Git objects.
- `packet.sha256`: SHA-256 identity for the canonical packet bytes.
- `REVIEW_GUIDE.md`: this human review procedure and authorization boundary.

The source manifest covers every tracked blob in the baseline tree. Dependency, test, verification, and evidence manifests carry their own canonical content digests. The tooling section binds the packet to the generator and specification hashes.

## Reproduction

From the repository root, make the backend package importable in the same manner used by repository verification, then execute:

```powershell
python -m trading_oms_backend.independent_review_packet verify --repository . --packet review/candidate-061/packet.json --digest review/candidate-061/packet.sha256
```

Run the complete repository gate separately:

```powershell
.\scripts\verify.ps1
```

A successful local verifier result establishes artifact identity and deterministic reproduction only. It is not independent acceptance, operational evidence, a security certification, or a readiness decision.

## Required disposition

The only valid current disposition is no-go. Independent review remains a human and external process. Findings must be resolved through separately approved work, and evidence must be collected with attributable provenance before any readiness reconsideration.

Candidate Slice 062 is outside this packet and must not begin without its own explicit approval. Completion of Candidate Slice 061 does not authorize it.
