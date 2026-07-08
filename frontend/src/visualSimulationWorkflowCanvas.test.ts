import { describe, expect, it } from "vitest";

import {
  visualSimulationWorkflowEdges,
  visualSimulationWorkflowNodeCatalog,
} from "./visualSimulationWorkflowCanvas";

describe("visualSimulationWorkflowCanvas", () => {
  it("defines the expected static simulation workflow scaffold", () => {
    expect(visualSimulationWorkflowNodeCatalog.map((node) => node.title)).toEqual([
      "Replay source",
      "Bar builder",
      "Strategy trigger",
      "Risk check",
      "Manual approval",
      "Fake broker",
      "Audit sink",
    ]);

    expect(visualSimulationWorkflowEdges.map((edge) => `${edge.source}->${edge.target}`)).toEqual([
      "replay-source->bar-builder",
      "bar-builder->strategy-trigger",
      "strategy-trigger->risk-check",
      "risk-check->manual-approval",
      "manual-approval->fake-broker",
      "fake-broker->audit-sink",
    ]);
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
});
