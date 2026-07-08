export type VisualWorkflowNodeType =
  | "replay_source"
  | "bar_builder"
  | "strategy_trigger"
  | "risk_check"
  | "approval_ticket"
  | "fake_broker"
  | "position_update"
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

export type VisualWorkflowNodeDefinition = {
  id: string;
  type: VisualWorkflowNodeType;
  title: string;
  detail: string;
  badge: string;
  role: VisualWorkflowNodeRole;
  requiredForRiskIncreasingPath: boolean;
  supportsExecution: false;
  position: {
    x: number;
    y: number;
  };
};

export type VisualWorkflowEdgeDefinition = {
  id: string;
  source: string;
  target: string;
};

export const simulationWorkflowNodeCatalog: VisualWorkflowNodeDefinition[] = [
  {
    id: "replay-source",
    type: "replay_source",
    title: "Replay source",
    detail: "Deterministic local replay input",
    badge: "local replay",
    role: "source",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 0, y: 110 },
  },
  {
    id: "bar-builder",
    type: "bar_builder",
    title: "Bar builder",
    detail: "Builds 5-minute simulation bars",
    badge: "deterministic",
    role: "transform",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 250, y: 110 },
  },
  {
    id: "strategy-trigger",
    type: "strategy_trigger",
    title: "Strategy trigger",
    detail: "First bar breakout with volume filter",
    badge: "signal only",
    role: "transform",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 500, y: 110 },
  },
  {
    id: "risk-check",
    type: "risk_check",
    title: "Risk check",
    detail: "Blocks stale data and unsafe state",
    badge: "required",
    role: "gate",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 750, y: 0 },
  },
  {
    id: "approval-ticket",
    type: "approval_ticket",
    title: "Approval ticket",
    detail: "Manual simulation approval gate",
    badge: "required",
    role: "approval",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 750, y: 220 },
  },
  {
    id: "fake-broker",
    type: "fake_broker",
    title: "Fake broker",
    detail: "Simulation-only acknowledgement and fills",
    badge: "no transport",
    role: "simulation",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 1000, y: 110 },
  },
  {
    id: "position-update",
    type: "position_update",
    title: "Position update",
    detail: "Applies simulated fills to local positions",
    badge: "simulation",
    role: "monitoring",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 1250, y: 20 },
  },
  {
    id: "alert",
    type: "alert",
    title: "Alert",
    detail: "Records local protection and safety alerts",
    badge: "local noop",
    role: "monitoring",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 1250, y: 210 },
  },
  {
    id: "audit-sink",
    type: "audit_sink",
    title: "Audit sink",
    detail: "Append-only journal references",
    badge: "append only",
    role: "audit",
    requiredForRiskIncreasingPath: true,
    supportsExecution: false,
    position: { x: 1500, y: 110 },
  },
];

export const simulationWorkflowEdgeCatalog: VisualWorkflowEdgeDefinition[] = [
  buildEdge("replay-source", "bar-builder"),
  buildEdge("bar-builder", "strategy-trigger"),
  buildEdge("strategy-trigger", "risk-check"),
  buildEdge("risk-check", "approval-ticket"),
  buildEdge("approval-ticket", "fake-broker"),
  buildEdge("fake-broker", "position-update"),
  buildEdge("position-update", "alert"),
  buildEdge("alert", "audit-sink"),
];

function buildEdge(source: string, target: string): VisualWorkflowEdgeDefinition {
  return {
    id: `${source}-to-${target}`,
    source,
    target,
  };
}
