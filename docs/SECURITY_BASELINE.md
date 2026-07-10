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

Authentication and authorization remain future Slice 054 work. Controlled rollout, emergency stop,
observability, backup/restore tooling, and live-readiness evidence remain later approved work.
