import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WorkflowSimulationApprovalPanel } from "./WorkflowSimulationApprovalPanel";
import type { WorkflowSimulationDecisionState } from "./workflowSimulationApproval";
import type { WorkflowRunInspectionItem } from "./workflowRunInspector";

describe("WorkflowSimulationApprovalPanel", () => {
  it("shows bounded review commands only for an eligible pending run", () => {
    const text = renderedText(renderPanel({ status: "idle" }, false));

    expect(text).toContain("SIMULATION ONLY");
    expect(text).toContain("workflow-001");
    expect(text).toContain("workflow-run-001");
    expect(text).toContain("workflow-run-001-approval-ticket");
    expect(text).toContain("Review approval");
    expect(text).toContain("Review rejection");
    expect(text).not.toContain("Transmit");
    expect(text).not.toContain("Connect broker");
  });

  it("requires a second confirmation and states that execution does not occur", () => {
    const state: WorkflowSimulationDecisionState = {
      status: "confirming",
      attempt: {
        action: "approve",
        workflowId: "workflow-001",
        workflowVersion: 1,
        runId: "workflow-run-001",
        approvalTicketId: "workflow-run-001-approval-ticket",
        request: {
          schema_version: 1,
          expected_workflow_version: 1,
          approval_ticket_id: "workflow-run-001-approval-ticket",
          decision_id: "workflow-run-001-approve-decision",
          decided_at: "2026-07-08T13:46:00.000Z",
          actor: "approver-operator-001",
          decision_reference: "workflow-run-001-approve-manual-review",
          reason: "operator_reviewed_simulation_evidence",
        },
      },
    };

    const unchecked = renderPanel(state, false);
    const checked = renderPanel(state, true);

    expect(renderedText(unchecked)).toContain("No OMS or fake-broker execution occurs");
    expect(renderedText(unchecked)).toContain("I confirm this manual simulation decision");
    expect(unchecked).toContain('disabled=""');
    expect(checked).not.toContain('disabled=""');
  });

  it("renders fail-closed permission posture without decision commands", () => {
    const html = renderToStaticMarkup(
      <WorkflowSimulationApprovalPanel
        confirmed={false}
        eligibility={{
          status: "authorization_blocked",
          message: "Dedicated approver permission is required",
        }}
        onCancel={() => undefined}
        onConfirm={() => undefined}
        onConfirmationChange={() => undefined}
        onReasonChange={() => undefined}
        onReview={() => undefined}
        reason="operator_reviewed_simulation_evidence"
        selected={pendingRun}
        state={{ status: "idle" }}
      />,
    );
    const text = renderedText(html);

    expect(text).toContain("Dedicated approver permission is required");
    expect(text).not.toContain("Review approval");
    expect(text).not.toContain("Review rejection");
  });

  it.each([
    [{ status: "deciding", attempt: approvalAttempt }, "Recording durable simulation decision"],
    [
      { status: "success", attempt: rejectionAttempt, record: rejectedRun },
      "Simulation rejected",
    ],
    [
      { status: "conflict", message: "Run approval state changed", attempt: approvalAttempt },
      "Run approval state changed",
    ],
    [
      {
        status: "emergency_stop_blocked",
        message: "Emergency stop blocks simulation approval",
        attempt: approvalAttempt,
      },
      "Emergency stop blocks simulation approval",
    ],
    [
      {
        status: "unavailable",
        message: "Simulation decision is unavailable",
        attempt: approvalAttempt,
      },
      "Simulation decision is unavailable",
    ],
  ] as [WorkflowSimulationDecisionState, string][])(
    "renders bounded decision state %#",
    (state, expected) => {
      expect(renderedText(renderPanel(state, false))).toContain(expected);
    },
  );
});

function renderPanel(state: WorkflowSimulationDecisionState, confirmed: boolean) {
  return renderToStaticMarkup(
    <WorkflowSimulationApprovalPanel
      confirmed={confirmed}
      eligibility={{ status: "eligible" }}
      onCancel={() => undefined}
      onConfirm={() => undefined}
      onConfirmationChange={() => undefined}
      onReasonChange={() => undefined}
      onReview={() => undefined}
      reason="operator_reviewed_simulation_evidence"
      selected={pendingRun}
      state={state}
    />,
  );
}

const pendingRun: WorkflowRunInspectionItem = {
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
    node_statuses: [],
    journal_references: ["journal_sequence:2"],
  },
};

const approvalAttempt = {
  action: "approve" as const,
  workflowId: "workflow-001",
  workflowVersion: 1,
  runId: "workflow-run-001",
  approvalTicketId: "workflow-run-001-approval-ticket",
  request: {
    schema_version: 1 as const,
    expected_workflow_version: 1,
    approval_ticket_id: "workflow-run-001-approval-ticket",
    decision_id: "workflow-run-001-approve-decision",
    decided_at: "2026-07-08T13:46:00.000Z",
    actor: "approver-operator-001",
    decision_reference: "workflow-run-001-approve-manual-review",
    reason: "operator_reviewed_simulation_evidence",
  },
};

const rejectionAttempt = {
  ...approvalAttempt,
  action: "reject" as const,
  request: {
    ...approvalAttempt.request,
    decision_id: "workflow-run-001-reject-decision",
    decision_reference: "workflow-run-001-reject-manual-review",
  },
};

const rejectedRun = {
  ...pendingRun.run,
  status: "rejected" as const,
  approval_decision: {
    schema_version: 1 as const,
    decision_id: rejectionAttempt.request.decision_id,
    ticket_id: rejectionAttempt.approvalTicketId,
    previous_status: "pending",
    new_status: "rejected",
    decided_at: rejectionAttempt.request.decided_at,
    actor: rejectionAttempt.request.actor,
    decision_reference: rejectionAttempt.request.decision_reference,
    reason: rejectionAttempt.request.reason,
    request: {},
    ticket: {},
  },
};

function renderedText(html: string) {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}
