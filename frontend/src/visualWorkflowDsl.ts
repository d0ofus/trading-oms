import type {
  VisualWorkflowEdgeDefinition,
  VisualWorkflowNodeDefinition,
  VisualWorkflowNodeType,
} from "./visualWorkflowNodeCatalog";
import {
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
} from "./visualWorkflowNodeCatalog";
import {
  validateCatalogWorkflowGraph,
  type VisualWorkflowValidationError,
} from "./visualWorkflowValidation";

export type VisualWorkflowDslNode = {
  id: string;
  type: VisualWorkflowNodeType;
  required_for_risk_increasing_path: boolean;
};

export type VisualWorkflowDslEdge = {
  source: string;
  target: string;
};

export type VisualWorkflowDslDocument = {
  schema_version: 1;
  workflow_id: "visual-simulation-workflow";
  mode: "simulation";
  runtime: "preview_only";
  broker: "fake_broker_only";
  nodes: VisualWorkflowDslNode[];
  edges: VisualWorkflowDslEdge[];
  safety_gates: {
    risk_check_required: true;
    manual_approval_required: true;
    audit_sink_required: true;
    broker_transport_allowed: false;
    live_trading_enabled: false;
    arbitrary_code_allowed: false;
  };
};

export type VisualWorkflowDslCompileResult =
  | {
      status: "compiled";
      document: VisualWorkflowDslDocument;
      errors: [];
    }
  | {
      status: "invalid";
      document: null;
      errors: VisualWorkflowValidationError[];
    };

export function compileVisualWorkflowDsl(
  nodes: VisualWorkflowNodeDefinition[],
  edges: VisualWorkflowEdgeDefinition[],
): VisualWorkflowDslCompileResult {
  const validation = validateCatalogWorkflowGraph(nodes, edges);

  if (validation.status === "invalid") {
    return {
      status: "invalid",
      document: null,
      errors: validation.errors,
    };
  }

  return {
    status: "compiled",
    document: {
      schema_version: 1,
      workflow_id: "visual-simulation-workflow",
      mode: "simulation",
      runtime: "preview_only",
      broker: "fake_broker_only",
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.type,
        required_for_risk_increasing_path: node.requiredForRiskIncreasingPath,
      })),
      edges: edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
      })),
      safety_gates: {
        risk_check_required: true,
        manual_approval_required: true,
        audit_sink_required: true,
        broker_transport_allowed: false,
        live_trading_enabled: false,
        arbitrary_code_allowed: false,
      },
    },
    errors: [],
  };
}

export const defaultVisualWorkflowDslCompileResult = compileVisualWorkflowDsl(
  simulationWorkflowNodeCatalog,
  simulationWorkflowEdgeCatalog,
);

export function formatVisualWorkflowDslPreview(result: VisualWorkflowDslCompileResult) {
  if (result.status === "invalid") {
    return JSON.stringify(
      {
        schema_version: 1,
        workflow_id: "visual-simulation-workflow",
        mode: "simulation",
        status: "invalid",
        errors: result.errors,
      },
      null,
      2,
    );
  }

  return JSON.stringify(result.document, null, 2);
}
