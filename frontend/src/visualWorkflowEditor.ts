import {
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
  type VisualWorkflowEdgeDefinition,
  type VisualWorkflowNodeDefinition,
  type VisualWorkflowNodeType,
} from "./visualWorkflowNodeCatalog";

export type VisualWorkflowEditorSelection = {
  kind: "node" | "edge";
  id: string;
};

export type VisualWorkflowEditorState = {
  nodes: VisualWorkflowNodeDefinition[];
  edges: VisualWorkflowEdgeDefinition[];
  selection: VisualWorkflowEditorSelection | null;
};

export type VisualWorkflowEditorRejectionReason =
  | "duplicate_edge"
  | "duplicate_node"
  | "invalid_position"
  | "nothing_selected"
  | "self_connection"
  | "unknown_edge"
  | "unknown_endpoint"
  | "unknown_node"
  | "unsupported_edge_type"
  | "unsupported_node_type";

export type VisualWorkflowEditorMutation = {
  state: VisualWorkflowEditorState;
  changed: boolean;
  reason: VisualWorkflowEditorRejectionReason | null;
};

const catalogOrder = new Map(
  simulationWorkflowNodeCatalog.map((node, index) => [node.type, index] as const),
);

export function createInitialVisualWorkflowEditorState(): VisualWorkflowEditorState {
  return {
    nodes: simulationWorkflowNodeCatalog.map(cloneNode),
    edges: simulationWorkflowEdgeCatalog.map(cloneEdge),
    selection: null,
  };
}

export function resetVisualWorkflowEditorState(): VisualWorkflowEditorState {
  return createInitialVisualWorkflowEditorState();
}

export function addVisualWorkflowNode(
  state: VisualWorkflowEditorState,
  nodeType: VisualWorkflowNodeType,
): VisualWorkflowEditorMutation {
  const template = simulationWorkflowNodeCatalog.find((node) => node.type === nodeType);
  if (!template) {
    return unchanged(state, "unsupported_node_type");
  }
  if (state.nodes.some((node) => node.id === template.id || node.type === template.type)) {
    return unchanged(state, "duplicate_node");
  }

  const nodes = [...state.nodes, cloneNode(template)].sort(
    (left, right) => catalogIndex(left.type) - catalogIndex(right.type),
  );
  return changed({
    ...state,
    nodes,
    selection: { kind: "node", id: template.id },
  });
}

export function removeVisualWorkflowNode(
  state: VisualWorkflowEditorState,
  nodeId: string,
): VisualWorkflowEditorMutation {
  if (!state.nodes.some((node) => node.id === nodeId)) {
    return unchanged(state, "unknown_node");
  }

  const removedEdgeIds = new Set(
    state.edges
      .filter((edge) => edge.source === nodeId || edge.target === nodeId)
      .map((edge) => edge.id),
  );
  const selection =
    state.selection?.id === nodeId ||
    (state.selection?.kind === "edge" && removedEdgeIds.has(state.selection.id))
      ? null
      : state.selection;

  return changed({
    nodes: state.nodes.filter((node) => node.id !== nodeId),
    edges: state.edges.filter((edge) => !removedEdgeIds.has(edge.id)),
    selection,
  });
}

export function moveVisualWorkflowNode(
  state: VisualWorkflowEditorState,
  nodeId: string,
  position: { x: number; y: number },
): VisualWorkflowEditorMutation {
  if (!Number.isFinite(position.x) || !Number.isFinite(position.y)) {
    return unchanged(state, "invalid_position");
  }
  const node = state.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) {
    return unchanged(state, "unknown_node");
  }
  if (node.position.x === position.x && node.position.y === position.y) {
    return unchanged(state, null);
  }

  return changed({
    ...state,
    nodes: state.nodes.map((candidate) =>
      candidate.id === nodeId
        ? { ...candidate, position: { x: position.x, y: position.y } }
        : candidate,
    ),
  });
}

export function connectVisualWorkflowNodes(
  state: VisualWorkflowEditorState,
  source: string,
  target: string,
  edgeType: string = "workflow",
): VisualWorkflowEditorMutation {
  if (edgeType !== "workflow") {
    return unchanged(state, "unsupported_edge_type");
  }
  const nodeIds = new Set(state.nodes.map((node) => node.id));
  if (!nodeIds.has(source) || !nodeIds.has(target)) {
    return unchanged(state, "unknown_endpoint");
  }
  if (source === target) {
    return unchanged(state, "self_connection");
  }
  if (state.edges.some((edge) => edge.source === source && edge.target === target)) {
    return unchanged(state, "duplicate_edge");
  }

  const edge: VisualWorkflowEdgeDefinition = {
    id: `${source}-to-${target}`,
    source,
    target,
    type: "workflow",
  };
  return changed({
    ...state,
    edges: [...state.edges, edge],
    selection: { kind: "edge", id: edge.id },
  });
}

export function removeVisualWorkflowEdge(
  state: VisualWorkflowEditorState,
  edgeId: string,
): VisualWorkflowEditorMutation {
  if (!state.edges.some((edge) => edge.id === edgeId)) {
    return unchanged(state, "unknown_edge");
  }
  return changed({
    ...state,
    edges: state.edges.filter((edge) => edge.id !== edgeId),
    selection:
      state.selection?.kind === "edge" && state.selection.id === edgeId
        ? null
        : state.selection,
  });
}

export function selectVisualWorkflowElement(
  state: VisualWorkflowEditorState,
  selection: VisualWorkflowEditorSelection | null,
): VisualWorkflowEditorState {
  if (selection === null) {
    return state.selection === null ? state : { ...state, selection: null };
  }
  const exists =
    selection.kind === "node"
      ? state.nodes.some((node) => node.id === selection.id)
      : state.edges.some((edge) => edge.id === selection.id);
  if (!exists) {
    return state;
  }
  if (state.selection?.kind === selection.kind && state.selection.id === selection.id) {
    return state;
  }
  return { ...state, selection };
}

export function removeSelectedVisualWorkflowElement(
  state: VisualWorkflowEditorState,
): VisualWorkflowEditorMutation {
  if (!state.selection) {
    return unchanged(state, "nothing_selected");
  }
  return state.selection.kind === "node"
    ? removeVisualWorkflowNode(state, state.selection.id)
    : removeVisualWorkflowEdge(state, state.selection.id);
}

export function isVisualWorkflowConnectionAllowed(
  state: VisualWorkflowEditorState,
  source: string | null,
  target: string | null,
) {
  if (!source || !target) {
    return false;
  }
  return connectVisualWorkflowNodes(state, source, target).changed;
}

function cloneNode(node: VisualWorkflowNodeDefinition): VisualWorkflowNodeDefinition {
  return {
    ...node,
    position: { ...node.position },
  };
}

function cloneEdge(edge: VisualWorkflowEdgeDefinition): VisualWorkflowEdgeDefinition {
  return { ...edge };
}

function catalogIndex(nodeType: VisualWorkflowNodeType) {
  return catalogOrder.get(nodeType) ?? Number.MAX_SAFE_INTEGER;
}

function changed(state: VisualWorkflowEditorState): VisualWorkflowEditorMutation {
  return { state, changed: true, reason: null };
}

function unchanged(
  state: VisualWorkflowEditorState,
  reason: VisualWorkflowEditorRejectionReason | null,
): VisualWorkflowEditorMutation {
  return { state, changed: false, reason };
}
