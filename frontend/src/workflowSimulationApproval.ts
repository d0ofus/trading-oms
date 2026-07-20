import {
  WorkflowApiError,
  type WorkflowApiClient,
  type WorkflowSimulationDecisionRequest,
  type WorkflowSimulationRunApiView,
} from "./workflowApiClient";
import type { WorkflowRunInspectionItem } from "./workflowRunInspector";

export type WorkflowSimulationDecisionAction = "approve" | "reject";

export type WorkflowSimulationDecisionContext = {
  canApproveSimulation: boolean;
  emergencyStopActive: boolean;
  actor?: string;
};

export type WorkflowSimulationDecisionAttempt = {
  action: WorkflowSimulationDecisionAction;
  workflowId: string;
  workflowVersion: number;
  runId: string;
  approvalTicketId: string;
  request: WorkflowSimulationDecisionRequest;
};

type BlockedStatus =
  | "validation_blocked"
  | "authorization_blocked"
  | "emergency_stop_blocked"
  | "conflict"
  | "unavailable";

export type WorkflowSimulationDecisionEligibility =
  | { status: "eligible" }
  | { status: BlockedStatus; message: string };

export type WorkflowSimulationDecisionState =
  | { status: "idle" }
  | { status: "confirming"; attempt: WorkflowSimulationDecisionAttempt }
  | { status: "deciding"; attempt: WorkflowSimulationDecisionAttempt }
  | {
      status: "success";
      attempt: WorkflowSimulationDecisionAttempt;
      record: WorkflowSimulationRunApiView;
    }
  | {
      status: BlockedStatus;
      message: string;
      attempt?: WorkflowSimulationDecisionAttempt;
    };

export function workflowSimulationDecisionEligibility(
  selected: WorkflowRunInspectionItem | null,
  context: WorkflowSimulationDecisionContext,
): WorkflowSimulationDecisionEligibility {
  if (!context.canApproveSimulation) {
    return {
      status: "authorization_blocked",
      message: "Dedicated approver permission is required",
    };
  }
  if (!selected || selected.run.status !== "waiting_for_approval") {
    return {
      status: "validation_blocked",
      message: "Select a saved workflow run waiting for manual approval",
    };
  }
  if (!selected.run.approval_ticket_id || selected.run.approval_decision) {
    return {
      status: "validation_blocked",
      message: "Selected run approval evidence is invalid",
    };
  }
  return { status: "eligible" };
}

export function prepareWorkflowSimulationDecision(
  selected: WorkflowRunInspectionItem | null,
  action: WorkflowSimulationDecisionAction,
  context: WorkflowSimulationDecisionContext,
  reason: string,
  factories: { now?: () => Date } = {},
): WorkflowSimulationDecisionState {
  const eligibility = workflowSimulationDecisionEligibility(selected, context);
  if (eligibility.status !== "eligible") {
    return eligibility;
  }
  if (action === "approve" && context.emergencyStopActive) {
    return {
      status: "emergency_stop_blocked",
      message: "Emergency stop blocks simulation approval",
    };
  }
  try {
    const actor = requireIdentifier(context.actor ?? "approver-operator-001");
    const safeReason = requireSafeReason(reason);
    const now = (factories.now ?? (() => new Date()))();
    if (!(now instanceof Date) || Number.isNaN(now.getTime())) {
      throw new Error("invalid decision time");
    }
    const item = selected!;
    const ticketId = requireIdentifier(item.run.approval_ticket_id);
    const actionWord = action === "approve" ? "approve" : "reject";
    return {
      status: "confirming",
      attempt: {
        action,
        workflowId: requireIdentifier(item.workflowId),
        workflowVersion: requirePositiveInteger(item.workflowVersion),
        runId: requireIdentifier(item.run.run_id),
        approvalTicketId: ticketId,
        request: {
          schema_version: 1,
          expected_workflow_version: item.workflowVersion,
          approval_ticket_id: ticketId,
          decision_id: `${item.run.run_id}-${actionWord}-decision`,
          decided_at: now.toISOString(),
          actor,
          decision_reference: `${item.run.run_id}-${actionWord}-manual-review`,
          reason: safeReason,
        },
      },
    };
  } catch {
    return {
      status: "validation_blocked",
      message: "A safe simulation decision could not be prepared",
    };
  }
}

export async function executeWorkflowSimulationDecision(
  client: WorkflowApiClient,
  attempt: WorkflowSimulationDecisionAttempt,
): Promise<WorkflowSimulationDecisionState> {
  try {
    const response =
      attempt.action === "approve"
        ? await client.approveSimulationRun(
            attempt.workflowId,
            attempt.runId,
            attempt.request,
          )
        : await client.rejectSimulationRun(
            attempt.workflowId,
            attempt.runId,
            attempt.request,
          );
    validateDecisionResponse(response, attempt);
    return { status: "success", attempt, record: response };
  } catch (error) {
    return mapDecisionError(error, attempt);
  }
}

function validateDecisionResponse(
  response: WorkflowSimulationRunApiView,
  attempt: WorkflowSimulationDecisionAttempt,
) {
  const expectedStatus =
    attempt.action === "approve" ? "approved_not_executed" : "rejected";
  const expectedDecision = attempt.action === "approve" ? "approved" : "rejected";
  if (
    response.schema_version !== 1 ||
    response.workflow_id !== attempt.workflowId ||
    response.run_id !== attempt.runId ||
    response.status !== expectedStatus ||
    response.approval_ticket_id !== attempt.approvalTicketId ||
    response.approval_decision?.decision_id !== attempt.request.decision_id ||
    response.approval_decision.ticket_id !== attempt.approvalTicketId ||
    response.approval_decision.new_status !== expectedDecision ||
    response.approval_decision.actor !== attempt.request.actor ||
    response.approval_decision.decided_at !== attempt.request.decided_at
  ) {
    throw new Error("workflow simulation decision response is invalid");
  }
  const approvalNode = response.node_statuses.find(
    (node) => node.node_type === "approval_ticket",
  );
  if (!approvalNode || approvalNode.status !== expectedStatus) {
    throw new Error("workflow simulation decision node evidence is invalid");
  }
  const downstreamStatuses = response.node_statuses
    .filter((node) => ["fake_broker", "position_update", "alert"].includes(node.node_type))
    .map((node) => node.status);
  const expectedDownstream =
    attempt.action === "approve"
      ? "blocked_pending_explicit_execution"
      : "blocked_rejected";
  if (
    downstreamStatuses.length !== 3 ||
    downstreamStatuses.some((status) => status !== expectedDownstream)
  ) {
    throw new Error("downstream simulation nodes are not safely blocked");
  }
}

function mapDecisionError(
  error: unknown,
  attempt: WorkflowSimulationDecisionAttempt,
): WorkflowSimulationDecisionState {
  if (error instanceof WorkflowApiError) {
    if (error.status === 400) {
      return {
        status: "validation_blocked",
        message: "Simulation decision was rejected",
        attempt,
      };
    }
    if (error.status === 401 || error.status === 403) {
      return {
        status: "authorization_blocked",
        message: "Dedicated approver permission is required",
        attempt,
      };
    }
    if (error.status === 409) {
      return {
        status: "conflict",
        message: "Run approval state changed; reload before deciding",
        attempt,
      };
    }
    if (error.status === 423) {
      return {
        status: "emergency_stop_blocked",
        message: "Emergency stop blocks simulation approval",
        attempt,
      };
    }
  }
  return {
    status: "unavailable",
    message: "Simulation decision is unavailable; no local success was assumed",
    attempt,
  };
}

function requireIdentifier(value: unknown) {
  if (
    typeof value !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(value) ||
    value.trim() !== value
  ) {
    throw new Error("identifier is invalid");
  }
  return value;
}

function requirePositiveInteger(value: unknown) {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
    throw new Error("version is invalid");
  }
  return value;
}

function requireSafeReason(value: string) {
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > 240) {
    throw new Error("reason is invalid");
  }
  const normalized = trimmed.toLowerCase().replaceAll("-", "_");
  if (
    [
      "api_key",
      "authorization:",
      "bearer ",
      "credential",
      "password",
      "private_key",
      "secret",
      "token",
    ].some((fragment) => normalized.includes(fragment))
  ) {
    throw new Error("reason contains unsafe text");
  }
  return trimmed;
}
