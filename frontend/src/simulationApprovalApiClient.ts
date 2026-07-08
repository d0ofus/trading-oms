import type { ApprovalDecisionRequest } from "./approvalInbox";

export type SimulationApprovalDecisionApiView = {
  schema_version: 1;
  decision_id: string;
  new_status: "approved" | "rejected";
};

export type SimulationApprovalApiFetch = (
  input: string,
  init: RequestInit,
) => Promise<Response>;

export type SimulationApprovalApiClient = {
  approveTicket: (
    ticketId: string,
    request: ApprovalDecisionRequest,
  ) => Promise<SimulationApprovalDecisionApiView>;
  rejectTicket: (
    ticketId: string,
    request: ApprovalDecisionRequest,
  ) => Promise<SimulationApprovalDecisionApiView>;
};

type SimulationApprovalApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: SimulationApprovalApiFetch;
};

export function createSimulationApprovalApiClient(
  options: SimulationApprovalApiClientOptions = {},
): SimulationApprovalApiClient {
  const fetchImpl = options.fetchImpl ?? defaultFetch;
  const baseUrl = options.baseUrl ?? "";
  const ticketPath = (ticketId: string, action: "approve" | "reject") =>
    `/api/approval-tickets/${encodeURIComponent(ticketId)}/${action}`;

  return {
    approveTicket: (ticketId, request) =>
      requestJson(fetchImpl, buildUrl(baseUrl, ticketPath(ticketId, "approve")), request),
    rejectTicket: (ticketId, request) =>
      requestJson(fetchImpl, buildUrl(baseUrl, ticketPath(ticketId, "reject")), request),
  };
}

async function requestJson(
  fetchImpl: SimulationApprovalApiFetch,
  url: string,
  body: ApprovalDecisionRequest,
): Promise<SimulationApprovalDecisionApiView> {
  const response = await fetchImpl(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new SimulationApprovalApiError(url, response.status);
  }

  return (await response.json()) as SimulationApprovalDecisionApiView;
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

class SimulationApprovalApiError extends Error {
  constructor(endpointPath: string, status: number) {
    super(`Simulation approval API ${endpointPath} failed with status ${status}`);
    this.name = "SimulationApprovalApiError";
  }
}
