export const READ_API_ENDPOINTS = {
  emergencyStop: "/api/emergency-stop",
  operatorSession: "/api/operator-session",
  safety: "/api/safety",
  auditEvents: "/api/audit-events",
  signals: "/api/signals",
  riskDecisions: "/api/risk-decisions",
  approvalTickets: "/api/approval-tickets",
  orders: "/api/orders",
  positions: "/api/positions",
  alerts: "/api/alerts",
  readiness: "/api/readiness",
  paperTrading: "/api/paper-trading",
} as const;

export type SafetyApiView = {
  schema_version: 1;
  app_env: string;
  app_mode: "paper" | "simulation";
  live_trading_enabled: false;
  broker_connectivity: string;
  alert_delivery: string;
  approval_mode: string;
  data_source: string;
};

export type OperatorSessionApiView = {
  schema_version: 1;
  operator_id: string;
  auth_state: "local_development";
  auth_method: "local_header";
  roles: string[];
  permissions: string[];
  can_view_operations: boolean;
  can_approve_simulation: boolean;
  can_administer_system: boolean;
  approval_role_required: string;
  role_separation: string;
};

export type EmergencyStopApiView = {
  schema_version: 1;
  active: boolean;
  status: "active" | "inactive";
  updated_at: string;
  activated_at: string | null;
  activated_by: string | null;
  activation_reason: string | null;
  deactivated_at: string | null;
  deactivated_by: string | null;
  deactivation_reason: string | null;
  blocking_risk_increasing_actions: boolean;
};

export type AuditEventApiView = {
  schema_version: 1;
  sequence: number;
  event_type: string;
  timestamp: string;
  summary: string;
  run_id: string | null;
  symbol: string | null;
  order_id: string | null;
  ticket_id: string | null;
  severity: "informational" | "warning" | "critical" | "emergency" | null;
};

export type SignalApiView = {
  schema_version: 1;
  signal_id: string;
  strategy_id: string;
  symbol: string;
  signal: "long_bias" | "risk_off_bias";
  reason: string;
  bar_start_timestamp: string;
  bar_end_timestamp: string;
};

export type RiskDecisionApiView = {
  schema_version: 1;
  request_id: string;
  evaluated_at: string;
  symbol: string;
  risk_intent: "increase" | "reduce";
  result: "passed" | "blocked";
  failed_check_names: string[];
};

export type ApprovalTicketApiView = {
  schema_version: 1;
  ticket_id: string;
  order_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  status: "pending" | "approved" | "rejected" | "expired" | "cancelled";
  risk_decision_id: string;
  created_at: string;
  expires_at: string;
};

export type OrderApiView = {
  schema_version: 1;
  order_id: string;
  client_order_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  state: string;
  updated_at: string;
  risk_decision_id: string;
  approval_reference: string | null;
  requires_reconciliation: boolean;
  cumulative_filled_quantity: number;
  leaves_quantity: number;
};

export type PositionApiView = {
  schema_version: 1;
  position_id: string;
  symbol: string;
  quantity: number;
  average_price: number;
  protection_status:
    | "expected_protection_present"
    | "missing_expected_protection"
    | "not_required"
    | "review_required";
  updated_at: string;
  source: string;
};

export type AlertApiView = {
  schema_version: 1;
  alert_id: string;
  severity: "informational" | "warning" | "critical" | "emergency";
  channel: string;
  status: "recorded" | "failed";
  title: string;
  created_at: string;
  source_event_reference: string;
};

export type ReadinessApiView = {
  schema_version: 1;
  evaluation_id: string;
  evaluated_at: string;
  result: "not_ready" | "ready_for_final_review";
  failed_checks: string[];
  required_human_action: string;
  live_trading_enabled: false;
  live_trading_authorized: false;
};

export type PaperTradingApiView = {
  schema_version: 1;
  adapter_name: string;
  paper_mode: "paper";
  live_trading_enabled: false;
  connection_state: string;
  requires_reconciliation: boolean;
  reconciliation_summary: string;
  order_status: string;
  order_client_reference: string;
  status_callback_state: string;
  fill_callback_state: string;
  cumulative_filled_quantity: number;
  leaves_quantity: number;
  updated_at: string;
};

export type OperationsApiSnapshot = {
  emergencyStop: EmergencyStopApiView;
  safety: SafetyApiView;
  operatorSession: OperatorSessionApiView;
  auditEvents: AuditEventApiView[];
  signals: SignalApiView[];
  riskDecisions: RiskDecisionApiView[];
  approvalTickets: ApprovalTicketApiView[];
  orders: OrderApiView[];
  positions: PositionApiView[];
  alerts: AlertApiView[];
  readiness: ReadinessApiView;
  paperTrading: PaperTradingApiView;
};

export type ReadApiLoadState =
  | {
      status: "loading";
      snapshot: OperationsApiSnapshot;
      errorMessage: null;
    }
  | {
      status: "loaded" | "empty";
      snapshot: OperationsApiSnapshot;
      errorMessage: null;
    }
  | {
      status: "error";
      snapshot: OperationsApiSnapshot;
      errorMessage: string;
    };

export type ReadApiFetch = (input: string, init: RequestInit) => Promise<Response>;

export type ReadApiClient = {
  getEmergencyStop: () => Promise<EmergencyStopApiView>;
  getOperatorSession: () => Promise<OperatorSessionApiView>;
  getSafety: () => Promise<SafetyApiView>;
  getAuditEvents: () => Promise<AuditEventApiView[]>;
  getSignals: () => Promise<SignalApiView[]>;
  getRiskDecisions: () => Promise<RiskDecisionApiView[]>;
  getApprovalTickets: () => Promise<ApprovalTicketApiView[]>;
  getOrders: () => Promise<OrderApiView[]>;
  getPositions: () => Promise<PositionApiView[]>;
  getAlerts: () => Promise<AlertApiView[]>;
  getReadiness: () => Promise<ReadinessApiView>;
  getPaperTrading: () => Promise<PaperTradingApiView>;
  getOperationsSnapshot: () => Promise<OperationsApiSnapshot>;
};

type ReadApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: ReadApiFetch;
};

export const safeFallbackOperationsSnapshot: OperationsApiSnapshot = {
  emergencyStop: {
    schema_version: 1,
    active: false,
    status: "inactive",
    updated_at: "2026-07-08T00:00:00Z",
    activated_at: null,
    activated_by: null,
    activation_reason: null,
    deactivated_at: null,
    deactivated_by: null,
    deactivation_reason: null,
    blocking_risk_increasing_actions: false,
  },
  safety: {
    schema_version: 1,
    app_env: "development",
    app_mode: "paper",
    live_trading_enabled: false,
    broker_connectivity: "not_configured",
    alert_delivery: "local_noop",
    approval_mode: "manual_required",
    data_source: "frontend_safe_fallback",
  },
  operatorSession: {
    schema_version: 1,
    operator_id: "human-operator-001",
    auth_state: "local_development",
    auth_method: "local_header",
    roles: ["admin"],
    permissions: ["view_operations", "administer_system"],
    can_view_operations: true,
    can_approve_simulation: false,
    can_administer_system: true,
    approval_role_required: "approver",
    role_separation: "admin_approver_separated",
  },
  auditEvents: [],
  signals: [],
  riskDecisions: [],
  approvalTickets: [],
  orders: [],
  positions: [],
  alerts: [],
  readiness: {
    schema_version: 1,
    evaluation_id: "frontend-safe-fallback",
    evaluated_at: "2026-07-08T00:00:00Z",
    result: "not_ready",
    failed_checks: ["backend_read_api_unavailable"],
    required_human_action: "inspect_backend_read_api",
    live_trading_enabled: false,
    live_trading_authorized: false,
  },
  paperTrading: {
    schema_version: 1,
    adapter_name: "ibkr_paper",
    paper_mode: "paper",
    live_trading_enabled: false,
    connection_state: "not_configured",
    requires_reconciliation: true,
    reconciliation_summary: "backend_read_api_unavailable",
    order_status: "unavailable",
    order_client_reference: "not_recorded",
    status_callback_state: "unavailable",
    fill_callback_state: "unavailable",
    cumulative_filled_quantity: 0,
    leaves_quantity: 0,
    updated_at: "2026-07-08T00:00:00Z",
  },
};

export const initialReadApiState: ReadApiLoadState = {
  status: "loading",
  snapshot: safeFallbackOperationsSnapshot,
  errorMessage: null,
};

export function createReadApiClient(options: ReadApiClientOptions = {}): ReadApiClient {
  const fetchImpl = options.fetchImpl ?? defaultFetch;
  const request = <Payload>(path: string) =>
    requestJson<Payload>(fetchImpl, buildUrl(options.baseUrl ?? "", path), path);

  const client: ReadApiClient = {
    getEmergencyStop: () => request<EmergencyStopApiView>(READ_API_ENDPOINTS.emergencyStop),
    getOperatorSession: () =>
      request<OperatorSessionApiView>(READ_API_ENDPOINTS.operatorSession),
    getSafety: () => request<SafetyApiView>(READ_API_ENDPOINTS.safety),
    getAuditEvents: () => request<AuditEventApiView[]>(READ_API_ENDPOINTS.auditEvents),
    getSignals: () => request<SignalApiView[]>(READ_API_ENDPOINTS.signals),
    getRiskDecisions: () => request<RiskDecisionApiView[]>(READ_API_ENDPOINTS.riskDecisions),
    getApprovalTickets: () =>
      request<ApprovalTicketApiView[]>(READ_API_ENDPOINTS.approvalTickets),
    getOrders: () => request<OrderApiView[]>(READ_API_ENDPOINTS.orders),
    getPositions: () => request<PositionApiView[]>(READ_API_ENDPOINTS.positions),
    getAlerts: () => request<AlertApiView[]>(READ_API_ENDPOINTS.alerts),
    getReadiness: () => request<ReadinessApiView>(READ_API_ENDPOINTS.readiness),
    getPaperTrading: () => request<PaperTradingApiView>(READ_API_ENDPOINTS.paperTrading),
    getOperationsSnapshot: async () => {
      const [
        emergencyStop,
        operatorSession,
        safety,
        auditEvents,
        signals,
        riskDecisions,
        approvalTickets,
        orders,
        positions,
        alerts,
        readiness,
        paperTrading,
      ] = await Promise.all([
        client.getEmergencyStop(),
        client.getOperatorSession(),
        client.getSafety(),
        client.getAuditEvents(),
        client.getSignals(),
        client.getRiskDecisions(),
        client.getApprovalTickets(),
        client.getOrders(),
        client.getPositions(),
        client.getAlerts(),
        client.getReadiness(),
        client.getPaperTrading(),
      ]);

      return {
        emergencyStop,
        operatorSession,
        safety,
        auditEvents,
        signals,
        riskDecisions,
        approvalTickets,
        orders,
        positions,
        alerts,
        readiness,
        paperTrading,
      };
    },
  };

  return client;
}

export async function loadOperationsSnapshot(
  client: ReadApiClient = createReadApiClient(),
): Promise<ReadApiLoadState> {
  try {
    const snapshot = await client.getOperationsSnapshot();
    return {
      status: isSnapshotEmpty(snapshot) ? "empty" : "loaded",
      snapshot,
      errorMessage: null,
    };
  } catch {
    return {
      status: "error",
      snapshot: safeFallbackOperationsSnapshot,
      errorMessage: "Read API request failed; showing safe local fallback.",
    };
  }
}

async function requestJson<Payload>(
  fetchImpl: ReadApiFetch,
  url: string,
  endpointPath: string,
): Promise<Payload> {
  const response = await fetchImpl(url, {
    method: "GET",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new ReadApiError(endpointPath, response.status);
  }

  return (await response.json()) as Payload;
}

function buildUrl(baseUrl: string, path: string) {
  if (!baseUrl) {
    return path;
  }
  return `${baseUrl.replace(/\/+$/, "")}${path}`;
}

function isSnapshotEmpty(snapshot: OperationsApiSnapshot) {
  return (
    snapshot.auditEvents.length === 0 &&
    snapshot.signals.length === 0 &&
    snapshot.riskDecisions.length === 0 &&
    snapshot.approvalTickets.length === 0 &&
    snapshot.orders.length === 0 &&
    snapshot.positions.length === 0 &&
    snapshot.alerts.length === 0
  );
}

async function defaultFetch(input: string, init: RequestInit) {
  return globalThis.fetch(input, init);
}

class ReadApiError extends Error {
  constructor(endpointPath: string, status: number) {
    super(`Read API ${endpointPath} failed with status ${status}`);
    this.name = "ReadApiError";
  }
}
