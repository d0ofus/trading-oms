# Product Requirements

## Product goal

Build a self-hosted, semi-automated trading workflow and OMS that supports deterministic simulation first, paper trading second, and live-readiness only after explicit human approval.

## Core capabilities

- Market-data ingestion.
- Deterministic replay.
- Local bar building.
- Strategy evaluation.
- Risk checks.
- Manual approval tickets.
- Fake broker execution.
- OMS state tracking.
- Event journal and audit log.
- Alerts.
- UI shell.
- Visual workflow builder.
- IBKR paper adapter later.

## First vertical slice strategy

Buy a configured quantity of a symbol if price crosses above the high of the first 5-minute bar, only if cumulative volume is at least 1.5x the 10-session average cumulative volume at the same session time.

Initial mode:

```text
replay data
→ bar builder
→ strategy trigger
→ risk check
→ approval ticket
→ fake broker
→ simulated fill
→ position update
→ alert log
→ audit log
```

## Out of scope at the start

- Live trading.
- Real IBKR order submission.
- Real credentials.
- Full visual builder.
- Production deployment.
