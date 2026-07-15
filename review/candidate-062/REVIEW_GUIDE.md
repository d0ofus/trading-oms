# Candidate Slice 062 External Design-Review Handoff

## Review boundary

This handoff was prepared internally and has **not** been independently reviewed. The external review remains `missing`.
Readiness remains `not_ready`; the decision remains `no_go`; all 14 controlled-
rollout evidence categories remain blocking and zero are verified.

This packet requests design review only. It provides no broker contact, SDK installation,
TWS/Gateway operation, authenticated paper session, contract or market-data request, order request,
callback, deployment, rollout, production operation, or live capability. There is no live trading.
The machine-checkable scope marker is `no_ibkr_dependency_or_runtime_change`.

Candidate 063 remains blocked. This handoff does not approve its implementation, an IBKR
connection, a paper lab, or any later activity.

## Immutable reviewed source

- Merged Candidate 062 commit: `eafc3939f2c5cdc2a7fe09280381395e648bc28d`
- Complete Git tree: `d1074dd86dc6b03ce6683cf90d9f2bce7a2da723`
- Plan path: `docs/execplans/candidate-slice-062-ibkr-paper-connector-execplan.md`
- Plan Git blob: `e72d53b9ca85744809e91a3fdff97c42e41bfa7a`
- Plan SHA-256: `b76575eaf048c13b91bc18ecb778c767b11d66da428d42ec9710ddfc1fade145`
- Merge subject: `Plan Candidate Slice 062 IBKR paper connector (#43)`

Reviewers must reproduce these identities before reviewing. A change to any reviewed source changes
the commit or tree and invalidates this handoff. Review comments against a later working tree are not
responses to this packet.

## Artifact inventory

- `spec.json`: internal review scope, source references, traceability, pre-review findings, and all
  unresolved evidence categories.
- `packet.json`: canonical deterministic packet generated from the specification and exact merged
  Git objects.
- `packet.sha256`: SHA-256 identity of the canonical packet bytes.
- `REVIEW_GUIDE.md`: this reviewer procedure, question set, and authorization boundary.
- `REVIEW_RESPONSE_TEMPLATE.md`: attributable response fields. A blank or pending template is not
  evidence.

The generated packet inventories the full baseline tree and carries separate source, dependency,
test, verification, and evidence manifests. It proves reproducible identity only; it does not prove
the design safe or the review independent.

The packet's `candidate_061_packet_v1` safety-policy value names the unchanged scanner schema first
introduced in Candidate 061. It does not identify this packet's source baseline; the `baseline`,
source manifest, and exact plan identities above do that.

## Required reviewers

### Architecture reviewer

Assess SDK containment, session and reader lifecycle, thread/queue ownership, state transitions,
durable dispatch, callback correlation, crash recovery, disconnect/reconnect, reconciliation, and
failure containment. Confirm that every unknown or ambiguous state blocks new risk.

### Trading-safety reviewer

Assess risk-before-approval-before-OMS ordering, immutable request binding, duplicate prevention,
market-data freshness, order identity, protection sequencing, partial-fill exposure, missing-
protection escalation, emergency-stop interaction, and reconciliation before risk increases.

### Security reviewer

Assess exact SDK provenance and license handling, localhost enforcement, public-exposure
prohibition, paper-session proof, exactly-one-account handling, sensitive data containment,
redaction, journal and error payloads, operator boundaries, and no-live-path claims.

One person may not silently satisfy multiple disciplines. The response must state each reviewer's
identity, role, competence, scope, date, evidence examined, disposition, and residual-risk decision.
Missing or ambiguous attribution keeps the gate closed.

## Blocking review questions

Every question requires a written disposition and evidence references. An unanswered question or
an unaccepted answer remains a blocking P0/P1 finding.

### `Q-SDK-01` - official API 10.48 provenance

What exact official native Python TWS API 10.48 artifact filename and version will Candidate 063
use? Record its independently obtained SHA-256, license and redistribution treatment, transitive
dependencies, Python 3.12 compatibility result, and compatible TWS/Gateway build. Explain how CI
and developers obtain the artifact without floating to a public registry or silently changing it.

### `Q-PAPER-01` - authoritative paper proof

What evidence makes an order-capable session provably paper-only beyond a configured paper port?
Explain how the connector remains unable to dispatch while proof is absent, contradictory, stale,
or ambiguous. Explain why the proposed proof is authoritative enough for the failure model.

### `Q-IDENTITY-01` - session, account ambiguity, and order identity

Is the dedicated nonzero client ID safe for the intended topology? How are persistent order-ID
allocation, collisions with other clients, reconnect sequences, exactly-one-account enforcement,
and account ambiguity handled? Confirm that sensitive broker values remain transient and excluded
from repository artifacts, journals, logs, errors, metrics, traces, alerts, exports, and review
evidence.

### `Q-OUTBOX-01` - durable dispatch and idempotency

Does the durable outbox establish an atomic, reconstructable boundary between the approved OMS
request and the single broker dispatch attempt? Review crash points before, during, and after
dispatch; timeout ambiguity; restart recovery; opaque correlation; duplicate suppression; and the
rule prohibiting automatic retry before reconciliation establishes broker truth.

### `Q-CALLBACK-01` - callbacks and broker truth

Are status, execution, commission, rejection, error, and connection callbacks durably recorded
before derived OMS changes? Review ordering, duplication, conflicts, stale callbacks, late fills,
unknown references, queue overflow, reader failure, day-boundary gaps, and differences between
local expectation and broker truth.

### `Q-PROTECTION-01` - protection and partial exposure

Does the proposed bracket/transmit sequence minimize unprotected exposure without asserting
atomicity the broker does not provide? Review partial fills, child rejection or cancellation,
quantity mismatch, delayed acknowledgement, restart, missing expected protection, critical local
alerting, the current no-op delivery limitation, and the prohibition on automatic flatten or global
cancel behavior.

### `Q-RESILIENCE-01` - disconnect, reconnect, and reconciliation

Does every disconnect, protocol error, reader failure, unknown callback, retrieval-window gap,
position mismatch, order mismatch, and account change force reconciliation and block new risk?
Review daily reset behavior, broker resubmission settings, durable checkpoint recovery, complete
comparison sources, operator resolution, and the evidence required to leave unknown state.

### `Q-SECURITY-01` - local-only and sensitive-data controls

Can literal and resolved destinations ever reach LAN, VPN, container-bridge, wildcard, proxy,
redirect, remote, or public interfaces? Review startup and drift checks, no-public-exposure evidence,
SDK diagnostics, exception sanitization, operator access, packet captures, support artifacts,
emergency-stop behavior, and failure paths that could reveal sensitive data or bypass paper-only
controls.

## Findings ledger procedure

The packet contains eight internally identified open findings:

| Finding | Severity | Required disposition |
| --- | --- | --- |
| `c062_001_sdk_provenance` | P1 | Accept exact provenance controls or require changes. |
| `c062_002_paper_proof_and_account_ambiguity` | P0 | Accept authoritative fail-closed proof and ambiguity handling or block. |
| `c062_003_client_order_identity_and_outbox` | P0 | Accept identity, persistence, outbox, recovery, and idempotency or block. |
| `c062_004_callbacks_and_protection` | P0 | Accept callback and protection behavior or block. |
| `c062_005_reconnect_and_reconciliation` | P0 | Accept recovery and broker-truth reconciliation or block. |
| `c062_006_network_and_private_data` | P0 | Accept local-only and sensitive-data controls or block. |
| `c062_007_alert_and_emergency_response` | P1 | Accept operator and emergency limitations or require changes. |
| `c062_008_independent_review_absent` | P0 | Remains open until all required independent reviews are attributable and accepted. |

These are internal pre-review findings, not conclusions from an independent reviewer. Reviewers may
raise additional findings. Every response must carry severity, evidence, owner, proposed resolution,
verification method, disposition, and accepted residual risk. Every P0/P1 finding must be resolved
and accepted against the unchanged source before Candidate 063 can be reconsidered.

## Candidate 063 entry gate

Candidate 063 remains blocked until all of the following are true:

The gate requires all three review disciplines and every P0/P1 finding to receive an attributable,
accepted disposition against unchanged source.

1. The exact reviewed source identities above still match.
2. A separate explicit human approval authorizes Candidate 063 implementation only.
3. All three review disciplines submit attributable completed responses.
4. Every P0/P1 finding, including newly raised findings, is resolved and independently accepted.
5. Each accepted residual risk names its owner, scope, expiry or review trigger, and rationale.
6. The official API artifact, digest, license, dependencies, Python compatibility, and compatible
   TWS/Gateway build are pinned and accepted.
7. Paper proof, client/order identity, outbox, callback, protection, reconnect, reconciliation,
   sensitive-data, local-only, alert, emergency, and test designs are accepted.
8. The resulting implementation plan still has no broker contact or paper-lab authorization.

If reviewed source changes, this packet is stale: regenerate the handoff for the new immutable
commit and repeat the affected reviews. A merge, green CI, internal self-review, or completed
template alone cannot open the gate.

## Reproduction

Run from the repository root with the backend package available in the same local environment used
by repository verification:

```powershell
git rev-parse eafc3939f2c5cdc2a7fe09280381395e648bc28d^{commit}
git show -s --format=%T eafc3939f2c5cdc2a7fe09280381395e648bc28d
git rev-parse eafc3939f2c5cdc2a7fe09280381395e648bc28d:docs/execplans/candidate-slice-062-ibkr-paper-connector-execplan.md
$env:PYTHONPATH = (Resolve-Path .\backend\src).Path
python -m trading_oms_backend.independent_review_packet verify --repository . --packet review/candidate-062/packet.json --digest review/candidate-062/packet.sha256
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

The packet verifier performs canonical reconstruction and recursive unsafe-content checks. The
focused handoff tests additionally scan all files under `review/candidate-062/` for secret-shaped,
account-shaped, private-data, external-URL, broker-destination, and live-affordance content.

Successful reproduction means `verified_local_artifact_identity` only. It is not independent
acceptance, external evidence, paper evidence, a security certification, readiness promotion,
Candidate 063 approval, rollout approval, or live-trading authorization.

## Required response

Use `REVIEW_RESPONSE_TEMPLATE.md` without changing this immutable packet. Keep each field `pending`
until a named reviewer supplies an attributable decision. Store the completed response through the
approved human review process, scan it before repository inclusion, and bind any accepted response
to this exact packet SHA-256.
