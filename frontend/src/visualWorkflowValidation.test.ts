import { describe, expect, it } from "vitest";

import {
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
} from "./visualWorkflowNodeCatalog";
import {
  validateCatalogWorkflowGraph,
  validateVisualWorkflowGraph,
} from "./visualWorkflowValidation";

describe("visualWorkflowValidation", () => {
  it("accepts the default simulation workflow catalog graph", () => {
    expect(
      validateCatalogWorkflowGraph(simulationWorkflowNodeCatalog, simulationWorkflowEdgeCatalog),
    ).toEqual({
      status: "valid",
      errors: [],
    });
  });

  it("reports missing risk, approval, and audit nodes explicitly", () => {
    const result = validateVisualWorkflowGraph(
      [
        { id: "replay-source", type: "replay_source" },
        { id: "bar-builder", type: "bar_builder" },
      ],
      [{ source: "replay-source", target: "bar-builder" }],
    );

    expect(result.status).toBe("invalid");
    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "missing_required_node",
          message: "Missing required risk check node.",
          nodeType: "risk_check",
        }),
        expect.objectContaining({
          code: "missing_required_node",
          message: "Missing required approval ticket node.",
          nodeType: "approval_ticket",
        }),
        expect.objectContaining({
          code: "missing_required_node",
          message: "Missing required audit sink node.",
          nodeType: "audit_sink",
        }),
      ]),
    );
  });

  it("blocks unsafe action nodes and unsupported nodes", () => {
    const result = validateVisualWorkflowGraph(
      [
        { id: "risk-check", type: "risk_check" },
        { id: "approval-ticket", type: "approval_ticket" },
        { id: "audit-sink", type: "audit_sink" },
        { id: "live-order", type: "live_order" },
        { id: "custom-node", type: "spreadsheet_macro" },
      ],
      [],
    );

    expect(result.status).toBe("invalid");
    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "unsafe_action_node",
          nodeId: "live-order",
          nodeType: "live_order",
        }),
        expect.objectContaining({
          code: "unsupported_node",
          nodeId: "custom-node",
          nodeType: "spreadsheet_macro",
        }),
      ]),
    );
  });

  it("reports cycles and unknown edge endpoints", () => {
    const result = validateVisualWorkflowGraph(
      [
        { id: "risk-check", type: "risk_check" },
        { id: "approval-ticket", type: "approval_ticket" },
        { id: "audit-sink", type: "audit_sink" },
      ],
      [
        { source: "risk-check", target: "approval-ticket" },
        { source: "approval-ticket", target: "risk-check" },
        { source: "approval-ticket", target: "missing-node" },
      ],
    );

    expect(result.status).toBe("invalid");
    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "cycle_detected" }),
        expect.objectContaining({ code: "unknown_edge_endpoint" }),
      ]),
    );
  });
});
