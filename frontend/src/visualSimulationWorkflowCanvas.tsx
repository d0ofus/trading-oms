import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import { AlertTriangle, Plus, RotateCcw, ShieldCheck, Trash2 } from "lucide-react";
import { useMemo, type CSSProperties, type Dispatch, type ReactNode, type SetStateAction } from "react";

import "@xyflow/react/dist/style.css";

import {
  addVisualWorkflowNode,
  connectVisualWorkflowNodes,
  isVisualWorkflowConnectionAllowed,
  moveVisualWorkflowNode,
  removeSelectedVisualWorkflowElement,
  removeVisualWorkflowEdge,
  removeVisualWorkflowNode,
  resetVisualWorkflowEditorState,
  selectVisualWorkflowElement,
  type VisualWorkflowEditorState,
} from "./visualWorkflowEditor";
import {
  simulationWorkflowNodeCatalog,
  type VisualWorkflowEdgeDefinition,
  type VisualWorkflowNodeDefinition,
  type VisualWorkflowNodeRole,
} from "./visualWorkflowNodeCatalog";
import { validateCatalogWorkflowGraph } from "./visualWorkflowValidation";

type FlowNodeData = {
  label: ReactNode;
};

type VisualSimulationWorkflowCanvasProps = {
  editorState: VisualWorkflowEditorState;
  onEditorStateChange: Dispatch<SetStateAction<VisualWorkflowEditorState>>;
};

export const visualSimulationWorkflowNodePalette = simulationWorkflowNodeCatalog;

export const visualSimulationWorkflowLayoutPolicy = {
  mode: "local_graph_editor",
  nodesDraggable: true,
  nodesConnectable: true,
  elementsSelectable: true,
  nodesDeletable: true,
  edgesDeletable: true,
  persistenceEnabled: false,
  executionEnabled: false,
  canvasMinHeightPx: 440,
  responsiveLayout: true,
} as const;

export function VisualSimulationWorkflowCanvas({
  editorState,
  onEditorStateChange,
}: VisualSimulationWorkflowCanvasProps) {
  const validation = useMemo(
    () => validateCatalogWorkflowGraph(editorState.nodes, editorState.edges),
    [editorState.edges, editorState.nodes],
  );
  const flowNodes = useMemo(() => buildFlowNodes(editorState), [editorState]);
  const flowEdges = useMemo(() => buildFlowEdges(editorState), [editorState]);
  const selectedLabel = selectionLabel(editorState);
  const canvasStyle = {
    "--workflow-canvas-min-height": `${visualSimulationWorkflowLayoutPolicy.canvasMinHeightPx}px`,
  } as CSSProperties;

  const updateEditor = (transform: (current: VisualWorkflowEditorState) => VisualWorkflowEditorState) =>
    onEditorStateChange((current) => transform(current));

  const onNodesChange = (changes: NodeChange<Node<FlowNodeData>>[]) => {
    updateEditor((current) => applyNodeChanges(current, changes));
  };

  const onEdgesChange = (changes: EdgeChange<Edge>[]) => {
    updateEditor((current) => applyEdgeChanges(current, changes));
  };

  const onConnect = (connection: Connection) => {
    updateEditor(
      (current) =>
        connectVisualWorkflowNodes(current, connection.source, connection.target).state,
    );
  };

  return (
    <div className="flow-scaffold" aria-label="Interactive simulation workflow editor">
      <div className="flow-editor-workspace">
        <aside className="flow-palette" aria-label="Safe simulation node palette">
          <div className="flow-palette-heading">
            <p className="eyebrow">Node palette</p>
            <span>Typed simulation nodes</span>
          </div>
          <div className="flow-palette-list">
            {visualSimulationWorkflowNodePalette.map((node) => {
              const alreadyPresent = editorState.nodes.some(
                (current) => current.id === node.id || current.type === node.type,
              );
              return (
                <button
                  aria-label={`Add ${node.title}`}
                  className={`palette-node palette-node-${node.role}`}
                  disabled={alreadyPresent}
                  key={node.type}
                  onClick={() =>
                    updateEditor((current) => addVisualWorkflowNode(current, node.type).state)
                  }
                  title={alreadyPresent ? `${node.title} already present` : `Add ${node.title}`}
                  type="button"
                >
                  <Plus aria-hidden="true" size={16} strokeWidth={2} />
                  <span>
                    <strong>{node.title}</strong>
                    <small>{node.badge}</small>
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        <div className="flow-editor-stage">
          <div className="flow-editor-toolbar" aria-label="Local graph tools">
            <div className="flow-selection" aria-live="polite">
              <span>Selection</span>
              <strong>{selectedLabel}</strong>
            </div>
            <div className="flow-editor-actions">
              <button
                aria-label="Remove selected graph element"
                disabled={editorState.selection === null}
                onClick={() =>
                  updateEditor((current) => removeSelectedVisualWorkflowElement(current).state)
                }
                title="Remove selected"
                type="button"
              >
                <Trash2 aria-hidden="true" size={16} />
                <span>Remove selected</span>
              </button>
              <button
                aria-label="Reset local workflow graph"
                onClick={() => updateEditor(resetVisualWorkflowEditorState)}
                title="Reset graph"
                type="button"
              >
                <RotateCcw aria-hidden="true" size={16} />
                <span>Reset graph</span>
              </button>
            </div>
          </div>

          <div className="react-flow-frame" style={canvasStyle}>
            <ReactFlow
              deleteKeyCode={["Backspace", "Delete"]}
              edges={flowEdges}
              edgesReconnectable={false}
              elementsSelectable={visualSimulationWorkflowLayoutPolicy.elementsSelectable}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              isValidConnection={(connection) =>
                isVisualWorkflowConnectionAllowed(
                  editorState,
                  connection.source,
                  connection.target,
                )
              }
              nodes={flowNodes}
              nodesConnectable={visualSimulationWorkflowLayoutPolicy.nodesConnectable}
              nodesDraggable={visualSimulationWorkflowLayoutPolicy.nodesDraggable}
              nodesFocusable
              onConnect={onConnect}
              onEdgeClick={(_event, edge) =>
                updateEditor((current) =>
                  selectVisualWorkflowElement(current, { kind: "edge", id: edge.id }),
                )
              }
              onEdgesChange={onEdgesChange}
              onNodeClick={(_event, node) =>
                updateEditor((current) =>
                  selectVisualWorkflowElement(current, { kind: "node", id: node.id }),
                )
              }
              onNodesChange={onNodesChange}
              onPaneClick={() => updateEditor((current) => selectVisualWorkflowElement(current, null))}
              panOnDrag
              preventScrolling={false}
              proOptions={{ hideAttribution: true }}
              zoomOnDoubleClick={false}
              zoomOnPinch
              zoomOnScroll={false}
            >
              <Controls showInteractive={false} />
              <Background color="#cfdbd5" gap={18} variant={BackgroundVariant.Dots} />
            </ReactFlow>
          </div>
        </div>
      </div>

      <div
        className={`flow-validation flow-validation-${validation.status}`}
        role={validation.status === "invalid" ? "alert" : "status"}
      >
        {validation.status === "valid" ? (
          <ShieldCheck aria-hidden="true" size={20} />
        ) : (
          <AlertTriangle aria-hidden="true" size={20} />
        )}
        <div>
          <h3>
            {validation.status === "valid"
              ? "Graph validation passed"
              : "Graph validation blocked"}
          </h3>
          {validation.errors.length === 0 ? (
            <p>
              Risk, approval, audit, and supported-node checks passed. Required simulation safety
              path connected.
            </p>
          ) : (
            <ul>
              {validation.errors.map((error) => (
                <li key={`${error.code}-${error.nodeId ?? error.nodeType ?? error.message}`}>
                  {error.message}
                </li>
              ))}
            </ul>
          )}
        </div>
        <span className="flow-local-state">Local graph only</span>
      </div>
    </div>
  );
}

function buildFlowNodes(editorState: VisualWorkflowEditorState): Node<FlowNodeData>[] {
  return editorState.nodes.map((node) => ({
    id: node.id,
    className: `simulation-flow-node simulation-flow-node-${node.role}`,
    connectable: visualSimulationWorkflowLayoutPolicy.nodesConnectable,
    data: {
      label: (
        <div className="flow-node-content">
          <span className={`flow-role flow-role-${node.role}`}>{node.badge}</span>
          <strong>{node.title}</strong>
          <span>{node.detail}</span>
        </div>
      ),
    },
    deletable: visualSimulationWorkflowLayoutPolicy.nodesDeletable,
    draggable: visualSimulationWorkflowLayoutPolicy.nodesDraggable,
    position: node.position,
    selected: editorState.selection?.kind === "node" && editorState.selection.id === node.id,
    selectable: visualSimulationWorkflowLayoutPolicy.elementsSelectable,
    type: flowNodeType(node),
  }));
}

function buildFlowEdges(editorState: VisualWorkflowEditorState): Edge[] {
  return editorState.edges.map((edge) => buildFlowEdge(edge, editorState));
}

function buildFlowEdge(edge: VisualWorkflowEdgeDefinition, editorState: VisualWorkflowEditorState): Edge {
  return {
    id: edge.id,
    animated: false,
    deletable: visualSimulationWorkflowLayoutPolicy.edgesDeletable,
    markerEnd: { type: MarkerType.ArrowClosed },
    reconnectable: false,
    selected: editorState.selection?.kind === "edge" && editorState.selection.id === edge.id,
    source: edge.source,
    target: edge.target,
    type: "smoothstep",
  };
}

function flowNodeType(node: VisualWorkflowNodeDefinition) {
  if (node.type === "replay_source") {
    return "input";
  }
  if (node.type === "audit_sink") {
    return "output";
  }
  return "default";
}

function selectionLabel(state: VisualWorkflowEditorState) {
  if (!state.selection) {
    return "None";
  }
  if (state.selection.kind === "node") {
    return state.nodes.find((node) => node.id === state.selection?.id)?.title ?? "None";
  }
  const edge = state.edges.find((candidate) => candidate.id === state.selection?.id);
  return edge ? `${edge.source} to ${edge.target}` : "None";
}

function applyNodeChanges(
  state: VisualWorkflowEditorState,
  changes: NodeChange<Node<FlowNodeData>>[],
) {
  let next = state;
  for (const change of changes) {
    if (change.type === "remove") {
      next = removeVisualWorkflowNode(next, change.id).state;
    } else if (change.type === "position" && change.position) {
      next = moveVisualWorkflowNode(next, change.id, change.position).state;
    } else if (change.type === "select") {
      next = selectVisualWorkflowElement(
        next,
        change.selected ? { kind: "node", id: change.id } : clearSelection(next, "node", change.id),
      );
    }
  }
  return next;
}

function applyEdgeChanges(state: VisualWorkflowEditorState, changes: EdgeChange<Edge>[]) {
  let next = state;
  for (const change of changes) {
    if (change.type === "remove") {
      next = removeVisualWorkflowEdge(next, change.id).state;
    } else if (change.type === "select") {
      next = selectVisualWorkflowElement(
        next,
        change.selected ? { kind: "edge", id: change.id } : clearSelection(next, "edge", change.id),
      );
    }
  }
  return next;
}

function clearSelection(
  state: VisualWorkflowEditorState,
  kind: "node" | "edge",
  id: string,
) {
  return state.selection?.kind === kind && state.selection.id === id ? null : state.selection;
}

export type { VisualWorkflowNodeRole };
