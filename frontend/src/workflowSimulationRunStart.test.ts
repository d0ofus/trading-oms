import { describe, expect, it, vi } from "vitest";

import type {
  WorkflowApiClient,
  WorkflowDefinitionApiView,
  WorkflowSimulationRunApiView,
} from "./workflowApiClient";
import {
  LOCAL_SIMULATION_REPLAY_REFERENCE,
  executeWorkflowSimulationRunStart,
  prepareWorkflowSimulationRunStart,
  workflowSimulationRunEligibility,
  type WorkflowSimulationRunStartContext,
} from "./workflowSimulationRunStart";

describe("workflow simulation run start", () => {
  it("prepares one exact confirmation request for an eligible saved workflow", () => {
    const createRunId = vi.fn(() => "fixed-id-001");
    const now = vi.fn(() => new Date("2026-07-16T06:30:00.000Z"));

    const state = prepareWorkflowSimulationRunStart(eligibleContext, { createRunId, now });

    expect(state).toEqual({
      status: "confirming",
      attempt: {
        workflowId: "workflow-001",
        workflowVersion: 3,
        replayInputReference: LOCAL_SIMULATION_REPLAY_REFERENCE,
        request: {
          schema_version: 1,
          expected_workflow_version: 3,
          run_id: "workflow-run-fixed-id-001",
          requested_at: "2026-07-16T06:30:00.000Z",
          evaluated_at: "2026-07-16T06:30:00.000Z",
          approval_expires_at: "2026-07-16T06:35:00.000Z",
          replay_input_reference: LOCAL_SIMULATION_REPLAY_REFERENCE,
        },
      },
    });
    expect(createRunId).toHaveBeenCalledTimes(1);
    expect(now).toHaveBeenCalledTimes(1);
  });

  it.each([
    [{ loadedWorkflow: null }, "validation_blocked"],
    [{ selectedWorkflowId: "workflow-other" }, "validation_blocked"],
    [{ draftDirty: true }, "validation_blocked"],
    [{ graphValid: false }, "validation_blocked"],
    [{ workflowListStatus: "loading" }, "unavailable"],
    [{ persistenceStatus: "version_conflict" }, "conflict"],
    [{ persistenceStatus: "unavailable" }, "unavailable"],
    [{ readStateStatus: "loading" }, "unavailable"],
    [{ canAdministerSystem: false }, "authorization_blocked"],
    [{ emergencyStopActive: true }, "emergency_stop_blocked"],
  ] as [Partial<WorkflowSimulationRunStartContext>, string][])(
    "blocks ineligible context %# before generating a request",
    (patch, expectedStatus) => {
      const createRunId = vi.fn(() => "must-not-run");
      const now = vi.fn(() => new Date("2026-07-16T06:30:00.000Z"));
      const context = { ...eligibleContext, ...patch };

      expect(workflowSimulationRunEligibility(context).status).toBe(expectedStatus);
      expect(prepareWorkflowSimulationRunStart(context, { createRunId, now }).status).toBe(
        expectedStatus,
      );
      expect(createRunId).not.toHaveBeenCalled();
      expect(now).not.toHaveBeenCalled();
    },
  );

  it("retains the exact request across explicit idempotent retry and never retries itself", async () => {
    const attempt = confirmingAttempt();
    const startSimulationRun = vi.fn(async () => validRun);
    const client = workflowClient({ startSimulationRun });

    const first = await executeWorkflowSimulationRunStart(client, attempt);

    expect(first.status).toBe("success");
    expect(startSimulationRun).toHaveBeenCalledTimes(1);
    expect(startSimulationRun).toHaveBeenLastCalledWith("workflow-001", attempt.request);

    const second = await executeWorkflowSimulationRunStart(client, attempt);

    expect(second.status).toBe("success");
    expect(startSimulationRun).toHaveBeenCalledTimes(2);
    expect(startSimulationRun.mock.calls[0]).toEqual(startSimulationRun.mock.calls[1]);
  });

  it.each([
    [400, "validation_blocked"],
    [401, "authorization_blocked"],
    [403, "authorization_blocked"],
    [409, "conflict"],
    [423, "emergency_stop_blocked"],
    [500, "unavailable"],
  ])("maps HTTP %s to generic %s state", async (status, expectedStatus) => {
    const client = workflowClient({
      startSimulationRun: async () => {
        const { WorkflowApiError } = await import("./workflowApiClient");
        throw new WorkflowApiError("private-value-must-not-render", status);
      },
    });

    const result = await executeWorkflowSimulationRunStart(client, confirmingAttempt());

    expect(result.status).toBe(expectedStatus);
    expect(JSON.stringify(result)).not.toContain("private-value-must-not-render");
  });

  it("rejects untrusted or mismatched success records", async () => {
    const client = workflowClient({
      startSimulationRun: async () =>
        ({
          ...validRun,
          workflow_id: "workflow-other",
          unexpected: "private-value-must-not-render",
        }) as WorkflowSimulationRunApiView,
    });

    const result = await executeWorkflowSimulationRunStart(client, confirmingAttempt());

    expect(result.status).toBe("unavailable");
    expect(JSON.stringify(result)).not.toContain("private-value-must-not-render");
  });
});

const workflow: WorkflowDefinitionApiView = {
  schema_version: 1,
  workflow_id: "workflow-001",
  display_name: "Opening breakout simulation",
  description: "Validated visual simulation workflow",
  version: 3,
  created_at: "2026-07-16T06:00:00Z",
  updated_at: "2026-07-16T06:15:00Z",
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

const eligibleContext: WorkflowSimulationRunStartContext = {
  loadedWorkflow: workflow,
  selectedWorkflowId: "workflow-001",
  draftDirty: false,
  graphValid: true,
  workflowListStatus: "loaded",
  persistenceStatus: "idle",
  readStateStatus: "loaded",
  canAdministerSystem: true,
  emergencyStopActive: false,
};

function confirmingAttempt() {
  const state = prepareWorkflowSimulationRunStart(eligibleContext, {
    createRunId: () => "fixed-id-001",
    now: () => new Date("2026-07-16T06:30:00.000Z"),
  });
  if (state.status !== "confirming") {
    throw new Error("expected confirming attempt");
  }
  return state.attempt;
}

const validRun: WorkflowSimulationRunApiView = {
  schema_version: 1,
  workflow_id: "workflow-001",
  run_id: "workflow-run-fixed-id-001",
  status: "waiting_for_approval",
  created_at: "2026-07-16T06:30:00.000Z",
  updated_at: "2026-07-16T06:30:00.000Z",
  approval_ticket_id: "workflow-run-fixed-id-001-approval-ticket",
  simulation_run: {
    schema_version: 1,
    run_id: "workflow-run-fixed-id-001",
    status: "completed",
    created_at: "2026-07-16T06:30:00.000Z",
    updated_at: "2026-07-16T06:30:00.000Z",
    replay_input_reference: LOCAL_SIMULATION_REPLAY_REFERENCE,
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

function workflowClient(overrides: Partial<WorkflowApiClient>): WorkflowApiClient {
  const unsupported = async () => {
    throw new Error("unexpected workflow API call");
  };
  return {
    listWorkflows: unsupported,
    getWorkflow: unsupported,
    createWorkflow: unsupported,
    updateWorkflow: unsupported,
    startSimulationRun: unsupported,
    listSimulationRuns: unsupported,
    getSimulationRun: unsupported,
    ...overrides,
  } as WorkflowApiClient;
}
