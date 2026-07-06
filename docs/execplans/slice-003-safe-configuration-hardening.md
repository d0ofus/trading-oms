# ExecPlan: Slice 003 safe configuration hardening

## 1. Goal

Create a strict backend configuration layer with validated safe defaults and hard failures for unsafe live-trading settings.

## 2. Non-goals

- Broker integration.
- Order submission.
- IBKR connectivity.
- Secret loading from `.env.local`.
- Production deployment.
- Risk engine.
- OMS.
- Event journal.

## 3. Safety constraints

- No live trading.
- No secrets.
- Default paper/simulation mode.
- Reject unsafe live-trading flags.
- Reject live IBKR account mode.
- Keep broker connectivity absent.
- Do not expose secret values through health responses.

## 4. Current state

Slice 002 introduced a minimal FastAPI backend and `Settings` dataclass. It validates `APP_MODE` as `paper` or `simulation` and rejects enabled live-trading flags. `.env.example` includes additional placeholder settings that are not yet modeled by the backend configuration.

## 5. Proposed design

- Expand `Settings` to include explicit `APP_ENV`, `APP_MODE`, `LIVE_TRADING_ENABLED`, `IBKR_HOST`, `IBKR_PORT`, and `IBKR_ACCOUNT_MODE`.
- Normalize and validate enum-like values.
- Reject public IBKR host binding, non-paper IBKR mode, invalid ports, invalid booleans, unknown app modes, and unsafe production/paper combinations.
- Keep Telegram and database secrets out of the structured settings for this slice.
- Update tests to cover defaults and hard failures.
- Update docs to describe safe configuration behavior.

## 6. Data model changes

None.

## 7. API changes

`GET /healthz` continues to return only non-secret safety posture metadata.

## 8. Test plan

- Unit tests for safe defaults.
- Unit tests for accepted simulation/test values.
- Unit tests rejecting live trading flags, live app mode, live IBKR mode, public IBKR host, invalid port, and unsafe production/paper combinations.
- Health endpoint test proving only non-secret safety posture is exposed.
- Existing frontend and scaffold checks.

## 9. Verification commands

- `make verify`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1`

## 10. Rollback plan

Revert the Slice 003 branch changes. No migrations, external services, secrets, broker connections, or trading behavior are introduced.

## 11. Implementation steps

1. Add config-hardening tests first.
2. Expand backend settings validation.
3. Update health endpoint and tests for non-secret posture.
4. Document safe configuration.
5. Mark Slice 003 ready for human review if verification passes.

## 12. Completion criteria

- Config defaults remain paper and live trading disabled.
- Unsafe live-trading config fails fast.
- IBKR account mode must be paper.
- IBKR host must remain localhost-only.
- Invalid values fail with clear config errors.
- Verification passes.
- No secrets, broker connectivity, or order paths are added.

## 13. Risks and assumptions

- This slice intentionally models only the safety-relevant config values already present in `.env.example`.
- Full secret-manager integration remains out of scope.
- Production deployment settings remain intentionally conservative and incomplete.
