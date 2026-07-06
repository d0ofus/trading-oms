# Slices

This file is the durable slice queue for Codex.

Codex may autonomously execute only the single slice marked `approved_for_autonomous_run: true`.

Codex must not mark the next slice approved unless the human explicitly asks it to.

## Status values

- `not_started`
- `approved_for_autonomous_run`
- `in_progress`
- `ready_for_human_review`
- `complete`
- `blocked`

---

## Slice 001 — repo operating system and Codex guidance

status: `complete`

Goal:
Create repo guidance, docs, CI scaffold, verification scripts, and conservative Codex configuration.

Completion evidence:
- `AGENTS.md` exists.
- `PLANS.md` exists.
- `.codex/config.toml` exists.
- `docs/` guidance exists.
- `scripts/verify.ps1` or equivalent exists.
- `make verify` or Windows verification command passes.

---

## Slice 002 — backend/frontend skeleton with real verification

status: `approved_for_autonomous_run`

branch: `slice-002-backend-frontend-skeleton`

Goal:
Make the repo ready for application development with a minimal backend, minimal frontend, and real local/CI verification.

Scope:
- backend Python project skeleton;
- FastAPI health endpoint;
- safe config model;
- pytest tests for health/config behavior;
- frontend React TypeScript skeleton;
- frontend lint/typecheck/test command where practical;
- Makefile commands should run real checks where practical;
- CI should run `make verify`;
- README should explain local setup.

Non-goals:
- broker integration;
- market data;
- order submission;
- IBKR;
- live trading;
- secrets;
- strategy engine;
- OMS;
- risk engine.

Acceptance criteria:
- [ ] Backend skeleton exists.
- [ ] Frontend skeleton exists.
- [ ] Health endpoint exists.
- [ ] Config defaults to `APP_MODE=paper`.
- [ ] `LIVE_TRADING_ENABLED` defaults to `false`.
- [ ] `make verify` runs real checks where practical.
- [ ] CI can run `make verify`.
- [ ] No code path can transmit broker orders.
- [ ] No secrets are introduced.
- [ ] Docs are updated if setup changes.

Verification commands:

```bash
make verify
```

On Windows without `make`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

---

## Slice 003 — safe configuration hardening

status: `not_started`

Goal:
Create a strict application configuration layer with validated safe defaults, explicit app mode, and hard failure for unsafe live-trading settings.

---

## Slice 004 — append-only event journal

status: `not_started`

Goal:
Add an append-only event journal foundation for auditability.

---

## Slice 005 — deterministic market-data replay format

status: `not_started`

Goal:
Create the deterministic replay data format and basic replay reader.

---

## Slice 006 — bar builder

status: `not_started`

Goal:
Build local bars from replayed tick or quote/trade events.

---

## Slice 007 — first replay-only strategy

status: `not_started`

Goal:
Implement the first strategy in replay mode only.

---

## Slice 008 — risk engine

status: `not_started`

Goal:
Implement structured risk checks before approval or execution.

---

## Slice 009 — fake broker

status: `not_started`

Goal:
Implement a fake broker adapter for simulation.

---

## Slice 010 — OMS state machine

status: `not_started`

Goal:
Implement explicit order lifecycle states and transitions.
