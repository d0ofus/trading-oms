import type {
  VisualWorkflowEdgeDefinition,
  VisualWorkflowNodeDefinition,
  VisualWorkflowNodeType,
} from "./visualWorkflowNodeCatalog";

export type VisualWorkflowGraphNodeInput = {
  id: string;
  type: string;
};

export type VisualWorkflowGraphEdgeInput = {
  source: string;
  target: string;
};

export type VisualWorkflowValidationErrorCode =
  | "missing_required_node"
  | "unsafe_action_node"
  | "unsupported_node"
  | "unknown_edge_endpoint"
  | "cycle_detected";

export type VisualWorkflowValidationError = {
  code: VisualWorkflowValidationErrorCode;
  message: string;
  nodeId?: string;
  nodeType?: string;
};

export type VisualWorkflowValidationResult = {
  status: "valid" | "invalid";
  errors: VisualWorkflowValidationError[];
};

const supportedNodeTypes: ReadonlySet<string> = new Set<VisualWorkflowNodeType>([
  "replay_source",
  "bar_builder",
  "strategy_trigger",
  "risk_check",
  "approval_ticket",
  "fake_broker",
  "position_update",
  "alert",
  "audit_sink",
]);

const requiredRiskIncreasingNodeTypes: Array<{
  type: VisualWorkflowNodeType;
  label: string;
}> = [
  { type: "risk_check", label: "risk check" },
  { type: "approval_ticket", label: "approval ticket" },
  { type: "audit_sink", label: "audit sink" },
];

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
  const nodeIds = new Set(nodes.map((node) => node.id));
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
      continue;
    }

    if (!supportedNodeTypes.has(node.type)) {
      errors.push({
        code: "unsupported_node",
        message: `Unsupported node type '${node.type}'.`,
        nodeId: node.id,
        nodeType: node.type,
      });
    }
  }

  for (const edge of edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      errors.push({
        code: "unknown_edge_endpoint",
        message: `Edge ${edge.source}->${edge.target} references an unknown node.`,
      });
    }
  }

  if (hasCycle(nodes, edges)) {
    errors.push({
      code: "cycle_detected",
      message: "Workflow graph contains a cycle.",
    });
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
    if (visiting.has(nodeId)) {
      return true;
    }
    if (visited.has(nodeId)) {
      return false;
    }

    visiting.add(nodeId);
    for (const target of outgoing.get(nodeId) ?? []) {
      if (visit(target)) {
        return true;
      }
    }
    visiting.delete(nodeId);
    visited.add(nodeId);
    return false;
  }

  for (const node of nodes) {
    if (visit(node.id)) {
      return true;
    }
  }

  return false;
}
