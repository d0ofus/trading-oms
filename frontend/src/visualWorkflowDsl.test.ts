import { describe, expect, it } from "vitest";

import {
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
} from "./visualWorkflowNodeCatalog";
import {
  compileVisualWorkflowDsl,
  defaultVisualWorkflowDslCompileResult,
  formatVisualWorkflowDslPreview,
} from "./visualWorkflowDsl";

describe("visualWorkflowDsl", () => {
  it("compiles the default graph to a simulation-only workflow DSL document", () => {
    expect(defaultVisualWorkflowDslCompileResult).toMatchObject({
      status: "compiled",
      document: {
        schema_version: 1,
        workflow_id: "visual-simulation-workflow",
        mode: "simulation",
        runtime: "preview_only",
        broker: "fake_broker_only",
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
    });

    if (defaultVisualWorkflowDslCompileResult.status !== "compiled") {
      throw new Error("default workflow should compile");
    }

    expect(defaultVisualWorkflowDslCompileResult.document.nodes.map((node) => node.type)).toEqual([
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
  });

  it("does not compile invalid graphs", () => {
    const result = compileVisualWorkflowDsl(
      simulationWorkflowNodeCatalog.filter((node) => node.type !== "risk_check"),
      simulationWorkflowEdgeCatalog,
    );

    expect(result.status).toBe("invalid");
    expect(result.document).toBeNull();
    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "missing_required_node",
          nodeType: "risk_check",
        }),
      ]),
    );
  });

  it("formats a safe JSON preview with no live, credential, route, or code fields", () => {
    const preview = formatVisualWorkflowDslPreview(defaultVisualWorkflowDslCompileResult).toLowerCase();

    expect(preview).toContain('"mode": "simulation"');
    expect(preview).toContain('"runtime": "preview_only"');
    expect(preview).toContain('"live_trading_enabled": false');

    const forbidden = [
      "account_id",
      "api_key",
      "broker_host",
      "credential",
      "eval(",
      "eval:",
      "ibkr",
      "javascript",
      "password",
      "place_order",
      "route",
      "secret",
      "submit_order",
      "token",
      "transmit_order",
    ];

    for (const term of forbidden) {
      expect(preview).not.toContain(term);
    }
  });
});
