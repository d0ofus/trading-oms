# ExecPlan: Slice 002 backend/frontend skeleton

## 1. Goal

Create a minimal backend and frontend application skeleton with real local and CI verification.

## 2. Non-goals

- Broker integration.
- Market data.
- Order submission.
- IBKR integration.
- Live trading.
- Secrets.
- Strategy engine.
- OMS.
- Risk engine.

## 3. Safety constraints

- No live trading.
- No secrets.
- Default paper/simulation mode.
- No broker connectivity.
- No order transmission path.
- No risk-increasing behavior.
- Keep unsafe live-mode configuration rejected.

## 4. Current state

The repository contains safety guidance, docs, prompts, CI scaffold, a Makefile, and a Windows verification script. No backend, frontend, tests, or real application checks exist yet.

## 5. Proposed design

- Add a small FastAPI backend under `backend/`.
- Add a safe config module with paper defaults and live-mode rejection.
- Add backend tests for config defaults and the health endpoint.
- Add a small React TypeScript frontend under `frontend/`.
- Add frontend lint, typecheck, and unit test scripts.
- Update `Makefile`, `scripts/verify.ps1`, CI, and README to run real checks.

## 6. Data model changes

None.

## 7. API changes

- Add backend HTTP health endpoint: `GET /healthz`.
- Add local verification commands for backend and frontend checks.

## 8. Test plan

- Backend unit tests for config defaults and unsafe live settings.
- Backend endpoint test for `/healthz`.
- Frontend unit test for displayed safety posture metadata.
- Frontend lint and TypeScript checks.
- Existing scaffold/security verification.

## 9. Verification commands

- `make verify`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1`

## 10. Rollback plan

Revert the Slice 002 branch changes. No data migrations, external services, secrets, or broker connections are introduced.

## 11. Implementation steps

1. Add backend tests and minimal backend package.
2. Add frontend tests and minimal frontend package.
3. Wire real verification commands.
4. Update README setup instructions.
5. Run verification and repair focused failures.
6. Self-review and red-team safety implications.
7. Mark Slice 002 ready for human review if acceptance criteria are met.

## 12. Completion criteria

- Backend skeleton exists.
- Frontend skeleton exists.
- Health endpoint exists.
- Config defaults to `APP_MODE=paper`.
- `LIVE_TRADING_ENABLED` defaults to `false`.
- Verification runs real checks where practical.
- CI runs `make verify`.
- No broker order transmission exists.
- No secrets are introduced.
- README explains local setup.

## 13. Risks and assumptions

- Local verification requires installing Python and Node dependencies.
- Windows users without `make` should use `scripts/verify.ps1`.
- Full production configuration hardening remains Slice 003.
