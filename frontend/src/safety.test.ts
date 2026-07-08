import { describe, expect, it } from "vitest";

import { safetyPosture } from "./safety";

describe("safetyPosture", () => {
  it("starts in paper mode without broker connectivity", () => {
    expect(safetyPosture).toEqual({
      appMode: "paper",
      liveTradingEnabled: false,
      brokerConnectivity: "none",
      alertDelivery: "local-noop",
      approvalMode: "manual-required",
      journalMode: "append-only",
    });
  });
});
