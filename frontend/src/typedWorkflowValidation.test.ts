import { describe, expect, it } from "vitest";

import {
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
} from "./typedWorkflowNodeCatalog";
import {
  isTypedConnectionValid,
  validateCatalogWorkflowGraph,
  validateVisualWorkflowGraph,
} from "./typedWorkflowValidation";

describe("visualWorkflowValidation", () => {
  it("rejects type-compatible wiring the simulator does not execute", () => {
    const edges = simulationWorkflowEdgeCatalog.map((edge) =>
      edge.target === "protective-stop" && edge.targetPort === "stop_price"
        ? { ...edge, source: "opening-high", sourcePort: "price" }
        : edge,
    );
    const result = validateCatalogWorkflowGraph(simulationWorkflowNodeCatalog, edges);
    expect(result.status).toBe("invalid");
    expect(result.errors).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "unsupported_topology" }),
    ]));
  });
  it("accepts the default typed first-five-minute workflow", () => {
    expect(
      validateCatalogWorkflowGraph(simulationWorkflowNodeCatalog, simulationWorkflowEdgeCatalog),
    ).toEqual({ status: "valid", errors: [] });
  });

  it("reports missing sizing, arming, protection, monitoring, and audit nodes", () => {
    const removedTypes = new Set([
      "long_risk_size",
      "armed_run_authorization",
      "protective_stop",
      "position_monitor",
      "audit_sink",
    ]);
    const nodes = simulationWorkflowNodeCatalog.filter((node) => !removedTypes.has(node.type));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges = simulationWorkflowEdgeCatalog.filter(
      (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target),
    );

    const result = validateCatalogWorkflowGraph(nodes, edges);

    expect(result.status).toBe("invalid");
    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "missing_required_node", nodeType: "long_risk_size" }),
        expect.objectContaining({
          code: "missing_required_node",
          nodeType: "armed_run_authorization",
        }),
        expect.objectContaining({ code: "missing_required_node", nodeType: "protective_stop" }),
        expect.objectContaining({ code: "missing_required_node", nodeType: "position_monitor" }),
        expect.objectContaining({ code: "missing_required_node", nodeType: "audit_sink" }),
      ]),
    );
  });

  it("rejects incompatible typed ports", () => {
    const result = validateVisualWorkflowGraph(simulationWorkflowNodeCatalog, [
      { source: "symbol", sourcePort: "symbol", target: "rth", targetPort: "trades" },
    ]);

    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "incompatible_port",
          message: "Cannot connect Symbol to TradeStream.",
        }),
      ]),
    );
    expect(
      isTypedConnectionValid(simulationWorkflowNodeCatalog, {
        source: "symbol",
        sourceHandle: "symbol",
        target: "rth",
        targetHandle: "trades",
      }),
    ).toBe(false);
    expect(
      isTypedConnectionValid(simulationWorkflowNodeCatalog, {
        source: "historical-data",
        sourceHandle: "trades",
        target: "rth",
        targetHandle: "trades",
      }),
    ).toBe(true);
  });

  it("blocks unsafe action nodes, unknown endpoints, cycles, and multiple sinks", () => {
    const unsafe = validateVisualWorkflowGraph(
      [
        ...simulationWorkflowNodeCatalog,
        { id: "unsafe", type: "transmit_order" },
        { id: "fake-broker-2", type: "fake_broker" },
      ],
      [
        ...simulationWorkflowEdgeCatalog.map((edge) =>
          edge.target === "risk-gate"
            ? { ...edge, source: "stale-data-gate", sourcePort: "plan" }
            : edge,
        ),
        {
          source: "missing",
          sourcePort: "plan",
          target: "risk-gate",
          targetPort: "plan",
        },
      ],
    );

    expect(unsafe.status).toBe("invalid");
    expect(unsafe.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "unsafe_action_node", nodeId: "unsafe" }),
        expect.objectContaining({ code: "multiple_execution_sinks" }),
        expect.objectContaining({ code: "unknown_edge_endpoint" }),
        expect.objectContaining({ code: "cycle_detected" }),
      ]),
    );
  });
});
