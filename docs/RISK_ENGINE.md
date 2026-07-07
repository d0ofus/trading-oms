# Risk Engine

Slice 008 introduces structured risk checks for proposed risk decisions.

It does not add live broker connectivity, order submission, live trading, approval ticket creation, OMS integration, fake broker execution, alerts, UI, or database migrations.

## Purpose

The risk engine evaluates a `RiskEvaluationRequest` against a `RiskPolicy` and returns a `RiskDecision`.

A passed risk decision is not human approval and is not permission to execute. Future approval, OMS, and broker slices must still enforce their own gates.

## Checks

The initial risk engine evaluates:

- allowed symbol;
- duplicate request ID;
- market-data freshness;
- unknown broker state for risk-increasing requests;
- maximum quantity;
- maximum notional;
- protective order plan or approved exception for risk-increasing requests.

Stale market data blocks all decisions. Unknown broker state blocks new risk-increasing decisions. Risk-reducing requests can pass unknown broker state only when all other checks pass.

## Request Shape

Requests are in-memory Python records with this JSON-compatible shape:

```json
{
  "schema_version": 1,
  "request_id": "risk-001",
  "symbol": "AAPL",
  "side": "buy",
  "risk_intent": "increase",
  "quantity": 10,
  "reference_price": 100.0,
  "market_data_timestamp": "2026-07-06T00:00:45Z",
  "evaluated_at": "2026-07-06T00:01:00Z",
  "broker_state_known": true,
  "protective_order": {
    "schema_version": 1,
    "kind": "stop_loss",
    "stop_price": 95.0
  },
  "protective_exception_approved": false
}
```

## Decision Shape

Decisions are journaled with event type:

```text
risk.decision.evaluated
```

The decision payload contains:

- `request_id`;
- `evaluated_at`;
- `symbol`;
- `risk_intent`;
- `result`: `passed` or `blocked`;
- the evaluated request snapshot;
- structured check results.

## Guarantees

- Every risk decision is appended to the event journal.
- The engine is deterministic and local.
- No network, live feed, broker, account, routing, submission, or credential path is used.
- Duplicate request IDs block.
- Stale market data blocks.
- Unknown broker state blocks risk-increasing requests.
- Risk-increasing requests require a valid protective order or explicitly approved exception.
- Invalid policy, request, protective plan, check, and decision records fail validation.

## Current Limitations

- No position tracking yet.
- OMS state transition validation exists separately in `docs/OMS_STATE_MACHINE.md`, but the risk
  engine is not integrated into a broker or OMS workflow yet.
- Approval ticket recording exists separately in `docs/APPROVAL_TICKETS.md`, but the risk engine
  does not create approval tickets directly yet.
- Fake broker behavior exists separately in `docs/FAKE_BROKER.md`, but the risk engine is not
  integrated into a broker or OMS workflow yet.
- No portfolio-level exposure model yet.
- No persistence beyond the local JSONL event journal.
- Numeric values currently use Python floats because earlier slices use Python floats.
