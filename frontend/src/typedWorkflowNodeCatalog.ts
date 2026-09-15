export type VisualWorkflowPortType =
  | "TradeStream"
  | "Session"
  | "Symbol"
  | "Contract"
  | "Price"
  | "Money"
  | "TriggerEvent"
  | "OrderPlan"
  | "AuthorizedOrderPlan"
  | "ProtectedOrderPlan"
  | "ExecutionReport"
  | "PositionState"
  | "AuditEvent";

export type VisualWorkflowNodeType =
  | "historical_dataset"
  | "live_trades"
  | "symbol_input"
  | "dollar_risk_input"
  | "rth_session"
  | "opening_range_high"
  | "opening_range_low"
  | "day_high"
  | "day_low"
  | "crosses_above"
  | "crosses_below"
  | "one_shot_per_session"
  | "long_risk_size"
  | "risk_gate"
  | "stale_data_gate"
  | "reconciliation_gate"
  | "emergency_stop_gate"
  | "armed_run_authorization"
  | "entry_lifetime"
  | "position_lifetime"
  | "protective_stop"
  | "stop_market_entry"
  | "fake_broker"
  | "position_monitor"
  | "alert"
  | "audit_sink";

export type VisualWorkflowNodeRole =
  | "source"
  | "transform"
  | "gate"
  | "approval"
  | "simulation"
  | "monitoring"
  | "audit";

export type VisualWorkflowNodeConfig = Record<string, string | number | boolean>;

export type VisualWorkflowNodeDefinition = {
  id: string;
  type: VisualWorkflowNodeType;
  title: string;
  detail: string;
  badge: string;
  role: VisualWorkflowNodeRole;
  requiredForRiskIncreasingPath: boolean;
  supportsExecution: false;
  executionCapability: "none" | "simulation_only";
  inputPorts: Record<string, VisualWorkflowPortType>;
  outputPorts: Record<string, VisualWorkflowPortType>;
  config: VisualWorkflowNodeConfig;
  position: {
    x: number;
    y: number;
  };
};

export type VisualWorkflowEdgeDefinition = {
  id: string;
  source: string;
  sourcePort: string;
  target: string;
  targetPort: string;
};

export type VisualWorkflowPaletteItem = {
  paletteId: string;
  type: VisualWorkflowNodeType;
  label: string;
  category: string;
  defaultConfig: VisualWorkflowNodeConfig;
};

type NodeTemplate = Omit<VisualWorkflowNodeDefinition, "id" | "position" | "type">;

export const visualWorkflowNodeTemplates: Record<VisualWorkflowNodeType, NodeTemplate> = {
  historical_dataset: template(
    "Historical dataset",
    "Immutable trade-tick or labeled five-second replay data",
    "dataset",
    "source",
    {},
    { trades: "TradeStream" },
    { resolution: "trade_ticks" },
  ),
  live_trades: template(
    "Live trades",
    "Read-only paper market-data stream for live-forward simulation",
    "read only",
    "source",
    {},
    { trades: "TradeStream" },
  ),
  symbol_input: template(
    "Symbol",
    "Required long US-stock runtime input",
    "runtime",
    "source",
    {},
    { symbol: "Symbol" },
  ),
  dollar_risk_input: template(
    "Dollar risk",
    "Maximum dollar loss supplied when a run is drafted",
    "runtime",
    "source",
    {},
    { money: "Money" },
  ),
  rth_session: template(
    "US regular session",
    "Uses resolved contract liquid hours and qualifying last trades",
    "RTH",
    "transform",
    { trades: "TradeStream", symbol: "Symbol" },
    { trades: "TradeStream", session: "Session", contract: "Contract" },
  ),
  opening_range_high: template(
    "Opening-range high",
    "Highest qualifying last trade during the configured opening interval",
    "session metric",
    "transform",
    { trades: "TradeStream", session: "Session" },
    { price: "Price" },
    { minutes: 5 },
  ),
  opening_range_low: template(
    "Opening-range low",
    "Lowest qualifying last trade during the configured opening interval",
    "session metric",
    "transform",
    { trades: "TradeStream", session: "Session" },
    { price: "Price" },
    { minutes: 5 },
  ),
  day_high: template(
    "Day high",
    "Rolling regular-session trade high",
    "session metric",
    "transform",
    { trades: "TradeStream", session: "Session" },
    { price: "Price" },
  ),
  day_low: template(
    "Day low",
    "Rolling regular-session low frozen when the trigger occurs",
    "session metric",
    "transform",
    { trades: "TradeStream", session: "Session" },
    { price: "Price" },
  ),
  crosses_above: template(
    "Crosses above",
    "First transition at or above level plus minimum tick",
    "typed trigger",
    "transform",
    { trades: "TradeStream", level: "Price", contract: "Contract" },
    { trigger: "TriggerEvent" },
  ),
  crosses_below: template(
    "Crosses below",
    "First transition at or below level less minimum tick",
    "typed trigger",
    "transform",
    { trades: "TradeStream", level: "Price", contract: "Contract" },
    { trigger: "TriggerEvent" },
  ),
  one_shot_per_session: template(
    "One shot per session",
    "Prevents duplicate triggers in the same RTH session",
    "idempotency",
    "gate",
    { trigger: "TriggerEvent", session: "Session" },
    { trigger: "TriggerEvent" },
  ),
  long_risk_size: template(
    "Long dollar-risk sizing",
    "Floors dollar loss divided by conservative per-share risk",
    "Decimal",
    "transform",
    {
      trigger: "TriggerEvent",
      stop_price: "Price",
      maximum_dollar_loss: "Money",
      contract: "Contract",
    },
    { plan: "OrderPlan" },
  ),
  risk_gate: template(
    "Risk gate",
    "Applies immutable administrator dollar, share, notional, exposure, and loss caps",
    "required",
    "gate",
    { plan: "OrderPlan" },
    { plan: "OrderPlan" },
  ),
  stale_data_gate: template(
    "Stale-data gate",
    "Blocks gaps, incomplete datasets, and stale live-forward data",
    "required",
    "gate",
    { plan: "OrderPlan", trades: "TradeStream" },
    { plan: "OrderPlan" },
  ),
  reconciliation_gate: template(
    "Reconciliation gate",
    "Blocks unknown execution state",
    "required",
    "gate",
    { plan: "OrderPlan" },
    { plan: "OrderPlan" },
  ),
  emergency_stop_gate: template(
    "Emergency-stop gate",
    "Disarms risk-increasing runs when the global stop is active",
    "required",
    "gate",
    { plan: "OrderPlan" },
    { plan: "OrderPlan" },
  ),
  armed_run_authorization: template(
    "Armed-run authorization",
    "Verifies the immutable operator-approved fingerprint",
    "human gate",
    "approval",
    { plan: "OrderPlan" },
    { plan: "AuthorizedOrderPlan" },
  ),
  entry_lifetime: template(
    "Entry lifetime",
    "DAY expires at RTH close; GTC resets session metrics until explicit expiry",
    "required",
    "gate",
    { plan: "AuthorizedOrderPlan" },
    { plan: "AuthorizedOrderPlan" },
    { value: "DAY" },
  ),
  position_lifetime: template(
    "Position lifetime",
    "Hold protected, exit at time, or use a validated typed exit",
    "required",
    "gate",
    { plan: "AuthorizedOrderPlan" },
    { plan: "AuthorizedOrderPlan" },
    { kind: "hold_with_protective_stop" },
  ),
  protective_stop: template(
    "Protective stop",
    "Plans a GTC sell stop before entry activation",
    "required",
    "gate",
    { plan: "AuthorizedOrderPlan", stop_price: "Price" },
    { plan: "ProtectedOrderPlan" },
    { time_in_force: "GTC" },
  ),
  stop_market_entry: template(
    "Stop-market entry",
    "Activates the protected entry plan on the typed cross",
    "planned only",
    "transform",
    { plan: "ProtectedOrderPlan", trigger: "TriggerEvent" },
    { plan: "ProtectedOrderPlan" },
  ),
  fake_broker: template(
    "Fake broker",
    "Deterministic simulated acknowledgement and adverse fills",
    "simulation only",
    "simulation",
    { plan: "ProtectedOrderPlan" },
    { report: "ExecutionReport" },
    {},
    "simulation_only",
  ),
  position_monitor: template(
    "Position monitor",
    "Tracks simulated position and protection state",
    "required",
    "monitoring",
    { report: "ExecutionReport" },
    { position: "PositionState" },
  ),
  alert: template(
    "Alerts",
    "Records critical simulated protection and risk-budget events",
    "local",
    "monitoring",
    { position: "PositionState" },
    { event: "AuditEvent" },
  ),
  audit_sink: template(
    "Audit sink",
    "Writes append-only journal events and references",
    "append only",
    "audit",
    { event: "AuditEvent" },
    {},
  ),
};

export const visualWorkflowPalette: VisualWorkflowPaletteItem[] = [
  palette("historical_dataset", "Historical dataset", "Inputs"),
  palette("live_trades", "Live trades", "Inputs"),
  palette("symbol_input", "Symbol", "Inputs"),
  palette("dollar_risk_input", "Dollar risk", "Inputs"),
  palette("rth_session", "US regular session", "Session"),
  palette("opening_range_high", "First 1-minute high", "Session metrics", { minutes: 1 }),
  palette("opening_range_low", "First 1-minute low", "Session metrics", { minutes: 1 }),
  palette("opening_range_high", "First 5-minute high", "Session metrics", { minutes: 5 }),
  palette("opening_range_low", "First 5-minute low", "Session metrics", { minutes: 5 }),
  palette("opening_range_high", "Configurable opening-range high", "Session metrics"),
  palette("opening_range_low", "Configurable opening-range low", "Session metrics"),
  palette("day_high", "Day high", "Session metrics"),
  palette("day_low", "Day low", "Session metrics"),
  palette("crosses_above", "Crosses above", "Logic"),
  palette("crosses_below", "Crosses below", "Logic"),
  palette("one_shot_per_session", "One shot per session", "Logic"),
  palette("long_risk_size", "Long dollar-risk sizing", "Sizing"),
  palette("risk_gate", "Risk gate", "Safety"),
  palette("stale_data_gate", "Stale-data gate", "Safety"),
  palette("reconciliation_gate", "Reconciliation gate", "Safety"),
  palette("emergency_stop_gate", "Emergency-stop gate", "Safety"),
  palette("armed_run_authorization", "Armed-run authorization", "Safety"),
  palette("entry_lifetime", "Entry lifetime", "Orders"),
  palette("position_lifetime", "Position lifetime", "Orders"),
  palette("protective_stop", "Protective stop", "Orders"),
  palette("stop_market_entry", "Stop-market entry", "Orders"),
  palette("fake_broker", "Fake broker", "Execution"),
  palette("position_monitor", "Position monitor", "Monitoring"),
  palette("alert", "Alerts", "Monitoring"),
  palette("audit_sink", "Audit sink", "Monitoring"),
];

export const simulationWorkflowNodeCatalog: VisualWorkflowNodeDefinition[] = [
  node("historical-data", "historical_dataset", 0, 0),
  node("symbol", "symbol_input", 0, 180),
  node("dollar-risk", "dollar_risk_input", 0, 360),
  node("rth", "rth_session", 280, 0),
  node("opening-high", "opening_range_high", 560, 0, { minutes: 5 }),
  node("day-low", "day_low", 560, 220),
  node("cross", "crosses_above", 840, 0),
  node("one-shot", "one_shot_per_session", 1120, 0),
  node("risk-size", "long_risk_size", 1400, 0),
  node("risk-gate", "risk_gate", 1680, 0),
  node("stale-data-gate", "stale_data_gate", 1960, 0),
  node("reconciliation-gate", "reconciliation_gate", 2240, 0),
  node("emergency-stop-gate", "emergency_stop_gate", 2520, 0),
  node("arming", "armed_run_authorization", 2800, 0),
  node("entry-lifetime", "entry_lifetime", 3080, 0),
  node("position-lifetime", "position_lifetime", 3360, 0),
  node("protective-stop", "protective_stop", 3640, 0),
  node("entry", "stop_market_entry", 3920, 0),
  node("fake-broker", "fake_broker", 4200, 0),
  node("position-monitor", "position_monitor", 4480, 0),
  node("alert", "alert", 4760, 0),
  node("audit", "audit_sink", 5040, 0),
];

export const simulationWorkflowEdgeCatalog: VisualWorkflowEdgeDefinition[] = [
  edge("historical-data", "trades", "rth", "trades"),
  edge("symbol", "symbol", "rth", "symbol"),
  edge("rth", "trades", "opening-high", "trades"),
  edge("rth", "session", "opening-high", "session"),
  edge("rth", "trades", "day-low", "trades"),
  edge("rth", "session", "day-low", "session"),
  edge("rth", "trades", "cross", "trades"),
  edge("rth", "contract", "cross", "contract"),
  edge("opening-high", "price", "cross", "level"),
  edge("cross", "trigger", "one-shot", "trigger"),
  edge("rth", "session", "one-shot", "session"),
  edge("one-shot", "trigger", "risk-size", "trigger"),
  edge("day-low", "price", "risk-size", "stop_price"),
  edge("dollar-risk", "money", "risk-size", "maximum_dollar_loss"),
  edge("rth", "contract", "risk-size", "contract"),
  edge("risk-size", "plan", "risk-gate", "plan"),
  edge("risk-gate", "plan", "stale-data-gate", "plan"),
  edge("rth", "trades", "stale-data-gate", "trades"),
  edge("stale-data-gate", "plan", "reconciliation-gate", "plan"),
  edge("reconciliation-gate", "plan", "emergency-stop-gate", "plan"),
  edge("emergency-stop-gate", "plan", "arming", "plan"),
  edge("arming", "plan", "entry-lifetime", "plan"),
  edge("entry-lifetime", "plan", "position-lifetime", "plan"),
  edge("position-lifetime", "plan", "protective-stop", "plan"),
  edge("day-low", "price", "protective-stop", "stop_price"),
  edge("protective-stop", "plan", "entry", "plan"),
  edge("one-shot", "trigger", "entry", "trigger"),
  edge("entry", "plan", "fake-broker", "plan"),
  edge("fake-broker", "report", "position-monitor", "report"),
  edge("position-monitor", "position", "alert", "position"),
  edge("alert", "event", "audit", "event"),
];

export function createVisualWorkflowNode(
  id: string,
  type: VisualWorkflowNodeType,
  position: { x: number; y: number },
  config: VisualWorkflowNodeConfig = {},
): VisualWorkflowNodeDefinition {
  return node(id, type, position.x, position.y, config);
}

export function portTypeForHandle(
  node: VisualWorkflowNodeDefinition,
  direction: "input" | "output",
  handle: string,
): VisualWorkflowPortType | undefined {
  return direction === "input" ? node.inputPorts[handle] : node.outputPorts[handle];
}

function template(
  title: string,
  detail: string,
  badge: string,
  role: VisualWorkflowNodeRole,
  inputPorts: Record<string, VisualWorkflowPortType>,
  outputPorts: Record<string, VisualWorkflowPortType>,
  config: VisualWorkflowNodeConfig = {},
  executionCapability: "none" | "simulation_only" = "none",
): NodeTemplate {
  return {
    title,
    detail,
    badge,
    role,
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    executionCapability,
    inputPorts,
    outputPorts,
    config,
  };
}

function node(
  id: string,
  type: VisualWorkflowNodeType,
  x: number,
  y: number,
  config: VisualWorkflowNodeConfig = {},
): VisualWorkflowNodeDefinition {
  const source = visualWorkflowNodeTemplates[type];
  return {
    ...source,
    id,
    type,
    config: { ...source.config, ...config },
    inputPorts: { ...source.inputPorts },
    outputPorts: { ...source.outputPorts },
    position: { x, y },
  };
}

function palette(
  type: VisualWorkflowNodeType,
  label: string,
  category: string,
  config: VisualWorkflowNodeConfig = {},
): VisualWorkflowPaletteItem {
  return {
    paletteId: `${type}-${label.toLowerCase().replaceAll(" ", "-")}`,
    type,
    label,
    category,
    defaultConfig: { ...visualWorkflowNodeTemplates[type].config, ...config },
  };
}

function edge(
  source: string,
  sourcePort: string,
  target: string,
  targetPort: string,
): VisualWorkflowEdgeDefinition {
  return {
    id: `${source}.${sourcePort}-to-${target}.${targetPort}`,
    source,
    sourcePort,
    target,
    targetPort,
  };
}
