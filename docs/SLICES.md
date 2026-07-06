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

status: `complete`

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
- [x] Backend skeleton exists.
- [x] Frontend skeleton exists.
- [x] Health endpoint exists.
- [x] Config defaults to `APP_MODE=paper`.
- [x] `LIVE_TRADING_ENABLED` defaults to `false`.
- [x] `make verify` runs real checks where practical.
- [x] CI can run `make verify`.
- [x] No code path can transmit broker orders.
- [x] No secrets are introduced.
- [x] Docs are updated if setup changes.

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

status: `complete`

branch: `slice-003-safe-configuration-hardening`

Goal:
Create a strict application configuration layer with validated safe defaults, explicit app mode, and hard failure for unsafe live-trading settings.

Scope:
- strict backend settings model for safety-relevant config values;
- validated defaults for paper/simulation mode;
- hard failures for live trading, live IBKR account mode, public IBKR host, invalid booleans, invalid ports, and unsafe production combinations;
- tests for safe defaults and unsafe settings;
- docs for configuration behavior.

Non-goals:
- broker integration;
- order submission;
- IBKR connectivity;
- secrets;
- strategy engine;
- OMS;
- risk engine.

Acceptance criteria:
- [x] Config defaults to paper mode with live trading disabled.
- [x] Unsafe live trading settings fail fast.
- [x] IBKR account mode must be paper.
- [x] IBKR host must be localhost-only.
- [x] Invalid config values fail with clear errors.
- [x] Health endpoint exposes only non-secret safety posture.
- [x] Verification passes.
- [x] No code path can transmit broker orders.
- [x] No secrets are introduced.

---

## Slice 004 — append-only event journal

status: `approved_for_autonomous_run`

branch: `slice-004-append-only-event-journal`

Goal:
Add an append-only event journal foundation for auditability.

Scope:
- backend event journal domain model for audit records;
- append-only JSONL journal writer and reader;
- deterministic sequence handling suitable for replay;
- validation for required event fields;
- tests proving append-only behavior and readback order;
- docs for journal guarantees and current limitations.

Non-goals:
- database migrations;
- broker integration;
- order submission;
- live trading;
- full OMS integration;
- alerts;
- UI.

Acceptance criteria:
- [ ] Event journal module exists.
- [ ] Journal records include type, timestamp, payload, and sequence metadata.
- [ ] Appending preserves existing records and never rewrites prior entries.
- [ ] Journal readback is deterministic and ordered.
- [ ] Invalid journal records fail validation.
- [ ] Tests cover append/read behavior and append-only guarantees.
- [ ] Verification passes.
- [ ] No code path can transmit broker orders.
- [ ] No secrets are introduced.

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
