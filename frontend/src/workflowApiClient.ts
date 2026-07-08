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

export type WorkflowApiFetch = (input: string, init: RequestInit) => Promise<Response>;

export type WorkflowApiClient = {
  listWorkflows: () => Promise<WorkflowDefinitionApiView[]>;
  getWorkflow: (workflowId: string) => Promise<WorkflowDefinitionApiView>;
  createWorkflow: (request: WorkflowDefinitionSaveRequest) => Promise<WorkflowDefinitionApiView>;
  updateWorkflow: (
    workflowId: string,
    request: WorkflowDefinitionSaveRequest,
  ) => Promise<WorkflowDefinitionApiView>;
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
