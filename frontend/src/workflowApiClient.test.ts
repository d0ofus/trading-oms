import { describe, expect, it } from "vitest";

import {
  WORKFLOW_API_ENDPOINTS,
  WorkflowApiError,
  createWorkflowApiClient,
  type WorkflowDefinitionApiView,
  type WorkflowDefinitionSaveRequest,
  type WorkflowDefinitionUpdateRequest,
  type WorkflowSimulationRunApiView,
  type WorkflowSimulationRunRequest,
} from "./workflowApiClient";
import type { VisualWorkflowDslDocument } from "./visualWorkflowDsl";

const sampleDocument: VisualWorkflowDslDocument = {
  schema_version: 1,
  workflow_id: "visual-simulation-workflow",
  mode: "simulation",
  runtime: "preview_only",
  broker: "fake_broker_only",
  nodes: [
    {
      id: "risk-check",
      type: "risk_check",
      required_for_risk_increasing_path: true,
    },
    {
      id: "approval-ticket",
      type: "approval_ticket",
      required_for_risk_increasing_path: true,
    },
    {
      id: "audit-sink",
      type: "audit_sink",
      required_for_risk_increasing_path: true,
    },
  ],
  edges: [
    {
      source: "risk-check",
      target: "approval-ticket",
    },
    {
      source: "approval-ticket",
      target: "audit-sink",
    },
  ],
  safety_gates: {
    risk_check_required: true,
    manual_approval_required: true,
    audit_sink_required: true,
    broker_transport_allowed: false,
    live_trading_enabled: false,
    arbitrary_code_allowed: false,
  },
};

const saveRequest: WorkflowDefinitionSaveRequest = {
  workflow_id: "workflow-001",
  display_name: "Opening breakout simulation",
  description: "Validated visual simulation workflow",
  requested_at: "2026-07-08T00:00:00Z",
  document: sampleDocument,
};

const updateRequest: WorkflowDefinitionUpdateRequest = {
  ...saveRequest,
  expected_version: 1,
};

const savedWorkflow: WorkflowDefinitionApiView = {
  schema_version: 1,
  ...saveRequest,
  version: 1,
  created_at: "2026-07-08T00:00:00Z",
  updated_at: "2026-07-08T00:00:00Z",
};

const simulationRunRequest: WorkflowSimulationRunRequest = {
  expected_workflow_version: 1,
  run_id: "workflow-run-001",
  requested_at: "2026-07-08T13:29:55Z",
  evaluated_at: "2026-07-08T13:45:10Z",
  approval_expires_at: "2026-07-08T13:50:10Z",
  replay_input_reference: "fixtures/replay/aapl-session.jsonl",
};

const simulationRun: WorkflowSimulationRunApiView = {
  schema_version: 1,
  workflow_id: "workflow-001",
  run_id: "workflow-run-001",
  status: "waiting_for_approval",
  created_at: "2026-07-08T13:29:55Z",
  updated_at: "2026-07-08T13:45:10Z",
  approval_ticket_id: "workflow-run-001-approval-ticket",
  simulation_run: {
    schema_version: 1,
    run_id: "workflow-run-001",
    status: "completed",
    created_at: "2026-07-08T13:29:55Z",
    updated_at: "2026-07-08T13:45:10Z",
    replay_input_reference: "fixtures/replay/aapl-session.jsonl",
    journal_references: ["journal_sequence:1"],
  },
  node_statuses: [
    {
      schema_version: 1,
      node_id: "approval-ticket",
      node_type: "approval_ticket",
      status: "waiting_for_approval",
      detail: "Manual approval is required before downstream simulation nodes",
      journal_reference: "journal_sequence:10",
    },
  ],
  journal_references: ["journal_sequence:10"],
};

describe("workflow API client", () => {
  it("uses safe workflow persistence endpoints with explicit methods", async () => {
    const calls: { input: string; init?: RequestInit }[] = [];
    const client = createWorkflowApiClient({
      fetchImpl: async (input, init) => {
        calls.push({ input: String(input), init });
        return jsonResponse(String(input).endsWith("/workflow-001") ? savedWorkflow : [savedWorkflow]);
      },
    });

    await client.listWorkflows();
    await client.getWorkflow("workflow-001");
    await client.createWorkflow(saveRequest);
    await client.updateWorkflow("workflow-001", updateRequest);
    await client.startSimulationRun("workflow-001", simulationRunRequest);
    await client.listSimulationRuns("workflow-001");
    await client.getSimulationRun("workflow-001", "workflow-run-001");

    expect(calls.map((call) => [call.input, call.init?.method])).toEqual([
      [WORKFLOW_API_ENDPOINTS.workflows, "GET"],
      [`${WORKFLOW_API_ENDPOINTS.workflows}/workflow-001`, "GET"],
      [WORKFLOW_API_ENDPOINTS.workflows, "POST"],
      [`${WORKFLOW_API_ENDPOINTS.workflows}/workflow-001`, "PUT"],
      [`${WORKFLOW_API_ENDPOINTS.workflows}/workflow-001/simulation-runs`, "POST"],
      [`${WORKFLOW_API_ENDPOINTS.workflows}/workflow-001/simulation-runs`, "GET"],
      [
        `${WORKFLOW_API_ENDPOINTS.workflows}/workflow-001/simulation-runs/workflow-run-001`,
        "GET",
      ],
    ]);
    expect(calls[2].init?.body).toBe(JSON.stringify(saveRequest));
    expect(calls[3].init?.body).toBe(JSON.stringify(updateRequest));
    expect(calls[4].init?.body).toBe(JSON.stringify(simulationRunRequest));
  });

  it("exposes response status without exposing response payloads", async () => {
    const client = createWorkflowApiClient({
      fetchImpl: async () => new Response("private backend detail", { status: 409 }),
    });

    const error = await client.getWorkflow("workflow-001").catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(WorkflowApiError);
    expect(error).toMatchObject({ status: 409 });
    expect(String(error)).not.toContain("private backend detail");
  });

  it("loads simulation run responses as approval-wait records", async () => {
    const client = createWorkflowApiClient({
      fetchImpl: async (input, init) =>
        jsonResponse(
          init.method === "GET" && String(input).endsWith("/simulation-runs")
            ? [simulationRun]
            : simulationRun,
        ),
    });

    await expect(client.startSimulationRun("workflow-001", simulationRunRequest)).resolves.toEqual(
      simulationRun,
    );
    await expect(client.listSimulationRuns("workflow-001")).resolves.toEqual([simulationRun]);
    await expect(client.getSimulationRun("workflow-001", "workflow-run-001")).resolves.toEqual(
      simulationRun,
    );
  });

  it("does not expose run, broker, credential, route, or live endpoints", () => {
    const serialized = JSON.stringify(WORKFLOW_API_ENDPOINTS).toLowerCase();
    const forbidden = [
      "account",
      "api_key",
      "broker_host",
      "connect",
      "credential",
      "eval",
      "ibkr",
      "javascript",
      "password",
      "place_order",
      "route",
      "script",
      "secret",
      "submit",
      "token",
      "transmit",
    ];

    for (const term of forbidden) {
      expect(serialized).not.toContain(term);
    }
  });
});

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
