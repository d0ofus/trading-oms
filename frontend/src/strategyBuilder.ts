export type StrategyBuilderState = {
  symbol: string;
  lookbackBars: number;
  timeframeSeconds: number;
};

export type StrategyDslDocument = {
  schema_version: 1;
  strategy_id: "visual-close-above-sma";
  strategy_type: "close_above_sma";
  mode: "replay";
  symbol: string;
  bar_timeframe_seconds: number;
  parameters: {
    lookback_bars: number;
    price_source: "close";
  };
};

export type StrategyBuilderNode = {
  id: string;
  label: string;
  detail: string;
};

export const defaultStrategyBuilderState: StrategyBuilderState = {
  symbol: "AAPL",
  lookbackBars: 3,
  timeframeSeconds: 60,
};

export const strategyBuilderNodes: StrategyBuilderNode[] = [
  {
    id: "replay-bars",
    label: "Replay bars",
    detail: "Local deterministic bars only",
  },
  {
    id: "close-source",
    label: "Close source",
    detail: "Price source fixed to close",
  },
  {
    id: "sma",
    label: "Simple moving average",
    detail: "Lookback from safe local control",
  },
  {
    id: "bias-signal",
    label: "Bias signal",
    detail: "Replay signal, not an order intent",
  },
  {
    id: "strategy-dsl",
    label: "Strategy DSL",
    detail: "Generated JSON preview",
  },
];

export function updateStrategyBuilderState(
  current: StrategyBuilderState,
  updates: Partial<StrategyBuilderState>,
): StrategyBuilderState {
  return {
    symbol: normalizeSymbol(updates.symbol ?? current.symbol),
    lookbackBars: clampWholeNumber(updates.lookbackBars ?? current.lookbackBars, 2),
    timeframeSeconds: clampWholeNumber(updates.timeframeSeconds ?? current.timeframeSeconds, 1),
  };
}

export function buildStrategyDslDocument(state: StrategyBuilderState): StrategyDslDocument {
  const safeState = updateStrategyBuilderState(defaultStrategyBuilderState, state);

  return {
    schema_version: 1,
    strategy_id: "visual-close-above-sma",
    strategy_type: "close_above_sma",
    mode: "replay",
    symbol: safeState.symbol,
    bar_timeframe_seconds: safeState.timeframeSeconds,
    parameters: {
      lookback_bars: safeState.lookbackBars,
      price_source: "close",
    },
  };
}

export function formatStrategyDslPreview(state: StrategyBuilderState) {
  return JSON.stringify(buildStrategyDslDocument(state), null, 2);
}

function normalizeSymbol(value: string) {
  const match = value.toUpperCase().match(/[A-Z0-9.-]+/);
  return (match?.[0] ?? defaultStrategyBuilderState.symbol).slice(0, 12);
}

function clampWholeNumber(value: number, minimum: number) {
  if (!Number.isFinite(value)) {
    return minimum;
  }
  return Math.max(minimum, Math.floor(value));
}
