# Product Gap Analysis

This document originally mapped the stated product goals to the post-Slice-018 repository state and
delivery queue. The historical map is retained below; current slice status lives in `docs/SLICES.md`.

This is a planning and safety-boundary document. It is not approval for live trading, IBKR
transport, production rollout, real credentials, or broker order transmission.

## Current Update

The post-Slice-018 queue through Slice 059 and Candidates 060-062 delivered the connected read API,
deterministic simulation orchestration, safe visual workflow foundation, local persistence
foundation, operator views, paper-adapter foundation, resilience checks, and fail-closed readiness
evidence described in `docs/SLICES.md`.

The non-broker simulation-run-inspector candidate closes one remaining operator-trust gap: the UI no
longer shows a hard-coded completed fake-broker run. It loads actual saved workflow simulation runs,
shows backend-recorded node and journal evidence, and renders explicit empty/error states. Current
workflow-run retention is process-local and remains a future durability gap.

The interactive visual-workflow-editor candidate closes the fixed-preview gap for local graph
authoring. Operators can add, select, move, and remove typed simulation nodes, connect and remove
typed edges, see continuous safety validation, and inspect regenerated preview DSL.

The validated persistence candidate closes the next gap by connecting that editor to the existing
workflow-definition list/detail/create/update APIs. Definitions are validated before requests and
again authoritatively before writes, stale updates fail with HTTP 409, and dirty drafts require
explicit discard confirmation before replacement. Simulation-run start controls remain
deliberately absent.

Candidate 063 connector implementation is deferred. No IBKR dependency, broker contact, order
transport, credentials, account identifiers, deployment, rollout, production operation, or live
trading is authorized by this update.

## Historical Post-Slice-018 Position

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

## Historical Post-Slice-018 Goal-To-Gap Map

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
| Visual workflow builder | Interactive frontend-local typed graph editing, validation, and preview DSL compilation exist. | Connect validated graphs to existing persistence and deterministic simulation-run APIs under a separate simulation-only slice. |
| IBKR paper adapter | Local adapter boundary exists without transport. | Add paper-only transport only after a separate explicit human approval and review. |
| Production readiness | Checklist evaluator, deployment plan, local auth/roles, and local emergency stop exist. | Add observability, backup/restore, incident response, evidence dashboard, rollout checklist, and external review evidence. |

## Historical Visual Builder Clarification

The current `Visual builder` is still not the complete Make.com-style product goal. It now provides
typed graph editing, preview compilation, and local backend-validated definition persistence, but
it does not run the edited graph.

The future visual workflow builder must be delivered in safe layers:

1. read-only graph inspection - complete;
2. drag/drop graph layout without execution - complete for canvas node movement;
3. typed node catalog - complete;
4. graph validation - complete for local editor rules;
5. graph-to-DSL compilation - complete for local preview;
6. workflow persistence - complete for deliberate local list/load/create/update with version checks;
7. simulation-only execution - existing APIs are available but not connected to this editor;
8. paper-only broker execution - deferred and separately gated.

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

## Historical Next Delivery Queue

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
