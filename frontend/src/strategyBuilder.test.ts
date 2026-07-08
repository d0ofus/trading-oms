import { describe, expect, it } from "vitest";

import {
  buildStrategyDslDocument,
  defaultStrategyBuilderState,
  strategyBuilderNodes,
  updateStrategyBuilderState,
} from "./strategyBuilder";

describe("strategyBuilder", () => {
  it("builds the replay-only close_above_sma DSL document", () => {
    expect(buildStrategyDslDocument(defaultStrategyBuilderState)).toEqual({
      schema_version: 1,
      strategy_id: "visual-close-above-sma",
      strategy_type: "close_above_sma",
      mode: "replay",
      symbol: "AAPL",
      bar_timeframe_seconds: 60,
      parameters: {
        lookback_bars: 3,
        price_source: "close",
      },
    });
  });

  it("updates only safe local DSL fields", () => {
    const updated = updateStrategyBuilderState(defaultStrategyBuilderState, {
      symbol: "msft",
      lookbackBars: 5,
      timeframeSeconds: 300,
    });

    expect(buildStrategyDslDocument(updated)).toMatchObject({
      mode: "replay",
      strategy_type: "close_above_sma",
      symbol: "MSFT",
      bar_timeframe_seconds: 300,
      parameters: {
        lookback_bars: 5,
        price_source: "close",
      },
    });
  });

  it("keeps edited values inside the safe DSL shape", () => {
    const updated = updateStrategyBuilderState(defaultStrategyBuilderState, {
      symbol: "aapl submit order",
      lookbackBars: 1,
      timeframeSeconds: 0,
    });

    expect(buildStrategyDslDocument(updated)).toEqual({
      schema_version: 1,
      strategy_id: "visual-close-above-sma",
      strategy_type: "close_above_sma",
      mode: "replay",
      symbol: "AAPL",
      bar_timeframe_seconds: 1,
      parameters: {
        lookback_bars: 2,
        price_source: "close",
      },
    });
  });

  it("defines the expected local visual workflow nodes", () => {
    expect(strategyBuilderNodes.map((node) => node.label)).toEqual([
      "Replay bars",
      "Close source",
      "Simple moving average",
      "Bias signal",
      "Strategy DSL",
    ]);
  });
});
