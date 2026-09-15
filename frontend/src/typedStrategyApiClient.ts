import type { VisualWorkflowDslV2Document } from "./typedWorkflowDsl";

export const WORKFLOW_API_ENDPOINTS = {
  workflows: "/api/typed-workflows",
  workflowNodeCatalog: "/api/typed-workflows/catalog",
  datasets: "/api/strategy-datasets",
  runs: "/api/strategy-runs",
  riskPolicy: "/api/strategy-risk-policy",
} as const;

export type WorkflowDefinitionSaveRequest = {
  schema_version?: 2;
  expected_version?: number;
  workflow_id: string;
  display_name: string;
  description: string;
  requested_at: string;
  document: VisualWorkflowDslV2Document;
};

export type WorkflowDefinitionApiView = {
  schema_version: 2;
  workflow_id: string;
  display_name: string;
  description: string;
  version: number;
  created_at: string;
  updated_at: string;
  document: VisualWorkflowDslV2Document;
  checksum?: string;
};

export type StrategyRunDraftRequest = {
  run_id: string;
  workflow_version: number;
  symbol: string;
  maximum_dollar_loss: string;
  runtime_mode: "historical_simulation" | "live_simulation";
  dataset_id: string;
  expires_at: string;
  requested_at: string;
};

export type MarketDataDatasetRegistrationRequest = {
  dataset_id: string;
  symbol: string;
  contract_id: string;
  primary_exchange: string;
  currency: "USD";
  routing: "SMART";
  min_tick: string;
  session_date: string;
  session_timezone: string;
  rth_open: string;
  rth_close: string;
  source: "local_fixture" | "ibkr_historical" | "live_forward_capture";
  resolution: "trade_ticks" | "five_second_bars";
  complete: boolean;
  quality: "complete" | "gap_detected" | "out_of_order" | "degraded";
  registered_at: string;
  trades: { timestamp: string; price: string; sequence: number; source?: "last_trade" }[];
};

export type MarketDataDatasetApiView = {
  schema_version: 2;
  dataset_id: string;
  symbol: string;
  contract: {
    contract_id: string;
    primary_exchange: string;
    currency: string;
    routing: string;
    min_tick: string;
  };
  session: { date: string; timezone: string; rth_open: string; rth_close: string };
  source: string;
  resolution: string;
  complete: boolean;
  quality: string;
  checksum: string;
  manifest_checksum: string;
  trade_count: number;
  start_at: string;
  end_at: string;
  simulated_data_only: true;
};

export type RiskPolicyApiView = {
  version_id: string;
  max_dollar_risk: string;
  max_shares: number;
  max_notional: string;
  max_concurrent_positions: number;
  max_symbol_exposure: string;
  max_daily_loss: string;
  admin_slippage_allowance: string;
  chase_threshold: string;
  max_data_age_seconds: number;
  mutable_through_run_request: false;
};

export type StrategyRunApiView = {
  schema_version: 2;
  run_id: string;
  state: "draft" | "armed" | "disarmed" | "blocked" | "completed";
  fingerprint: string;
  envelope: {
    workflow_id: string;
    workflow_version: number;
    symbol: string;
    maximum_dollar_loss: string;
    runtime_mode: "historical_simulation" | "live_simulation";
    dataset_id: string;
    contract_id: string;
    primary_exchange: string;
    currency: string;
    routing: string;
    min_tick: string;
    session_date: string;
    session_timezone: string;
    rth_open: string;
    rth_close: string;
    opening_range_minutes: number;
    entry_lifetime: "DAY" | "GTC";
    position_lifetime: Record<string, string>;
    risk_policy_version: string;
  };
  authorization: null | {
    fingerprint: string;
    authorized_at: string;
    expires_at: string;
    authorized_by: string;
  };
  result: null | {
    status: string;
    opening_range_high: string | null;
    trigger_threshold: string | null;
    trigger_price: string | null;
    frozen_day_low: string | null;
    conservative_entry: string | null;
    per_share_risk: string | null;
    shares: string | null;
    entry_fill_price: string | null;
    protective_stop_price: string | null;
    protection_state: string;
    simulated: true;
  };
  disarm_reason: string | null;
  journal_references: string[];
  execution_target: "fake_broker";
  simulated: true;
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
  validateWorkflow: (
    workflowId: string,
    document: VisualWorkflowDslV2Document,
  ) => Promise<{ status: "valid"; checksum: string; errors: [] }>;
  listWorkflowVersions: (workflowId: string) => Promise<WorkflowDefinitionApiView[]>;
  registerDataset: (
    request: MarketDataDatasetRegistrationRequest,
  ) => Promise<MarketDataDatasetApiView>;
  getDataset: (datasetId: string) => Promise<MarketDataDatasetApiView>;
  getRiskPolicy: () => Promise<RiskPolicyApiView>;
  createStrategyRun: (
    workflowId: string,
    request: StrategyRunDraftRequest,
  ) => Promise<StrategyRunApiView>;
  armStrategyRun: (
    runId: string,
    request: { authorized_at: string; expires_at: string },
  ) => Promise<StrategyRunApiView>;
  disarmStrategyRun: (
    runId: string,
    request: { disarmed_at: string; reason: string },
  ) => Promise<StrategyRunApiView>;
  simulateStrategyRun: (
    runId: string,
    request: {
      buying_power: string;
      concurrent_positions: number;
      current_symbol_exposure: string;
      daily_realized_loss: string;
      reconciled: boolean;
      evaluated_at?: string;
    },
  ) => Promise<StrategyRunApiView>;
  getStrategyRun: (runId: string) => Promise<StrategyRunApiView>;
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
    validateWorkflow: (workflowId, document) =>
      requestJson<{ status: "valid"; checksum: string; errors: [] }>(
        fetchImpl,
        buildUrl(baseUrl, `${workflowPath(workflowId)}/validate`),
        "POST",
        { document },
      ),
    listWorkflowVersions: (workflowId) =>
      requestJson<WorkflowDefinitionApiView[]>(
        fetchImpl,
        buildUrl(baseUrl, `${workflowPath(workflowId)}/versions`),
        "GET",
      ),
    registerDataset: (request) =>
      requestJson<MarketDataDatasetApiView>(
        fetchImpl,
        buildUrl(baseUrl, WORKFLOW_API_ENDPOINTS.datasets),
        "POST",
        request,
      ),
    getDataset: (datasetId) =>
      requestJson<MarketDataDatasetApiView>(
        fetchImpl,
        buildUrl(
          baseUrl,
          `${WORKFLOW_API_ENDPOINTS.datasets}/${encodeURIComponent(datasetId)}`,
        ),
        "GET",
      ),
    getRiskPolicy: () =>
      requestJson<RiskPolicyApiView>(
        fetchImpl,
        buildUrl(baseUrl, WORKFLOW_API_ENDPOINTS.riskPolicy),
        "GET",
      ),
    createStrategyRun: (workflowId, request) =>
      requestJson<StrategyRunApiView>(
        fetchImpl,
        buildUrl(baseUrl, `${workflowPath(workflowId)}/runs`),
        "POST",
        request,
      ),
    armStrategyRun: (runId, request) =>
      requestJson<StrategyRunApiView>(
        fetchImpl,
        buildUrl(baseUrl, `${WORKFLOW_API_ENDPOINTS.runs}/${encodeURIComponent(runId)}/arm`),
        "POST",
        request,
      ),
    disarmStrategyRun: (runId, request) =>
      requestJson<StrategyRunApiView>(
        fetchImpl,
        buildUrl(baseUrl, `${WORKFLOW_API_ENDPOINTS.runs}/${encodeURIComponent(runId)}/disarm`),
        "POST",
        request,
      ),
    simulateStrategyRun: (runId, request) =>
      requestJson<StrategyRunApiView>(
        fetchImpl,
        buildUrl(baseUrl, `${WORKFLOW_API_ENDPOINTS.runs}/${encodeURIComponent(runId)}/simulate`),
        "POST",
        request,
      ),
    getStrategyRun: (runId) =>
      requestJson<StrategyRunApiView>(
        fetchImpl,
        buildUrl(baseUrl, `${WORKFLOW_API_ENDPOINTS.runs}/${encodeURIComponent(runId)}`),
        "GET",
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
