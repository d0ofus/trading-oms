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

status: `complete`

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
- [x] Approval ticket module exists.
- [x] Tickets can be created only with passed risk-decision context.
- [x] Tickets represent pending, approved, rejected, expired, and cancelled states explicitly.
- [x] Approval decisions require an explicit human approval actor/reference.
- [x] Approval decisions are idempotent when payloads match and rejected when payloads conflict.
- [x] Every ticket creation and decision is journaled.
- [x] Approved tickets do not automatically submit orders.
- [x] Tests cover create, approve, reject, expire, cancel, idempotency, journaling, and validation failures.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No secrets are introduced.

---

## Slice 012 — alerts

status: `complete`

branch: `slice-012-alerts`

Goal:
Add a safe alerting foundation for safety-critical workflow events without real credentials or live network delivery.

Scope:
- backend alert domain model for alert intents and dispatch outcomes;
- explicit alert severities for informational, warning, critical, and emergency conditions;
- local/no-op alert dispatcher interface suitable for tests and later adapters;
- Telegram-compatible payload formatter without tokens, credentials, or network transport;
- event journal append for every alert intent and dispatch outcome;
- validation for alert IDs, event references, severity, channel, timestamps, payload fields, and redacted metadata;
- tests proving alert creation, formatting, journaling, validation failures, and no secret/no network behavior;
- docs for alert behavior, current limitations, and future adapter boundaries.

Non-goals:
- real Telegram integration;
- Telegram bot tokens or chat IDs;
- network delivery;
- broker integration;
- order submission;
- live trading;
- UI;
- database migrations;
- incident automation or escalation workflows.

Acceptance criteria:
- [x] Alert module exists.
- [x] Alerts represent informational, warning, critical, and emergency severities explicitly.
- [x] Alert intents and dispatch outcomes are journaled.
- [x] Telegram-compatible formatting exists without token handling or network transport.
- [x] Alert payloads reject or redact credential-shaped fields.
- [x] Tests cover creation, formatting, journaling, validation failures, and no secret/no network behavior.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No real Telegram tokens or secrets are introduced.

---

## Slice 013 — UI shell

status: `complete`

branch: `slice-013-ui-shell`

Goal:
Create the first frontend UI shell for safely inspecting the local trading workflow state without
adding live trading, broker connectivity, order submission, or secret-bearing integrations.

Scope:
- frontend application shell with persistent product header, safety posture, and navigation;
- static/local sections for signals, approval tickets, orders, positions, audit events, and alerts;
- clear disabled/default safety state for paper mode, live trading disabled, and no broker connectivity;
- local demo data only, with no API mutation, broker action, Telegram delivery, or order-submission controls;
- tests proving safety posture, shell sections, and absence of live trading/order-submission affordances;
- docs for UI shell behavior, safety constraints, and current limitations.

Non-goals:
- live trading;
- broker integration;
- real broker credentials;
- Telegram tokens or alert delivery;
- order submission, cancellation, or approval actions;
- backend API integration;
- authentication or authorization;
- database persistence;
- Strategy DSL editing;
- visual workflow builder.

Acceptance criteria:
- [x] Frontend UI shell exists.
- [x] Shell shows app mode, live trading disabled, and broker connectivity status.
- [x] Shell includes sections for signals, approval tickets, orders, positions, audit events, and alerts.
- [x] UI uses static/local demo data only.
- [x] UI contains no enabled order submission, broker, live trading, Telegram, or credential controls.
- [x] Tests cover shell rendering, safety posture, expected sections, and forbidden live-action affordances.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No real Telegram tokens or secrets are introduced.

---

## Slice 014 — Strategy DSL

status: `complete`

branch: `slice-014-strategy-dsl`

Goal:
Create the first typed, validated Strategy DSL foundation for replay-only strategy configuration
without arbitrary code execution, broker connectivity, order intents, or live-trading behavior.

Scope:
- backend Strategy DSL domain model for versioned replay-only strategy definitions;
- JSON-compatible parser/validator for the existing `close_above_sma` replay strategy;
- compiler from DSL documents to existing replay strategy config;
- replay-only DSL runner that consumes local bars and journals generated strategy signals through the existing strategy path;
- validation that rejects live mode, broker/order/action fields, credentials/secrets, unsupported strategy types, unsupported price sources, invalid symbols, invalid timeframes, and arbitrary-code-shaped fields;
- tests proving deterministic parsing, validation, replay execution, journal coverage, and no order/broker/secret-shaped payloads;
- docs for DSL shape, guarantees, current limitations, and future visual-builder boundaries.

Non-goals:
- live trading;
- broker integration;
- order intents or order submission;
- risk checks;
- approval tickets;
- OMS integration;
- fake broker orchestration;
- real market-data ingestion;
- arbitrary expressions or code execution;
- YAML parser dependency;
- visual workflow builder;
- UI editing.

Acceptance criteria:
- [x] Strategy DSL module exists.
- [x] DSL documents are versioned and validated before execution.
- [x] DSL supports the existing `close_above_sma` replay strategy.
- [x] DSL can compile to the existing replay strategy config.
- [x] DSL replay runner journals generated signals through the existing strategy path.
- [x] DSL rejects live mode, broker/order/action fields, secrets, unsupported strategy types, and arbitrary-code-shaped fields.
- [x] Tests cover parsing, validation failures, deterministic replay execution, journal coverage, and no order/broker/secret-shaped payloads.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No real credentials, tokens, or secrets are introduced.

---

## Slice 015 — Visual workflow builder

status: `complete`

branch: `slice-015-visual-workflow-builder`

Goal:
Create the first safe visual workflow builder foundation backed by the typed replay-only Strategy DSL
without adding live trading, broker connectivity, order submission, dependency installs, or backend mutation.

Scope:
- frontend visual workflow builder section in the existing UI shell;
- static/local node graph for the supported `close_above_sma` replay strategy;
- safe editable local controls for symbol, lookback bars, and timeframe only;
- generated JSON-compatible Strategy DSL preview matching the Slice 014 document shape;
- explicit safety posture showing replay-only mode, no broker connectivity, no order actions, and no credential fields;
- tests proving the builder renders expected nodes, produces safe DSL text, and contains no live trading/order/broker/secret affordances;
- docs for visual builder behavior, safety boundaries, and current limitations.

Non-goals:
- live trading;
- broker integration;
- order intents or order submission;
- risk checks;
- approval execution workflow;
- OMS or fake broker orchestration;
- real market-data ingestion;
- backend API mutation or persistence;
- adding React Flow or other new dependencies;
- arbitrary expressions, custom scripts, or code execution;
- drag-and-drop graph editing;
- importing or exporting files;
- real credentials, tokens, or secrets.

Acceptance criteria:
- [x] Visual workflow builder section exists in the frontend shell.
- [x] Builder represents the replay-only `close_above_sma` flow as visual nodes.
- [x] Builder can update safe local DSL fields for symbol, lookback bars, and timeframe.
- [x] Builder renders a generated DSL preview with `schema_version: 1`, `mode: replay`, and `strategy_type: close_above_sma`.
- [x] UI clearly states no broker connectivity, no order actions, and no credential fields.
- [x] UI contains no enabled order submission, broker, live trading, Telegram, credential, import/export, or code-execution controls.
- [x] Tests cover node rendering, DSL preview behavior, safe editable controls, and forbidden live-action affordances.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No real credentials, tokens, or secrets are introduced.

---

## Slice 016 — IBKR paper adapter

status: `complete`

branch: `slice-016-ibkr-paper-adapter`

Goal:
Create the first IBKR paper adapter foundation behind a broker-specific adapter boundary without
adding a live order path, real IBKR credentials, public IBKR exposure, or network transport.

Scope:
- backend IBKR paper adapter module with typed paper-only configuration;
- validation that adapter settings are paper-only, live trading disabled, localhost-only, and limited to known paper TWS/Gateway ports;
- adapter-local connection state model for disconnected, connected-paper, and unknown/reconciliation-required states;
- local, non-transmitting paper order plan built from an already risk-passed and approval-referenced `BrokerOrderRequest`;
- event journal append for adapter connection state records and local paper order plans;
- tests proving safe defaults, unsafe config rejection, order-plan validation, journal coverage, unknown-state behavior, and absence of account/credential/live-transmission fields;
- docs for adapter boundaries, current limitations, TWS/Gateway local-only safety posture, and future reconnect/reconciliation work.

Non-goals:
- live trading;
- live IBKR account mode;
- real broker credentials, account IDs, certificates, private keys, passwords, or secrets;
- public IBKR host or port exposure;
- IBKR SDK dependency;
- socket or network transport;
- connecting to TWS or IB Gateway;
- submitting, placing, transmitting, cancelling, or modifying real or paper broker orders;
- market-data subscriptions;
- contract resolution against IBKR;
- OMS orchestration;
- approval workflow orchestration;
- reconnect/reconciliation/chaos behavior beyond explicit local state representation;
- UI changes.

Acceptance criteria:
- [x] IBKR paper adapter module exists.
- [x] Adapter config validates paper-only mode, live trading disabled, localhost-only host, and known paper ports.
- [x] Adapter exposes broker-specific behavior behind an isolated adapter boundary.
- [x] Adapter can record local paper connection state without opening network connections.
- [x] Adapter can build and journal a local non-transmitting paper order plan from a validated `BrokerOrderRequest`.
- [x] Unknown IBKR state is represented explicitly and marked as requiring reconciliation.
- [x] Adapter rejects unsafe settings, unsafe order requests, and non-paper account mode.
- [x] Tests cover config validation, state journaling, order-plan journaling, unsafe rejection, and no account/credential/live-transmission fields.
- [x] Verification passes.
- [x] No IBKR SDK, socket, network transport, live broker connectivity, or order submission path is added.
- [x] No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets are introduced.

---

## Slice 017 — reconnect/reconciliation/chaos tests

status: `complete`

branch: `slice-017-reconnect-reconciliation-chaos-tests`

Goal:
Add a deterministic local resilience and chaos-test foundation for disconnect, reconnect, stale data,
unknown broker state, duplicate events, and reconciliation behavior.

Scope:
- backend resilience domain model for local connection, reconciliation, and chaos events;
- deterministic reconnect/reconciliation scenario runner with append-only journal coverage;
- explicit unknown-state and reconciliation-required behavior that blocks risk-increasing work;
- duplicate resilience event IDs are rejected or replayed idempotently only when payloads match;
- tests proving disconnect/reconnect journaling, reconciliation completion, stale-data blocking,
  unknown broker state blocking, duplicate-event handling, and no network/secrets/live-order behavior;
- docs for resilience/chaos guarantees, current limitations, and future adapter boundaries.

Non-goals:
- live trading;
- real broker credentials, account IDs, certificates, private keys, passwords, or secrets;
- IBKR SDK dependency;
- socket or network transport;
- connecting to TWS, IB Gateway, or any broker;
- submitting, placing, transmitting, cancelling, or modifying real or paper broker orders;
- market-data subscriptions;
- production reconciliation against real broker state;
- UI changes;
- dependency installs.

Acceptance criteria:
- [x] Resilience/chaos module exists.
- [x] Disconnect, reconnect, reconciliation start, and reconciliation completion events are journaled.
- [x] Reconnect leaves risk-increasing work blocked until reconciliation completes.
- [x] Unknown broker state blocks risk-increasing work.
- [x] Stale market data blocks risk-increasing work in the chaos test coverage.
- [x] Duplicate resilience event IDs are blocked or idempotently replayed when payloads match.
- [x] Tests cover deterministic reconnect/reconciliation scenarios and safety edge cases.
- [x] Verification passes.
- [x] No IBKR SDK, socket, network transport, live broker connectivity, or order submission path is added.
- [x] No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets are introduced.

---

## Slice 018 — live-trading readiness checklist

status: `complete`

branch: `slice-018-live-trading-readiness-checklist`

Goal:
Harden the live-trading readiness gate so the repository can explicitly show why live trading remains
disabled and what evidence would be required before any future consideration.

Scope:
- structured live-trading readiness checklist model or verifier;
- explicit status showing live trading is not ready;
- tests proving missing readiness evidence keeps live trading blocked;
- docs explaining readiness evidence, current gaps, and approval boundaries.

Non-goals:
- live trading;
- enabling live trading configuration;
- broker order submission;
- real broker credentials, account IDs, certificates, private keys, passwords, or secrets;
- IBKR SDK dependency;
- socket or network transport;
- changing the default paper/simulation posture;
- production rollout.

Acceptance criteria:
- [x] Live-trading readiness gate remains disabled by default.
- [x] Missing readiness evidence blocks readiness.
- [x] Readiness status is explicit and auditable.
- [x] Tests cover not-ready behavior and forbidden enablement paths.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets are introduced.

---

## Post-Slice-018 delivery gates

The original safety-foundation queue is complete. The next queue moves toward the stated product
goals through explicit human approval gates.

Gate A has been approved by the human request to implement the post-Slice-018 plan. Gate A covers
documentation and queue setup only.

The following gates require separate explicit human approval before implementation starts:

- Gate B: simulation mutation endpoints.
- Gate C: visual workflow save/run.
- Gate D: IBKR paper transport planning.
- Gate E: IBKR paper transport implementation.
- Gate F: production-readiness planning.
- Gate G: any future live-trading readiness review.

No future slice may enable live trading, add live-order transmission, add real credentials, expose
IBKR TWS/Gateway ports publicly, or bypass risk, approval, OMS, or audit gates.

---

## Slice 019 - product gap analysis and post-Slice-018 queue

status: `complete`

branch: `slice-019-product-gap-plan`

Goal:
Create a durable product gap analysis and post-Slice-018 implementation queue.

Scope:
- add `docs/PRODUCT_GAP_ANALYSIS.md`;
- add the post-Slice-018 queue entries;
- document explicit approval gates;
- update README references;
- preserve the hard stops around live trading, broker transport, secrets, and production rollout.

Non-goals:
- backend implementation changes;
- frontend implementation changes;
- API endpoints;
- simulation mutation endpoints;
- persistence;
- React Flow;
- IBKR transport;
- live trading;
- production rollout.

Acceptance criteria:
- [x] Product gap analysis exists.
- [x] Slice 019 through Slice 059 are represented in this queue.
- [x] Future approval gates are explicit.
- [x] No implementation behavior is changed.
- [x] Verification passes.
- [x] No live broker connectivity or order submission path is added.
- [x] No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets are introduced.

---

## Slice 020 - backend read models

status: `complete`

Gate: A

branch: `slice-020-backend-read-models`

Goal:
Create typed backend read models for safe inspection views.

Scope:
- safety posture read model;
- journal record read model;
- signal, risk decision, approval ticket, order, position, alert, and readiness read models;
- local fixture/read-model assembler for the current domain components;
- tests proving models are read-only and contain no action affordances or secrets.

Non-goals:
- HTTP endpoints;
- frontend integration;
- mutation endpoints;
- simulation orchestration;
- broker connectivity;
- live trading.

Acceptance criteria:
- [x] Safety posture read model exists.
- [x] Journal/audit event read model exists.
- [x] Signal, risk decision, approval ticket, order, position, alert, and readiness read models exist.
- [x] Aggregate local operations read-model assembler exists.
- [x] Tests prove models are read-only and contain no action affordances or secrets.
- [x] Verification passes.
- [x] No HTTP endpoints, mutation endpoints, simulation orchestration, broker connectivity, or live trading are added.
- [x] No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets are introduced.

---

## Slice 021 - backend read-only API endpoints

status: `complete`

Gate: A

branch: `slice-021-backend-read-only-api-endpoints`

Goal:
Expose read-only FastAPI endpoints for the safe inspection views.

Scope:
- `GET /api/safety`;
- `GET /api/audit-events`;
- `GET /api/signals`;
- `GET /api/risk-decisions`;
- `GET /api/approval-tickets`;
- `GET /api/orders`;
- `GET /api/positions`;
- `GET /api/alerts`;
- `GET /api/readiness`;
- tests proving the endpoints are read-only and expose no secrets or order-submission controls.

Non-goals:
- POST/PUT/PATCH/DELETE endpoints;
- approval actions;
- simulation runs;
- persistence;
- broker connectivity;
- live trading.

Acceptance criteria:
- [x] `GET /api/safety` exists.
- [x] `GET /api/audit-events` exists.
- [x] `GET /api/signals` exists.
- [x] `GET /api/risk-decisions` exists.
- [x] `GET /api/approval-tickets` exists.
- [x] `GET /api/orders` exists.
- [x] `GET /api/positions` exists.
- [x] `GET /api/alerts` exists.
- [x] `GET /api/readiness` exists.
- [x] Tests prove the endpoints are read-only and expose no secrets or order-submission controls.
- [x] Verification passes.
- [x] No mutation endpoints, approval actions, simulation runs, persistence, broker connectivity,
  or live trading are added.
- [x] No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets
  are introduced.

---

## Slice 022 - frontend API client and safe loading states

status: `complete`

Gate: A

branch: `slice-022-frontend-api-client`

Goal:
Add a frontend API client for read-only backend views.

Scope:
- typed client functions for the read-only endpoints;
- loading, empty, and error states;
- safety posture fallback if the backend is unavailable;
- frontend tests for safe rendering and forbidden action affordances.

Non-goals:
- mutation calls;
- approval action UI;
- order submission UI;
- broker connection UI;
- credentials;
- live trading.

Acceptance criteria:
- [x] Typed client functions exist for all read-only endpoints.
- [x] Loading, empty, loaded, and error states exist.
- [x] Backend-unavailable errors fall back to a safe local posture.
- [x] Tests prove the client uses `GET` requests only.
- [x] Tests prove forbidden action, broker, credential, and secret affordances are absent.
- [x] Verification passes.
- [x] No mutation calls, approval action UI, order submission UI, broker connection UI,
  credentials, or live trading are added.

---

## Slice 023 - connect UI shell to backend read APIs

status: `ready_for_human_review`

Gate: A

branch: `slice-023-connect-ui-to-read-apis`

Goal:
Replace static/local UI shell records with backend-derived read data.

Scope:
- wire the existing sections to read APIs;
- keep the visual builder local and replay-only;
- preserve visible safety posture;
- browser-check the local UI at `http://localhost:5173`.

Non-goals:
- simulation run creation;
- approval actions;
- broker actions;
- workflow persistence;
- live trading.

Acceptance criteria:
- [x] Existing workflow sections read from frontend read API state.
- [x] Safety posture renders backend-derived mode, broker connectivity, alert delivery, and read
  API status.
- [x] Backend-unavailable state falls back to a safe no-live-trading posture.
- [x] Visual builder remains local and replay-only.
- [x] Tests prove backend-derived records render and static demo rows are removed.
- [x] Tests prove forbidden live-action and credential affordances are absent.
- [x] Verification passes.
- [ ] Browser-check the local UI at `http://localhost:5173`.
- [x] No simulation run creation, approval actions, broker actions, workflow persistence, or live
  trading are added.

---

## Slice 024 - simulation run model

status: `ready_for_human_review`

Gate: B - requires separate explicit approval

branch: `slice-024-simulation-run-model`

Goal:
Create the deterministic simulation run model.

Scope:
- run ID, status, timestamps, replay input reference, and journal references;
- deterministic run lifecycle states;
- tests for validation, idempotency, and journal coverage.

Non-goals:
- running a strategy;
- approval mutation endpoints;
- fake broker orchestration;
- broker connectivity;
- live trading.

Acceptance criteria:
- [x] Simulation run records include run ID, status, timestamps, replay input reference, and
  journal references.
- [x] Deterministic lifecycle statuses and allowed transitions exist.
- [x] Accepted create and transition operations append journal records.
- [x] Duplicate create and transition IDs are idempotent only when payloads match.
- [x] Invalid transitions fail without journaling.
- [x] Tests cover validation, idempotency, lifecycle transitions, and journal coverage.
- [x] Verification passes.
- [x] No strategy execution, simulation run HTTP endpoints, approval mutation endpoints, fake
  broker orchestration, broker connectivity, or live trading are added.

---

## Slice 025 - first product strategy

status: `ready_for_human_review`

Gate: B - requires separate explicit approval

branch: `slice-025-first-product-strategy`

Goal:
Implement the product requirements strategy in replay mode.

Scope:
- first 5-minute bar high breakout;
- cumulative volume at least 1.5x the 10-session average cumulative volume at the same session time;
- deterministic replay-only signal generation;
- journal every signal.

Non-goals:
- live market data;
- order submission;
- broker connectivity;
- arbitrary strategy code;
- live trading.

Acceptance criteria:
- [x] First 5-minute bar high breakout detection exists.
- [x] Cumulative volume must be at least 1.5x the 10-session average cumulative volume at the
  same session time.
- [x] Strategy consumes deterministic local bars only.
- [x] Every generated signal is journaled.
- [x] Signal payloads contain no quantity, side, order ID, broker routing, account, credential,
  submit, or transmit fields.
- [x] Tests cover deterministic signal generation, volume-filter blocking, validation failures,
  journaling, and no transport/order behavior.
- [x] Verification passes.
- [x] No live market data, order intents, order submission, broker connectivity, arbitrary
  strategy code, or live trading are added.

---

## Slice 026 - order-intent proposal model

status: `ready_for_human_review`

Gate: B - requires separate explicit approval

branch: `slice-026-order-intent-proposal-model`

Goal:
Represent strategy output as non-executable order-intent proposals.

Scope:
- typed order-intent proposal records;
- explicit non-routable status;
- protective-order plan or approved exception fields;
- duplicate proposal prevention;
- journaling.

Non-goals:
- broker submission;
- approval decisions;
- OMS transitions;
- live trading.

Acceptance criteria:
- [x] Typed order-intent proposal records exist.
- [x] Proposal status is explicitly non-routable.
- [x] Risk-increasing proposals require a protective-order plan or approved exception reference.
- [x] Duplicate proposal IDs and duplicate source signal references are prevented.
- [x] Every accepted proposal is journaled.
- [x] Tests cover creation, idempotency, duplicate blocking, protection requirements, validation,
  journaling, and no transport/order-submission behavior.
- [x] Verification passes.
- [x] No broker submission, approval decisions, OMS transitions, broker connectivity, or live
  trading are added.

---

## Slice 027 - replay to risk to approval orchestration

status: `ready_for_human_review`

Gate: B - requires separate explicit approval

branch: `slice-027-replay-risk-approval-orchestration`

Goal:
Wire replay, bars, product strategy, order intent, risk decision, and approval ticket creation.

Scope:
- deterministic simulation orchestration;
- every generated event appended to the journal;
- stale data, duplicate ID, and unknown broker state blocks.

Non-goals:
- fake broker execution;
- approval action endpoints;
- broker connectivity;
- live trading.

Acceptance criteria:
- [x] Replay events are deterministically converted to local 5-minute bars.
- [x] Product strategy signals create non-routable order-intent proposals.
- [x] Every generated signal, proposal, risk decision, OMS pending-approval transition, approval
  ticket, and simulation run transition is journaled.
- [x] Approval tickets are created only after passed risk.
- [x] Stale market data blocks approval-ticket creation.
- [x] Duplicate risk request IDs block approval-ticket creation.
- [x] Unknown broker state blocks risk-increasing approval-ticket creation.
- [x] Duplicate order-intent proposal IDs are blocked safely.
- [x] Tests cover passed orchestration, risk blocks, no-signal behavior, duplicate proposal blocking,
  and no transport/order-submission behavior.
- [x] Verification passes.
- [x] No fake broker execution, approval action endpoints, broker connectivity, or live trading are
  added.

---

## Slice 028 - simulation approval decisions

status: `ready_for_human_review`

Gate: B - requires separate explicit approval

branch: `slice-028-simulation-approval-decisions`

Goal:
Allow explicit approve/reject decisions for simulation-only approval tickets.

Scope:
- simulation-only approval mutation endpoints;
- actor and reason capture;
- idempotency;
- journaled approval decisions.

Non-goals:
- broker order transmission;
- real account actions;
- bypassing risk or OMS;
- live trading.

Acceptance criteria:
- [x] `POST /api/approval-tickets/{ticket_id}/approve` exists for simulation tickets only.
- [x] `POST /api/approval-tickets/{ticket_id}/reject` exists for simulation tickets only.
- [x] Actor, reason, decision reference, decision ID, and timestamp are captured.
- [x] Repeating the same decision payload is idempotent.
- [x] A ticket cannot be decided twice with different decision IDs.
- [x] Unknown ticket IDs fail safely.
- [x] Responses contain no broker, account, credential, route, submit, or transmit affordances.
- [x] Tests cover approve, reject, idempotency, rejected second decisions, unknown tickets, response
  safety, and allowed mutation route boundaries.
- [x] Verification passes.
- [x] No broker order transmission, real account actions, OMS advancement after approval, fake
  broker execution, IBKR transport, or live trading are added.

---

## Slice 029 - OMS and fake broker simulation orchestration

status: `ready_for_human_review`

Gate: B - requires separate explicit approval

branch: `slice-029-oms-fake-broker-orchestration`

Goal:
Advance approved simulation orders through OMS and fake broker.

Scope:
- OMS transitions after approval;
- fake broker acknowledgement/fill/cancel/reject paths;
- journaled order transitions;
- duplicate prevention.

Non-goals:
- IBKR transport;
- paper account orders;
- live trading.

Acceptance criteria:
- [x] Approved simulation orders advance through OMS `APPROVED` and `SUBMITTED`.
- [x] Fake broker acknowledgement and fill paths are supported.
- [x] Fake broker cancel path is supported with OMS `CANCEL_REQUESTED` before `CANCELLED`.
- [x] Fake broker reject path is supported and mirrored to OMS `REJECTED`.
- [x] Every approval decision, OMS transition, and fake broker transition is journaled.
- [x] Duplicate execution IDs are idempotent when payloads match.
- [x] Terminal order states block repeat execution attempts.
- [x] Tests cover fill, reject, cancel, idempotency, terminal-state blocking, and no
  transport/order-submission behavior.
- [x] Verification passes.
- [x] No IBKR transport, paper account orders, live broker connectivity, HTTP order-execution
  endpoint, or live trading are added.

---

## Slice 030 - simulated positions, protection monitoring, and alerts

status: `ready_for_human_review`

Gate: B - requires separate explicit approval

branch: `slice-030-simulated-positions-alerts`

Goal:
Track simulated positions and raise alerts for missing expected protection.

Scope:
- position records from simulated fills;
- protective-order expectation checks;
- critical alert when expected protection is missing;
- audit coverage.

Non-goals:
- real portfolio reconciliation;
- real alert delivery;
- broker connectivity;
- live trading.

Acceptance criteria:
- [x] Simulated filled fake broker transitions can update local positions.
- [x] Position protection status is explicit.
- [x] Missing expected protection creates a critical local alert intent.
- [x] Missing expected protection records a local no-op alert dispatch.
- [x] Every accepted position update and alert is journaled.
- [x] Duplicate position update IDs are idempotent when payloads match.
- [x] Conflicting duplicate update IDs fail safely.
- [x] Tests cover protected positions, missing-protection alerts, idempotency, duplicate conflict,
  validation, payload safety, and no transport/order-submission behavior.
- [x] Verification passes.
- [x] No real portfolio reconciliation, real alert delivery, broker connectivity, HTTP position
  endpoint, or live trading are added.

---

## Slice 031 - simulation run detail UI

status: `ready_for_human_review`

Gate: B - requires separate explicit approval

branch: `slice-031-simulation-run-detail-ui`

Goal:
Show end-to-end simulation run detail in the UI.

Scope:
- run timeline;
- signal, risk, approval, OMS, fake broker, fill, position, alert, and audit sections;
- browser verification.

Non-goals:
- visual workflow editing;
- IBKR transport;
- live trading.

Acceptance criteria:
- [x] UI shows a simulation run timeline.
- [x] UI shows signal, risk, approval, OMS, fake broker, fill, position, alert, and audit detail
  sections.
- [x] UI remains read-only with no buttons, forms, execution controls, broker connect controls,
  credential fields, or live-trading controls.
- [x] Frontend tests cover the run detail timeline and safety records.
- [x] Browser verification at `http://localhost:5173` is complete.
- [x] Verification passes.
- [x] No visual workflow editing, IBKR transport, broker connectivity, or live trading are added.

---

## Slice 032 - React Flow visual canvas scaffold

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-032-react-flow-visual-canvas`

Goal:
Add the first React Flow visual canvas without execution.

Scope:
- dependency addition;
- static canvas shell;
- replay-only labels and safety posture;
- tests proving no execution, broker, credential, or live-trading controls.

Non-goals:
- graph persistence;
- graph execution;
- broker connectivity;
- live trading.

Acceptance criteria:
- [x] React Flow dependency is installed.
- [x] Static simulation workflow canvas renders.
- [x] Canvas shows replay source, bar builder, strategy trigger, risk check, manual approval, fake
  broker, and audit sink.
- [x] Canvas is locked with no graph editing, save, run, broker, credential, route, script, import,
  eval, or live-mode controls.
- [x] Tests cover the scaffold shape and forbidden affordances.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, or production rollout are
  added.

---

## Slice 033 - editable graph layout

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-033-editable-graph-layout`

Goal:
Allow drag/drop layout edits for replay strategy nodes without changing execution behavior.

Scope:
- local graph layout state;
- safe node movement;
- generated read-only DSL preview remains safe.

Non-goals:
- saving workflows;
- executing workflows;
- adding arbitrary nodes;
- live trading.

Acceptance criteria:
- [x] React Flow nodes can be moved in local frontend state.
- [x] Edges remain fixed and nodes remain non-connectable.
- [x] Generated read-only DSL preview remains safe.
- [x] No save, run, broker, credential, route, script, import, eval, or live-mode controls are
  added.
- [x] Tests cover local layout policy and forbidden affordances.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, or production rollout are
  added.

---

## Slice 034 - typed visual node catalog

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-034-typed-visual-node-catalog`

Goal:
Create the safe node catalog for simulation workflows.

Scope:
- replay source, bar builder, strategy trigger, risk check, approval ticket, fake broker, position update, alert, and audit sink nodes;
- typed node metadata;
- forbidden node/key validation.

Non-goals:
- arbitrary code nodes;
- broker credential nodes;
- live mode nodes;
- execution.

Acceptance criteria:
- [x] Typed visual node catalog exists.
- [x] Catalog includes replay source, bar builder, strategy trigger, risk check, approval ticket,
  fake broker, position update, alert, and audit sink nodes.
- [x] Catalog nodes are non-executing and typed.
- [x] Canvas renders from the typed catalog.
- [x] Tests cover catalog shape, required risk-increasing path nodes, fixed edges, and forbidden
  broker/credential/live/code affordances.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, or production rollout are
  added.

---

## Slice 035 - visual graph validation

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-035-graph-validation`

Goal:
Validate visual workflows before they can be saved or run.

Scope:
- missing risk check errors;
- missing approval errors;
- missing audit sink errors;
- unsupported node and cycle detection;
- visible UI validation messages.

Non-goals:
- execution;
- broker connectivity;
- live trading.

Acceptance criteria:
- [x] Graph validation accepts the default typed simulation workflow graph.
- [x] Graph validation rejects missing risk, approval, and audit sink nodes with explicit errors.
- [x] Graph validation rejects unsafe action nodes and unsupported nodes.
- [x] Graph validation rejects cycles and unknown edge endpoints.
- [x] UI shows validation state without save, run, broker, credential, route, script, import, eval,
  or live-mode controls.
- [x] Tests cover valid and invalid validation cases.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, or production rollout are
  added.

---

## Slice 036 - graph-to-DSL compiler

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-036-graph-to-dsl-compiler`

Goal:
Compile safe visual graphs to a typed simulation workflow DSL.

Scope:
- backend parser/validator;
- frontend generated DSL preview;
- rejection of arbitrary code, secrets, broker routing, and live-mode fields.

Non-goals:
- persistence;
- workflow execution;
- IBKR transport;
- live trading.

Acceptance criteria:
- [x] Validated graph compiles to a typed simulation workflow DSL document.
- [x] Backend parser/validator accepts the safe simulation workflow DSL.
- [x] Backend parser/validator rejects unsafe fields, missing required nodes, unsupported nodes,
  unknown edges, and cycles.
- [x] Invalid frontend graph compilation is blocked with validation errors.
- [x] DSL preview is visible in the visual builder UI.
- [x] DSL explicitly keeps broker transport, live trading, and arbitrary code disabled.
- [x] Tests cover successful compilation, invalid graph blocking, backend parser validation, preview
  formatting, and forbidden credential/route/live/code affordances.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, or production rollout are
  added.

---

## Slice 037 - workflow persistence

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-037-workflow-persistence`

Goal:
Save and load validated simulation workflow definitions.

Scope:
- local persistence for workflow definitions;
- list, detail, create, and update endpoints;
- versioned workflow documents.

Non-goals:
- execution;
- broker connectivity;
- live trading.

Acceptance criteria:
- [x] Valid simulation workflow DSL documents can be saved, listed, loaded, and updated locally.
- [x] Invalid or unsafe workflow documents are rejected before persistence.
- [x] Workflow updates are versioned and idempotent for identical payloads.
- [x] Endpoints do not run workflows or expose broker/live/secret/action affordances.
- [x] Frontend shows persistence status without run, broker, credential, route, script, import, eval,
  or live-mode controls.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, or production rollout are
  added.

---

## Slice 038 - run saved simulation workflows

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-038-run-saved-simulation-workflows`

Goal:
Run saved visual workflows against deterministic replay in simulation only.

Scope:
- validate before run;
- produce simulation run records;
- journal node execution status.

Non-goals:
- IBKR paper transport;
- live trading;
- production rollout.

Acceptance criteria:
- [x] Saved workflows can start deterministic local simulation runs.
- [x] Runs validate saved DSL before orchestration.
- [x] Runs reach manual approval wait only and do not auto-approve.
- [x] Node statuses are journaled for replay, bar, strategy, risk, approval, blocked downstream
  execution nodes, and audit.
- [x] API and frontend surfaces expose no broker/live/secret/action affordances.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, or production rollout are
  added.

---

## Slice 039 - visual run inspection

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-039-visual-run-inspection`

Goal:
Show visual workflow run status and audit references on the graph.

Scope:
- node status display;
- risk blocks;
- approval waits;
- fills and alerts;
- journal references.

Non-goals:
- broker transport;
- live trading.

Acceptance criteria:
- [x] Saved workflow simulation run records can be inspected through read-only endpoints.
- [x] Visual canvas shows node statuses and journal references.
- [x] Approval waits and risk/block states are visible.
- [x] Status vocabulary can represent fills and alerts without enabling execution.
- [x] UI contains no broker, credential, route, script, import, eval, submit, transmit, or live-mode
  controls.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, or production rollout are
  added.

---

## Slice 040 - local persistence foundation

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-040-local-persistence-foundation`

Goal:
Add local persistence for workflows, simulation runs, read models, and journal indexes.

Scope:
- SQLite by default;
- deterministic migration/setup command;
- persistence tests.

Non-goals:
- production database deployment;
- secrets;
- live trading.

Acceptance criteria:
- [x] Local SQLite schema setup is deterministic and idempotent.
- [x] A setup command initializes the local schema.
- [x] Workflow definitions can be persisted and listed.
- [x] Workflow simulation run records can be persisted and listed.
- [x] Operations read-model snapshots can be persisted and loaded.
- [x] Journal records can be indexed with run, event type, symbol, order ID, ticket ID, severity,
  and timestamp fields for later filtering.
- [x] Secret-shaped, live-enabled, broker-host/account, submit, transmit, and route-live payloads
  are rejected before persistence.
- [x] Verification passes.
- [x] No production database deployment, IBKR transport, broker connectivity, live trading, secrets,
  or production rollout are added.

---

## Slice 041 - audit explorer UI

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-041-audit-explorer-ui`

Goal:
Add a UI for filtering and inspecting audit events.

Scope:
- filters by run, event type, symbol, order ID, ticket ID, severity, and timestamp;
- event detail view;
- no secret rendering.

Non-goals:
- audit deletion;
- mutable event history;
- live trading.

Acceptance criteria:
- [x] UI shows audit filters for run, event type, symbol, order ID, ticket ID, severity, and
  timestamp.
- [x] UI shows a read-only audit event detail panel.
- [x] Frontend filter helper covers each required field.
- [x] Secret-shaped audit text is redacted before rendering.
- [x] Audit read models expose optional safe filter metadata fields.
- [x] UI contains no broker, credential, route, script, import, eval, submit, transmit, or live-mode
  controls.
- [x] Verification passes.
- [x] No audit deletion, mutable history, IBKR transport, broker connectivity, live trading,
  secrets, or production rollout are added.

---

## Slice 042 - approval inbox UI

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-042-approval-inbox-ui`

Goal:
Create an operator approval inbox for simulation-only tickets.

Scope:
- pending ticket list;
- approve/reject forms;
- actor and reason capture;
- idempotency feedback.

Non-goals:
- broker transmission without paper-transport gate;
- live trading.

Acceptance criteria:
- [x] UI lists pending simulation approval tickets.
- [x] UI captures actor and reason.
- [x] UI exposes approve/reject controls labeled simulation-only.
- [x] UI shows idempotency feedback.
- [x] Frontend client posts only to simulation approval endpoints.
- [x] UI contains no broker, credential, route, script, import, eval, submit-order,
  transmit-order, or live-mode controls.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, fake broker execution, or
  production rollout are added.

---

## Slice 043 - order and position detail pages

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-043-order-position-details`

Goal:
Add detailed order and position inspection pages.

Scope:
- OMS transitions;
- fills;
- position protection state;
- linked audit events.

Non-goals:
- live position reconciliation;
- broker order amendments;
- live trading.

Acceptance criteria:
- [x] UI shows read-only order detail with current OMS state.
- [x] UI shows cumulative filled and leaves quantities.
- [x] UI shows order risk, approval, reconciliation, and linked audit references.
- [x] UI shows read-only position detail with quantity, average price, source, and protection
  state.
- [x] UI links position detail to audit records without exposing secrets.
- [x] UI contains no broker, credential, route, script, import, eval, submit-order,
  transmit-order, amendment, reconciliation-action, or live-mode controls.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, real alert delivery, or
  production rollout are added.

---

## Slice 044 - protection monitoring dashboard

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-044-protection-monitoring-dashboard`

Goal:
Show expected protection, exceptions, and critical alerts in the UI.

Scope:
- protected/unprotected position views;
- exception references;
- alert linkage.

Non-goals:
- live broker reconciliation;
- real alert delivery;
- live trading.

Acceptance criteria:
- [x] UI shows expected-protection position counts.
- [x] UI shows missing-protection position counts as critical when present.
- [x] UI shows exception and review-required references.
- [x] UI shows critical and emergency local alerts with source linkage.
- [x] Secret-shaped dashboard text is redacted before rendering.
- [x] UI contains no broker, credential, route, script, import, eval, submit-order,
  transmit-order, alert-delivery, reconciliation-action, or live-mode controls.
- [x] Verification passes.
- [x] No IBKR transport, broker connectivity, live trading, secrets, real alert delivery, or
  production rollout are added.

---

## Slice 045 - audit export bundle

status: `ready_for_human_review`

Gate: C - requires separate explicit approval

branch: `slice-045-audit-export-bundle`

Goal:
Export reviewable audit bundles without secrets.

Scope:
- deterministic export package;
- secret-shaped content scan;
- run/workflow/journal references.

Non-goals:
- uploading exports;
- external delivery;
- live trading.

Acceptance criteria:
- [x] Export bundle output is deterministic stable JSON.
- [x] Export bundle includes workflow IDs, run IDs, journal references, and read-model data.
- [x] Export recursively rejects secret-shaped content, live-enabled booleans, broker host/account
  fields, submit/transmit/route affordances, and arbitrary-code-shaped text.
- [x] `GET /api/audit-export-bundle` returns a safe read-only bundle.
- [x] Local file writing emits the same stable JSON.
- [x] Verification passes.
- [x] No uploads, external delivery, IBKR transport, broker connectivity, live trading, secrets, or
  production rollout are added.

---

## Slice 046 - IBKR paper transport plan and external review checklist

status: `ready_for_human_review`

Gate: D - requires separate explicit approval

branch: `slice-046-ibkr-paper-transport-plan`

Goal:
Plan paper-only IBKR transport before implementation.

Scope:
- ExecPlan;
- external review checklist;
- paper-only safety controls;
- no code transport yet.

Non-goals:
- IBKR SDK;
- network transport;
- order placement;
- live trading.

Acceptance criteria:
- [x] Slice 046 ExecPlan exists.
- [x] External paper-only IBKR transport review checklist exists.
- [x] Checklist explicitly blocks live trading, real credentials, account identifiers, public IBKR
  port exposure, production rollout, and order placement.
- [x] Checklist requires separate Gate E approval before any SDK, connectivity probe, contract
  lookup, paper order transport, callback handling, or paper trading UI.
- [x] Planning docs document paper-only safety controls and local-only TWS/Gateway assumptions
  without adding configurable broker host fields, credentials, account identifiers, or live-mode
  fields.
- [x] Verification passes.
- [x] No IBKR SDK, transport implementation, connectivity probe, order-placement path, secrets,
  account identifiers, production-readiness work, production rollout, or live trading path is added.

---

## Slice 047 - local IBKR paper connectivity probe

status: `not_started`

Gate: E - requires separate explicit approval

Goal:
Probe local TWS/Gateway paper connectivity without order placement.

Scope:
- localhost-only connection attempt;
- no public host;
- no account ID or credential storage;
- journal connection state.

Non-goals:
- order placement;
- market orders;
- live account mode;
- live trading.

---

## Slice 048 - paper contract lookup

status: `not_started`

Gate: E - requires separate explicit approval

Goal:
Resolve paper-mode contract metadata safely.

Scope:
- paper-only contract lookup;
- validation and journaling;
- no market order placement.

Non-goals:
- live account lookup;
- order placement;
- live trading.

---

## Slice 049 - paper order submission adapter

status: `not_started`

Gate: E - requires separate explicit approval

Goal:
Submit paper-only IBKR orders behind the broker adapter boundary.

Scope:
- risk-passed, approval-referenced, OMS-ready paper orders only;
- paper-only config enforcement;
- reconciliation-safe state requirements;
- journal every submission attempt and outcome.

Non-goals:
- live account mode;
- live order routing;
- bypassing approval;
- live trading.

---

## Slice 050 - paper order status and fill callbacks

status: `not_started`

Gate: E - requires separate explicit approval

Goal:
Handle paper order status and fill callbacks safely.

Scope:
- callback validation;
- idempotency;
- OMS/fill reconciliation;
- journal coverage.

Non-goals:
- live account mode;
- live trading.

---

## Slice 051 - paper transport chaos tests

status: `not_started`

Gate: E - requires separate explicit approval

Goal:
Prove paper transport safety under disconnect, reconnect, duplicates, stale data, and unknown state.

Scope:
- deterministic chaos tests;
- reconciliation-required blocks;
- duplicate callback handling.

Non-goals:
- live account testing;
- live trading.

---

## Slice 052 - paper trading operator UI

status: `not_started`

Gate: E - requires separate explicit approval

Goal:
Expose paper-only broker state and order status in the UI.

Scope:
- paper-only labeling;
- connection state;
- order status;
- reconciliation warnings.

Non-goals:
- live trading controls;
- credential inputs;
- public broker host configuration.

---

## Slice 053 - deployment and secrets-management plan

status: `not_started`

Gate: F - requires separate explicit approval

Goal:
Plan production-like deployment and secret handling while live trading remains disabled.

Scope:
- deployment architecture;
- secret storage strategy;
- network exposure review;
- rollback plan.

Non-goals:
- production rollout;
- live trading;
- adding real secrets.

---

## Slice 054 - authentication and authorization

status: `not_started`

Gate: F - requires separate explicit approval

Goal:
Add operator authentication and authorization.

Scope:
- operator identity;
- permissions for viewing, approving, and administration;
- audit every privileged action.

Non-goals:
- broker credential storage;
- live trading.

---

## Slice 055 - operator roles and approval permissions

status: `not_started`

Gate: F - requires separate explicit approval

Goal:
Harden role-based controls for approval and operations.

Scope:
- approver role;
- separation of duties;
- approval audit evidence.

Non-goals:
- live trading approval;
- production rollout.

---

## Slice 056 - emergency stop implementation

status: `not_started`

Gate: F - requires separate explicit approval

Goal:
Implement and test emergency stop behavior.

Scope:
- local emergency stop state;
- risk-increasing work blocked while active;
- journaled activation/deactivation;
- tests.

Non-goals:
- live trading;
- broker-side liquidation.

---

## Slice 057 - observability, retention, backup, and incident response

status: `not_started`

Gate: F - requires separate explicit approval

Goal:
Add production-readiness operating controls.

Scope:
- logs and metrics plan;
- audit retention;
- backup/restore;
- incident response workflow.

Non-goals:
- live trading;
- production rollout.

---

## Slice 058 - live-readiness evidence dashboard

status: `not_started`

Gate: F - requires separate explicit approval

Goal:
Display live-readiness evidence without enabling live trading.

Scope:
- evidence checklist UI;
- readiness decision display;
- missing evidence visibility.

Non-goals:
- enabling live trading;
- live order path.

---

## Slice 059 - controlled paper-production rollout checklist

status: `not_started`

Gate: F - requires separate explicit approval

Goal:
Prepare a controlled paper-production rollout checklist.

Scope:
- paper-only rollout criteria;
- external review evidence;
- rollback and incident response evidence.

Non-goals:
- live trading rollout;
- enabling live order submission.
