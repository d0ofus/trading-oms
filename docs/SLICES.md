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

status: `complete`

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
- [x] Event journal module exists.
- [x] Journal records include type, timestamp, payload, and sequence metadata.
- [x] Appending preserves existing records and never rewrites prior entries.
- [x] Journal readback is deterministic and ordered.
- [x] Invalid journal records fail validation.
- [x] Tests cover append/read behavior and append-only guarantees.
- [x] Verification passes.
- [x] No code path can transmit broker orders.
- [x] No secrets are introduced.

---

## Slice 005 — deterministic market-data replay format

status: `complete`

branch: `slice-005-deterministic-market-data-replay`

Goal:
Create the deterministic replay data format and basic replay reader.

Scope:
- backend replay domain model for market-data events;
- deterministic JSONL replay file reader;
- validation for required event fields and event ordering;
- tests proving stable replay order and validation failures;
- docs for replay format and current limitations.

Non-goals:
- live market-data ingestion;
- broker integration;
- order submission;
- strategy execution;
- bar building;
- risk engine;
- UI.

Acceptance criteria:
- [x] Replay module exists.
- [x] Replay events include sequence, timestamp, symbol, event type, and payload.
- [x] Replay reader returns events in deterministic file order.
- [x] Invalid replay records fail validation.
- [x] Out-of-order or duplicate sequences fail validation.
- [x] Tests cover replay readback and validation failures.
- [x] Verification passes.
- [x] No live market-data source is added.
- [x] No code path can transmit broker orders.
- [x] No secrets are introduced.

---

## Slice 006 — bar builder

status: `complete`

branch: `slice-006-bar-builder`

Goal:
Build local bars from replayed tick or quote/trade events.

Scope:
- backend bar builder domain model for local OHLCV bars;
- deterministic time-bucketed bar construction from replay events;
- validation for trade prices, quote-derived prices, sizes, symbols, timestamps, and timeframe duration;
- tests proving deterministic bars and validation failures;
- docs for bar builder behavior and current limitations.

Non-goals:
- live market-data ingestion;
- broker integration;
- order submission;
- strategy execution;
- risk engine;
- OMS integration;
- event journal integration;
- UI.

Acceptance criteria:
- [x] Bar builder module exists.
- [x] Bars include symbol, timeframe, start/end timestamps, OHLC, volume, and event count.
- [x] Trade replay events build deterministic OHLCV bars.
- [x] Quote replay events require an explicit configured price source.
- [x] Invalid or unsupported events fail validation.
- [x] Tests cover bar readback and validation failures.
- [x] Verification passes.
- [x] No live market-data source is added.
- [x] No code path can transmit broker orders.
- [x] No secrets are introduced.

---

## Slice 007 — first replay-only strategy

status: `complete`

branch: `slice-007-first-replay-only-strategy`

Goal:
Implement the first strategy in replay mode only.

Scope:
- backend replay strategy domain model for deterministic bias signals;
- hard-coded close-vs-simple-moving-average strategy;
- event journal append for every generated strategy signal;
- validation for strategy config, bars, signal payloads, symbols, timeframes, timestamps, and prices;
- tests proving deterministic signals, journal coverage, and validation failures;
- docs for strategy behavior and current limitations.

Non-goals:
- live market-data ingestion;
- broker integration;
- order intents;
- order submission;
- risk engine;
- approval tickets;
- OMS integration;
- alerts;
- UI;
- Strategy DSL execution.

Acceptance criteria:
- [x] Replay-only strategy module exists.
- [x] Strategy consumes local bars only.
- [x] Strategy emits deterministic bias signals, not order intents.
- [x] Every generated signal is journaled.
- [x] Signal payloads contain no broker, account, order routing, quantity, or submission fields.
- [x] Invalid strategy inputs fail validation.
- [x] Tests cover deterministic signal generation, journaling, and validation failures.
- [x] Verification passes.
- [x] No live market-data source is added.
- [x] No code path can transmit broker orders.
- [x] No secrets are introduced.

---

## Slice 008 — risk engine

status: `complete`

branch: `slice-008-risk-engine`

Goal:
Implement structured risk checks before approval or execution.

Scope:
- backend risk engine domain model for policies, evaluation requests, checks, and decisions;
- deterministic risk checks for allowed symbols, duplicate request IDs, market-data freshness, broker-state knowledge, quantity limits, notional limits, and protective-order requirements;
- event journal append for every risk decision;
- tests proving passed decisions, blocked decisions, journaling, and validation failures;
- docs for risk engine behavior and current limitations.

Non-goals:
- broker integration;
- order submission;
- live trading;
- approval tickets;
- OMS integration;
- fake broker execution;
- alerts;
- UI;
- database migrations.

Acceptance criteria:
- [x] Risk engine module exists.
- [x] Risk decisions include structured check results.
- [x] Every risk decision is journaled.
- [x] Stale market data blocks decisions.
- [x] Unknown broker state blocks risk-increasing decisions.
- [x] Duplicate request IDs are blocked.
- [x] Risk-increasing requests require a protective plan or explicitly approved exception.
- [x] Quantity and notional limits are enforced.
- [x] Tests cover passed decisions, blocked decisions, journaling, and validation failures.
- [x] Verification passes.
- [x] No broker connectivity or order submission path is added.
- [x] No secrets are introduced.

---

## Slice 009 — fake broker

status: `complete`

branch: `slice-009-fake-broker`

Goal:
Implement a fake broker adapter for simulation.

Scope:
- backend broker adapter protocol for simulation-only order handling;
- fake broker implementation with deterministic order acknowledgements, fills, cancels, and rejects;
- event journal append for every fake broker order transition;
- validation for order intent, quantities, prices, sides, symbols, request IDs, and timestamps;
- tests proving deterministic transitions, journaling, duplicate prevention, and validation failures;
- docs for fake broker behavior and current limitations.

Non-goals:
- live broker integration;
- real broker credentials;
- network access;
- IBKR connectivity;
- automatic order submission from strategies;
- approval tickets;
- full OMS state machine;
- alerts;
- UI;
- database migrations.

Acceptance criteria:
- [x] Fake broker module exists.
- [x] Broker adapter interface is simulation-only and broker-agnostic.
- [x] Fake broker can acknowledge accepted orders deterministically.
- [x] Fake broker can create deterministic fills for configured fill behavior.
- [x] Fake broker can cancel open fake orders deterministically.
- [x] Fake broker can reject invalid or explicitly rejected fake orders deterministically.
- [x] Duplicate client order IDs are blocked.
- [x] Every fake broker order transition is journaled.
- [x] Tests cover accepted, filled, cancelled, rejected, duplicate, journaling, and validation behavior.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No secrets are introduced.

---

## Slice 010 — OMS state machine

status: `complete`

branch: `slice-010-oms-state-machine`

Goal:
Implement explicit order lifecycle states and transitions.

Scope:
- backend OMS domain model for order lifecycle states and transitions;
- explicit allowed transition table for initial OMS states;
- deterministic transition application with idempotency keys;
- event journal append for every accepted OMS transition;
- validation for order IDs, symbols, sides, quantities, timestamps, reasons, risk decision IDs, approval references, and broker transition references;
- tests proving valid transitions, invalid transition blocking, duplicate/idempotent behavior, unknown broker state handling, journaling, and validation failures;
- docs for OMS state machine behavior and current limitations.

Non-goals:
- live broker integration;
- real broker credentials;
- network access;
- IBKR connectivity;
- automatic order submission from strategies;
- approval ticket implementation;
- fake broker execution orchestration;
- alerts;
- UI;
- database migrations;
- position tracking.

Acceptance criteria:
- [x] OMS state machine module exists.
- [x] Initial lifecycle states are represented explicitly.
- [x] Allowed transitions are explicit and invalid transitions fail validation.
- [x] Every accepted order lifecycle transition is journaled.
- [x] Duplicate transition IDs are idempotent when payloads match and rejected when payloads conflict.
- [x] Unknown broker state can be represented as `UNKNOWN_REQUIRES_RECONCILIATION`.
- [x] Unknown broker state exposes a flag that blocks new risk-increasing decisions.
- [x] Tests cover valid transitions, invalid transitions, idempotency, unknown state, journaling, and validation failures.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No secrets are introduced.

---

## Slice 011 — approval tickets

status: `not_started`

branch: `slice-011-approval-tickets`

Goal:
Implement semi-automatic human approval tickets before any broker submission workflow.

Scope:
- backend approval ticket domain model for pending, approved, rejected, expired, and cancelled approval decisions;
- deterministic ticket creation from passed risk decisions and OMS pending-approval context;
- explicit approval decision application with idempotency keys;
- event journal append for every ticket creation and approval decision;
- validation for ticket IDs, order IDs, client order IDs, risk decision IDs, OMS transition references, timestamps, decision actors, reasons, and expiry timestamps;
- tests proving ticket creation, approve/reject/expire/cancel decisions, duplicate/idempotent behavior, journaling, and validation failures;
- docs for approval ticket behavior and current limitations.

Non-goals:
- live broker integration;
- real broker credentials;
- network access;
- IBKR connectivity;
- automatic execution after approval;
- UI approval screens;
- alert delivery;
- Telegram integration;
- database migrations;
- position tracking;
- full OMS/fake broker orchestration.

Acceptance criteria:
- [ ] Approval ticket module exists.
- [ ] Tickets can be created only with passed risk-decision context.
- [ ] Tickets represent pending, approved, rejected, expired, and cancelled states explicitly.
- [ ] Approval decisions require an explicit human approval actor/reference.
- [ ] Approval decisions are idempotent when payloads match and rejected when payloads conflict.
- [ ] Every ticket creation and decision is journaled.
- [ ] Approved tickets do not automatically submit orders.
- [ ] Tests cover create, approve, reject, expire, cancel, idempotency, journaling, and validation failures.
- [ ] Verification passes.
- [ ] No live broker connectivity or order submission path is added.
- [ ] No secrets are introduced.
