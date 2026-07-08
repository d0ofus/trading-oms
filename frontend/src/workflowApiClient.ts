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
  run_id: string;
  requested_at: string;
  evaluated_at: string;
  approval_expires_at: string;
  replay_input_reference: string;
};

export type WorkflowNodeRunStatusApiView = {
  schema_version: 1;
  node_id: string;
  node_type: string;
  status: string;
  detail: string;
  journal_reference: string;
};

export type WorkflowSimulationRunApiView = {
  schema_version: 1;
  workflow_id: string;
  run_id: string;
  status: "waiting_for_approval" | "completed";
  created_at: string;
  updated_at: string;
  approval_ticket_id: string | null;
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
    request: WorkflowDefinitionSaveRequest,
  ) => Promise<WorkflowDefinitionApiView>;
  startSimulationRun: (
    workflowId: string,
    request: WorkflowSimulationRunRequest,
  ) => Promise<WorkflowSimulationRunApiView>;
};

type WorkflowApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: WorkflowApiFetch;
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
      ),
    getWorkflow: (workflowId) =>
      requestJson<WorkflowDefinitionApiView>(
        fetchImpl,
        buildUrl(baseUrl, workflowPath(workflowId)),
        "GET",
      ),
    createWorkflow: (request) =>
      requestJson<WorkflowDefinitionApiView>(
        fetchImpl,
        buildUrl(baseUrl, WORKFLOW_API_ENDPOINTS.workflows),
        "POST",
        request,
      ),
    updateWorkflow: (workflowId, request) =>
      requestJson<WorkflowDefinitionApiView>(
        fetchImpl,
        buildUrl(baseUrl, workflowPath(workflowId)),
        "PUT",
        request,
      ),
    startSimulationRun: (workflowId, request) =>
      requestJson<WorkflowSimulationRunApiView>(
        fetchImpl,
        buildUrl(baseUrl, `${workflowPath(workflowId)}/simulation-runs`),
        "POST",
        request,
      ),
  };
}

async function requestJson<Payload>(
  fetchImpl: WorkflowApiFetch,
  url: string,
  method: "GET" | "POST" | "PUT",
  body?: unknown,
): Promise<Payload> {
  const response = await fetchImpl(url, {
    method,
    headers:
      body === undefined
        ? { Accept: "application/json" }
        : {
            Accept: "application/json",
            "Content-Type": "application/json",
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

class WorkflowApiError extends Error {
  constructor(path: string, status: number) {
    super(`Workflow API ${path} failed with status ${status}`);
    this.name = "WorkflowApiError";
  }
}
