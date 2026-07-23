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
  liveReadinessEvidence: "/api/live-readiness-evidence",
  paperTrading: "/api/paper-trading",
  operationalControls: "/api/operational-controls",
} as const;

export const OPERATIONS_PROVENANCE_RESOURCES = [
  "emergency_stop",
  "operator_session",
  "safety",
  "audit_events",
  "signals",
  "risk_decisions",
  "approval_tickets",
  "orders",
  "positions",
  "alerts",
  "readiness",
  "paper_trading",
  "operational_controls",
  "live_readiness_evidence",
] as const;

export type OperationsProvenanceResource =
  (typeof OPERATIONS_PROVENANCE_RESOURCES)[number];

export type ProvenanceClassification =
  | "representative"
  | "demo"
  | "simulated"
  | "local_only"
  | "test_double"
  | "adapter_only"
  | "fake_broker_derived"
  | "externally_unverified";

export type ReadModelProvenanceApiView = {
  schema_version: 1;
  resource: OperationsProvenanceResource;
  source: string;
  classifications: ProvenanceClassification[];
  broker_derived: false;
  externally_verified: false;
  summary: string;
};

export type ReadApiEnvelope<Payload> = {
  schema_version: 1;
  resource: OperationsProvenanceResource;
  provenance: ReadModelProvenanceApiView;
  data: Payload;
};

export type OperationsProvenanceCatalog = Record<
  OperationsProvenanceResource,
  ReadModelProvenanceApiView
>;

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
  decision_attribution?: SimulationDecisionAttributionApiView | null;
  execution_attribution?: SimulationExecutionAttributionApiView | null;
};

export type SimulationDecisionAttributionApiView = {
  schema_version: 1;
  workflow_id: string;
  workflow_version: number;
  run_id: string;
  run_status:
    | "waiting_for_approval"
    | "approved_not_executed"
    | "rejected"
    | "executed"
    | "executed_protection_missing";
  signal_id: string;
  order_intent_id: string;
  risk_decision_id: string;
  approval_ticket_id: string;
  approval_decision_id: string | null;
  approval_decision: "approved" | "rejected" | null;
  approval_actor: string | null;
  approval_reason: string | null;
  approval_decided_at: string | null;
  signal_journal_reference: string;
  order_intent_journal_reference: string;
  risk_journal_reference: string;
  approval_ticket_journal_reference: string;
  approval_decision_journal_reference: string | null;
  journal_references: string[];
  evidence_source: "schema_v4_sqlite_digest_bound_jsonl";
  classifications: ProvenanceClassification[];
  broker_derived: false;
  externally_verified: false;
};

export type SimulationExecutionAttributionApiView = {
  schema_version: 1;
  workflow_id: string;
  workflow_version: number;
  run_id: string;
  execution_id: string;
  order_intent_id: string;
  risk_decision_id: string;
  approval_ticket_id: string;
  approval_decision_id: string;
  order_id: string;
  fill_reference: string;
  position_id: string;
  protection_status: "expected_protection_present" | "missing_expected_protection";
  expected_protection_kind: string;
  risk_increasing_actions_blocked: boolean;
  alert_id: string;
  journal_references: string[];
  execution_journal_references: string[];
  evidence_source: "schema_v4_sqlite_digest_bound_jsonl";
  classifications: ProvenanceClassification[];
  broker_derived: false;
  externally_verified: false;
};

export type SignalApiView = {
  schema_version: 1;
  signal_id: string;
  strategy_id: string;
  symbol: string;
  signal: "long_bias" | "risk_off_bias" | "long_entry_candidate";
  reason: string;
  bar_start_timestamp: string;
  bar_end_timestamp: string;
  decision_attribution?: SimulationDecisionAttributionApiView | null;
};

export type RiskDecisionApiView = {
  schema_version: 1;
  request_id: string;
  evaluated_at: string;
  symbol: string;
  risk_intent: "increase" | "reduce";
  result: "passed" | "blocked";
  failed_check_names: string[];
  decision_attribution?: SimulationDecisionAttributionApiView | null;
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
  decision_attribution?: SimulationDecisionAttributionApiView | null;
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
  execution_attribution?: SimulationExecutionAttributionApiView | null;
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
  execution_attribution?: SimulationExecutionAttributionApiView | null;
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
  execution_attribution?: SimulationExecutionAttributionApiView | null;
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

export type LiveReadinessEvidenceItemApiView = {
  schema_version: 1;
  evidence_id: string;
  category:
    | "external_review"
    | "paper_trading_history"
    | "live_readiness"
    | "secret_management"
    | "network_exposure"
    | "authentication_authorization"
    | "emergency_stop"
    | "observability"
    | "audit_retention"
    | "backup_restore"
    | "reconciliation"
    | "rollback"
    | "incident_response"
    | "operator_signoff";
  label: string;
  status: "verified" | "missing" | "unverified" | "expired" | "contradictory";
  required_for_final_review: boolean;
  summary: string;
  source_reference: string;
};

export type LiveReadinessEvidenceApiView = {
  schema_version: 1;
  dashboard_id: string;
  evaluated_at: string;
  result: "not_ready" | "ready_for_final_review";
  live_trading_enabled: false;
  live_trading_authorized: false;
  external_review_required: boolean;
  explicit_human_approval_required: boolean;
  verified_evidence_count: number;
  missing_evidence_count: number;
  unverified_evidence_count: number;
  expired_evidence_count: number;
  contradictory_evidence_count: number;
  blocking_evidence_count: number;
  blocking_reason: string;
  evidence_items: LiveReadinessEvidenceItemApiView[];
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

export type ObservabilityMetricApiView = {
  schema_version: 1;
  metric_name: string;
  metric_value: number;
  unit: string;
  status: "ok" | "warning" | "critical";
  observed_at: string;
  summary: string;
};

export type ObservabilityEventApiView = {
  schema_version: 1;
  event_id: string;
  event_type: string;
  observed_at: string;
  severity: "informational" | "warning" | "critical" | "emergency";
  summary: string;
  journal_reference: string;
};

export type AuditRetentionApiView = {
  schema_version: 1;
  policy_id: string;
  mode: "retain_until_reviewed" | "retain_indefinitely";
  minimum_retention_days: number;
  destructive_retention_enabled: false;
  append_only_journal_required: boolean;
  next_review_due_at: string;
  status: string;
};

export type BackupRestoreApiView = {
  schema_version: 1;
  plan_id: string;
  backup_status: string;
  restore_verification_status: string;
  last_verified_at: string;
  storage_mode: string;
  external_storage_configured: false;
  redaction_status: string;
};

export type IncidentResponseApiView = {
  schema_version: 1;
  plan_id: string;
  active_incident_state: string;
  severity_floor_for_operator_review: "informational" | "warning" | "critical" | "emergency";
  emergency_stop_required_for_critical_incidents: boolean;
  post_incident_review_required: boolean;
  current_runbook_status: string;
  last_reviewed_at: string;
};

export type OperationalControlsApiView = {
  schema_version: 1;
  observed_at: string;
  live_trading_enabled: false;
  production_rollout_authorized: false;
  metrics: ObservabilityMetricApiView[];
  events: ObservabilityEventApiView[];
  retention: AuditRetentionApiView;
  backup_restore: BackupRestoreApiView;
  incident_response: IncidentResponseApiView;
};

export type OperationsApiSnapshot = {
  provenance: OperationsProvenanceCatalog;
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
  liveReadinessEvidence: LiveReadinessEvidenceApiView;
  paperTrading: PaperTradingApiView;
  operationalControls: OperationalControlsApiView;
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
  getEmergencyStop: () => Promise<ReadApiEnvelope<EmergencyStopApiView>>;
  getOperatorSession: () => Promise<ReadApiEnvelope<OperatorSessionApiView>>;
  getSafety: () => Promise<ReadApiEnvelope<SafetyApiView>>;
  getAuditEvents: () => Promise<ReadApiEnvelope<AuditEventApiView[]>>;
  getSignals: () => Promise<ReadApiEnvelope<SignalApiView[]>>;
  getRiskDecisions: () => Promise<ReadApiEnvelope<RiskDecisionApiView[]>>;
  getApprovalTickets: () => Promise<ReadApiEnvelope<ApprovalTicketApiView[]>>;
  getOrders: () => Promise<ReadApiEnvelope<OrderApiView[]>>;
  getPositions: () => Promise<ReadApiEnvelope<PositionApiView[]>>;
  getAlerts: () => Promise<ReadApiEnvelope<AlertApiView[]>>;
  getReadiness: () => Promise<ReadApiEnvelope<ReadinessApiView>>;
  getLiveReadinessEvidence: () => Promise<ReadApiEnvelope<LiveReadinessEvidenceApiView>>;
  getPaperTrading: () => Promise<ReadApiEnvelope<PaperTradingApiView>>;
  getOperationalControls: () => Promise<ReadApiEnvelope<OperationalControlsApiView>>;
  getOperationsSnapshot: () => Promise<OperationsApiSnapshot>;
};

type ReadApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: ReadApiFetch;
  headers?: Record<string, string>;
};

export const safeFallbackOperationsSnapshot: OperationsApiSnapshot = {
  provenance: buildSafeFallbackProvenance(),
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
  liveReadinessEvidence: {
    schema_version: 1,
    dashboard_id: "frontend-safe-fallback",
    evaluated_at: "2026-07-08T00:08:00Z",
    result: "not_ready",
    live_trading_enabled: false,
    live_trading_authorized: false,
    external_review_required: true,
    explicit_human_approval_required: true,
    verified_evidence_count: 0,
    missing_evidence_count: 6,
    unverified_evidence_count: 8,
    expired_evidence_count: 0,
    contradictory_evidence_count: 0,
    blocking_evidence_count: 14,
    blocking_reason: "backend_read_api_unavailable",
    evidence_items: buildSafeFallbackEvidenceItems(),
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
  operationalControls: {
    schema_version: 1,
    observed_at: "2026-07-08T00:00:00Z",
    live_trading_enabled: false,
    production_rollout_authorized: false,
    metrics: [
      {
        schema_version: 1,
        metric_name: "system.health",
        metric_value: 0,
        unit: "status",
        status: "warning",
        observed_at: "2026-07-08T00:00:00Z",
        summary: "Backend read API unavailable",
      },
      {
        schema_version: 1,
        metric_name: "audit_journal.health",
        metric_value: 0,
        unit: "status",
        status: "warning",
        observed_at: "2026-07-08T00:00:00Z",
        summary: "Append-only journal visibility unavailable",
      },
    ],
    events: [
      {
        schema_version: 1,
        event_id: "frontend-fallback-operational-event",
        event_type: "read_api.fallback",
        observed_at: "2026-07-08T00:00:00Z",
        severity: "warning",
        summary: "Frontend rendered safe operational fallback",
        journal_reference: "journal_sequence:0",
      },
    ],
    retention: {
      schema_version: 1,
      policy_id: "audit-retention-local-fallback",
      mode: "retain_until_reviewed",
      minimum_retention_days: 365,
      destructive_retention_enabled: false,
      append_only_journal_required: true,
      next_review_due_at: "2026-08-08T00:00:00Z",
      status: "fallback_planned_local_only",
    },
    backup_restore: {
      schema_version: 1,
      plan_id: "backup-restore-local-fallback",
      backup_status: "backend_unavailable",
      restore_verification_status: "backend_unavailable",
      last_verified_at: "2026-07-08T00:00:00Z",
      storage_mode: "local_encrypted_storage_required",
      external_storage_configured: false,
      redaction_status: "redaction_required",
    },
    incident_response: {
      schema_version: 1,
      plan_id: "incident-response-local-fallback",
      active_incident_state: "none_declared",
      severity_floor_for_operator_review: "warning",
      emergency_stop_required_for_critical_incidents: true,
      post_incident_review_required: true,
      current_runbook_status: "documented_local_playbook",
      last_reviewed_at: "2026-07-08T00:00:00Z",
    },
  },
};

function buildSafeFallbackProvenance(): OperationsProvenanceCatalog {
  const simulatedResources = new Set<OperationsProvenanceResource>([
    "audit_events",
    "signals",
    "risk_decisions",
    "approval_tickets",
    "orders",
    "positions",
    "alerts",
    "readiness",
  ]);
  return Object.fromEntries(
    OPERATIONS_PROVENANCE_RESOURCES.map((resource) => {
      let classifications: ProvenanceClassification[];
      let summary: string;
      if (simulatedResources.has(resource)) {
        classifications = [
          "representative",
          "demo",
          "simulated",
          "local_only",
          "externally_unverified",
        ];
        summary = "Safe frontend simulation fallback; not external evidence";
      } else if (resource === "paper_trading") {
        classifications = [
          "representative",
          "demo",
          "local_only",
          "test_double",
          "adapter_only",
          "externally_unverified",
        ];
        summary =
          "Representative adapter fallback; not an authenticated IBKR paper session";
      } else if (
        resource === "operational_controls" ||
        resource === "live_readiness_evidence"
      ) {
        classifications = [
          "representative",
          "demo",
          "local_only",
          "externally_unverified",
        ];
        summary = "Safe frontend planning fallback; not external evidence";
      } else {
        classifications = ["local_only", "externally_unverified"];
        summary = "Safe frontend local fallback; not external evidence";
      }
      return [
        resource,
        {
          schema_version: 1,
          resource,
          source: "frontend_safe_fallback",
          classifications,
          broker_derived: false,
          externally_verified: false,
          summary,
        } satisfies ReadModelProvenanceApiView,
      ];
    }),
  ) as OperationsProvenanceCatalog;
}

function buildSafeFallbackEvidenceItems(): LiveReadinessEvidenceItemApiView[] {
  const items: Array<
    [
      LiveReadinessEvidenceItemApiView["category"],
      string,
      LiveReadinessEvidenceItemApiView["status"],
    ]
  > = [
    ["external_review", "External review evidence", "missing"],
    ["paper_trading_history", "Paper-trading history evidence", "missing"],
    ["live_readiness", "Live-readiness evidence", "unverified"],
    ["secret_management", "Secret-management review", "unverified"],
    ["network_exposure", "Network-exposure review", "missing"],
    [
      "authentication_authorization",
      "Authentication and authorization evidence",
      "unverified",
    ],
    ["emergency_stop", "Emergency-stop evidence", "unverified"],
    ["observability", "Observability evidence", "unverified"],
    ["audit_retention", "Audit-retention evidence", "unverified"],
    ["backup_restore", "Backup and restore evidence", "unverified"],
    ["reconciliation", "Reconciliation evidence", "unverified"],
    ["rollback", "Rollback evidence", "missing"],
    ["incident_response", "Incident-response evidence", "missing"],
    ["operator_signoff", "Operator sign-off evidence", "missing"],
  ];
  return items.map(([category, label, status]) => ({
    schema_version: 1,
    evidence_id: `fallback-${category.replaceAll("_", "-")}`,
    category,
    label,
    status,
    required_for_final_review: true,
    summary:
      status === "missing"
        ? `${label} is missing`
        : `${label} is local-only and externally unverified`,
    source_reference: "frontend-safe-fallback",
  }));
}

export const initialReadApiState: ReadApiLoadState = {
  status: "loading",
  snapshot: safeFallbackOperationsSnapshot,
  errorMessage: null,
};

export function createReadApiClient(options: ReadApiClientOptions = {}): ReadApiClient {
  const fetchImpl = options.fetchImpl ?? defaultFetch;
  const request = <Payload>(
    path: string,
    resource: OperationsProvenanceResource,
  ) =>
    requestEnvelope<Payload>(
      fetchImpl,
      buildUrl(options.baseUrl ?? "", path),
      path,
      resource,
      options.headers ?? {},
    );

  const client: ReadApiClient = {
    getEmergencyStop: () =>
      request<EmergencyStopApiView>(READ_API_ENDPOINTS.emergencyStop, "emergency_stop"),
    getOperatorSession: () =>
      request<OperatorSessionApiView>(
        READ_API_ENDPOINTS.operatorSession,
        "operator_session",
      ),
    getSafety: () => request<SafetyApiView>(READ_API_ENDPOINTS.safety, "safety"),
    getAuditEvents: () =>
      request<AuditEventApiView[]>(READ_API_ENDPOINTS.auditEvents, "audit_events"),
    getSignals: () =>
      request<SignalApiView[]>(READ_API_ENDPOINTS.signals, "signals"),
    getRiskDecisions: () =>
      request<RiskDecisionApiView[]>(
        READ_API_ENDPOINTS.riskDecisions,
        "risk_decisions",
      ),
    getApprovalTickets: () =>
      request<ApprovalTicketApiView[]>(
        READ_API_ENDPOINTS.approvalTickets,
        "approval_tickets",
      ),
    getOrders: () => request<OrderApiView[]>(READ_API_ENDPOINTS.orders, "orders"),
    getPositions: () =>
      request<PositionApiView[]>(READ_API_ENDPOINTS.positions, "positions"),
    getAlerts: () => request<AlertApiView[]>(READ_API_ENDPOINTS.alerts, "alerts"),
    getReadiness: () =>
      request<ReadinessApiView>(READ_API_ENDPOINTS.readiness, "readiness"),
    getLiveReadinessEvidence: () =>
      request<LiveReadinessEvidenceApiView>(
        READ_API_ENDPOINTS.liveReadinessEvidence,
        "live_readiness_evidence",
      ),
    getPaperTrading: () =>
      request<PaperTradingApiView>(READ_API_ENDPOINTS.paperTrading, "paper_trading"),
    getOperationalControls: () =>
      request<OperationalControlsApiView>(
        READ_API_ENDPOINTS.operationalControls,
        "operational_controls",
      ),
    getOperationsSnapshot: async () => {
      const [
        emergencyStopEnvelope,
        operatorSessionEnvelope,
        safetyEnvelope,
        auditEventsEnvelope,
        signalsEnvelope,
        riskDecisionsEnvelope,
        approvalTicketsEnvelope,
        ordersEnvelope,
        positionsEnvelope,
        alertsEnvelope,
        readinessEnvelope,
        liveReadinessEvidenceEnvelope,
        paperTradingEnvelope,
        operationalControlsEnvelope,
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
        client.getLiveReadinessEvidence(),
        client.getPaperTrading(),
        client.getOperationalControls(),
      ]);

      const snapshot = {
        provenance: {
          emergency_stop: emergencyStopEnvelope.provenance,
          operator_session: operatorSessionEnvelope.provenance,
          safety: safetyEnvelope.provenance,
          audit_events: auditEventsEnvelope.provenance,
          signals: signalsEnvelope.provenance,
          risk_decisions: riskDecisionsEnvelope.provenance,
          approval_tickets: approvalTicketsEnvelope.provenance,
          orders: ordersEnvelope.provenance,
          positions: positionsEnvelope.provenance,
          alerts: alertsEnvelope.provenance,
          readiness: readinessEnvelope.provenance,
          paper_trading: paperTradingEnvelope.provenance,
          operational_controls: operationalControlsEnvelope.provenance,
          live_readiness_evidence: liveReadinessEvidenceEnvelope.provenance,
        },
        emergencyStop: emergencyStopEnvelope.data,
        operatorSession: operatorSessionEnvelope.data,
        safety: safetyEnvelope.data,
        auditEvents: auditEventsEnvelope.data,
        signals: signalsEnvelope.data,
        riskDecisions: riskDecisionsEnvelope.data,
        approvalTickets: approvalTicketsEnvelope.data,
        orders: ordersEnvelope.data,
        positions: positionsEnvelope.data,
        alerts: alertsEnvelope.data,
        readiness: readinessEnvelope.data,
        liveReadinessEvidence: liveReadinessEvidenceEnvelope.data,
        paperTrading: paperTradingEnvelope.data,
        operationalControls: operationalControlsEnvelope.data,
      };
      validateExecutionProjectionSnapshot(snapshot);
      return snapshot;
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

async function requestEnvelope<Payload>(
  fetchImpl: ReadApiFetch,
  url: string,
  endpointPath: string,
  expectedResource: OperationsProvenanceResource,
  requestHeaders: Record<string, string>,
): Promise<ReadApiEnvelope<Payload>> {
  const response = await fetchImpl(url, {
    method: "GET",
    headers: { Accept: "application/json", ...requestHeaders },
  });

  if (!response.ok) {
    throw new ReadApiError(endpointPath, response.status);
  }

  return validateEnvelope<Payload>(await response.json(), expectedResource);
}

function validateEnvelope<Payload>(
  value: unknown,
  expectedResource: OperationsProvenanceResource,
): ReadApiEnvelope<Payload> {
  if (!isRecord(value) || value.schema_version !== 1) {
    throw new ReadApiProvenanceError("Read API envelope is missing or invalid");
  }
  if (value.resource !== expectedResource || !("data" in value)) {
    throw new ReadApiProvenanceError("Read API resource provenance does not match");
  }
  const provenance = value.provenance;
  if (
    !isRecord(provenance) ||
    provenance.schema_version !== 1 ||
    provenance.resource !== expectedResource ||
    typeof provenance.source !== "string" ||
    !provenance.source ||
    typeof provenance.summary !== "string" ||
    !provenance.summary ||
    !Array.isArray(provenance.classifications)
  ) {
    throw new ReadApiProvenanceError("Read API provenance is missing or invalid");
  }
  const allowed = new Set<ProvenanceClassification>([
    "representative",
    "demo",
    "simulated",
    "local_only",
    "test_double",
    "adapter_only",
    "fake_broker_derived",
    "externally_unverified",
  ]);
  const classifications = provenance.classifications;
  if (
    classifications.length === 0 ||
    classifications.some(
      (classification) =>
        typeof classification !== "string" ||
        !allowed.has(classification as ProvenanceClassification),
    ) ||
    new Set(classifications).size !== classifications.length ||
    !classifications.includes("externally_unverified")
  ) {
    throw new ReadApiProvenanceError("Read API provenance classifications are unsafe");
  }
  if (provenance.broker_derived !== false || provenance.externally_verified !== false) {
    throw new ReadApiProvenanceError("Read API provenance exceeds the current evidence boundary");
  }
  return value as ReadApiEnvelope<Payload>;
}

function validateExecutionProjectionSnapshot(snapshot: OperationsApiSnapshot) {
  const lifecycleResources = [
    "audit_events",
    "signals",
    "risk_decisions",
    "approval_tickets",
    "orders",
    "positions",
    "alerts",
  ] as const;
  const lifecycleSource = "durable_saved_workflow_simulation";
  const executionSource = "durable_saved_workflow_simulation_execution";
  const durableResources = lifecycleResources.filter((resource) =>
    [lifecycleSource, executionSource].includes(snapshot.provenance[resource].source),
  );
  const allRecords = [
    ...snapshot.auditEvents,
    ...snapshot.signals,
    ...snapshot.riskDecisions,
    ...snapshot.approvalTickets,
    ...snapshot.orders,
    ...snapshot.positions,
    ...snapshot.alerts,
  ];
  if (durableResources.length === 0) {
    if (
      allRecords.some(
        (record) =>
          ("decision_attribution" in record && record.decision_attribution != null) ||
          ("execution_attribution" in record && record.execution_attribution != null),
      )
    ) {
      throw new ReadApiProvenanceError(
        "Representative read records must not claim durable simulation attribution",
      );
    }
    return;
  }
  if (durableResources.length !== lifecycleResources.length) {
    throw new ReadApiProvenanceError("Durable simulation provenance is incomplete");
  }
  const lifecycleClassifications = ["simulated", "local_only", "externally_unverified"];
  for (const resource of [
    "audit_events",
    "signals",
    "risk_decisions",
    "approval_tickets",
  ] as const) {
    const provenance = snapshot.provenance[resource];
    if (
      provenance.source !== lifecycleSource ||
      provenance.classifications.join(",") !== lifecycleClassifications.join(",")
    ) {
      throw new ReadApiProvenanceError("Durable upstream provenance is inconsistent");
    }
  }
  if (
    snapshot.signals.length === 0 ||
    snapshot.riskDecisions.length === 0 ||
    snapshot.approvalTickets.length === 0 ||
    snapshot.auditEvents.length === 0
  ) {
    throw new ReadApiProvenanceError("Durable upstream projection is partial");
  }
  const downstreamResources = ["orders", "positions", "alerts"] as const;
  const executionMode = snapshot.provenance.orders.source === executionSource;
  const downstreamSource = executionMode ? executionSource : lifecycleSource;
  const downstreamClassifications = executionMode
    ? ["simulated", "local_only", "fake_broker_derived", "externally_unverified"]
    : lifecycleClassifications;
  if (
    downstreamResources.some(
      (resource) =>
        snapshot.provenance[resource].source !== downstreamSource ||
        snapshot.provenance[resource].classifications.join(",") !==
          downstreamClassifications.join(","),
    )
  ) {
    throw new ReadApiProvenanceError("Durable downstream provenance is inconsistent");
  }
  if (
    lifecycleResources.some((resource) =>
      snapshot.provenance[resource].classifications.includes("representative"),
    )
  ) {
    throw new ReadApiProvenanceError("Durable projection contains representative provenance");
  }

  const signalByRun = new Map<string, SignalApiView>();
  const riskByRun = new Map<string, RiskDecisionApiView>();
  const ticketByRun = new Map<string, ApprovalTicketApiView>();
  const signalIds = new Set<string>();
  const riskIds = new Set<string>();
  const ticketIds = new Set<string>();
  for (const signal of snapshot.signals) {
    validateDecisionAttribution(signal.decision_attribution);
    const attribution = signal.decision_attribution;
    if (
      signal.signal_id !== attribution.signal_id ||
      signal.signal !== "long_entry_candidate" ||
      signalIds.has(signal.signal_id) ||
      signalByRun.has(attribution.run_id)
    ) {
      throw new ReadApiProvenanceError("Durable signal attribution is inconsistent");
    }
    signalIds.add(signal.signal_id);
    signalByRun.set(attribution.run_id, signal);
  }
  for (const risk of snapshot.riskDecisions) {
    validateDecisionAttribution(risk.decision_attribution);
    const attribution = risk.decision_attribution;
    if (
      risk.request_id !== attribution.risk_decision_id ||
      risk.result !== "passed" ||
      risk.failed_check_names.length !== 0 ||
      riskIds.has(risk.request_id) ||
      riskByRun.has(attribution.run_id)
    ) {
      throw new ReadApiProvenanceError("Durable risk attribution is inconsistent");
    }
    riskIds.add(risk.request_id);
    riskByRun.set(attribution.run_id, risk);
  }
  for (const ticket of snapshot.approvalTickets) {
    validateDecisionAttribution(ticket.decision_attribution);
    const attribution = ticket.decision_attribution;
    const expectedTicketStatus =
      attribution.run_status === "waiting_for_approval"
        ? "pending"
        : attribution.run_status === "rejected"
          ? "rejected"
          : "approved";
    if (
      ticket.ticket_id !== attribution.approval_ticket_id ||
      ticket.risk_decision_id !== attribution.risk_decision_id ||
      ticket.status !== expectedTicketStatus ||
      ticketIds.has(ticket.ticket_id) ||
      ticketByRun.has(attribution.run_id)
    ) {
      throw new ReadApiProvenanceError("Durable approval attribution is inconsistent");
    }
    ticketIds.add(ticket.ticket_id);
    ticketByRun.set(attribution.run_id, ticket);
  }
  const runIds = new Set(signalByRun.keys());
  if (
    !sameStringSet(runIds, new Set(riskByRun.keys())) ||
    !sameStringSet(runIds, new Set(ticketByRun.keys()))
  ) {
    throw new ReadApiProvenanceError("Durable upstream run identities are incomplete");
  }
  for (const runId of runIds) {
    const signalAttribution = signalByRun.get(runId)?.decision_attribution;
    const riskAttribution = riskByRun.get(runId)?.decision_attribution;
    const ticketAttribution = ticketByRun.get(runId)?.decision_attribution;
    if (
      JSON.stringify(signalAttribution) !== JSON.stringify(riskAttribution) ||
      JSON.stringify(signalAttribution) !== JSON.stringify(ticketAttribution)
    ) {
      throw new ReadApiProvenanceError("Durable upstream attribution snapshots disagree");
    }
  }
  const auditReferencesByRun = new Map<string, Set<string>>();
  for (const event of snapshot.auditEvents) {
    validateDecisionAttribution(event.decision_attribution);
    const attribution = event.decision_attribution;
    const ticket = ticketByRun.get(attribution.run_id);
    const eventReference = `journal_sequence:${event.sequence}`;
    if (
      event.run_id !== attribution.run_id ||
      event.ticket_id !== attribution.approval_ticket_id ||
      !ticket ||
      event.order_id !== ticket.order_id ||
      !attribution.journal_references.includes(eventReference) ||
      JSON.stringify(attribution) !== JSON.stringify(ticket.decision_attribution)
    ) {
      throw new ReadApiProvenanceError("Durable audit decision attribution is inconsistent");
    }
    const references = auditReferencesByRun.get(attribution.run_id) ?? new Set<string>();
    references.add(eventReference);
    auditReferencesByRun.set(attribution.run_id, references);
  }
  for (const runId of runIds) {
    const expectedReferences = new Set(
      ticketByRun.get(runId)?.decision_attribution?.journal_references ?? [],
    );
    if (!sameStringSet(expectedReferences, auditReferencesByRun.get(runId) ?? new Set())) {
      throw new ReadApiProvenanceError("Durable audit manifest projection is incomplete");
    }
  }

  if (!executionMode) {
    if (
      snapshot.orders.length !== 0 ||
      snapshot.positions.length !== 0 ||
      snapshot.alerts.length !== 0 ||
      snapshot.auditEvents.some((event) => event.execution_attribution != null)
    ) {
      throw new ReadApiProvenanceError("Unreached durable execution stages must be empty");
    }
    return;
  }
  if (
    snapshot.orders.length === 0 ||
    snapshot.positions.length === 0 ||
    snapshot.alerts.length === 0
  ) {
    throw new ReadApiProvenanceError("Durable execution projection is partial");
  }
  const executionRecords = [...snapshot.orders, ...snapshot.positions, ...snapshot.alerts];
  for (const record of executionRecords) {
    validateExecutionAttribution(record.execution_attribution);
    const executionAttribution = record.execution_attribution;
    const decisionAttribution =
      ticketByRun.get(executionAttribution.run_id)?.decision_attribution;
    if (
      !decisionAttribution ||
      !["executed", "executed_protection_missing"].includes(decisionAttribution.run_status) ||
      executionAttribution.workflow_id !== decisionAttribution.workflow_id ||
      executionAttribution.workflow_version !== decisionAttribution.workflow_version ||
      executionAttribution.order_intent_id !== decisionAttribution.order_intent_id ||
      executionAttribution.risk_decision_id !== decisionAttribution.risk_decision_id ||
      executionAttribution.approval_ticket_id !== decisionAttribution.approval_ticket_id ||
      executionAttribution.approval_decision_id !==
        decisionAttribution.approval_decision_id
    ) {
      throw new ReadApiProvenanceError("Durable execution and decision lineage disagree");
    }
  }
  for (const order of snapshot.orders) {
    const attribution = order.execution_attribution!;
    if (
      order.order_id !== attribution.order_id ||
      order.risk_decision_id !== attribution.risk_decision_id
    ) {
      throw new ReadApiProvenanceError("Durable order attribution is inconsistent");
    }
  }
  for (const position of snapshot.positions) {
    const attribution = position.execution_attribution!;
    if (
      position.position_id !== attribution.position_id ||
      position.protection_status !== attribution.protection_status
    ) {
      throw new ReadApiProvenanceError("Durable position attribution is inconsistent");
    }
  }
  for (const alert of snapshot.alerts) {
    if (alert.alert_id !== alert.execution_attribution!.alert_id) {
      throw new ReadApiProvenanceError("Durable alert attribution is inconsistent");
    }
  }
  for (const event of snapshot.auditEvents) {
    if (event.execution_attribution == null) {
      continue;
    }
    const attribution = event.execution_attribution;
    validateExecutionAttribution(attribution);
    if (
      event.run_id !== attribution.run_id ||
      event.order_id !== attribution.order_id ||
      event.ticket_id !== attribution.approval_ticket_id
    ) {
      throw new ReadApiProvenanceError("Durable audit attribution is inconsistent");
    }
  }
  const orderExecutions = new Set(
    snapshot.orders.map((record) => record.execution_attribution?.execution_id),
  );
  const positionExecutions = new Set(
    snapshot.positions.map((record) => record.execution_attribution?.execution_id),
  );
  const alertExecutions = new Set(
    snapshot.alerts.map((record) => record.execution_attribution?.execution_id),
  );
  const auditExecutions = new Set(
    snapshot.auditEvents
      .filter((record) => record.execution_attribution != null)
      .map((record) => record.execution_attribution?.execution_id),
  );
  if (
    orderExecutions.size !== snapshot.orders.length ||
    positionExecutions.size !== snapshot.positions.length ||
    alertExecutions.size !== snapshot.alerts.length ||
    new Set(snapshot.auditEvents.map((event) => event.sequence)).size !==
      snapshot.auditEvents.length ||
    !sameStringSet(orderExecutions, positionExecutions) ||
    !sameStringSet(orderExecutions, alertExecutions) ||
    !sameStringSet(orderExecutions, auditExecutions)
  ) {
    throw new ReadApiProvenanceError("Durable execution projection identities are incomplete");
  }
}

function validateDecisionAttribution(
  value: SimulationDecisionAttributionApiView | null | undefined,
): asserts value is SimulationDecisionAttributionApiView {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    typeof value.workflow_version !== "number" ||
    !Number.isInteger(value.workflow_version) ||
    value.workflow_version < 1
  ) {
    throw new ReadApiProvenanceError("Durable decision attribution is invalid");
  }
  const identifiers = [
    "workflow_id",
    "run_id",
    "signal_id",
    "order_intent_id",
    "risk_decision_id",
    "approval_ticket_id",
    "signal_journal_reference",
    "order_intent_journal_reference",
    "risk_journal_reference",
    "approval_ticket_journal_reference",
  ] as const;
  if (identifiers.some((field) => typeof value[field] !== "string" || !value[field])) {
    throw new ReadApiProvenanceError("Durable decision attribution identities are incomplete");
  }
  const validRunStatuses = new Set([
    "waiting_for_approval",
    "approved_not_executed",
    "rejected",
    "executed",
    "executed_protection_missing",
  ]);
  if (!validRunStatuses.has(String(value.run_status))) {
    throw new ReadApiProvenanceError("Durable decision attribution status is invalid");
  }
  const decisionValues = [
    value.approval_decision_id,
    value.approval_decision,
    value.approval_actor,
    value.approval_reason,
    value.approval_decided_at,
    value.approval_decision_journal_reference,
  ];
  if (value.run_status === "waiting_for_approval") {
    if (decisionValues.some((item) => item !== null)) {
      throw new ReadApiProvenanceError("Pending decision attribution contains terminal fields");
    }
  } else {
    if (decisionValues.some((item) => typeof item !== "string" || !item)) {
      throw new ReadApiProvenanceError("Terminal decision attribution is incomplete");
    }
    const expectedDecision = value.run_status === "rejected" ? "rejected" : "approved";
    if (value.approval_decision !== expectedDecision) {
      throw new ReadApiProvenanceError("Terminal decision attribution is contradictory");
    }
  }
  const expectedClassifications = ["simulated", "local_only", "externally_unverified"];
  if (
    value.evidence_source !== "schema_v4_sqlite_digest_bound_jsonl" ||
    !Array.isArray(value.classifications) ||
    value.classifications.join(",") !== expectedClassifications.join(",") ||
    value.broker_derived !== false ||
    value.externally_verified !== false ||
    !Array.isArray(value.journal_references) ||
    value.journal_references.length === 0
  ) {
    throw new ReadApiProvenanceError("Durable decision provenance exceeds evidence boundary");
  }
  const journalReferences = value.journal_references;
  if (
    journalReferences.some((reference) => !isJournalReference(reference)) ||
    new Set(journalReferences).size !== journalReferences.length ||
    !isSequenceOrdered(journalReferences)
  ) {
    throw new ReadApiProvenanceError("Durable decision journal references are invalid");
  }
  const eventReferences = [
    value.signal_journal_reference,
    value.order_intent_journal_reference,
    value.risk_journal_reference,
    value.approval_ticket_journal_reference,
    ...(value.approval_decision_journal_reference === null
      ? []
      : [value.approval_decision_journal_reference]),
  ];
  if (
    value.signal_id !== value.signal_journal_reference ||
    new Set(eventReferences).size !== eventReferences.length ||
    eventReferences.some((reference) => !journalReferences.includes(reference))
  ) {
    throw new ReadApiProvenanceError("Durable decision event references are inconsistent");
  }
}

function isJournalReference(value: unknown): value is string {
  return typeof value === "string" && /^journal_sequence:[1-9][0-9]*$/.test(value);
}

function isSequenceOrdered(values: string[]) {
  const sequences = values.map((value) => Number(value.slice("journal_sequence:".length)));
  return sequences.every((value, index) => index === 0 || sequences[index - 1] < value);
}

function validateExecutionAttribution(
  value: SimulationExecutionAttributionApiView | null | undefined,
): asserts value is SimulationExecutionAttributionApiView {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    typeof value.workflow_version !== "number" ||
    !Number.isInteger(value.workflow_version) ||
    value.workflow_version < 1
  ) {
    throw new ReadApiProvenanceError("Durable execution attribution is invalid");
  }
  const identifiers = [
    "workflow_id",
    "run_id",
    "execution_id",
    "order_intent_id",
    "risk_decision_id",
    "approval_ticket_id",
    "approval_decision_id",
    "order_id",
    "fill_reference",
    "position_id",
    "expected_protection_kind",
    "alert_id",
  ] as const;
  const expectedClassifications = [
    "simulated",
    "local_only",
    "fake_broker_derived",
    "externally_unverified",
  ];
  if (
    identifiers.some((field) => typeof value[field] !== "string" || !value[field]) ||
    !["expected_protection_present", "missing_expected_protection"].includes(
      String(value.protection_status),
    ) ||
    value.risk_increasing_actions_blocked !==
      (value.protection_status === "missing_expected_protection") ||
    value.evidence_source !== "schema_v4_sqlite_digest_bound_jsonl" ||
    value.broker_derived !== false ||
    value.externally_verified !== false ||
    !Array.isArray(value.classifications) ||
    value.classifications.join(",") !== expectedClassifications.join(",") ||
    !validJournalReferences(value.journal_references) ||
    !validJournalReferences(value.execution_journal_references) ||
    !value.execution_journal_references.every((item) =>
      value.journal_references.includes(item),
    )
  ) {
    throw new ReadApiProvenanceError("Durable execution attribution is unsafe");
  }
}

function validJournalReferences(value: unknown): value is string[] {
  if (
    !Array.isArray(value) ||
    value.length === 0 ||
    !value.every(
      (item) => typeof item === "string" && /^journal_sequence:[1-9][0-9]*$/.test(item),
    ) ||
    new Set(value).size !== value.length
  ) {
    return false;
  }
  const sequences = value.map((item) => Number(item.split(":")[1]));
  return sequences.every((sequence, index) => index === 0 || sequence > sequences[index - 1]);
}

function sameStringSet(left: Set<string | undefined>, right: Set<string | undefined>) {
  return (
    !left.has(undefined) &&
    !right.has(undefined) &&
    left.size === right.size &&
    [...left].every((item) => right.has(item))
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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

class ReadApiProvenanceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReadApiProvenanceError";
  }
}
