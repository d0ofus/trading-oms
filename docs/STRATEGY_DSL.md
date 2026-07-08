# Strategy DSL

Slice 014 introduces the first typed Strategy DSL foundation.

It does not add live trading, broker integration, order intents, order submission, risk checks,
approval tickets, OMS integration, fake broker orchestration, real market-data ingestion, arbitrary
expressions, code execution, YAML parsing, UI editing, or the visual workflow builder.

## Purpose

The Strategy DSL is a versioned JSON-compatible representation of replay-only strategy
configuration. It is validated before execution and compiles to the existing replay strategy
configuration.

The initial DSL supports only the existing replay strategy:

```text
close_above_sma
```

## Document Shape

Example:

```json
{
  "schema_version": 1,
  "strategy_id": "dsl-close-above-sma-demo",
  "strategy_type": "close_above_sma",
  "mode": "replay",
  "symbol": "AAPL",
  "bar_timeframe_seconds": 60,
  "parameters": {
    "lookback_bars": 3,
    "price_source": "close"
  }
}
```

Supported fields:

- `schema_version`: must be `1`;
- `strategy_id`: non-empty identifier;
- `strategy_type`: must be `close_above_sma`;
- `mode`: must be `replay`;
- `symbol`: uppercase symbol;
- `bar_timeframe_seconds`: positive integer;
- `parameters.lookback_bars`: integer greater than or equal to `2`;
- `parameters.price_source`: must be `close`.

Unknown fields are rejected.

## Parsing And Compilation

The backend module is:

```text
trading_oms_backend.strategy_dsl
```

It can:

- parse a JSON-compatible Python mapping;
- parse a JSON string;
- validate the typed DSL document;
- compile the DSL document to `ReplayStrategyConfig`;
- run the DSL in replay mode by calling the existing replay strategy path.

DSL execution still consumes local `Bar` records only. Generated signals are journaled through the
existing `strategy.signal.generated` event type.

## Safety Rejections

The DSL rejects:

- live mode;
- unsupported strategy types;
- unsupported price sources;
- invalid symbols, timeframes, and lookbacks;
- unknown fields;
- action/order/broker-shaped fields;
- credential or secret-shaped fields;
- arbitrary-code-shaped fields such as expression, eval, function, script, import, or code.

The DSL cannot express buy/sell actions, sides, quantities, order types, broker destinations,
transmission flags, account identifiers, tokens, passwords, credentials, or host/socket details.

## Guarantees

- Deterministic.
- Versioned.
- Validated before execution.
- No arbitrary code execution.
- Replay-compatible.
- UI-compatible as a future visual-builder target.
- Auditable through the existing strategy signal journal events.
- No network, live feed, broker, account, order-routing, order-submission, or credential path is
  used.

## Current Limitations

- JSON-compatible inputs only; YAML parsing is deferred.
- One supported strategy type: `close_above_sma`.
- One supported price source: `close`.
- A first local visual workflow builder exists, documented in `docs/VISUAL_WORKFLOW_BUILDER.md`.
- No persisted frontend DSL editor yet.
- No risk, approval, OMS, or broker orchestration yet.
- Numeric values currently use Python floats because bars currently use Python floats.
