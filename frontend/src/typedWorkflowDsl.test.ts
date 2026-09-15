import { describe, expect, it } from "vitest";

import {
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
} from "./typedWorkflowNodeCatalog";
import {
  compileVisualWorkflowDsl,
  defaultVisualWorkflowDslCompileResult,
  formatVisualWorkflowDslPreview,
} from "./typedWorkflowDsl";

describe("visualWorkflowDsl", () => {
  it("compiles the default typed graph to schema-v2 fake-broker simulation", () => {
    expect(defaultVisualWorkflowDslCompileResult).toMatchObject({
      status: "compiled",
      document: {
        schema_version: 2,
        workflow_id: "first-five-minute-breakout",
        mode: "simulation",
        runtime_modes: ["historical_simulation", "live_simulation"],
        execution_target: "fake_broker",
        runtime_inputs: [
          { key: "symbol", data_type: "Symbol", required: true },
          { key: "maximum_dollar_loss", data_type: "Money", required: true },
        ],
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
    });

    if (defaultVisualWorkflowDslCompileResult.status !== "compiled") {
      throw new Error("default workflow should compile");
    }

    expect(defaultVisualWorkflowDslCompileResult.document.nodes.map((node) => node.type)).toEqual(
      expect.arrayContaining([
        "opening_range_high",
        "day_low",
        "crosses_above",
        "long_risk_size",
        "risk_gate",
        "armed_run_authorization",
        "protective_stop",
        "fake_broker",
        "position_monitor",
        "audit_sink",
      ]),
    );
    expect(defaultVisualWorkflowDslCompileResult.document.edges[0]).toHaveProperty(
      "source_port",
    );
  });

  it("does not compile graphs missing the risk gate", () => {
    const result = compileVisualWorkflowDsl(
      simulationWorkflowNodeCatalog.filter((node) => node.type !== "risk_gate"),
      simulationWorkflowEdgeCatalog.filter(
        (edge) => edge.source !== "risk-gate" && edge.target !== "risk-gate",
      ),
    );

    expect(result.status).toBe("invalid");
    expect(result.document).toBeNull();
    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "missing_required_node",
          nodeType: "risk_gate",
        }),
      ]),
    );
  });

  it("formats a safe JSON preview with no credentials or external transport", () => {
    const preview = formatVisualWorkflowDslPreview(defaultVisualWorkflowDslCompileResult).toLowerCase();

    expect(preview).toContain('"schema_version": 2');
    expect(preview).toContain('"execution_target": "fake_broker"');
    expect(preview).toContain('"live_trading_enabled": false');

    const forbidden = [
      "account_id",
      "api_key",
      "broker_host",
      "credential",
      "eval(",
      "external_transport",
      "javascript",
      "password",
      "place_order",
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
