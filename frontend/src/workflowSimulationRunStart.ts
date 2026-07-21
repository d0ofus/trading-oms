import {
  WorkflowApiError,
  type WorkflowApiClient,
  type WorkflowDefinitionApiView,
  type WorkflowNodeRunStatusApiView,
  type WorkflowSimulationRunApiView,
  type WorkflowSimulationRunRequest,
} from "./workflowApiClient";

export const LOCAL_SIMULATION_REPLAY_REFERENCE =
  "fixtures/replay/aapl-session.jsonl" as const;

type BlockingStatus =
  | "validation_blocked"
  | "authorization_blocked"
  | "emergency_stop_blocked"
  | "conflict"
  | "unavailable";

export type WorkflowSimulationRunEligibility =
  | { status: "eligible" }
  | { status: BlockingStatus; message: string };

export type WorkflowSimulationRunStartContext = {
  loadedWorkflow: WorkflowDefinitionApiView | null;
  selectedWorkflowId: string | null;
  draftDirty: boolean;
  graphValid: boolean;
  workflowListStatus: "loading" | "loaded" | "unavailable";
  persistenceStatus:
    | "idle"
    | "loading"
    | "saving"
    | "saved"
    | "validation_error"
    | "version_conflict"
    | "unavailable";
  readStateStatus: "loading" | "loaded" | "empty" | "error";
  canAdministerSystem: boolean;
  emergencyStopActive: boolean;
};

export type WorkflowSimulationRunAttempt = {
  workflowId: string;
  workflowVersion: number;
  replayInputReference: typeof LOCAL_SIMULATION_REPLAY_REFERENCE;
  request: WorkflowSimulationRunRequest;
};

type BlockingState = {
  status: BlockingStatus;
  message: string;
  attempt?: WorkflowSimulationRunAttempt;
};

export type WorkflowSimulationRunStartState =
  | { status: "idle" }
  | { status: "confirming"; attempt: WorkflowSimulationRunAttempt }
  | { status: "starting"; attempt: WorkflowSimulationRunAttempt }
  | {
      status: "success";
      attempt: WorkflowSimulationRunAttempt;
      record: WorkflowSimulationRunApiView;
    }
  | BlockingState;

type AttemptFactories = {
  createRunId?: () => string;
  now?: () => Date;
};

const validationBlocked = (message: string): WorkflowSimulationRunEligibility => ({
  status: "validation_blocked",
  message,
});

export function workflowSimulationRunEligibility(
  context: WorkflowSimulationRunStartContext,
): WorkflowSimulationRunEligibility {
  if (context.readStateStatus !== "loaded" || context.workflowListStatus !== "loaded") {
    return { status: "unavailable", message: "Simulation safety state is unavailable" };
  }
  if (context.persistenceStatus === "version_conflict") {
    return { status: "conflict", message: "Saved workflow changed; reload before starting" };
  }
  if (context.persistenceStatus === "unavailable") {
    return { status: "unavailable", message: "Saved workflow state is unavailable" };
  }
  if (context.persistenceStatus === "loading" || context.persistenceStatus === "saving") {
    return { status: "unavailable", message: "Wait for the workflow operation to finish" };
  }
  if (context.persistenceStatus === "validation_error") {
    return validationBlocked("Workflow validation must pass before simulation start");
  }
  if (!context.canAdministerSystem) {
    return {
      status: "authorization_blocked",
      message: "Local admin permission is required",
    };
  }
  if (context.emergencyStopActive) {
    return {
      status: "emergency_stop_blocked",
      message: "Emergency stop blocks simulation start",
    };
  }
  if (
    !context.loadedWorkflow ||
    !context.selectedWorkflowId ||
    context.selectedWorkflowId !== context.loadedWorkflow.workflow_id
  ) {
    return validationBlocked("Load a saved workflow before simulation start");
  }
  if (context.draftDirty) {
    return validationBlocked("Save or discard unsaved changes before simulation start");
  }
  if (!context.graphValid) {
    return validationBlocked("Workflow validation must pass before simulation start");
  }
  if (!positiveInteger(context.loadedWorkflow.version)) {
    return validationBlocked("Saved workflow version is invalid");
  }
  return { status: "eligible" };
}

export function prepareWorkflowSimulationRunStart(
  context: WorkflowSimulationRunStartContext,
  factories: AttemptFactories = {},
): WorkflowSimulationRunStartState {
  const eligibility = workflowSimulationRunEligibility(context);
  if (eligibility.status !== "eligible") {
    return eligibility;
  }

  try {
    const idPart = requireSafeIdPart((factories.createRunId ?? defaultRunId)());
    const now = (factories.now ?? defaultNow)();
    if (!(now instanceof Date) || Number.isNaN(now.getTime())) {
      throw new Error("invalid simulation time");
    }
    const requestedAt = now.toISOString();
    const approvalExpiresAt = new Date(now.getTime() + 5 * 60 * 1000).toISOString();
    const loadedWorkflow = context.loadedWorkflow!;
    const request: WorkflowSimulationRunRequest = {
      schema_version: 1,
      expected_workflow_version: loadedWorkflow.version,
      run_id: `workflow-run-${idPart}`,
      requested_at: requestedAt,
      evaluated_at: requestedAt,
      approval_expires_at: approvalExpiresAt,
      replay_input_reference: LOCAL_SIMULATION_REPLAY_REFERENCE,
    };
    validateAttemptRequest(request);
    return {
      status: "confirming",
      attempt: {
        workflowId: loadedWorkflow.workflow_id,
        workflowVersion: loadedWorkflow.version,
        replayInputReference: LOCAL_SIMULATION_REPLAY_REFERENCE,
        request,
      },
    };
  } catch {
    return {
      status: "validation_blocked",
      message: "A safe simulation request could not be prepared",
    };
  }
}

export async function executeWorkflowSimulationRunStart(
  client: WorkflowApiClient,
  attempt: WorkflowSimulationRunAttempt,
): Promise<WorkflowSimulationRunStartState> {
  try {
    validateAttempt(attempt);
    const response = await client.startSimulationRun(attempt.workflowId, attempt.request);
    return {
      status: "success",
      attempt,
      record: validateWorkflowSimulationRunResponse(response, attempt),
    };
  } catch (error) {
    return mapStartError(error, attempt);
  }
}

export function canRetryWorkflowSimulationRunStart(state: WorkflowSimulationRunStartState) {
  return state.status === "unavailable" && state.attempt !== undefined;
}

function mapStartError(
  error: unknown,
  attempt: WorkflowSimulationRunAttempt,
): WorkflowSimulationRunStartState {
  if (error instanceof WorkflowApiError) {
    if (error.status === 400) {
      return { status: "validation_blocked", message: "Simulation request was rejected", attempt };
    }
    if (error.status === 401 || error.status === 403) {
      return {
        status: "authorization_blocked",
        message: "Local admin permission is required",
        attempt,
      };
    }
    if (error.status === 409) {
      return {
        status: "conflict",
        message: "Saved workflow changed; reload before starting",
        attempt,
      };
    }
    if (error.status === 423) {
      return {
        status: "emergency_stop_blocked",
        message: "Emergency stop blocks simulation start",
        attempt,
      };
    }
  }
  return {
    status: "unavailable",
    message: "Simulation start is unavailable; current workflow was kept",
    attempt,
  };
}

function validateAttempt(attempt: WorkflowSimulationRunAttempt) {
  requireIdentifier(attempt.workflowId, "workflowId");
  if (!positiveInteger(attempt.workflowVersion)) {
    throw new Error("invalid workflow version");
  }
  if (attempt.replayInputReference !== LOCAL_SIMULATION_REPLAY_REFERENCE) {
    throw new Error("invalid replay reference");
  }
  if (attempt.request.expected_workflow_version !== attempt.workflowVersion) {
    throw new Error("workflow version mismatch");
  }
  validateAttemptRequest(attempt.request);
}

function validateAttemptRequest(request: WorkflowSimulationRunRequest) {
  const exact = requireExactObject(request, [
    "schema_version",
    "expected_workflow_version",
    "run_id",
    "requested_at",
    "evaluated_at",
    "approval_expires_at",
    "replay_input_reference",
  ]);
  if (exact.schema_version !== 1 || !positiveInteger(exact.expected_workflow_version)) {
    throw new Error("invalid simulation request schema");
  }
  requireIdentifier(exact.run_id, "run_id");
  const requestedAt = requireTimestamp(exact.requested_at, "requested_at");
  const evaluatedAt = requireTimestamp(exact.evaluated_at, "evaluated_at");
  const approvalExpiresAt = requireTimestamp(exact.approval_expires_at, "approval_expires_at");
  if (evaluatedAt.getTime() !== requestedAt.getTime() || approvalExpiresAt <= evaluatedAt) {
    throw new Error("invalid simulation request timestamps");
  }
  if (exact.replay_input_reference !== LOCAL_SIMULATION_REPLAY_REFERENCE) {
    throw new Error("invalid replay reference");
  }
}

function validateWorkflowSimulationRunResponse(
  value: unknown,
  attempt: WorkflowSimulationRunAttempt,
): WorkflowSimulationRunApiView {
  const record = requireExactObject(value, [
    "schema_version",
    "workflow_id",
    "expected_workflow_version",
    "run_id",
    "status",
    "created_at",
    "updated_at",
    "approval_ticket_id",
    "simulation_run",
    "node_statuses",
    "journal_references",
    "approval_decision",
    "execution",
  ]);
  if (
    record.schema_version !== 1 ||
    record.workflow_id !== attempt.workflowId ||
    record.expected_workflow_version !== attempt.workflowVersion ||
    record.run_id !== attempt.request.run_id ||
    record.status !== "waiting_for_approval" ||
    record.approval_decision !== null ||
    record.execution !== null
  ) {
    throw new Error("simulation response attribution is invalid");
  }
  if (
    requireTimestamp(record.created_at, "created_at").toISOString() !==
      new Date(attempt.request.requested_at).toISOString() ||
    requireTimestamp(record.updated_at, "updated_at").toISOString() !==
      new Date(attempt.request.evaluated_at).toISOString()
  ) {
    throw new Error("simulation response timestamps are invalid");
  }
  const approvalTicketId = requireIdentifier(record.approval_ticket_id, "approval_ticket_id");
  const simulationRun = validateSimulationRun(record.simulation_run, attempt);
  if (!Array.isArray(record.node_statuses) || record.node_statuses.length === 0) {
    throw new Error("simulation node statuses are invalid");
  }
  const nodeStatuses = record.node_statuses.map(validateNodeStatus);
  const nodeIds = new Set(nodeStatuses.map((node) => node.node_id));
  if (nodeIds.size !== nodeStatuses.length) {
    throw new Error("duplicate simulation node status");
  }
  const approvalNode = nodeStatuses.find((node) => node.node_type === "approval_ticket");
  if (!approvalNode || approvalNode.status !== "waiting_for_approval") {
    throw new Error("manual approval wait is missing");
  }
  return {
    schema_version: 1,
    workflow_id: attempt.workflowId,
    expected_workflow_version: attempt.workflowVersion,
    run_id: attempt.request.run_id,
    status: "waiting_for_approval",
    created_at: record.created_at as string,
    updated_at: record.updated_at as string,
    approval_ticket_id: approvalTicketId,
    simulation_run: simulationRun,
    node_statuses: nodeStatuses,
    journal_references: validateJournalReferences(record.journal_references),
    approval_decision: null,
    execution: null,
  };
}

function validateSimulationRun(value: unknown, attempt: WorkflowSimulationRunAttempt) {
  const run = requireExactObject(value, [
    "schema_version",
    "run_id",
    "status",
    "created_at",
    "updated_at",
    "replay_input_reference",
    "journal_references",
  ]);
  if (
    run.schema_version !== 1 ||
    run.run_id !== attempt.request.run_id ||
    run.status !== "completed" ||
    run.replay_input_reference !== attempt.replayInputReference
  ) {
    throw new Error("simulation run response is invalid");
  }
  requireTimestamp(run.created_at, "simulation_run.created_at");
  requireTimestamp(run.updated_at, "simulation_run.updated_at");
  return {
    schema_version: 1 as const,
    run_id: run.run_id as string,
    status: run.status as string,
    created_at: run.created_at as string,
    updated_at: run.updated_at as string,
    replay_input_reference: LOCAL_SIMULATION_REPLAY_REFERENCE,
    journal_references: validateJournalReferences(run.journal_references),
  };
}

function validateNodeStatus(value: unknown): WorkflowNodeRunStatusApiView {
  const node = requireExactObject(value, [
    "schema_version",
    "node_id",
    "node_type",
    "status",
    "detail",
    "journal_reference",
  ]);
  if (node.schema_version !== 1) {
    throw new Error("node status schema is invalid");
  }
  return {
    schema_version: 1,
    node_id: requireIdentifier(node.node_id, "node_id"),
    node_type: requireIdentifier(node.node_type, "node_type"),
    status: requireIdentifier(node.status, "status"),
    detail: requireSafeDetail(node.detail),
    journal_reference: requireJournalReference(node.journal_reference),
  };
}

function validateJournalReferences(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error("journal references are invalid");
  }
  return value.map(requireJournalReference);
}

function requireJournalReference(value: unknown) {
  if (typeof value !== "string" || !/^journal_sequence:\d+$/.test(value)) {
    throw new Error("journal reference is invalid");
  }
  return value;
}

function requireSafeDetail(value: unknown) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error("node detail is invalid");
  }
  const normalized = value.toLowerCase().replaceAll("-", "_");
  for (const token of ["api_key", "credential", "password", "private_key", "secret", "token"]) {
    if (normalized.includes(token)) {
      throw new Error("node detail contains private content");
    }
  }
  return value;
}

function requireExactObject(value: unknown, keys: string[]) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("value must be an object");
  }
  const record = value as Record<string, unknown>;
  if (JSON.stringify(Object.keys(record).sort()) !== JSON.stringify([...keys].sort())) {
    throw new Error("value has an invalid shape");
  }
  return record;
}

function requireIdentifier(value: unknown, field: string) {
  if (
    typeof value !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(value) ||
    value.trim() !== value
  ) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function requireTimestamp(value: unknown, field: string) {
  if (
    typeof value !== "string" ||
    !/(?:Z|[+-]\d\d:\d\d)$/.test(value) ||
    Number.isNaN(Date.parse(value))
  ) {
    throw new Error(`${field} is invalid`);
  }
  return new Date(value);
}

function requireSafeIdPart(value: unknown) {
  if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(value)) {
    throw new Error("run id is invalid");
  }
  return value;
}

function positiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function defaultRunId() {
  return globalThis.crypto.randomUUID();
}

function defaultNow() {
  return new Date();
}
