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
visibility for observability, retention, backup/restore posture, and incident response.

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

Live-readiness evidence and controlled rollout remain later approved work.
