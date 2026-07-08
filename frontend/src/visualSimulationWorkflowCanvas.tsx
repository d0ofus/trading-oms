import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
  useNodesState,
} from "@xyflow/react";
import type { ReactNode } from "react";

import "@xyflow/react/dist/style.css";

import {
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
  type VisualWorkflowNodeRole,
} from "./visualWorkflowNodeCatalog";
import {
  defaultVisualWorkflowRunInspection,
  inspectionByNodeId,
  type VisualWorkflowRunStatus,
} from "./visualWorkflowRunInspection";
import { validateCatalogWorkflowGraph } from "./visualWorkflowValidation";

type FlowNodeData = {
  label: ReactNode;
};

export const visualSimulationWorkflowNodeCatalog = simulationWorkflowNodeCatalog;

export const visualSimulationWorkflowEdges: Edge[] = simulationWorkflowEdgeCatalog.map((edge) =>
  buildEdge(edge.source, edge.target, edge.id),
);

export const visualSimulationWorkflowLayoutPolicy = {
  mode: "local_editable_layout",
  nodesDraggable: true,
  nodesConnectable: false,
  elementsSelectable: true,
  persistenceEnabled: false,
  executionEnabled: false,
} as const;

export const visualSimulationWorkflowValidation = validateCatalogWorkflowGraph(
  visualSimulationWorkflowNodeCatalog,
  simulationWorkflowEdgeCatalog,
);

export const visualSimulationWorkflowRunInspection = defaultVisualWorkflowRunInspection;

export const visualSimulationWorkflowStatusLegend: VisualWorkflowRunStatus[] = [
  "completed",
  "passed",
  "risk_blocked",
  "waiting_for_approval",
  "blocked_waiting_for_approval",
  "filled",
  "alert_recorded",
];

export function VisualSimulationWorkflowCanvas() {
  const [nodes, , onNodesChange] = useNodesState(visualSimulationWorkflowNodes);

  return (
    <div className="flow-scaffold" aria-label="React Flow simulation workflow scaffold">
      <div className="react-flow-frame">
        <ReactFlow
          edges={visualSimulationWorkflowEdges}
          elementsSelectable={visualSimulationWorkflowLayoutPolicy.elementsSelectable}
          fitView
          nodes={nodes}
          nodesConnectable={visualSimulationWorkflowLayoutPolicy.nodesConnectable}
          nodesDraggable={visualSimulationWorkflowLayoutPolicy.nodesDraggable}
          onNodesChange={onNodesChange}
          panOnDrag={false}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
          zoomOnDoubleClick={false}
          zoomOnPinch={false}
          zoomOnScroll={false}
        >
          <Background color="#cfdbd5" gap={18} variant={BackgroundVariant.Dots} />
        </ReactFlow>
      </div>

      <ol className="flow-node-ledger" aria-label="Simulation workflow scaffold nodes">
        <li className={`flow-validation flow-validation-${visualSimulationWorkflowValidation.status}`}>
          <span className="flow-role flow-role-gate">validation</span>
          <div>
            <h3>
              {visualSimulationWorkflowValidation.status === "valid"
                ? "Graph validation passed"
                : "Graph validation blocked"}
            </h3>
            {visualSimulationWorkflowValidation.errors.length === 0 ? (
              <p>Risk, approval, audit, and supported-node checks passed</p>
            ) : (
              <ul>
                {visualSimulationWorkflowValidation.errors.map((error) => (
                  <li key={`${error.code}-${error.nodeId ?? error.nodeType ?? error.message}`}>
                    {error.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </li>
        <li className="flow-layout-policy">
          <span className="flow-role flow-role-transform">local layout</span>
          <div>
            <h3>Editable layout</h3>
            <p>Node movement changes only local canvas positions</p>
          </div>
        </li>
        {visualSimulationWorkflowNodeCatalog.map((node) => (
          <li key={node.id}>
            <span className={`flow-role flow-role-${node.role}`}>{node.badge}</span>
            <div>
              <h3>{node.title}</h3>
              <p>{node.detail}</p>
              <RunInspection nodeId={node.id} />
            </div>
          </li>
        ))}
        <li className="flow-status-legend">
          <span className="flow-role flow-role-audit">statuses</span>
          <div>
            <h3>Run inspection statuses</h3>
            <p>Read-only status vocabulary for approval waits, risk blocks, fills, and alerts</p>
            <ul>
              {visualSimulationWorkflowStatusLegend.map((status) => (
                <li key={status}>
                  <span className={`run-inspection run-inspection-${status}`}>
                    <span>{formatStatus(status)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </li>
      </ol>
    </div>
  );
}

const visualSimulationWorkflowNodes: Node<FlowNodeData>[] = visualSimulationWorkflowNodeCatalog.map(
  (node) => ({
    id: node.id,
    className: `simulation-flow-node simulation-flow-node-${node.role}`,
    connectable: false,
    data: {
      label: (
        <div className="flow-node-content">
          <span className={`flow-role flow-role-${node.role}`}>{node.badge}</span>
          <strong>{node.title}</strong>
          <span>{node.detail}</span>
          <RunInspection nodeId={node.id} compact />
        </div>
      ),
    },
    draggable: visualSimulationWorkflowLayoutPolicy.nodesDraggable,
    position: node.position,
    selectable: visualSimulationWorkflowLayoutPolicy.elementsSelectable,
    type: node.id === "replay-source" ? "input" : node.id === "audit-sink" ? "output" : "default",
  }),
);

const runInspectionByNodeId = inspectionByNodeId(visualSimulationWorkflowRunInspection);

function RunInspection({ compact = false, nodeId }: { compact?: boolean; nodeId: string }) {
  const inspection = runInspectionByNodeId.get(nodeId);
  if (!inspection) {
    return null;
  }

  return (
    <span className={`run-inspection run-inspection-${inspection.status}`}>
      <span>{formatStatus(inspection.status)}</span>
      {!compact && <span>{inspection.detail}</span>}
      <span>{inspection.journalReference}</span>
    </span>
  );
}

function formatStatus(status: string) {
  return status.replaceAll("_", " ");
}

function buildEdge(source: string, target: string, id: string): Edge {
  return {
    id,
    animated: false,
    markerEnd: {
      type: MarkerType.ArrowClosed,
    },
    source,
    target,
    type: "smoothstep",
  };
}

export type { VisualWorkflowNodeRole };
