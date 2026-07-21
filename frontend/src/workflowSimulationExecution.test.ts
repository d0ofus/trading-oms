import { describe, expect, it, vi } from "vitest";

import {
  WorkflowApiError,
  type WorkflowApiClient,
  type WorkflowSimulationRunApiView,
} from "./workflowApiClient";
import type { WorkflowRunInspectionItem } from "./workflowRunInspector";
import {
  canRetryWorkflowSimulationExecution,
  executeWorkflowSimulationExecution,
  prepareWorkflowSimulationExecution,
  workflowSimulationExecutionEligibility,
} from "./workflowSimulationExecution";

describe("workflow simulation execution", () => {
  it("requires admin authority, committed approval, and an inactive emergency stop", () => {
    expect(workflowSimulationExecutionEligibility(item(), context())).toEqual({
      status: "eligible",
    });
    expect(
      workflowSimulationExecutionEligibility(item(), {
        ...context(),
        canAdministerSystem: false,
      }),
    ).toMatchObject({ status: "authorization_blocked" });
    expect(
      workflowSimulationExecutionEligibility(item(), {
        ...context(),
        emergencyStopActive: true,
      }),
    ).toMatchObject({ status: "emergency_stop_blocked" });
    expect(
      workflowSimulationExecutionEligibility(
        item({ status: "waiting_for_approval", approval_decision: null }),
        context(),
      ),
    ).toMatchObject({ status: "validation_blocked" });
  });

  it("prepares an exact reviewed command without executing automatically", () => {
    const state = prepareWorkflowSimulationExecution(item(), context(), true, {
      now: () => new Date("2026-07-08T13:47:00Z"),
    });

    expect(state).toEqual({
      status: "confirming",
      attempt: {
        workflowId: "workflow-001",
        workflowVersion: 1,
        runId: "workflow-run-001",
        request: {
          schema_version: 1,
          expected_workflow_version: 1,
          approval_ticket_id: "workflow-run-001-approval-ticket",
          approval_decision_id: "workflow-run-001-approve-decision",
          order_intent_id: "workflow-run-001-intent",
          risk_decision_id: "workflow-run-001-risk",
          order_id: "workflow-run-001-order",
          execution_id: "workflow-run-001-execution",
          executed_at: "2026-07-08T13:47:00.000Z",
          actor: "human-operator-001",
          execution_reference: "workflow-run-001-admin-execution-review",
          reason: "operator_confirmed_simulation_execution",
          broker_state_known: true,
          expected_protection_present: true,
        },
      },
    });
  });

  it("validates committed deterministic execution evidence and exact retry", async () => {
    const prepared = prepareWorkflowSimulationExecution(item(), context(), true, {
      now: () => new Date("2026-07-08T13:47:00Z"),
    });
    expect(prepared.status).toBe("confirming");
    if (prepared.status !== "confirming") {
      return;
    }
    const executeSimulationRun = vi.fn().mockResolvedValue(executedRun());
    const client = { executeSimulationRun } as unknown as WorkflowApiClient;

    const first = await executeWorkflowSimulationExecution(client, prepared.attempt);
    const retry = await executeWorkflowSimulationExecution(client, prepared.attempt);

    expect(first).toMatchObject({ status: "success", record: { status: "executed" } });
    expect(retry).toEqual(first);
    expect(executeSimulationRun).toHaveBeenCalledTimes(2);
    expect(executeSimulationRun).toHaveBeenNthCalledWith(
      1,
      "workflow-001",
      "workflow-run-001",
      prepared.attempt.request,
    );
  });

  it.each([
    [400, "validation_blocked"],
    [403, "authorization_blocked"],
    [409, "conflict"],
    [423, "emergency_stop_blocked"],
    [503, "unavailable"],
  ])("maps API status %s to %s without assuming success", async (status, expected) => {
    const prepared = prepareWorkflowSimulationExecution(item(), context(), true, {
      now: () => new Date("2026-07-08T13:47:00Z"),
    });
    expect(prepared.status).toBe("confirming");
    if (prepared.status !== "confirming") {
      return;
    }
    const client = {
      executeSimulationRun: vi
        .fn()
        .mockRejectedValue(new WorkflowApiError("/simulation-runs/run/execute", status)),
    } as unknown as WorkflowApiClient;

    const result = await executeWorkflowSimulationExecution(client, prepared.attempt);

    expect(result.status).toBe(expected);
    expect(canRetryWorkflowSimulationExecution(result)).toBe(status === 503);
  });

  it("fails closed for contradictory response evidence", async () => {
    const prepared = prepareWorkflowSimulationExecution(item(), context(), true, {
      now: () => new Date("2026-07-08T13:47:00Z"),
    });
    expect(prepared.status).toBe("confirming");
    if (prepared.status !== "confirming") {
      return;
    }
    const client = {
      executeSimulationRun: vi.fn().mockResolvedValue({
        ...executedRun(),
        execution: { ...executedRun().execution!, order_id: "different-order" },
      }),
    } as unknown as WorkflowApiClient;

    const result = await executeWorkflowSimulationExecution(client, prepared.attempt);

    expect(result).toMatchObject({ status: "unavailable" });
  });

  it("surfaces committed execution as recovered durable evidence", () => {
    expect(
      workflowSimulationExecutionEligibility(
        item({ ...executedRun(), execution: executedRun().execution }),
        context(),
      ),
    ).toMatchObject({ status: "recovered" });
  });
});

function context() {
  return {
    canAdministerSystem: true,
    emergencyStopActive: false,
    actor: "human-operator-001",
  };
}

function item(
  overrides: Partial<WorkflowSimulationRunApiView> = {},
): WorkflowRunInspectionItem {
  const run: WorkflowSimulationRunApiView = {
    schema_version: 1,
    workflow_id: "workflow-001",
    expected_workflow_version: 1,
    run_id: "workflow-run-001",
    status: "approved_not_executed",
    created_at: "2026-07-08T13:29:55Z",
    updated_at: "2026-07-08T13:46:00Z",
    approval_ticket_id: "workflow-run-001-approval-ticket",
    approval_decision: {
      schema_version: 1,
      decision_id: "workflow-run-001-approve-decision",
      ticket_id: "workflow-run-001-approval-ticket",
      previous_status: "pending",
      new_status: "approved",
      decided_at: "2026-07-08T13:46:00Z",
      actor: "approver-operator-001",
      decision_reference: "workflow-run-001-approve-manual-review",
      reason: "operator_reviewed_simulation_evidence",
      request: {},
      ticket: {},
    },
    execution: null,
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
        status: "approved_not_executed",
        detail: "Approved simulation evidence awaits explicit execution",
        journal_reference: "journal_sequence:10",
      },
    ],
    journal_references: ["journal_sequence:10"],
    ...overrides,
  };
  return {
    key: "workflow-001::workflow-run-001",
    workflowId: "workflow-001",
    workflowName: "Opening breakout simulation",
    workflowVersion: 1,
    run,
  };
}

function executedRun(): WorkflowSimulationRunApiView {
  return {
    ...item().run,
    status: "executed",
    updated_at: "2026-07-08T13:47:00.000Z",
    node_statuses: [
      ["approval_ticket", "approved_consumed"],
      ["fake_broker", "filled"],
      ["position_update", "completed"],
      ["alert", "completed_local_noop"],
      ["audit_sink", "completed"],
    ].map(([node_type, status], index) => ({
      schema_version: 1 as const,
      node_id: `${node_type}-${index}`,
      node_type,
      status,
      detail: "Committed local simulation evidence",
      journal_reference: `journal_sequence:${20 + index}`,
    })),
    execution: {
      schema_version: 1,
      workflow_id: "workflow-001",
      expected_workflow_version: 1,
      run_id: "workflow-run-001",
      approval_ticket_id: "workflow-run-001-approval-ticket",
      approval_decision_id: "workflow-run-001-approve-decision",
      order_intent_id: "workflow-run-001-intent",
      risk_decision_id: "workflow-run-001-risk",
      order_id: "workflow-run-001-order",
      execution_id: "workflow-run-001-execution",
      executed_at: "2026-07-08T13:47:00.000Z",
      actor: "human-operator-001",
      execution_reference: "workflow-run-001-admin-execution-review",
      reason: "operator_confirmed_simulation_execution",
      broker_state_known: true,
      expected_protection_present: true,
      protection_status: "expected_protection_present",
      risk_increasing_actions_blocked: false,
      oms_transitions: ["APPROVED", "SUBMITTED", "ACKNOWLEDGED", "FILLED"].map(
        (new_state) => ({ new_state }),
      ),
      broker_transitions: ["acknowledged", "filled"].map((state) => ({ state })),
      position: {
        schema_version: 1,
        position_id: "workflow-run-001-position",
        symbol: "AAPL",
        quantity: 10,
        average_price: 101.25,
        protection_status: "expected_protection_present",
        expected_protection_kind: "stop",
        updated_at: "2026-07-08T13:47:00.000Z",
        source_fill_reference: "workflow-run-001-execution-fill",
        journal_references: ["journal_sequence:20"],
      },
      alert_intents: [
        {
          alert_id: "workflow-run-001-execution-alert",
          channel: "local",
          severity: "informational",
        },
      ],
      alert_dispatches: [
        {
          alert_id: "workflow-run-001-execution-alert",
          channel: "local",
          status: "recorded",
          dispatcher: "noop",
        },
      ],
      journal_references: ["journal_sequence:20", "journal_sequence:21"],
    },
  };
}
