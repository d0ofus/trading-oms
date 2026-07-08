# Visual Workflow Builder

Slice 015 introduces the first safe visual workflow builder foundation. Slice 032 adds the first
React Flow canvas scaffold for Gate C.

It does not add live trading, broker integration, order intents, order submission, risk checks,
approval execution workflow, OMS or fake broker orchestration, real market-data ingestion, backend
API mutation, persistence, arbitrary expressions, custom scripts, code execution, file
import/export, credentials, tokens, or secrets.

## Purpose

The visual builder is a frontend-only inspection and configuration surface for the typed
replay-only Strategy DSL. It helps operators see the supported `close_above_sma` workflow as local
nodes and inspect the generated JSON-compatible DSL document.

The builder is local state only. It does not save, run, submit, transmit, connect, import, export,
or call a backend mutation API.

## Visual Flow

The original Strategy DSL preview graph is fixed to:

```text
Replay bars -> Close source -> Simple moving average -> Bias signal -> Strategy DSL
```

Each node is descriptive only. Nodes do not execute orders, call brokers, fetch live market data, or
run arbitrary code.

The Gate C React Flow scaffold is fixed to:

```text
Replay source -> Bar builder -> Strategy trigger -> Risk check -> Manual approval -> Fake broker -> Audit sink
```

The scaffold is non-executing. Slice 033 allows local node movement only; nodes are still not
connectable and graph layout changes are not persisted.

## Safe Controls

The builder exposes only these local controls:

- `symbol`
- `lookback_bars`
- `bar_timeframe_seconds`

The generated DSL always uses:

- `schema_version: 1`
- `strategy_id: visual-close-above-sma`
- `strategy_type: close_above_sma`
- `mode: replay`
- `parameters.price_source: close`

## Safety Posture

The UI explicitly displays:

- `Replay only`
- `No broker connectivity`
- `No order actions`
- `No credential fields`

The builder contains no buttons, forms, order submission controls, broker connection controls,
Telegram delivery controls, credential fields, import/export controls, or code execution controls.

## Current Limitations

- Frontend-only local state.
- Fixed node graph for `close_above_sma`.
- React Flow canvas scaffold exists.
- Local node layout editing exists.
- No persistence or backend API integration.
- No workflow save or run behavior.
- No file import or export.
- No validation call to the backend Strategy DSL parser yet.
- No custom strategy types, arbitrary expressions, scripts, or code execution.
