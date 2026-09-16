export type Json =
  string | number | boolean | null | Json[] | { [key: string]: Json };
export type Block = {
  id: string;
  kind: string;
  label?: string;
  params: Record<string, string | number>;
  position?: { x: number; y: number };
};
export type Graph = {
  schema_version: number;
  settings: Record<string, string | number>;
  nodes: Block[];
  edges: { source: string; target: string; input: string }[];
};
export type Draft = {
  id: string;
  name: string;
  document: Graph;
  revision: number;
  published_version: number;
  updated_at: string;
};
export type Explanation = { node: string; kind: string; text: string };
export type Version = {
  strategy_id: string;
  name: string;
  version: number;
  hash: string;
  document: Graph;
  explanation: Explanation[];
  published_at: string;
};
export type Spec = {
  kind: string;
  label: string;
  group: string;
  inputs: Record<string, string>;
  output: string;
  defaults: Record<string, string | number>;
  fields?: string[];
  choices?: string[];
};
export type Template = {
  id: string;
  name: string;
  description: string;
  document: Graph;
};
export type Issue = {
  code: string;
  message: string;
  node?: string;
  field?: string;
  remediation?: string;
};
export type Check = {
  code: string;
  title: string;
  passed: boolean;
  detail: string;
  remediation: string;
};
export type Run = {
  id: string;
  name: string;
  version: number;
  strategy_id: string;
  symbol: string;
  conid: number;
  state: string;
  armed: boolean;
  position: string;
  protected: boolean;
  risk: string;
  last_signal?: string;
  blocking_reason?: string;
  expires_at?: string;
};
export type Order = {
  id: string;
  run_id: string;
  state: string;
  broker_id: number;
  created_at: string;
  payload: {
    purpose?: string;
    symbol: string;
    quantity: number;
    limit: string;
    stop?: string;
    target?: string;
  };
};
export type Position = {
  run_id: string;
  symbol: string;
  quantity: string;
  cash: string;
  conid: number;
};
export type DataState = {
  conid: number;
  symbol: string;
  live: boolean;
  warm: boolean;
  received_at: string | null;
  price?: string;
  source_at?: string;
};
export type Contract = {
  conid: number;
  symbol: string;
  exchange: string;
  name: string;
  min_tick: string;
};
export type Incident = {
  id: string;
  severity: string;
  detail: string;
  timestamp: string;
  resolved: boolean;
};
export type Snapshot = {
  mode: string;
  connection: string;
  attested: boolean;
  entry_permission: boolean;
  emergency: boolean;
  checks: Check[];
  runs: Run[];
  orders: Order[];
  positions: Position[];
  data: DataState[];
  contracts: Contract[];
  incidents: Incident[];
  account_facts: Record<string, string>;
  evaluations?: Record<
    string,
    { node: string; label: string; value: string | boolean | null }[]
  >;
  timestamp: string;
};
export type ArmPreview = {
  eligible: boolean;
  checks: Check[];
  runs: Run[];
  expires_at: string | null;
  entry_cutoff: string | null;
  limits: {
    id: string;
    version: number;
    shares: number;
    planned_stop_risk: string;
    notional: string;
    daily_loss: string;
  };
  authorization: string;
  summaries?: (Version & { run_id: string })[];
};
export type Dataset = {
  id: string;
  name: string;
  source: string;
  ticks: number;
  created_at: string;
};
export type Replay = {
  id: string;
  strategy_id: string;
  strategy_name: string;
  version: number;
  dataset: string;
  dataset_source: string;
  timestamp: string;
  ticks: number;
  realized_pnl: string;
  signals: {
    timestamp: string;
    quantity: number;
    limit: string;
    stop: string;
  }[];
  trades: {
    entered_at: string;
    exited_at: string;
    entry: string;
    exit: string;
    quantity: number;
    pnl: string;
    reason: string;
  }[];
  open_position: { quantity: number; entry: string; stop: string } | null;
  working_entry: boolean;
  limitations: string[];
};
export type Event = {
  sequence: number;
  timestamp: string;
  type: string;
  payload: Record<string, Json>;
};

export class ApiError extends Error {
  status: number;
  issues: Issue[];
  constructor(status: number, detail: string, issues: Issue[] = []) {
    super(detail);
    this.status = status;
    this.issues = issues;
  }
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers:
      method === "GET"
        ? {}
        : {
            "Content-Type": "application/json",
            "X-Idempotency-Key": mutationId(),
          },
    body: method === "GET" ? undefined : JSON.stringify(body ?? {}),
  });
  const result = (await response.json()) as T & {
    detail?: string;
    issues?: Issue[];
  };
  if (!response.ok)
    throw new ApiError(
      response.status,
      typeof result.detail === "string"
        ? result.detail
        : "The action could not be completed.",
      result.issues,
    );
  return result;
}

export function readPreference<T>(key: string, fallback: T): T {
  try {
    const value = localStorage.getItem(`oms.workspace.${key}`);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
}
export function preference(key: string, value: unknown) {
  try {
    localStorage.setItem(`oms.workspace.${key}`, JSON.stringify(value));
  } catch {
    /* Browser storage may be unavailable; server drafts remain authoritative. */
  }
}
export const titleCase = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export const money = (value: string | number | undefined) =>
  value === undefined
    ? "Unavailable"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(Number(value));
export const localTime = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short",
      })
    : "Not available";
export const exchangeTime = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("en-US", {
        timeZone: "America/New_York",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })
    : "No exchange session";
export const mutationId = () => crypto.randomUUID().replaceAll("-", "");
