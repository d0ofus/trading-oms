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
- Keep Codex command network access disabled unless explicitly needed.

## Configuration

Use `.env.example` for placeholders only.
Use `.env.local` or a secret manager for local private values.
`*.local` files must not be committed.
