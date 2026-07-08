import { describe, expect, it } from "vitest";

import {
  visualSimulationWorkflowEdges,
  visualSimulationWorkflowLayoutPolicy,
  visualSimulationWorkflowNodeCatalog,
} from "./visualSimulationWorkflowCanvas";

describe("visualSimulationWorkflowCanvas", () => {
  it("defines the expected static simulation workflow scaffold", () => {
    expect(visualSimulationWorkflowNodeCatalog.map((node) => node.title)).toEqual([
      "Replay source",
      "Bar builder",
      "Strategy trigger",
      "Risk check",
      "Approval ticket",
      "Fake broker",
      "Position update",
      "Alert",
      "Audit sink",
    ]);

    expect(visualSimulationWorkflowEdges.map((edge) => `${edge.source}->${edge.target}`)).toEqual([
      "replay-source->bar-builder",
      "bar-builder->strategy-trigger",
      "strategy-trigger->risk-check",
      "risk-check->approval-ticket",
      "approval-ticket->fake-broker",
      "fake-broker->position-update",
      "position-update->alert",
      "alert->audit-sink",
    ]);
  });

  it("defines typed catalog entries required for risk-increasing simulation paths", () => {
    expect(visualSimulationWorkflowNodeCatalog.map((node) => node.type)).toEqual([
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
    expect(visualSimulationWorkflowNodeCatalog.every((node) => node.supportsExecution === false)).toBe(
      true,
    );
    expect(
      visualSimulationWorkflowNodeCatalog.every((node) => node.requiredForRiskIncreasingPath),
    ).toBe(true);
  });

  it("keeps the scaffold free of broker, credential, live, route, and code affordances", () => {
    const serialized = JSON.stringify({
      nodes: visualSimulationWorkflowNodeCatalog,
      edges: visualSimulationWorkflowEdges,
    }).toLowerCase();
    const forbidden = [
      "ibkr",
      "account",
      "credential",
      "api_key",
      "password",
      "secret",
      "token",
      "live mode",
      "live trading",
      "submit",
      "transmit",
      "place order",
      "route",
      "broker host",
      "javascript",
      "script",
      "eval",
      "import",
    ];

    for (const term of forbidden) {
      expect(serialized).not.toContain(term);
    }
  });

  it("allows local layout editing without enabling connection, persistence, or execution", () => {
    expect(visualSimulationWorkflowLayoutPolicy).toMatchObject({
      mode: "local_editable_layout",
      nodesDraggable: true,
      nodesConnectable: false,
      elementsSelectable: true,
      persistenceEnabled: false,
      executionEnabled: false,
    });
  });
});
