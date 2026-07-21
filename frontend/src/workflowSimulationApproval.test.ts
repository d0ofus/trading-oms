import { describe, expect, it, vi } from "vitest";

import {
  WorkflowApiError,
  type WorkflowApiClient,
  type WorkflowSimulationRunApiView,
} from "./workflowApiClient";
import type { WorkflowRunInspectionItem } from "./workflowRunInspector";
import {
  executeWorkflowSimulationDecision,
  prepareWorkflowSimulationDecision,
  workflowSimulationDecisionEligibility,
} from "./workflowSimulationApproval";

describe("durable workflow simulation approval", () => {
  it("requires an approver and blocks approval during emergency stop while allowing rejection", () => {
    expect(
      workflowSimulationDecisionEligibility(item(), {
        canApproveSimulation: false,
        emergencyStopActive: false,
      }),
    ).toEqual({
      status: "authorization_blocked",
      message: "Dedicated approver permission is required",
    });
    expect(
      prepareWorkflowSimulationDecision(item(), "approve", context(true), "reviewed", {
        now: () => new Date("2026-07-08T13:46:00Z"),
      }),
    ).toMatchObject({ status: "emergency_stop_blocked" });
    expect(
      prepareWorkflowSimulationDecision(item(), "reject", context(true), "reviewed", {
        now: () => new Date("2026-07-08T13:46:00Z"),
      }),
    ).toMatchObject({ status: "confirming", attempt: { action: "reject" } });
  });

  it("builds exact bound decision requests and validates approved-but-not-executed responses", async () => {
    const prepared = prepareWorkflowSimulationDecision(
      item(),
      "approve",
      context(false),
      "operator_reviewed_simulation_evidence",
      { now: () => new Date("2026-07-08T13:46:00Z") },
    );
    expect(prepared.status).toBe("confirming");
    if (prepared.status !== "confirming") {
      throw new Error("expected confirming state");
    }
    expect(prepared.attempt.request).toEqual({
      schema_version: 1,
      expected_workflow_version: 1,
      approval_ticket_id: "workflow-run-001-approval-ticket",
      decision_id: "workflow-run-001-approve-decision",
      decided_at: "2026-07-08T13:46:00.000Z",
      actor: "approver-operator-001",
      decision_reference: "workflow-run-001-approve-manual-review",
      reason: "operator_reviewed_simulation_evidence",
    });
    const response = decidedRun("approved");
    const client = {
      approveSimulationRun: vi.fn().mockResolvedValue(response),
    } as unknown as WorkflowApiClient;

    const result = await executeWorkflowSimulationDecision(client, prepared.attempt);

    expect(result).toEqual({ status: "success", attempt: prepared.attempt, record: response });
    expect(client.approveSimulationRun).toHaveBeenCalledWith(
      "workflow-001",
      "workflow-run-001",
      prepared.attempt.request,
    );
  });

  it("rejects unsafe reasons and runs that are already decided", () => {
    expect(
      prepareWorkflowSimulationDecision(item(), "approve", context(false), "token=private"),
    ).toMatchObject({ status: "validation_blocked" });
    expect(
      workflowSimulationDecisionEligibility(
        item({ status: "approved_not_executed" }),
        context(false),
      ),
    ).toMatchObject({ status: "validation_blocked" });
  });

  it("validates durable rejection and maps fail-closed API states without private details", async () => {
    const prepared = prepareWorkflowSimulationDecision(
      item(),
      "reject",
      context(false),
      "operator_rejected_simulation_evidence",
      { now: () => new Date("2026-07-08T13:46:00Z") },
    );
    if (prepared.status !== "confirming") {
      throw new Error("expected confirming rejection");
    }
    const rejected = decidedRun("rejected");
    const successClient = {
      rejectSimulationRun: vi.fn().mockResolvedValue(rejected),
    } as unknown as WorkflowApiClient;

    expect(await executeWorkflowSimulationDecision(successClient, prepared.attempt)).toEqual({
      status: "success",
      attempt: prepared.attempt,
      record: rejected,
    });

    for (const [status, expected] of [
      [400, "validation_blocked"],
      [403, "authorization_blocked"],
      [409, "conflict"],
      [423, "emergency_stop_blocked"],
      [500, "unavailable"],
    ] as const) {
      const client = {
        rejectSimulationRun: vi
          .fn()
          .mockRejectedValue(new WorkflowApiError("private-value-must-not-render", status)),
      } as unknown as WorkflowApiClient;
      const result = await executeWorkflowSimulationDecision(client, prepared.attempt);

      expect(result.status).toBe(expected);
      expect(JSON.stringify(result)).not.toContain("private-value-must-not-render");
    }
  });
});

function context(emergencyStopActive: boolean) {
  return {
    canApproveSimulation: true,
    emergencyStopActive,
    actor: "approver-operator-001",
  };
}

function item(
  overrides: Partial<WorkflowSimulationRunApiView> = {},
): WorkflowRunInspectionItem {
  return {
    key: "workflow-001::workflow-run-001",
    workflowId: "workflow-001",
    workflowName: "Opening breakout simulation",
    workflowVersion: 1,
    run: {
      schema_version: 1,
      workflow_id: "workflow-001",
      expected_workflow_version: 1,
      run_id: "workflow-run-001",
      status: "waiting_for_approval",
      created_at: "2026-07-08T13:29:55Z",
      updated_at: "2026-07-08T13:45:10Z",
      approval_ticket_id: "workflow-run-001-approval-ticket",
      approval_decision: null,
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
          detail: "Manual approval is required",
          journal_reference: "journal_sequence:2",
        },
        ...["fake_broker", "position_update", "alert"].map((nodeType, index) => ({
          schema_version: 1 as const,
          node_id: nodeType.replace("_", "-"),
          node_type: nodeType,
          status: "blocked_waiting_for_approval",
          detail: "Blocked pending manual approval",
          journal_reference: `journal_sequence:${index + 3}`,
        })),
      ],
      journal_references: ["journal_sequence:2"],
      ...overrides,
    },
  };
}

function decidedRun(decision: "approved" | "rejected"): WorkflowSimulationRunApiView {
  const base = item().run;
  return {
    ...base,
    status: decision === "approved" ? "approved_not_executed" : "rejected",
    updated_at: "2026-07-08T13:46:00.000Z",
    approval_decision: {
      schema_version: 1,
      decision_id: `workflow-run-001-${decision === "approved" ? "approve" : "reject"}-decision`,
      ticket_id: "workflow-run-001-approval-ticket",
      previous_status: "pending",
      new_status: decision,
      decided_at: "2026-07-08T13:46:00.000Z",
      actor: "approver-operator-001",
      decision_reference: `workflow-run-001-${decision === "approved" ? "approve" : "reject"}-manual-review`,
      reason: "operator_reviewed_simulation_evidence",
      request: {},
      ticket: {},
    },
    node_statuses: [
      ...base.node_statuses.map((node) => ({
        ...node,
        status:
          node.node_type === "approval_ticket"
            ? decision === "approved"
              ? "approved_not_executed"
              : "rejected"
            : decision === "approved"
              ? "blocked_pending_explicit_execution"
              : "blocked_rejected",
      })),
    ],
  };
}
