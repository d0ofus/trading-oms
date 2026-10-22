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
  settings: Record<string, string | number | null>;
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
  feed_health?: "healthy" | "checking" | "blocked";
  evaluated_at?: string;
  structural_valid?: boolean;
  freshness_reason?: string;
  execution_state?:
    | "waiting_clock"
    | "waiting_quotes"
    | "waiting_live_minute"
    | "ready"
    | "checking"
    | "submitted"
    | "uncertain"
    | "broker_rejected"
    | "partially_filled"
    | "filled"
    | "blocked";
  execution_detail?: string;
  signal_source?: string;
  observation_ages?: Record<string, number | null>;
  stable?: boolean;
  authorization_ready?: boolean;
  depends_on?: string;
  code: string;
  title: string;
  passed: boolean;
  detail: string;
  remediation: string | null;
  status?: "ready" | "checking" | "waiting" | "blocked" | "unsupported";
};
export type Run = {
  required_inputs?: { ready: boolean; detail: string; evaluated_at: string };
  signal_progress?: {
    source: string;
    price: string;
    observed_at: string;
    reference_candle: string | null;
    reference_high: string | null;
    comparison: string;
    above_high: boolean | null;
  } | null;
  signal_outcome?: {
    state: string;
    detail: string;
    last_reason?: string;
    updated_at: string;
    order_id?: string;
    trigger: {
      high?: string;
      candle?: string;
      price?: string;
      triggered_at?: string;
    };
    rejection?: Rejection | null;
  } | null;
  authorization_status?:
    | "authorized"
    | "temporarily_suspended"
    | "revoked"
    | "expired"
    | "completed";
  resume_policy?: string | null;
  archived?: boolean;
  display_state?: string;
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
  protection_verification?: ProtectionVerification;
  protection_type?: string;
  session_policy?: string;
  capability_error?: string;
  binding?: {
    execution_plan?: {
      policy?: string;
      funding_policy?: string;
      authorization_policy?: string;
      family?: string;
      signal_source?: string;
      base_currency?: string;
      risk_policy?: string;
      session_mode?: string;
      hash: string;
      currency: string;
      session_policy: string;
      rules: StockRules;
    };
    hash: string;
    strategy_hash: string;
    sizing: Record<string, string | number | null>;
    contract: Contract;
  };
  risk: string;
  last_signal?: string;
  blocking_reason?: string;
  expires_at?: string;
};
export type Rejection = {
  code: number;
  category: string;
  detail: string;
  available: boolean;
  advanced_codes: string[];
};
export type Order = {
  id: string;
  run_id: string;
  state: string;
  broker_id: number;
  created_at: string;
  diagnostics?: {
    quantity_evidence?: {
      reported: string | null;
      effective: string | null;
      basis: string;
    };
    warning?: {
      code: number;
      state: string;
      detail: string;
      broker_status?: string;
    } | null;
    broker_status: string | null;
    acknowledgment_pending: boolean;
    identity_status: "pending" | "verified" | "mismatch" | "not_evaluated";
    status_label: string;
    status_conflict: boolean;
    cancellation_reason: string | null;
    cancellation_detail: string | null;
    rejection?: Rejection | null;
  };
  payload: {
    currency?: string;
    price_scale?: string;
    cash_quantity?: string;
    purpose?: string;
    execution?: string;
    action?: string;
    candle?: string;
    prices?: Record<string, string>;
    symbol: string;
    quantity: number | string;
    limit?: string;
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
export type RequestProgress = {
  request_state?: string;
  waiting_reason?: string | null;
  next_eligible_at?: string | null;
};
export const requestLabel = (state?: string) =>
  ({
    queued: "Queued",
    waiting_connection: "Waiting for broker connection",
    waiting_contract: "Waiting for contract resolution",
    waiting_pacing: "Waiting for pacing",
    requested: "Requested",
    receiving: "Receiving data",
    complete: "History complete",
    failed: "Failed",
  })[state ?? ""] ?? "Queued";

export type DataState = {
  candle_policy?: string;
  broker_reference?: { candle: string; high: string; revision: string } | null;
  candle_stream_status?: string;
  feed_health?: "healthy" | "checking" | "blocked";
  stream_health?: "healthy" | "checking" | "blocked";
  evaluated_at?: string;
  structural_valid?: boolean;
  freshness_reason?: string;
  family?: string;
  base_currency?: string;
  signal_source?: string;
  signal_price?: string | null;
  signal_at?: string;
  fx_sources?: (RequestProgress & {
    source: string;
    status: string;
    bars: number;
    detail?: string;
  })[];
  fx_feeds?: (RequestProgress & {
    kind: string;
    status: string;
    detail?: string;
    retry_available: boolean;
  })[];
  session_mode?: string;
  session_open?: boolean;
  history_ready?: boolean;
  price_scale?: string;
  components?: FeedComponents;
  extended_history?: {
    status: string;
    detail?: string;
    minute_bars: number;
    retry_available: boolean;
  };
  execution_detail?: string;
  ages?: Record<string, number | null>;
  currency?: string;
  subscription_status?: string;
  data_type?: string;
  candle_source?: string;
  diagnostic?: string;
  sizes?: Record<string, { value: string; received_at: string }>;
  candles?: Record<
    string,
    {
      timestamp: string;
      open: string;
      high: string;
      low: string;
      close: string;
      volume: string | null;
      complete: boolean;
      source: string;
    }[]
  >;
  conid: number;
  symbol: string;
  live: boolean;
  warm: boolean;
  received_at: string | null;
  price?: string;
  source_at?: string;
  history_loaded?: boolean;
  history_status?: string;
  feed_status?: string;
  ready?: boolean;
  quotes?: Record<string, { price: string; received_at: string }>;
  history_progress?: {
    minute_bars: number;
    fine_bars: number;
    complete_reference_sessions: number;
    required_reference_sessions: number;
  };
};
export type Capabilities = {
  executions: string[];
  unsupported_reason?: string;
  session_policy: string;
  protection_type?: string;
  candle_source: string;
};
export type StockRules = {
  revision: number;
  source: string;
  reference: string;
  calendar: string;
  currency: string;
  quantity_increment: string;
  minimum_quantity: string;
  exit_increment: string;
  price_scale: string;
  fee_reserve: string;
  same_day_resale: boolean;
  broker_protection: boolean;
  native_oca: boolean;
  local_protection: boolean;
  fractional_protection: boolean;
};
export type StockCompatibility = {
  resolution_status?: string;
  minimum_lot?: {
    quantity: string;
    currency: string;
    native_notional: string;
    notional_usd: string;
    fee_reserve: string;
    native_funds: string;
    published_ceiling_usd: string;
    stop_risk_usd?: string | null;
  };
  can_prepare?: boolean;
  preparation_blockers?: string[];
  arming_requirements?: string[];
  field_requirements?: { field: string; available: boolean }[];
  evidence?: Record<
    string,
    { source: string; reference: string; revision: number }
  >;
  fee_policy?: { amount: string; revision: number };
  indicative_sizing?: {
    quantity: string;
    notional_usd: string;
    stop_risk_usd: string | null;
    native_funds: string;
    currency: string;
  };
  status: string;
  blockers: string[];
  rules?: StockRules;
  plan?: {
    funding_policy?: string;
    family?: string;
    signal_source?: string;
    base_currency?: string;
    hash: string;
    session_policy: string;
    currency: string;
    protection_type: string;
    rules: StockRules;
    session_mode?: string;
  };
};
export type Contract = {
  stock_rules?: StockRules;
  min_size?: string;
  size_increment?: string;
  resolved?: boolean;
  sec_type?: string;
  currency?: string;
  routing_exchange?: string;
  primary_exchange?: string;
  expiry?: string;
  strike?: string;
  right?: string;
  trading_class?: string;
  multiplier?: string;
  capabilities?: Capabilities;
  conid: number;
  symbol: string;
  exchange: string;
  name: string;
  min_tick: string;
};
export type Incident = {
  actionable?: boolean;
  category?: "operational" | "critical" | "requirement" | "diagnostic";
  current_relevance?: string;
  blocking_stages?: string[];
  release_policy?: "automatic" | "manual";
  automatic_release_enabled?: boolean;
  release_kind?: "dependency_retired" | "verified_recovery";
  remaining_seconds?: number;
  rejection?: Rejection | null;
  order_context?: { order_id: string; run_id: string; broker_id: number };
  recovery?: {
    checks: { code: string; title: string; passed: boolean; detail: string }[];
    checked_at: string;
    remaining_seconds: number;
    can_release: boolean;
  };
  feeds?: { conid: number; components: FeedComponents };
  id: string;
  severity: string;
  detail: string;
  timestamp: string;
  resolved: boolean;
  code?: string;
  revision?: number;
  scope?: { type: string; key: string };
  condition?: "active" | "unknown" | "recovered";
  restriction?: "held" | "ready_for_release" | "released";
  investigation?: "open" | "closed";
  review_policy?: "arming" | "dedicated";
  recovery_detail?: string;
  first_at?: string;
  last_at?: string;
  occurrences?: number;
  evidence?: Json;
  release_evidence?: Json;
  diagnostic?: Json;
  release_reason?: string;
  investigation_outcome?: string;
};
export type FeedComponents = Partial<
  Record<
    "quote" | "trade" | "history",
    {
      status: string;
      source?: string;
      signal_source?: string;
      request_state?: string;
      waiting_reason?: string | null;
      next_eligible_at?: string | null;
      diagnostic?: {
        code: number;
        reason: string;
        detail: string;
        at: string;
      } | null;
      progress?: Record<string, number> | null;
      retry_available: boolean;
      retry_pending: boolean;
      retry_in_seconds: number | null;
      attempts: number;
    }
  >
>;
export type ProtectionVerification = {
  state:
    "active" | "checking" | "missing" | "mismatch" | "exit_pending" | "closed";
  reasons: string[];
  evaluated_at: string;
  evidence_revision: number;
  broker_status: string | null;
  stop?: string;
};
export type StockProtection = {
  verification?: ProtectionVerification;
  family?: string;
  base_currency?: string;
  price_scale?: string;
  run_id: string;
  quantity: string;
  stop: string;
  average: string;
  status: string;
  type: string;
  currency: string;
};
export type Snapshot = {
  fx_protection?: StockProtection[];
  stock_protection?: StockProtection[];
  stock_triggers?: {
    run_id: string;
    high?: string;
    state: string;
    candle: string;
    expires_at: string;
    reason?: string;
  }[];
  build?: {
    backend: string;
    frontend: string | null;
    started_at: string;
  } | null;
  incident_counts?: Record<string, number>;
  incident_next_cursor?: number | null;
  migration?: {
    pending: boolean;
    status: string;
    detail: string;
  } | null;
  outage?: { active: boolean; started_at: string; recovered_at?: string };
  local_protection?: {
    run_id: string;
    quantity: string;
    stop: string;
    average: string;
    status: string;
  }[];
  crypto_triggers?: {
    run_id: string;
    high?: string;
    state: string;
    candle: string;
    expires_at: string;
    reason?: string;
  }[];
  oca_groups?: {
    currency?: string;
    price_scale?: string;
    id: string;
    run_id: string;
    state: string;
    candle: string;
    winner: string | null;
    protection: string;
    average?: string;
    stop?: string;
  }[];
  mode: string;
  environment?: string;
  session_policy?: string;
  execution_provider?: string;
  data_source?: string;
  simulation_assumptions?: string[];
  currency_positions?: {
    conid: number;
    symbol: string;
    currency: string;
    quantity: string;
    exchange: string;
  }[];
  reconciliation?: {
    ready: boolean;
    detail: string;
    in_progress?: boolean;
    evidence_revision?: number;
    verified_revision?: number | null;
    age_seconds?: number | null;
  };
  watchdog?: {
    ready: boolean;
    state: string;
    detail: string;
    age_seconds: number | null;
  };
  pnl?: {
    value: string | null;
    currency: string | null;
    received_at: string | null;
    status: string;
    informational: boolean;
    diagnostic?: string | null;
  };
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
  policy_replacement?: {
    target_policy_revision: string;
    target_execution_policy_revision?: string;
    eligible: boolean;
    items: {
      run_id: string;
      binding_hash: string;
      needs_replacement: boolean;
      blockers: string[];
      replacement_id: string | null;
      replacement_state?: string | null;
      action?: "adopt" | "restore";
    }[];
  };
  can_authorize?: boolean;
  can_dispatch?: boolean;
  review_fingerprint?: string;
  resume_policy?: string | null;
  eligible_after_recovery_ack?: boolean;
  recoveries?: Incident[];
  review_instance?: string;
  crypto_entries?: { run_id: string; cash_ceiling: string }[];
  paired_entries?: {
    run_id: string;
    status: string;
    candle?: string;
    prices?: Record<string, string>;
    quantity?: string;
    reservation?: { risk: string; notional: string };
    hypothetical_short: boolean;
  }[];
  eligible: boolean;
  checks: Check[];
  runs: Run[];
  expires_at: string | null;
  entry_cutoff: string | null;
  limits: {
    fx_units?: number | null;
    stock_units?: number | null;
    id: string;
    version: number;
    shares?: number;
    quantity?: string;
    risk_policy?: string;
    planned_stop_risk: string | null;
    notional: string | null;
  };
  authorization: string;
  environment?: string;
  session_policy?: string;
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
  dependencies: {
    code: string;
    detail: string;
    run_id?: string;
    run_name?: string;
    action?: string;
  }[];
  constructor(
    status: number,
    detail: string,
    issues: Issue[] = [],
    dependencies: ApiError["dependencies"] = [],
  ) {
    super(detail);
    this.status = status;
    this.issues = issues;
    this.dependencies = dependencies;
  }
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    signal,
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
    dependencies?: ApiError["dependencies"];
  };
  if (!response.ok)
    throw new ApiError(
      response.status,
      typeof result.detail === "string"
        ? result.detail
        : "The action could not be completed.",
      result.issues,
      result.dependencies,
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
export const money = (
  value: string | number | undefined,
  currency = "USD",
  scale = "1",
) =>
  value === undefined
    ? "Unavailable"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
      }).format(Number(value) * Number(scale));
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

export function policyLabel(run: Run) {
  const plan = run.binding?.execution_plan;
  return plan?.funding_policy === "paper_buying_power_v1" &&
    (plan.family !== "spot_fx" ||
      (plan.authorization_policy === "quiet_fx_v1" &&
        plan.policy === "idealpro_broker_candles_v2"))
    ? "Current execution policy"
    : plan?.funding_policy === "paper_buying_power_v1"
      ? "Earlier live-minute candle policy"
      : plan?.funding_policy === "broker_credit_v1"
        ? "Earlier credit-preview policy"
        : "Earlier cash-only policy";
}
