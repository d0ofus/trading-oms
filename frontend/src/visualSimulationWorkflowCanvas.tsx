import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import type { ReactNode } from "react";

import "@xyflow/react/dist/style.css";

export type VisualSimulationWorkflowNode = {
  id: string;
  title: string;
  detail: string;
  badge: string;
  role: "source" | "transform" | "gate" | "approval" | "simulation" | "audit";
  position: {
    x: number;
    y: number;
  };
};

type FlowNodeData = {
  label: ReactNode;
};

export const visualSimulationWorkflowNodeCatalog: VisualSimulationWorkflowNode[] = [
  {
    id: "replay-source",
    title: "Replay source",
    detail: "Deterministic local replay input",
    badge: "local replay",
    role: "source",
    position: { x: 0, y: 80 },
  },
  {
    id: "bar-builder",
    title: "Bar builder",
    detail: "Builds 5-minute simulation bars",
    badge: "deterministic",
    role: "transform",
    position: { x: 260, y: 80 },
  },
  {
    id: "strategy-trigger",
    title: "Strategy trigger",
    detail: "First bar breakout with volume filter",
    badge: "signal only",
    role: "transform",
    position: { x: 520, y: 80 },
  },
  {
    id: "risk-check",
    title: "Risk check",
    detail: "Blocks stale data and unsafe state",
    badge: "required",
    role: "gate",
    position: { x: 780, y: 0 },
  },
  {
    id: "manual-approval",
    title: "Manual approval",
    detail: "Human simulation approval gate",
    badge: "required",
    role: "approval",
    position: { x: 780, y: 170 },
  },
  {
    id: "fake-broker",
    title: "Fake broker",
    detail: "Simulation-only acknowledgement and fills",
    badge: "no transport",
    role: "simulation",
    position: { x: 1040, y: 80 },
  },
  {
    id: "audit-sink",
    title: "Audit sink",
    detail: "Append-only journal references",
    badge: "append only",
    role: "audit",
    position: { x: 1300, y: 80 },
  },
];

export const visualSimulationWorkflowEdges: Edge[] = [
  buildEdge("replay-source", "bar-builder", "replay-source-to-bar-builder"),
  buildEdge("bar-builder", "strategy-trigger", "bar-builder-to-strategy-trigger"),
  buildEdge("strategy-trigger", "risk-check", "strategy-trigger-to-risk-check"),
  buildEdge("risk-check", "manual-approval", "risk-check-to-manual-approval"),
  buildEdge("manual-approval", "fake-broker", "manual-approval-to-fake-broker"),
  buildEdge("fake-broker", "audit-sink", "fake-broker-to-audit-sink"),
];

export function VisualSimulationWorkflowCanvas() {
  return (
    <div className="flow-scaffold" aria-label="React Flow simulation workflow scaffold">
      <div className="react-flow-frame">
        <ReactFlow
          edges={visualSimulationWorkflowEdges}
          elementsSelectable={false}
          fitView
          nodes={visualSimulationWorkflowNodes}
          nodesConnectable={false}
          nodesDraggable={false}
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
        {visualSimulationWorkflowNodeCatalog.map((node) => (
          <li key={node.id}>
            <span className={`flow-role flow-role-${node.role}`}>{node.badge}</span>
            <div>
              <h3>{node.title}</h3>
              <p>{node.detail}</p>
            </div>
          </li>
        ))}
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
        </div>
      ),
    },
    draggable: false,
    position: node.position,
    selectable: false,
    type: node.id === "replay-source" ? "input" : node.id === "audit-sink" ? "output" : "default",
  }),
);

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
