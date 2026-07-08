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
- Keep Codex command network access disabled unless explicitly needed.

## Configuration

Use `.env.example` for placeholders only.
Use `.env.local` or a secret manager for local private values.
`*.local` files must not be committed.
Application config must default to paper or simulation mode, keep live trading disabled, keep IBKR account mode paper-only, and require localhost-only IBKR host values.
