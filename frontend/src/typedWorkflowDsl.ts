import type {
  VisualWorkflowEdgeDefinition,
  VisualWorkflowNodeConfig,
  VisualWorkflowNodeDefinition,
  VisualWorkflowNodeType,
} from "./typedWorkflowNodeCatalog";
import {
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
} from "./typedWorkflowNodeCatalog";
import {
  validateCatalogWorkflowGraph,
  type VisualWorkflowValidationError,
} from "./typedWorkflowValidation";

export type VisualWorkflowDslV1Node = {
  id: string;
  type:
    | "replay_source"
    | "bar_builder"
    | "strategy_trigger"
    | "risk_check"
    | "approval_ticket"
    | "fake_broker"
    | "position_update"
    | "alert"
    | "audit_sink";
  required_for_risk_increasing_path: boolean;
};

export type VisualWorkflowDslV1Document = {
  schema_version: 1;
  workflow_id: "visual-simulation-workflow";
  mode: "simulation";
  runtime: "preview_only";
  broker: "fake_broker_only";
  nodes: VisualWorkflowDslV1Node[];
  edges: Array<{ source: string; target: string }>;
  safety_gates: {
    risk_check_required: true;
    manual_approval_required: true;
    audit_sink_required: true;
    broker_transport_allowed: false;
    live_trading_enabled: false;
    arbitrary_code_allowed: false;
  };
};

export type VisualWorkflowDslV2Node = {
  id: string;
  type: VisualWorkflowNodeType;
  config: VisualWorkflowNodeConfig;
  position: { x: number; y: number };
};

export type VisualWorkflowDslV2Edge = {
  id: string;
  source_node: string;
  source_port: string;
  target_node: string;
  target_port: string;
};

export type VisualWorkflowDslV2Document = {
  schema_version: 2;
  workflow_id: "first-five-minute-breakout";
  mode: "simulation";
  runtime_modes: ["historical_simulation", "live_simulation"];
  execution_target: "fake_broker";
  instrument_scope: {
    asset_class: "stock";
    side: "long";
    currency: "USD";
    routing: "SMART";
    session: "US_RTH";
  };
  runtime_inputs: [
    { key: "symbol"; data_type: "Symbol"; required: true },
    { key: "maximum_dollar_loss"; data_type: "Money"; required: true },
  ];
  nodes: VisualWorkflowDslV2Node[];
  edges: VisualWorkflowDslV2Edge[];
  safety_gates: {
    risk_check_required: true;
    armed_authorization_required: true;
    protective_stop_required: true;
    stale_data_required: true;
    reconciliation_required: true;
    emergency_stop_required: true;
    position_monitor_required: true;
    audit_sink_required: true;
    broker_transport_allowed: false;
    live_trading_enabled: false;
    arbitrary_code_allowed: false;
  };
};

export type VisualWorkflowDslDocument =
  | VisualWorkflowDslV1Document
  | VisualWorkflowDslV2Document;

export type VisualWorkflowDslCompileResult =
  | {
      status: "compiled";
      document: VisualWorkflowDslV2Document;
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
      schema_version: 2,
      workflow_id: "first-five-minute-breakout",
      mode: "simulation",
      runtime_modes: ["historical_simulation", "live_simulation"],
      execution_target: "fake_broker",
      instrument_scope: {
        asset_class: "stock",
        side: "long",
        currency: "USD",
        routing: "SMART",
        session: "US_RTH",
      },
      runtime_inputs: [
        { key: "symbol", data_type: "Symbol", required: true },
        { key: "maximum_dollar_loss", data_type: "Money", required: true },
      ],
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.type,
        config: { ...node.config },
        position: { ...node.position },
      })),
      edges: edges.map((edge) => ({
        id: edge.id,
        source_node: edge.source,
        source_port: edge.sourcePort,
        target_node: edge.target,
        target_port: edge.targetPort,
      })),
      safety_gates: {
        risk_check_required: true,
        armed_authorization_required: true,
        protective_stop_required: true,
        stale_data_required: true,
        reconciliation_required: true,
        emergency_stop_required: true,
        position_monitor_required: true,
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
        schema_version: 2,
        workflow_id: "first-five-minute-breakout",
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
