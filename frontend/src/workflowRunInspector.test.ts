import { describe, expect, it, vi } from "vitest";

import type {
  WorkflowApiClient,
  WorkflowDefinitionApiView,
  WorkflowSimulationRunApiView,
} from "./workflowApiClient";
import {
  loadWorkflowRunInspection,
  type WorkflowRunInspectionState,
} from "./workflowRunInspector";

describe("loadWorkflowRunInspection", () => {
  it("loads every saved workflow and orders runs newest first", async () => {
    const listSimulationRuns = vi.fn(async (workflowId: string) =>
      workflowId === "workflow-alpha" ? [olderRun] : [newerRun],
    );
    const client = workflowClient({
      listWorkflows: async () => [workflowAlpha, workflowBeta],
      listSimulationRuns,
    });

    const state = await loadWorkflowRunInspection(client);

    expect(state).toEqual<WorkflowRunInspectionState>({
      status: "loaded",
      items: [
        {
          key: "workflow-beta::run-newer",
          workflowId: "workflow-beta",
          workflowName: "Beta workflow",
          workflowVersion: 2,
          run: newerRun,
        },
        {
          key: "workflow-alpha::run-older",
          workflowId: "workflow-alpha",
          workflowName: "Alpha workflow",
          workflowVersion: 1,
          run: olderRun,
        },
      ],
      errorMessage: null,
    });
    expect(listSimulationRuns).toHaveBeenCalledTimes(2);
    expect(listSimulationRuns).toHaveBeenCalledWith("workflow-alpha");
    expect(listSimulationRuns).toHaveBeenCalledWith("workflow-beta");
  });

  it("returns an explicit empty loaded state when there are no saved workflows", async () => {
    const listSimulationRuns = vi.fn(async () => []);
    const client = workflowClient({
      listWorkflows: async () => [],
      listSimulationRuns,
    });

    await expect(loadWorkflowRunInspection(client)).resolves.toEqual({
      status: "loaded",
      items: [],
      errorMessage: null,
    });
    expect(listSimulationRuns).not.toHaveBeenCalled();
  });

  it("fails closed without exposing API error text or partial run data", async () => {
    const client = workflowClient({
      listWorkflows: async () => [workflowAlpha],
      listSimulationRuns: async () => {
        throw new Error("private-value-that-must-not-render");
      },
    });

    const state = await loadWorkflowRunInspection(client);

    expect(state).toEqual({
      status: "error",
      items: [],
      errorMessage: "Workflow simulation run history is unavailable",
    });
    expect(JSON.stringify(state)).not.toContain("private-value-that-must-not-render");
  });

  it("rejects mismatched workflow attribution and duplicate run keys", async () => {
    const mismatched = workflowClient({
      listWorkflows: async () => [workflowAlpha],
      listSimulationRuns: async () => [{ ...olderRun, workflow_id: "workflow-beta" }],
    });
    const duplicated = workflowClient({
      listWorkflows: async () => [workflowAlpha],
      listSimulationRuns: async () => [olderRun, olderRun],
    });

    await expect(loadWorkflowRunInspection(mismatched)).resolves.toEqual({
      status: "error",
      items: [],
      errorMessage: "Workflow simulation run history is unavailable",
    });
    await expect(loadWorkflowRunInspection(duplicated)).resolves.toEqual({
      status: "error",
      items: [],
      errorMessage: "Workflow simulation run history is unavailable",
    });
  });
});

function workflowClient(overrides: Partial<WorkflowApiClient>): WorkflowApiClient {
  const unsupported = async () => {
    throw new Error("unexpected workflow API call");
  };
  return {
    listWorkflows: async () => [],
    getWorkflow: unsupported,
    createWorkflow: unsupported,
    updateWorkflow: unsupported,
    startSimulationRun: unsupported,
    listSimulationRuns: async () => [],
    getSimulationRun: unsupported,
    ...overrides,
  } as WorkflowApiClient;
}

const workflowAlpha: WorkflowDefinitionApiView = workflow("workflow-alpha", "Alpha workflow", 2);
const workflowBeta: WorkflowDefinitionApiView = workflow("workflow-beta", "Beta workflow", 3);

const olderRun = run("workflow-alpha", "run-older", "2026-07-15T00:00:00Z");
const newerRun = run("workflow-beta", "run-newer", "2026-07-15T01:00:00Z");

function workflow(
  workflowId: string,
  displayName: string,
  version: number,
): WorkflowDefinitionApiView {
  return {
    schema_version: 1,
    workflow_id: workflowId,
    display_name: displayName,
    description: "Simulation workflow",
    version,
    created_at: "2026-07-14T00:00:00Z",
    updated_at: "2026-07-14T01:00:00Z",
    document: {
      schema_version: 1,
      workflow_id: "visual-simulation-workflow",
      mode: "simulation",
      runtime: "preview_only",
      broker: "fake_broker_only",
      nodes: [],
      edges: [],
      safety_gates: {
        risk_check_required: true,
        manual_approval_required: true,
        audit_sink_required: true,
        broker_transport_allowed: false,
        live_trading_enabled: false,
        arbitrary_code_allowed: false,
      },
    },
  };
}

function run(
  workflowId: string,
  runId: string,
  updatedAt: string,
): WorkflowSimulationRunApiView {
  return {
    schema_version: 1,
    workflow_id: workflowId,
    expected_workflow_version: workflowId === "workflow-alpha" ? 1 : 2,
    run_id: runId,
    status: "waiting_for_approval",
    created_at: updatedAt,
    updated_at: updatedAt,
    approval_ticket_id: `ticket-${runId}`,
    simulation_run: {
      schema_version: 1,
      run_id: runId,
      status: "waiting_for_approval",
      created_at: updatedAt,
      updated_at: updatedAt,
      replay_input_reference: `fixture://${runId}`,
      journal_references: ["journal_sequence:1"],
    },
    node_statuses: [
      {
        schema_version: 1,
        node_id: "approval-ticket",
        node_type: "approval_ticket",
        status: "waiting_for_approval",
        detail: "Manual approval is required",
        journal_reference: "journal_sequence:2",
      },
    ],
    journal_references: ["journal_sequence:2"],
  };
}
