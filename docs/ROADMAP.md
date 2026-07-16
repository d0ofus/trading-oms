# Roadmap

## Phase 0: Repo quality gate

Create repo instructions, docs, CI, verification commands, and safe defaults.

## Phase 1: Simulation vertical slice

Implement deterministic replay, bar builder, simple strategy, fake broker, and audit events.

## Phase 2: OMS and risk hardening

Add explicit order state machine, idempotency, risk checks, duplicate prevention, and position tracking.

## Phase 3: Strategy DSL and replay

Add typed strategy config and replay tests.

## Phase 4: UI shell and manual approval

Create UI for signals, approval tickets, orders, positions, and audit events.

## Phase 5: React Flow visual builder

Add visual workflow builder backed by typed DSL.
The current editor supports typed node/edge editing, continuous frontend and authoritative backend
safety validation, preview DSL compilation, and deliberate local workflow-definition list/load/
create/update controls with optimistic version checks. Deterministic simulation-run start remains
a later, separately bounded simulation-only slice with no broker transport.

## Phase 6: Alerts

Add Telegram-compatible alert adapter with no secrets in repo.

## Phase 7: IBKR paper adapter

Add IBKR adapter in paper mode only. No live order path. The first foundation is local-only;
paper transport requires later explicit approval and reconciliation work.

## Phase 8: Chaos and resilience

Test disconnect, reconnect, stale data, unknown broker state, duplicate events, and reconciliation.
The first foundation is local and deterministic; production broker reconciliation remains future work.

## Phase 9: Live-readiness gate

Create checklist and hard-coded live-trading disabled default.
The first backend readiness verifier is an audit gate only and cannot enable live trading.

## Phase 10: Controlled production rollout

Only after explicit human approval, external review, paper-trading history, and readiness checklist completion.
Slice 053 documents deployment and secrets-management planning requirements only; it does not approve
or start controlled production rollout.
Slice 059 documents the fail-closed controlled paper-production rollout checklist only. It does not
start this phase, and its current result remains `not_ready`.
