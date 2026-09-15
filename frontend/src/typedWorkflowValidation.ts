import {
  visualWorkflowNodeTemplates,
  type VisualWorkflowEdgeDefinition,
  type VisualWorkflowNodeDefinition,
  type VisualWorkflowNodeType,
} from "./typedWorkflowNodeCatalog";

export type VisualWorkflowGraphNodeInput = {
  id: string;
  type: string;
};

export type VisualWorkflowGraphEdgeInput = {
  source: string;
  sourcePort?: string;
  target: string;
  targetPort?: string;
};

export type VisualWorkflowValidationErrorCode =
  | "unsupported_topology"
  | "missing_required_node"
  | "unsafe_action_node"
  | "unsupported_node"
  | "unknown_edge_endpoint"
  | "unknown_port"
  | "incompatible_port"
  | "duplicate_input_connection"
  | "missing_input_connection"
  | "multiple_execution_sinks"
  | "unsafe_execution_path"
  | "cycle_detected";

export type VisualWorkflowValidationError = {
  code: VisualWorkflowValidationErrorCode;
  message: string;
  nodeId?: string;
  nodeType?: string;
  edgeId?: string;
};

export type VisualWorkflowValidationResult = {
  status: "valid" | "invalid";
  errors: VisualWorkflowValidationError[];
};

const supportedNodeTypes = new Set(Object.keys(visualWorkflowNodeTemplates));

const requiredRiskIncreasingNodeTypes: Array<{
  type: VisualWorkflowNodeType;
  label: string;
}> = [
  { type: "historical_dataset", label: "historical dataset" },
  { type: "symbol_input", label: "symbol input" },
  { type: "dollar_risk_input", label: "dollar-risk input" },
  { type: "rth_session", label: "RTH session" },
  { type: "opening_range_high", label: "opening-range high" },
  { type: "day_low", label: "day low" },
  { type: "crosses_above", label: "crosses-above trigger" },
  { type: "one_shot_per_session", label: "one-shot session gate" },
  { type: "long_risk_size", label: "dollar-risk sizing" },
  { type: "risk_gate", label: "risk gate" },
  { type: "stale_data_gate", label: "stale-data gate" },
  { type: "reconciliation_gate", label: "reconciliation gate" },
  { type: "emergency_stop_gate", label: "emergency-stop gate" },
  { type: "armed_run_authorization", label: "armed-run authorization" },
  { type: "entry_lifetime", label: "entry lifetime" },
  { type: "position_lifetime", label: "position lifetime" },
  { type: "protective_stop", label: "protective stop" },
  { type: "stop_market_entry", label: "stop-market entry" },
  { type: "fake_broker", label: "fake broker" },
  { type: "position_monitor", label: "position monitor" },
  { type: "alert", label: "alert" },
  { type: "audit_sink", label: "audit sink" },
];

const upstreamSafetyTypes = new Set<VisualWorkflowNodeType>([
  "long_risk_size",
  "risk_gate",
  "stale_data_gate",
  "reconciliation_gate",
  "emergency_stop_gate",
  "armed_run_authorization",
  "entry_lifetime",
  "position_lifetime",
  "protective_stop",
  "stop_market_entry",
]);

const downstreamSafetyTypes = new Set<VisualWorkflowNodeType>([
  "position_monitor",
  "alert",
  "audit_sink",
]);

const unsafeActionNodeTypes = new Set([
  "broker_transport",
  "credential",
  "custom_code",
  "eval",
  "ibkr_transport",
  "live_order",
  "script",
  "submit_order",
  "transmit_order",
]);

export function validateVisualWorkflowGraph(
  nodes: VisualWorkflowGraphNodeInput[],
  edges: VisualWorkflowGraphEdgeInput[],
): VisualWorkflowValidationResult {
  const errors: VisualWorkflowValidationError[] = [];
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const nodeTypes = new Set(nodes.map((node) => node.type));

  for (const required of requiredRiskIncreasingNodeTypes) {
    if (!nodeTypes.has(required.type)) {
      errors.push({
        code: "missing_required_node",
        message: `Missing required ${required.label} node.`,
        nodeType: required.type,
      });
    }
  }

  for (const node of nodes) {
    if (unsafeActionNodeTypes.has(node.type)) {
      errors.push({
        code: "unsafe_action_node",
        message: `Unsafe action node '${node.type}' is not allowed in simulation workflows.`,
        nodeId: node.id,
        nodeType: node.type,
      });
    } else if (!supportedNodeTypes.has(node.type)) {
      errors.push({
        code: "unsupported_node",
        message: `Unsupported node type '${node.type}'.`,
        nodeId: node.id,
        nodeType: node.type,
      });
    }
  }

  const executionNodes = nodes.filter((node) => node.type === "fake_broker");
  if (executionNodes.length !== 1) {
    errors.push({
      code: "multiple_execution_sinks",
      message: "Workflow must contain exactly one simulation execution sink.",
    });
  }

  const occupiedInputs = new Set<string>();
  const validEndpointEdges: VisualWorkflowGraphEdgeInput[] = [];
  for (const [index, edge] of edges.entries()) {
    const edgeId = `${edge.source}.${edge.sourcePort ?? "?"}->${edge.target}.${edge.targetPort ?? "?"}`;
    const source = nodesById.get(edge.source);
    const target = nodesById.get(edge.target);
    if (!source || !target) {
      errors.push({
        code: "unknown_edge_endpoint",
        message: `Edge ${edge.source}->${edge.target} references an unknown node.`,
        edgeId,
      });
      continue;
    }
    const sourceTemplate = isSupportedType(source.type)
      ? visualWorkflowNodeTemplates[source.type]
      : undefined;
    const targetTemplate = isSupportedType(target.type)
      ? visualWorkflowNodeTemplates[target.type]
      : undefined;
    const outputType = edge.sourcePort ? sourceTemplate?.outputPorts[edge.sourcePort] : undefined;
    const inputType = edge.targetPort ? targetTemplate?.inputPorts[edge.targetPort] : undefined;
    if (!outputType || !inputType) {
      errors.push({
        code: "unknown_port",
        message: `Edge ${index + 1} must connect named, existing typed ports.`,
        edgeId,
      });
      continue;
    }
    if (outputType !== inputType) {
      errors.push({
        code: "incompatible_port",
        message: `Cannot connect ${outputType} to ${inputType}.`,
        edgeId,
      });
      continue;
    }
    const inputKey = `${edge.target}.${edge.targetPort}`;
    if (occupiedInputs.has(inputKey)) {
      errors.push({
        code: "duplicate_input_connection",
        message: `Input ${inputKey} already has a connection.`,
        edgeId,
      });
      continue;
    }
    occupiedInputs.add(inputKey);
    validEndpointEdges.push(edge);
  }

  if (hasCycle(nodes, validEndpointEdges)) {
    errors.push({
      code: "cycle_detected",
      message: "Workflow graph contains a cycle.",
    });
  }

  if (executionNodes.length === 1) {
    const executionId = executionNodes[0].id;
    const ancestors = reachable(executionId, validEndpointEdges, true);
    const descendants = reachable(executionId, validEndpointEdges, false);
    const ancestorTypes = new Set(
      [...ancestors].map((nodeId) => nodesById.get(nodeId)?.type as VisualWorkflowNodeType),
    );
    const descendantTypes = new Set(
      [...descendants].map((nodeId) => nodesById.get(nodeId)?.type as VisualWorkflowNodeType),
    );
    if (![...upstreamSafetyTypes].every((type) => ancestorTypes.has(type))) {
      errors.push({
        code: "unsafe_execution_path",
        message: "Every required safety node must be upstream of fake execution.",
      });
    }
    if (![...downstreamSafetyTypes].every((type) => descendantTypes.has(type))) {
      errors.push({
        code: "unsafe_execution_path",
        message: "Position monitoring, alerts, and audit must follow fake execution.",
      });
    }
  }

  for (const node of nodes) {
    if (!isSupportedType(node.type)) {
      continue;
    }
    for (const inputName of Object.keys(visualWorkflowNodeTemplates[node.type].inputPorts)) {
      if (!occupiedInputs.has(`${node.id}.${inputName}`)) {
        errors.push({
          code: "missing_input_connection",
          message: `Required input ${node.id}.${inputName} is not connected.`,
          nodeId: node.id,
          nodeType: node.type,
        });
      }
    }
  }

  const edgeKeys = edges.map((edge) =>
    `${nodesById.get(edge.source)?.type}:${edge.sourcePort}:${nodesById.get(edge.target)?.type}:${edge.targetPort}`,
  );
  if (nodes.length !== requiredRiskIncreasingNodeTypes.length || nodesById.size !== nodes.length
      || edgeKeys.length !== supportedBreakoutEdges.size
      || new Set(edgeKeys).size !== edgeKeys.length
      || edgeKeys.some((key) => !supportedBreakoutEdges.has(key))) {
    errors.push({ code: "unsupported_topology", message: "Use the supported opening-breakout wiring. Other graph shapes cannot execute." });
  }
  return {
    status: errors.length === 0 ? "valid" : "invalid",
    errors,
  };
}

export function validateCatalogWorkflowGraph(
  nodes: VisualWorkflowNodeDefinition[],
  edges: VisualWorkflowEdgeDefinition[],
): VisualWorkflowValidationResult {
  return validateVisualWorkflowGraph(nodes, edges);
}

export function isTypedConnectionValid(
  nodes: VisualWorkflowNodeDefinition[],
  connection: {
    source: string | null;
    sourceHandle: string | null;
    target: string | null;
    targetHandle: string | null;
  },
): boolean {
  if (
    !connection.source ||
    !connection.sourceHandle ||
    !connection.target ||
    !connection.targetHandle ||
    connection.source === connection.target
  ) {
    return false;
  }
  const source = nodes.find((node) => node.id === connection.source);
  const target = nodes.find((node) => node.id === connection.target);
  return (
    source?.outputPorts[connection.sourceHandle] !== undefined &&
    source.outputPorts[connection.sourceHandle] === target?.inputPorts[connection.targetHandle]
  );
}

function isSupportedType(value: string): value is VisualWorkflowNodeType {
  return supportedNodeTypes.has(value);
}

function hasCycle(
  nodes: VisualWorkflowGraphNodeInput[],
  edges: VisualWorkflowGraphEdgeInput[],
): boolean {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const outgoing = new Map<string, string[]>();
  for (const node of nodes) {
    outgoing.set(node.id, []);
  }
  for (const edge of edges) {
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      outgoing.get(edge.source)?.push(edge.target);
    }
  }
  const visiting = new Set<string>();
  const visited = new Set<string>();
  function visit(nodeId: string): boolean {
    if (visiting.has(nodeId)) return true;
    if (visited.has(nodeId)) return false;
    visiting.add(nodeId);
    for (const target of outgoing.get(nodeId) ?? []) {
      if (visit(target)) return true;
    }
    visiting.delete(nodeId);
    visited.add(nodeId);
    return false;
  }
  return nodes.some((node) => visit(node.id));
}

function reachable(
  start: string,
  edges: VisualWorkflowGraphEdgeInput[],
  reverse: boolean,
): Set<string> {
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    const origin = reverse ? edge.target : edge.source;
    const destination = reverse ? edge.source : edge.target;
    adjacency.set(origin, [...(adjacency.get(origin) ?? []), destination]);
  }
  const seen = new Set<string>();
  const pending = [...(adjacency.get(start) ?? [])];
  while (pending.length > 0) {
    const nodeId = pending.pop();
    if (!nodeId || seen.has(nodeId)) continue;
    seen.add(nodeId);
    pending.push(...(adjacency.get(nodeId) ?? []));
  }
  return seen;
}

const supportedBreakoutEdges = new Set([
  "alert:event:audit_sink:event",
  "armed_run_authorization:plan:entry_lifetime:plan",
  "crosses_above:trigger:one_shot_per_session:trigger",
  "day_low:price:long_risk_size:stop_price",
  "day_low:price:protective_stop:stop_price",
  "dollar_risk_input:money:long_risk_size:maximum_dollar_loss",
  "emergency_stop_gate:plan:armed_run_authorization:plan",
  "entry_lifetime:plan:position_lifetime:plan",
  "fake_broker:report:position_monitor:report",
  "historical_dataset:trades:rth_session:trades",
  "long_risk_size:plan:risk_gate:plan",
  "one_shot_per_session:trigger:long_risk_size:trigger",
  "one_shot_per_session:trigger:stop_market_entry:trigger",
  "opening_range_high:price:crosses_above:level",
  "position_lifetime:plan:protective_stop:plan",
  "position_monitor:position:alert:position",
  "protective_stop:plan:stop_market_entry:plan",
  "reconciliation_gate:plan:emergency_stop_gate:plan",
  "risk_gate:plan:stale_data_gate:plan",
  "rth_session:contract:crosses_above:contract",
  "rth_session:contract:long_risk_size:contract",
  "rth_session:session:day_low:session",
  "rth_session:session:one_shot_per_session:session",
  "rth_session:session:opening_range_high:session",
  "rth_session:trades:crosses_above:trades",
  "rth_session:trades:day_low:trades",
  "rth_session:trades:opening_range_high:trades",
  "rth_session:trades:stale_data_gate:trades",
  "stale_data_gate:plan:reconciliation_gate:plan",
  "stop_market_entry:plan:fake_broker:plan",
  "symbol_input:symbol:rth_session:symbol"
]);
