import { describe, expect, it } from "vitest";

import { visualWorkflowPalette } from "./typedWorkflowNodeCatalog";
import {
  visualSimulationWorkflowEdges,
  visualSimulationWorkflowLayoutPolicy,
  visualSimulationWorkflowNodeCatalog,
  visualSimulationWorkflowStatusLegend,
  visualSimulationWorkflowValidation,
} from "./TypedStrategyCanvas";

describe("visualSimulationWorkflowCanvas", () => {
  it("defines the requested opening-breakout graph and typed edge handles", () => {
    expect(visualSimulationWorkflowNodeCatalog.map((node) => node.title)).toEqual(
      expect.arrayContaining([
        "Historical dataset",
        "Dollar risk",
        "Opening-range high",
        "Day low",
        "Crosses above",
        "Long dollar-risk sizing",
        "Risk gate",
        "Armed-run authorization",
        "Stop-market entry",
        "Protective stop",
        "Fake broker",
        "Position monitor",
        "Audit sink",
      ]),
    );
    expect(visualSimulationWorkflowEdges.every((edge) => edge.sourceHandle && edge.targetHandle)).toBe(
      true,
    );
  });

  it("offers focused one-minute, five-minute, and day metric palette nodes", () => {
    const labels = visualWorkflowPalette.map((item) => item.label);
    expect(labels).toEqual(
      expect.arrayContaining([
        "First 1-minute high",
        "First 1-minute low",
        "First 5-minute high",
        "First 5-minute low",
        "Day high",
        "Day low",
      ]),
    );
  });

  it("keeps execution simulation-only and external transport absent", () => {
    expect(visualSimulationWorkflowNodeCatalog.every((node) => node.supportsExecution === false)).toBe(
      true,
    );
    expect(
      visualSimulationWorkflowNodeCatalog.filter((node) => node.executionCapability !== "none"),
    ).toEqual([expect.objectContaining({ type: "fake_broker", executionCapability: "simulation_only" })]);
    const serialized = JSON.stringify({
      nodes: visualSimulationWorkflowNodeCatalog,
      edges: visualSimulationWorkflowEdges,
    }).toLowerCase();
    for (const term of [
      "account_id",
      "api_key",
      "credential",
      "external_transport",
      "password",
      "place_order",
      "secret",
      "submit_order",
      "transmit_order",
    ]) {
      expect(serialized).not.toContain(term);
    }
  });

  it("enables drag, typed connections, persistence, and fake-broker-only execution", () => {
    expect(visualSimulationWorkflowLayoutPolicy).toEqual({
      mode: "typed_drag_drop_builder",
      nodesDraggable: true,
      nodesConnectable: true,
      elementsSelectable: true,
      persistenceEnabled: true,
      executionEnabled: "fake_broker_only",
    });
    expect(visualSimulationWorkflowValidation).toEqual({ status: "valid", errors: [] });
  });

  it("retains run inspection vocabulary for blocks, fills, and alerts", () => {
    expect(visualSimulationWorkflowStatusLegend).toEqual([
      "completed",
      "passed",
      "risk_blocked",
      "waiting_for_approval",
      "blocked_waiting_for_approval",
      "filled",
      "alert_recorded",
    ]);
  });
});
