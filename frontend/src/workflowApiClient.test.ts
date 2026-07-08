import { describe, expect, it } from "vitest";

import {
  WORKFLOW_API_ENDPOINTS,
  createWorkflowApiClient,
  type WorkflowDefinitionApiView,
  type WorkflowDefinitionSaveRequest,
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

const savedWorkflow: WorkflowDefinitionApiView = {
  schema_version: 1,
  ...saveRequest,
  version: 1,
  created_at: "2026-07-08T00:00:00Z",
  updated_at: "2026-07-08T00:00:00Z",
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
    await client.updateWorkflow("workflow-001", saveRequest);

    expect(calls.map((call) => [call.input, call.init?.method])).toEqual([
      [WORKFLOW_API_ENDPOINTS.workflows, "GET"],
      [`${WORKFLOW_API_ENDPOINTS.workflows}/workflow-001`, "GET"],
      [WORKFLOW_API_ENDPOINTS.workflows, "POST"],
      [`${WORKFLOW_API_ENDPOINTS.workflows}/workflow-001`, "PUT"],
    ]);
    expect(calls[2].init?.body).toBe(JSON.stringify(saveRequest));
    expect(calls[3].init?.body).toBe(JSON.stringify(saveRequest));
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
      "run",
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
