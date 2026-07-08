# Configuration

The application configuration layer is safety-first. Defaults must keep the system in a non-live posture.

## Safe defaults

- `APP_ENV=development`
- `APP_MODE=paper`
- `LIVE_TRADING_ENABLED=false`
- `IBKR_HOST=127.0.0.1`
- `IBKR_PORT=7497`
- `IBKR_ACCOUNT_MODE=paper`

## Validation rules

- `APP_ENV` must be `development`, `test`, or `production`.
- `APP_MODE` must be `paper` or `simulation`.
- `LIVE_TRADING_ENABLED` must parse as a boolean and must remain `false`.
- `IBKR_ACCOUNT_MODE` must be `paper`.
- `IBKR_HOST` must be localhost-only: `127.0.0.1`, `localhost`, or `::1`.
- `IBKR_PORT` must be an integer TCP port from `1` through `65535`.
- `APP_ENV=production` requires `APP_MODE=simulation`.

These checks are startup safety checks only. They do not add broker connectivity, order submission, OMS behavior, or live trading.

## Live-readiness gate

The live-readiness checker is an audit artifact only. It can evaluate and journal checklist evidence,
but it cannot override configuration safety checks or enable live trading. Truthy
`LIVE_TRADING_ENABLED` values continue to fail configuration validation.

## IBKR paper adapter checks

The Slice 016 IBKR paper adapter adds an adapter-local configuration boundary on top of `Settings`.
`IbkrPaperAdapterConfig` accepts only known local paper ports:

- `7497`: TWS paper trading API port.
- `4002`: IB Gateway paper trading API port.

The adapter rejects live trading, non-paper account mode, non-localhost hosts, and non-paper ports.
It still does not connect to TWS or IB Gateway and does not submit orders.

## Secret handling

Do not commit real secrets. Keep `.env.example` limited to placeholders and safe defaults. Use local secret files or a secret manager for private values, and keep those files out of git.
