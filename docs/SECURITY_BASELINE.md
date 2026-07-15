# Security Baseline

## Secrets

Never commit:

- broker credentials;
- IBKR account identifiers;
- Telegram tokens;
- OpenAI keys;
- GitHub tokens;
- passwords;
- private keys;
- certificates;
- production database URLs.

## Network

- Do not expose IBKR TWS or Gateway API ports to the public internet.
- Prefer localhost-only broker connectivity.
- IBKR paper adapter configuration may use only localhost and known paper ports `7497` or `4002`.
- Resilience and chaos tests must remain local and must not open broker or market-data network connections.
- Keep Codex command network access disabled unless explicitly needed.

## Configuration

Use `.env.example` for placeholders only.
Use `.env.local` or a secret manager for local private values.
`*.local` files must not be committed.
Application config must default to paper or simulation mode, keep live trading disabled, keep IBKR account mode paper-only, and require localhost-only IBKR host values.
Live-readiness evaluation must remain an audit/checklist mechanism only and must not override disabled live-trading configuration.

## Production-Like Paper Planning

`docs/DEPLOYMENT_AND_SECRETS_MANAGEMENT_PLAN.md` is a planning boundary only.

Planning only: this document does not approve production rollout.

Live trading remains disabled.

No live broker order path may be introduced.

Production-like paper operation requires separate explicit human approval and external review.

No real broker credentials, account identifiers, passwords, certificates, private keys, tokens, or secrets may be committed, logged, displayed, exported, or stored in repository files.

IBKR TWS or Gateway API ports must never be exposed to the public internet.

## Authentication And Authorization

Slice 054 adds a local operator authentication and authorization foundation. Slice 055 hardens
local operator roles and approval permissions only. Slice 056 adds a local emergency stop for
simulation and paper-mode risk-increasing work. Slice 057 adds read-only local operating-control
visibility for observability, retention, backup/restore posture, and incident response. Slice 058
adds read-only live-readiness evidence visibility for missing evidence, external review, explicit
human approval, and final-review blockers.

It is not production authentication and does not add passwords, bearer tokens, cookies, OAuth,
API keys, certificates, private keys, identity-provider secrets, broker credentials, account
identifiers, live trading, or production rollout.

Production mode must not silently trust local header authentication.

Authorization decisions for privileged local actions should be journaled without recording secrets,
broker credentials, account identifiers, broker hosts, or broker ports.

Simulation approval requires the dedicated local `approver` role. Local `admin` operators may
administer workflow definitions and saved simulation workflow runs, but cannot approve or reject
simulation tickets. A local identity cannot combine `admin` and `approver` roles.

Emergency stop activation/deactivation is local admin-only, journaled, and blocks risk-increasing
simulation or paper-mode work while active. It does not add broker-side liquidation, live cancel,
live flatten, live order submission, broker transport, production rollout, credentials, account
identifiers, or secrets.

Slice 057 operating controls are not production observability, backup execution, restore execution,
audit deletion, external storage, external incident tooling, or production rollout.

Slice 058 live-readiness evidence is not live-trading approval, controlled rollout approval,
external review completion, or authorization to change disabled live-trading configuration.

Slice 059 adds a fail-closed controlled paper-production rollout checklist. It records current
evidence as `not_ready`; it does not approve, automate, or start a rollout.

Checklist completion cannot authorize production operation or live trading. Any future rollout
work remains subject to a separate explicit human approval, independent review, and new ExecPlan.

## Independent Review Packet

Candidate Slice 061 adds a local, deterministic review packet tied to the exact merged Candidate
Slice 060 commit and tree. The packet contains only repository-derived manifests, internal
pre-review findings, unresolved evidence, and reproducible local commands.

Packet generation and verification do not use a network, API, external upload, broker transport,
account identifier, private value, credential, deployment mechanism, or order path. Recursive
safety validation rejects those affordances from machine-readable packet content.

A valid packet digest establishes local artifact identity only. It is not independent review,
security certification, evidence acceptance, production-readiness approval, paper-production
rollout approval, or live-trading authorization. External-review evidence remains missing, all 14
controlled-rollout evidence categories remain blocking, and the required decision remains
`not_ready` / `no_go`.

## Candidate Slice 062 Connector Planning

Candidate Slice 062 is connector planning only. Its proposed dependency is the official native
Python client from TWS API Latest 10.48, subject to exact artifact hash, license, dependency,
compatibility, and external design review before any later implementation.

Candidate Slice 062 does not add an SDK, broker connection, authenticated session, or order path.
It does not add a socket call, callback listener, credential/account field, config key, endpoint,
paper session, contract or market-data request, deployment, rollout, production operation, or live
capability.

Any later connector must remain default-off, paper-only, and localhost-only on `7497` or `4002`.
Paper configuration and a paper port do not prove session mode. Account identifiers must remain
transient private memory and must never enter repository files, persistence, logs, metrics, traces,
errors, screenshots, tests, exports, alerts, or review packets. Zero or multiple accessible
accounts, unproven paper mode, stale data, unknown broker state, or any reconciliation discrepancy
must block risk-increasing work.

External-review evidence remains missing. Candidate Slice 062 is not external review or
paper-session evidence. Readiness remains `not_ready`, the decision remains `no_go`, zero
controlled-rollout evidence categories are verified, and all 14 remain blocking. Candidate 063
requires separate explicit approval and accepted architecture, trading-safety, and security review.

## Candidate Slice 062 External Design-Review Handoff

The handoff at `review/candidate-062/REVIEW_GUIDE.md` binds a deterministic packet to the exact
merged Candidate Slice 062 commit, tree, plan Git blob, and plan SHA-256. It carries internal
pre-review P0/P1 findings, discipline-specific questions, an attributable response template, and
reproducible local verification commands. Recursive scanning covers machine-readable and human
handoff artifacts for secret-shaped, account-shaped, private-data, external-URL, broker-routing,
and live-affordance content.

The handoff is internally prepared and is not independently reviewed. It is not a security
certification, implementation approval, paper-session record, broker evidence, readiness decision,
deployment approval, or rollout approval. Readiness remains `not_ready`; external-review evidence
remains `missing`; all 14 controlled-rollout evidence categories remain blocking; zero are verified.

Candidate 063 remains blocked until separate explicit human approval, completed attributable
architecture/trading-safety/security review against unchanged source, independent acceptance of
every P0/P1 resolution and residual risk, and every Candidate 062 entry criterion. The handoff adds
no IBKR dependency, connector, socket, TWS/Gateway operation, credential/account field, broker
request, callback listener, deployment, rollout, production operation, or live capability.
