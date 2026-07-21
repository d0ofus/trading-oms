import {
  WorkflowApiError,
  type WorkflowApiClient,
  type WorkflowSimulationExecutionRequest,
  type WorkflowSimulationRunApiView,
} from "./workflowApiClient";
import type { WorkflowRunInspectionItem } from "./workflowRunInspector";

export type WorkflowSimulationExecutionContext = {
  canAdministerSystem: boolean;
  emergencyStopActive: boolean;
  actor?: string;
};

export type WorkflowSimulationExecutionAttempt = {
  workflowId: string;
  workflowVersion: number;
  runId: string;
  request: WorkflowSimulationExecutionRequest;
};

type BlockedStatus =
  | "validation_blocked"
  | "authorization_blocked"
  | "emergency_stop_blocked"
  | "conflict"
  | "unavailable";

export type WorkflowSimulationExecutionEligibility =
  | { status: "eligible" }
  | { status: "recovered"; message: string }
  | { status: BlockedStatus; message: string };

export type WorkflowSimulationExecutionState =
  | { status: "idle" }
  | { status: "confirming"; attempt: WorkflowSimulationExecutionAttempt }
  | { status: "executing"; attempt: WorkflowSimulationExecutionAttempt }
  | {
      status: "success";
      attempt: WorkflowSimulationExecutionAttempt;
      record: WorkflowSimulationRunApiView;
    }
  | {
      status: BlockedStatus;
      message: string;
      attempt?: WorkflowSimulationExecutionAttempt;
    };

export function workflowSimulationExecutionEligibility(
  selected: WorkflowRunInspectionItem | null,
  context: WorkflowSimulationExecutionContext,
): WorkflowSimulationExecutionEligibility {
  if (!context.canAdministerSystem) {
    return {
      status: "authorization_blocked",
      message: "Simulation operator or admin permission is required",
    };
  }
  if (context.emergencyStopActive) {
    return {
      status: "emergency_stop_blocked",
      message: "Emergency stop blocks simulation execution",
    };
  }
  if (!selected) {
    return {
      status: "validation_blocked",
      message: "Select a saved workflow run",
    };
  }
  if (
    ["executed", "executed_protection_missing"].includes(selected.run.status) &&
    selected.run.execution
  ) {
    return {
      status: "recovered",
      message: "Committed execution evidence recovered from local persistence",
    };
  }
  const decision = selected.run.approval_decision;
  if (
    selected.run.status !== "approved_not_executed" ||
    selected.run.execution ||
    !selected.run.approval_ticket_id ||
    !decision ||
    decision.new_status !== "approved" ||
    decision.ticket_id !== selected.run.approval_ticket_id
  ) {
    return {
      status: "validation_blocked",
      message: "A committed approved_not_executed run is required",
    };
  }
  return { status: "eligible" };
}

export function prepareWorkflowSimulationExecution(
  selected: WorkflowRunInspectionItem | null,
  context: WorkflowSimulationExecutionContext,
  expectedProtectionPresent: boolean,
  factories: { now?: () => Date } = {},
): WorkflowSimulationExecutionState {
  const eligibility = workflowSimulationExecutionEligibility(selected, context);
  if (eligibility.status !== "eligible") {
    return eligibility.status === "recovered"
      ? { status: "validation_blocked", message: eligibility.message }
      : eligibility;
  }
  try {
    const item = selected!;
    const actor = requireIdentifier(context.actor ?? "human-operator-001");
    const runId = requireIdentifier(item.run.run_id);
    const workflowId = requireIdentifier(item.workflowId);
    const workflowVersion = requirePositiveInteger(item.workflowVersion);
    const ticketId = requireIdentifier(item.run.approval_ticket_id);
    const decisionId = requireIdentifier(item.run.approval_decision?.decision_id);
    const now = (factories.now ?? (() => new Date()))();
    if (!(now instanceof Date) || Number.isNaN(now.getTime())) {
      throw new Error("invalid execution time");
    }
    if (typeof expectedProtectionPresent !== "boolean") {
      throw new Error("invalid protection observation");
    }
    return {
      status: "confirming",
      attempt: {
        workflowId,
        workflowVersion,
        runId,
        request: {
          schema_version: 1,
          expected_workflow_version: workflowVersion,
          approval_ticket_id: ticketId,
          approval_decision_id: decisionId,
          order_intent_id: `${runId}-intent`,
          risk_decision_id: `${runId}-risk`,
          order_id: `${runId}-order`,
          execution_id: `${runId}-execution`,
          executed_at: now.toISOString(),
          actor,
          execution_reference: `${runId}-admin-execution-review`,
          reason: "operator_confirmed_simulation_execution",
          broker_state_known: true,
          expected_protection_present: expectedProtectionPresent,
        },
      },
    };
  } catch {
    return {
      status: "validation_blocked",
      message: "Exact approved simulation evidence could not be prepared",
    };
  }
}

export async function executeWorkflowSimulationExecution(
  client: WorkflowApiClient,
  attempt: WorkflowSimulationExecutionAttempt,
): Promise<WorkflowSimulationExecutionState> {
  try {
    validateAttempt(attempt);
    const response = await client.executeSimulationRun(
      attempt.workflowId,
      attempt.runId,
      attempt.request,
    );
    validateExecutionResponse(response, attempt);
    return { status: "success", attempt, record: response };
  } catch (error) {
    return mapExecutionError(error, attempt);
  }
}

export function canRetryWorkflowSimulationExecution(
  state: WorkflowSimulationExecutionState,
) {
  return state.status === "unavailable" && Boolean(state.attempt);
}

function validateAttempt(attempt: WorkflowSimulationExecutionAttempt) {
  const request = attempt.request;
  if (
    requireIdentifier(attempt.workflowId) !== attempt.workflowId ||
    requireIdentifier(attempt.runId) !== attempt.runId ||
    requirePositiveInteger(attempt.workflowVersion) !== request.expected_workflow_version ||
    request.schema_version !== 1 ||
    request.approval_ticket_id.length === 0 ||
    request.approval_decision_id.length === 0 ||
    request.order_intent_id !== `${attempt.runId}-intent` ||
    request.risk_decision_id !== `${attempt.runId}-risk` ||
    request.order_id !== `${attempt.runId}-order` ||
    request.execution_id !== `${attempt.runId}-execution` ||
    request.broker_state_known !== true ||
    typeof request.expected_protection_present !== "boolean"
  ) {
    throw new Error("execution attempt is invalid");
  }
  requireIdentifier(request.actor);
  requireIdentifier(request.approval_ticket_id);
  requireIdentifier(request.approval_decision_id);
  requireIdentifier(request.execution_reference);
  if (Number.isNaN(Date.parse(request.executed_at))) {
    throw new Error("execution timestamp is invalid");
  }
}

function validateExecutionResponse(
  response: WorkflowSimulationRunApiView,
  attempt: WorkflowSimulationExecutionAttempt,
) {
  const request = attempt.request;
  const execution = response.execution;
  const expectedProtectionStatus = request.expected_protection_present
    ? "expected_protection_present"
    : "missing_expected_protection";
  const expectedRunStatus = request.expected_protection_present
    ? "executed"
    : "executed_protection_missing";
  if (
    response.schema_version !== 1 ||
    response.workflow_id !== attempt.workflowId ||
    response.expected_workflow_version !== attempt.workflowVersion ||
    response.run_id !== attempt.runId ||
    response.status !== expectedRunStatus ||
    response.updated_at !== request.executed_at ||
    response.approval_ticket_id !== request.approval_ticket_id ||
    response.approval_decision?.decision_id !== request.approval_decision_id ||
    response.approval_decision.new_status !== "approved" ||
    !execution ||
    execution.workflow_id !== attempt.workflowId ||
    execution.expected_workflow_version !== attempt.workflowVersion ||
    execution.run_id !== attempt.runId ||
    execution.approval_ticket_id !== request.approval_ticket_id ||
    execution.approval_decision_id !== request.approval_decision_id ||
    execution.order_intent_id !== request.order_intent_id ||
    execution.risk_decision_id !== request.risk_decision_id ||
    execution.order_id !== request.order_id ||
    execution.execution_id !== request.execution_id ||
    execution.executed_at !== request.executed_at ||
    execution.actor !== request.actor ||
    execution.execution_reference !== request.execution_reference ||
    execution.broker_state_known !== true ||
    execution.expected_protection_present !== request.expected_protection_present ||
    execution.protection_status !== expectedProtectionStatus ||
    execution.risk_increasing_actions_blocked !== !request.expected_protection_present ||
    execution.position.protection_status !== expectedProtectionStatus ||
    execution.journal_references.length === 0
  ) {
    throw new Error("workflow simulation execution response is invalid");
  }
  if (
    execution.oms_transitions.map((item) => item.new_state).join(",") !==
      "APPROVED,SUBMITTED,ACKNOWLEDGED,FILLED" ||
    execution.broker_transitions.map((item) => item.state).join(",") !==
      "acknowledged,filled" ||
    execution.alert_intents.length !== 1 ||
    execution.alert_intents[0].channel !== "local" ||
    execution.alert_intents[0].severity !==
      (request.expected_protection_present ? "informational" : "critical") ||
    execution.alert_dispatches.length !== 1 ||
    execution.alert_dispatches[0].channel !== "local" ||
    execution.alert_dispatches[0].status !== "recorded" ||
    execution.alert_dispatches[0].dispatcher !== "noop"
  ) {
    throw new Error("workflow simulation execution domain evidence is invalid");
  }
  const requiredNodeStates = new Map([
    ["approval_ticket", "approved_consumed"],
    ["fake_broker", "filled"],
    [
      "position_update",
      request.expected_protection_present ? "completed" : "critical_missing_protection",
    ],
    [
      "alert",
      request.expected_protection_present ? "completed_local_noop" : "critical_local_noop",
    ],
    ["audit_sink", "completed"],
  ]);
  for (const [nodeType, status] of requiredNodeStates) {
    if (!response.node_statuses.some((node) => node.node_type === nodeType && node.status === status)) {
      throw new Error("workflow simulation execution node evidence is invalid");
    }
  }
}

function mapExecutionError(
  error: unknown,
  attempt: WorkflowSimulationExecutionAttempt,
): WorkflowSimulationExecutionState {
  if (error instanceof WorkflowApiError) {
    if (error.status === 400) {
      return {
        status: "validation_blocked",
        message: "Simulation execution evidence was rejected",
        attempt,
      };
    }
    if (error.status === 401 || error.status === 403) {
      return {
        status: "authorization_blocked",
        message: "Simulation operator or admin permission is required",
        attempt,
      };
    }
    if (error.status === 409) {
      return {
        status: "conflict",
        message: "Execution state changed; reload before continuing",
        attempt,
      };
    }
    if (error.status === 423) {
      return {
        status: "emergency_stop_blocked",
        message: "Emergency stop blocks simulation execution",
        attempt,
      };
    }
  }
  return {
    status: "unavailable",
    message: "Execution result is unavailable; durable evidence must be reloaded",
    attempt,
  };
}

function requireIdentifier(value: unknown): string {
  if (
    typeof value !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(value) ||
    value.trim() !== value
  ) {
    throw new Error("identifier is invalid");
  }
  return value;
}

function requirePositiveInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
    throw new Error("version is invalid");
  }
  return value;
}
