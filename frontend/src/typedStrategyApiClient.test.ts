import { describe, expect, it } from "vitest";
import { createWorkflowApiClient } from "./typedStrategyApiClient";
import { defaultVisualWorkflowDslCompileResult } from "./typedWorkflowDsl";

describe("typed strategy API client", () => {
  it("sends the reviewed version to the typed update endpoint", async () => {
    const calls: Array<{ url: string; init: RequestInit }> = [];
    const client = createWorkflowApiClient({ fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ version: 3 }), { status: 200 });
    }});
    const compiled = defaultVisualWorkflowDslCompileResult;
    if (compiled.status !== "compiled") throw new Error("Fixture must compile");
    await client.updateWorkflow("first-five-minute-breakout", {
      schema_version: 2, workflow_id: "first-five-minute-breakout",
      display_name: "Breakout", description: "Simulation", requested_at: "2026-07-08T12:00:00Z",
      expected_version: 2, document: compiled.document,
    });
    expect(calls[0].url).toBe("/api/typed-workflows/first-five-minute-breakout");
    expect(JSON.parse(String(calls[0].init.body)).expected_version).toBe(2);
    expect(calls[0].init.method).toBe("PUT");
  });

  it("surfaces a conflict without silently creating or retrying", async () => {
    let calls = 0;
    const client = createWorkflowApiClient({ fetchImpl: async () => {
      calls += 1; return new Response("{}", { status: 409 });
    }});
    await expect(client.getWorkflow("first-five-minute-breakout")).rejects.toThrow("409");
    expect(calls).toBe(1);
  });

  it("keeps typed datasets and runs separate from v1 execution", async () => {
    const urls: string[] = [];
    const client = createWorkflowApiClient({ fetchImpl: async (url) => {
      urls.push(url); return new Response("{}", { status: 200 });
    }});
    await client.getDataset("fixture-one");
    await client.armStrategyRun("run-one", {
      authorized_at: "2026-07-08T13:00:00Z", expires_at: "2026-07-08T20:00:00Z",
    });
    await client.getStrategyRun("run-one");
    expect(urls).toEqual(["/api/strategy-datasets/fixture-one",
      "/api/strategy-runs/run-one/arm", "/api/strategy-runs/run-one"]);
  });

  it("does not automatically retry when execution evidence is unavailable", async () => {
    let calls = 0;
    const client = createWorkflowApiClient({ fetchImpl: async () => {
      calls += 1; return new Response("{}", { status: 503 });
    }});
    await expect(client.simulateStrategyRun("run-one", {
      buying_power: "50000.00", concurrent_positions: 0,
      current_symbol_exposure: "0.00", daily_realized_loss: "0.00", reconciled: true,
    })).rejects.toThrow("503");
    expect(calls).toBe(1);
  });
});
