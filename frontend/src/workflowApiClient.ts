import type { VisualWorkflowDslDocument } from "./visualWorkflowDsl";

export const WORKFLOW_API_ENDPOINTS = {
  workflows: "/api/workflows",
} as const;

export type WorkflowDefinitionSaveRequest = {
  schema_version?: 1;
  workflow_id: string;
  display_name: string;
  description: string;
  requested_at: string;
  document: VisualWorkflowDslDocument;
};

export type WorkflowDefinitionUpdateRequest = WorkflowDefinitionSaveRequest & {
  expected_version: number;
};

export type WorkflowDefinitionApiView = {
  schema_version: 1;
  workflow_id: string;
  display_name: string;
  description: string;
  version: number;
  created_at: string;
  updated_at: string;
  document: VisualWorkflowDslDocument;
};

export type WorkflowSimulationRunRequest = {
  schema_version?: 1;
  expected_workflow_version: number;
  run_id: string;
  requested_at: string;
  evaluated_at: string;
  approval_expires_at: string;
  replay_input_reference: string;
};

export type WorkflowSimulationDecisionRequest = {
  schema_version: 1;
  expected_workflow_version: number;
  approval_ticket_id: string;
  decision_id: string;
  decided_at: string;
  actor: string;
  decision_reference: string;
  reason: string;
};

export type WorkflowSimulationExecutionRequest = {
  schema_version: 1;
  expected_workflow_version: number;
  approval_ticket_id: string;
  approval_decision_id: string;
  order_intent_id: string;
  risk_decision_id: string;
  order_id: string;
  execution_id: string;
  executed_at: string;
  actor: string;
  execution_reference: string;
  reason: string;
  broker_state_known: boolean;
  expected_protection_present: boolean;
};

export type WorkflowSimulationApprovalDecisionApiView = {
  schema_version: 1;
  decision_id: string;
  ticket_id: string;
  previous_status: "pending";
  new_status: "approved" | "rejected";
  decided_at: string;
  actor: string;
  decision_reference: string;
  reason: string;
  request: Record<string, unknown>;
  ticket: Record<string, unknown>;
};

export type WorkflowNodeRunStatusApiView = {
  schema_version: 1;
  node_id: string;
  node_type: string;
  status: string;
  detail: string;
  journal_reference: string;
};

export type WorkflowSimulationExecutionApiView = {
  schema_version: 1;
  workflow_id: string;
  expected_workflow_version: number;
  run_id: string;
  approval_ticket_id: string;
  approval_decision_id: string;
  order_intent_id: string;
  risk_decision_id: string;
  order_id: string;
  execution_id: string;
  executed_at: string;
  actor: string;
  execution_reference: string;
  reason: string;
  broker_state_known: true;
  expected_protection_present: boolean;
  protection_status: "expected_protection_present" | "missing_expected_protection";
  risk_increasing_actions_blocked: boolean;
  oms_transitions: Array<{ new_state: string; [key: string]: unknown }>;
  broker_transitions: Array<{ state: string; [key: string]: unknown }>;
  position: {
    schema_version: 1;
    position_id: string;
    symbol: string;
    quantity: number;
    average_price: number;
    protection_status: "expected_protection_present" | "missing_expected_protection";
    expected_protection_kind: string;
    updated_at: string;
    source_fill_reference: string;
    journal_references: string[];
  };
  alert_intents: Array<{
    alert_id: string;
    channel: string;
    severity: string;
    [key: string]: unknown;
  }>;
  alert_dispatches: Array<{
    alert_id: string;
    channel: string;
    status: string;
    dispatcher: string;
    [key: string]: unknown;
  }>;
  journal_references: string[];
};

export type WorkflowSimulationRunApiView = {
  schema_version: 1;
  workflow_id: string;
  expected_workflow_version: number;
  run_id: string;
  status:
    | "waiting_for_approval"
    | "approved_not_executed"
    | "rejected"
    | "executed"
    | "executed_protection_missing";
  created_at: string;
  updated_at: string;
  approval_ticket_id: string | null;
  approval_decision?: WorkflowSimulationApprovalDecisionApiView | null;
  execution?: WorkflowSimulationExecutionApiView | null;
  simulation_run: {
    schema_version: 1;
    run_id: string;
    status: string;
    created_at: string;
    updated_at: string;
    replay_input_reference: string;
    journal_references: string[];
  };
  node_statuses: WorkflowNodeRunStatusApiView[];
  journal_references: string[];
};

export type WorkflowApiFetch = (input: string, init: RequestInit) => Promise<Response>;

export type WorkflowApiClient = {
  listWorkflows: () => Promise<WorkflowDefinitionApiView[]>;
  getWorkflow: (workflowId: string) => Promise<WorkflowDefinitionApiView>;
  createWorkflow: (request: WorkflowDefinitionSaveRequest) => Promise<WorkflowDefinitionApiView>;
  updateWorkflow: (
    workflowId: string,
    request: WorkflowDefinitionUpdateRequest,
  ) => Promise<WorkflowDefinitionApiView>;
  startSimulationRun: (
    workflowId: string,
    request: WorkflowSimulationRunRequest,
  ) => Promise<WorkflowSimulationRunApiView>;
  listSimulationRuns: (workflowId: string) => Promise<WorkflowSimulationRunApiView[]>;
  getSimulationRun: (
    workflowId: string,
    runId: string,
  ) => Promise<WorkflowSimulationRunApiView>;
  approveSimulationRun: (
    workflowId: string,
    runId: string,
    request: WorkflowSimulationDecisionRequest,
  ) => Promise<WorkflowSimulationRunApiView>;
  rejectSimulationRun: (
    workflowId: string,
    runId: string,
    request: WorkflowSimulationDecisionRequest,
  ) => Promise<WorkflowSimulationRunApiView>;
  executeSimulationRun: (
    workflowId: string,
    runId: string,
    request: WorkflowSimulationExecutionRequest,
  ) => Promise<WorkflowSimulationRunApiView>;
};

type WorkflowApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: WorkflowApiFetch;
  headers?: Record<string, string>;
};

export function createWorkflowApiClient(
  options: WorkflowApiClientOptions = {},
): WorkflowApiClient {
  const fetchImpl = options.fetchImpl ?? defaultFetch;
  const baseUrl = options.baseUrl ?? "";
  const workflowPath = (workflowId: string) =>
    `${WORKFLOW_API_ENDPOINTS.workflows}/${encodeURIComponent(workflowId)}`;

  return {
    listWorkflows: () =>
      requestJson<WorkflowDefinitionApiView[]>(
        fetchImpl,
        buildUrl(baseUrl, WORKFLOW_API_ENDPOINTS.workflows),
        "GET",
        undefined,
        options.headers,
      ),
    getWorkflow: (workflowId) =>
      requestJson<WorkflowDefinitionApiView>(
        fetchImpl,
        buildUrl(baseUrl, workflowPath(workflowId)),
        "GET",
        undefined,
        options.headers,
      ),
    createWorkflow: (request) =>
      requestJson<WorkflowDefinitionApiView>(
        fetchImpl,
        buildUrl(baseUrl, WORKFLOW_API_ENDPOINTS.workflows),
        "POST",
        request,
        options.headers,
      ),
    updateWorkflow: (workflowId, request) =>
      requestJson<WorkflowDefinitionApiView>(
        fetchImpl,
        buildUrl(baseUrl, workflowPath(workflowId)),
        "PUT",
        request,
        options.headers,
      ),
    startSimulationRun: (workflowId, request) =>
      requestJson<WorkflowSimulationRunApiView>(
        fetchImpl,
        buildUrl(baseUrl, `${workflowPath(workflowId)}/simulation-runs`),
        "POST",
        request,
        options.headers,
      ),
    listSimulationRuns: (workflowId) =>
      requestJson<WorkflowSimulationRunApiView[]>(
        fetchImpl,
        buildUrl(baseUrl, `${workflowPath(workflowId)}/simulation-runs`),
        "GET",
        undefined,
        options.headers,
      ),
    getSimulationRun: (workflowId, runId) =>
      requestJson<WorkflowSimulationRunApiView>(
        fetchImpl,
        buildUrl(
          baseUrl,
          `${workflowPath(workflowId)}/simulation-runs/${encodeURIComponent(runId)}`,
        ),
        "GET",
        undefined,
        options.headers,
      ),
    approveSimulationRun: (workflowId, runId, request) =>
      requestJson<WorkflowSimulationRunApiView>(
        fetchImpl,
        buildUrl(
          baseUrl,
          `${workflowPath(workflowId)}/simulation-runs/${encodeURIComponent(runId)}/approve`,
        ),
        "POST",
        request,
        options.headers,
      ),
    rejectSimulationRun: (workflowId, runId, request) =>
      requestJson<WorkflowSimulationRunApiView>(
        fetchImpl,
        buildUrl(
          baseUrl,
          `${workflowPath(workflowId)}/simulation-runs/${encodeURIComponent(runId)}/reject`,
        ),
        "POST",
        request,
        options.headers,
      ),
    executeSimulationRun: (workflowId, runId, request) =>
      requestJson<WorkflowSimulationRunApiView>(
        fetchImpl,
        buildUrl(
          baseUrl,
          `${workflowPath(workflowId)}/simulation-runs/${encodeURIComponent(runId)}/execute`,
        ),
        "POST",
        request,
        options.headers,
      ),
  };
}

async function requestJson<Payload>(
  fetchImpl: WorkflowApiFetch,
  url: string,
  method: "GET" | "POST" | "PUT",
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<Payload> {
  const response = await fetchImpl(url, {
    method,
    headers:
      body === undefined
        ? { Accept: "application/json", ...extraHeaders }
        : {
            Accept: "application/json",
            "Content-Type": "application/json",
            ...extraHeaders,
          },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    throw new WorkflowApiError(url, response.status);
  }

  return (await response.json()) as Payload;
}

function buildUrl(baseUrl: string, path: string) {
  if (!baseUrl) {
    return path;
  }
  return `${baseUrl.replace(/\/+$/, "")}${path}`;
}

async function defaultFetch(input: string, init: RequestInit) {
  return globalThis.fetch(input, init);
}

export class WorkflowApiError extends Error {
  readonly status: number;

  constructor(path: string, status: number) {
    super(`Workflow API ${path} failed with status ${status}`);
    this.name = "WorkflowApiError";
    this.status = status;
  }
}
