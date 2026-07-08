# Product Gap Analysis

This document maps the stated product goals to the current repository state and the post-Slice-018
delivery queue.

This is a planning and safety-boundary document. It is not approval for live trading, IBKR
transport, production rollout, real credentials, or broker order transmission.

## Current Position

The repository has completed the first safety foundation:

- safe configuration with live trading disabled;
- append-only JSONL event journal;
- deterministic market-data replay reader;
- local bar builder;
- first replay-only strategy signal path;
- structured risk checks;
- simulation-only fake broker;
- explicit OMS state machine;
- local approval tickets;
- local/no-op alerts;
- read-only UI shell;
- replay-only Strategy DSL;
- local visual builder foundation;
- local IBKR paper adapter boundary without transport;
- deterministic local resilience/chaos checks;
- live-readiness checklist evaluation.

The repository does not yet have a connected trading workflow product. The frontend still displays
mostly local/static inspection data, and backend domain modules are not yet orchestrated into a full
simulation run.

## Goal-To-Gap Map

| Product goal | Current state | Gap to close |
| --- | --- | --- |
| Market-data ingestion | Deterministic replay reader exists. | Add run-level replay ingestion, fixtures, and later live/paper data boundaries. |
| Deterministic replay | Replay records and validation exist. | Add simulation run orchestration and repeatable run summaries. |
| Local bar building | Bar builder exists. | Wire bars into product strategy and run records. |
| Product strategy evaluation | A close-above-SMA replay strategy exists. | Implement the first requirements strategy: first 5-minute bar breakout plus 1.5x cumulative volume filter. |
| Risk checks | Risk engine exists. | Wire all order-intent proposals through risk before approval. |
| Manual approval tickets | Approval domain exists. | Add API/UI approval inbox and orchestration into simulation state. |
| Fake broker execution | Fake broker exists. | Execute approved simulation orders through fake broker and OMS. |
| OMS state tracking | OMS state machine exists. | Persist/read OMS views and orchestrate state transitions from approvals/fills. |
| Positions | Not implemented as a product view. | Add simulated position tracking, protection monitoring, and critical alerts. |
| Event journal and audit log | Journal exists. | Add read APIs, audit explorer, filters, export, and event indexing. |
| Alerts | Local/no-op alert domain exists. | Wire alerts to protection and run events; keep delivery local until a later approved adapter. |
| UI shell | Read-only shell exists. | Connect shell to backend read APIs and add workflow-specific views. |
| Visual workflow builder | Local fixed replay DSL preview exists. | Add React Flow style drag/drop graph editing, validation, DSL compilation, persistence, and simulation-only execution. |
| IBKR paper adapter | Local adapter boundary exists without transport. | Add paper-only transport only after a separate explicit human approval and review. |
| Production readiness | Checklist evaluator exists. | Add deployment plan, auth, emergency stop, observability, backup/restore, and external review evidence. |

## Visual Builder Clarification

The current `Visual builder` is not the Make.com-style product goal. It is only a local, fixed,
replay-only Strategy DSL preview for the `close_above_sma` strategy.

The future visual workflow builder must be delivered in safe layers:

1. read-only graph inspection;
2. drag/drop graph layout without execution;
3. typed node catalog;
4. graph validation;
5. graph-to-DSL compilation;
6. workflow persistence;
7. simulation-only execution;
8. paper-only broker execution after separate approval.

The builder must never compile arbitrary code, store credentials, bypass risk, bypass approval,
bypass OMS, bypass audit logging, or create a live-trading path.

## Approval Gates

The next work proceeds through explicit gates:

- Gate A: start the post-Slice-018 implementation queue.
- Gate B: allow simulation mutation endpoints.
- Gate C: allow visual workflow save/run.
- Gate D: allow IBKR paper transport planning.
- Gate E: allow IBKR paper transport implementation.
- Gate F: allow production-readiness planning.
- Gate G: allow any future live-trading readiness review.

Gate A is limited to documentation and planning queue setup. Gates B through G require separate
human approval before implementation starts.

## Next Delivery Queue

The detailed queue now lives in `docs/SLICES.md`, beginning with Slice 019.

The immediate next safe implementation after Slice 019 is Slice 020: backend read models for safety
posture, journal records, signals, risk decisions, approval tickets, orders, positions, alerts, and
readiness state.

## Hard Stops

- Do not enable live trading.
- Do not add real broker credentials, real Telegram tokens, account IDs, passwords, certificates,
  private keys, tokens, or secrets.
- Do not add a live broker order-transmission path.
- Do not expose IBKR TWS or Gateway ports beyond localhost.
- Do not add IBKR paper transport without separate explicit approval.
- Do not start production rollout without separate explicit approval, external review, and
  readiness evidence.
