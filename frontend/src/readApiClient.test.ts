import { describe, expect, it } from "vitest";

import {
  READ_API_ENDPOINTS,
  createReadApiClient,
  initialReadApiState,
  loadOperationsSnapshot,
  safeFallbackOperationsSnapshot,
  type OperationsApiSnapshot,
  type OperationsProvenanceResource,
} from "./readApiClient";

const sampleSnapshot: OperationsApiSnapshot = {
  emergencyStop: {
    schema_version: 1,
    active: true,
    status: "active",
    updated_at: "2026-07-08T13:45:00Z",
    activated_at: "2026-07-08T13:45:00Z",
    activated_by: "admin-operator-001",
    activation_reason: "operator_review",
    deactivated_at: null,
    deactivated_by: null,
    deactivation_reason: null,
    blocking_risk_increasing_actions: true,
  },
  safety: {
    schema_version: 1,
    app_env: "development",
    app_mode: "paper",
    live_trading_enabled: false,
    broker_connectivity: "not_configured",
    alert_delivery: "local_noop",
    approval_mode: "manual_required",
    data_source: "local_read_model",
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
  auditEvents: [
    {
      schema_version: 1,
      sequence: 1,
      event_type: "strategy.signal.generated",
      timestamp: "2026-07-08T00:00:00Z",
      summary: "Replay strategy signal recorded",
      run_id: "sim-run-001",
      symbol: "AAPL",
      order_id: "order-001",
      ticket_id: "ticket-001",
      severity: "informational",
    },
  ],
  signals: [
    {
      schema_version: 1,
      signal_id: "signal-001",
      strategy_id: "visual-close-above-sma",
      symbol: "AAPL",
      signal: "long_bias",
      reason: "close_above_sma",
      bar_start_timestamp: "2026-07-08T00:00:00Z",
      bar_end_timestamp: "2026-07-08T00:01:00Z",
    },
  ],
  riskDecisions: [
    {
      schema_version: 1,
      request_id: "risk-001",
      evaluated_at: "2026-07-08T00:01:00Z",
      symbol: "AAPL",
      risk_intent: "increase",
      result: "blocked",
      failed_check_names: ["market_data_freshness"],
    },
  ],
  approvalTickets: [
    {
      schema_version: 1,
      ticket_id: "ticket-001",
      order_id: "order-001",
      symbol: "AAPL",
      side: "buy",
      quantity: 10,
      status: "pending",
      risk_decision_id: "risk-001",
      created_at: "2026-07-08T00:02:00Z",
      expires_at: "2026-07-08T00:12:00Z",
    },
  ],
  orders: [
    {
      schema_version: 1,
      order_id: "order-001",
      client_order_id: "client-001",
      symbol: "AAPL",
      side: "buy",
      quantity: 10,
      state: "PENDING_APPROVAL",
      updated_at: "2026-07-08T00:02:00Z",
      risk_decision_id: "risk-001",
      approval_reference: null,
      requires_reconciliation: false,
      cumulative_filled_quantity: 0,
      leaves_quantity: 10,
    },
  ],
  positions: [
    {
      schema_version: 1,
      position_id: "position-001",
      symbol: "AAPL",
      quantity: 10,
      average_price: 101.25,
      protection_status: "expected_protection_present",
      updated_at: "2026-07-08T00:03:00Z",
      source: "simulation",
    },
  ],
  alerts: [
    {
      schema_version: 1,
      alert_id: "alert-001",
      severity: "critical",
      channel: "local",
      status: "recorded",
      title: "Protection review required",
      created_at: "2026-07-08T00:04:00Z",
      source_event_reference: "position-001",
    },
  ],
  readiness: {
    schema_version: 1,
    evaluation_id: "readiness-001",
    evaluated_at: "2026-07-08T00:05:00Z",
    result: "not_ready",
    failed_checks: ["emergency_stop_implemented"],
    required_human_action: "collect_missing_evidence",
    live_trading_enabled: false,
    live_trading_authorized: false,
  },
  liveReadinessEvidence: {
    schema_version: 1,
    dashboard_id: "live-readiness-evidence-001",
    evaluated_at: "2026-07-08T00:08:00Z",
    result: "not_ready",
    live_trading_enabled: false,
    live_trading_authorized: false,
    external_review_required: true,
    explicit_human_approval_required: true,
    verified_evidence_count: 0,
    missing_evidence_count: 4,
    unverified_evidence_count: 0,
    expired_evidence_count: 0,
    contradictory_evidence_count: 0,
    blocking_evidence_count: 1,
    blocking_reason: "missing_external_review_and_human_approval",
    evidence_items: [
      {
        schema_version: 1,
        evidence_id: "evidence-external-review",
        category: "external_review",
        label: "External review",
        status: "missing",
        required_for_final_review: true,
        summary: "Independent review evidence is missing",
        source_reference: "docs/live-trading-readiness-checklist",
      },
    ],
  },
  paperTrading: {
    schema_version: 1,
    adapter_name: "ibkr_paper",
    paper_mode: "paper",
    live_trading_enabled: false,
    connection_state: "unknown_requires_reconciliation",
    requires_reconciliation: true,
    reconciliation_summary: "stale_callback_requires_review",
    order_status: "PARTIALLY_FILLED",
    order_client_reference: "client-paper-001",
    status_callback_state: "accepted_status_update",
    fill_callback_state: "accepted_fill_update",
    cumulative_filled_quantity: 4,
    leaves_quantity: 6,
    updated_at: "2026-07-08T00:06:00Z",
  },
  operationalControls: {
    schema_version: 1,
    observed_at: "2026-07-08T00:07:00Z",
    live_trading_enabled: false,
    production_rollout_authorized: false,
    metrics: [
      {
        schema_version: 1,
        metric_name: "system.health",
        metric_value: 1,
        unit: "status",
        status: "ok",
        observed_at: "2026-07-08T00:07:00Z",
        summary: "Local service health is visible",
      },
    ],
    events: [
      {
        schema_version: 1,
        event_id: "observability-event-001",
        event_type: "system.health",
        observed_at: "2026-07-08T00:07:00Z",
        severity: "informational",
        summary: "Local observability snapshot recorded",
        journal_reference: "journal_sequence:0",
      },
    ],
    retention: {
      schema_version: 1,
      policy_id: "audit-retention-local-001",
      mode: "retain_until_reviewed",
      minimum_retention_days: 365,
      destructive_retention_enabled: false,
      append_only_journal_required: true,
      next_review_due_at: "2026-08-08T00:00:00Z",
      status: "planned_local_only",
    },
    backup_restore: {
      schema_version: 1,
      plan_id: "backup-restore-local-001",
      backup_status: "local_plan_documented",
      restore_verification_status: "local_plan_documented",
      last_verified_at: "2026-07-08T00:07:00Z",
      storage_mode: "local_encrypted_storage_required",
      external_storage_configured: false,
      redaction_status: "redaction_required",
    },
    incident_response: {
      schema_version: 1,
      plan_id: "incident-response-local-001",
      active_incident_state: "none_declared",
      severity_floor_for_operator_review: "warning",
      emergency_stop_required_for_critical_incidents: true,
      post_incident_review_required: true,
      current_runbook_status: "documented_local_playbook",
      last_reviewed_at: "2026-07-08T00:07:00Z",
    },
  },
  provenance: safeFallbackOperationsSnapshot.provenance,
};

const responseByEndpoint: Record<string, unknown> = {
  [READ_API_ENDPOINTS.emergencyStop]: readEnvelope(
    "emergency_stop",
    sampleSnapshot.emergencyStop,
  ),
  [READ_API_ENDPOINTS.safety]: readEnvelope("safety", sampleSnapshot.safety),
  [READ_API_ENDPOINTS.operatorSession]: readEnvelope(
    "operator_session",
    sampleSnapshot.operatorSession,
  ),
  [READ_API_ENDPOINTS.auditEvents]: readEnvelope(
    "audit_events",
    sampleSnapshot.auditEvents,
  ),
  [READ_API_ENDPOINTS.signals]: readEnvelope("signals", sampleSnapshot.signals),
  [READ_API_ENDPOINTS.riskDecisions]: readEnvelope(
    "risk_decisions",
    sampleSnapshot.riskDecisions,
  ),
  [READ_API_ENDPOINTS.approvalTickets]: readEnvelope(
    "approval_tickets",
    sampleSnapshot.approvalTickets,
  ),
  [READ_API_ENDPOINTS.orders]: readEnvelope("orders", sampleSnapshot.orders),
  [READ_API_ENDPOINTS.positions]: readEnvelope("positions", sampleSnapshot.positions),
  [READ_API_ENDPOINTS.alerts]: readEnvelope("alerts", sampleSnapshot.alerts),
  [READ_API_ENDPOINTS.readiness]: readEnvelope("readiness", sampleSnapshot.readiness),
  [READ_API_ENDPOINTS.liveReadinessEvidence]: readEnvelope(
    "live_readiness_evidence",
    sampleSnapshot.liveReadinessEvidence,
  ),
  [READ_API_ENDPOINTS.paperTrading]: readEnvelope(
    "paper_trading",
    sampleSnapshot.paperTrading,
  ),
  [READ_API_ENDPOINTS.operationalControls]: readEnvelope(
    "operational_controls",
    sampleSnapshot.operationalControls,
  ),
};

function readEnvelope(resource: OperationsProvenanceResource, data: unknown) {
  return {
    schema_version: 1,
    resource,
    provenance: sampleSnapshot.provenance[resource],
    data,
  };
}

describe("read API client", () => {
  it("uses GET only for every read endpoint", async () => {
    const calls: { input: string; init?: RequestInit }[] = [];
    const client = createReadApiClient({
      headers: {
        "x-operator-id": "approver-operator-001",
        "x-operator-roles": "approver",
      },
      fetchImpl: async (input, init) => {
        calls.push({ input: String(input), init });
        return jsonResponse(responseByEndpoint[String(input)]);
      },
    });

    await client.getEmergencyStop();
    await client.getOperatorSession();
    await client.getSafety();
    await client.getAuditEvents();
    await client.getSignals();
    await client.getRiskDecisions();
    await client.getApprovalTickets();
    await client.getOrders();
    await client.getPositions();
    await client.getAlerts();
    await client.getReadiness();
    await client.getLiveReadinessEvidence();
    await client.getPaperTrading();
    await client.getOperationalControls();

    expect(calls.map((call) => call.input)).toEqual(Object.values(READ_API_ENDPOINTS));
    expect(calls.every((call) => call.init?.method === "GET")).toBe(true);
    expect(
      calls.every(
        (call) =>
          new Headers(call.init?.headers).get("x-operator-id") ===
            "approver-operator-001" &&
          new Headers(call.init?.headers).get("x-operator-roles") === "approver",
      ),
    ).toBe(true);
  });

  it("loads an aggregate operations snapshot from read endpoints", async () => {
    const client = createReadApiClient({
      fetchImpl: async (input) => jsonResponse(responseByEndpoint[String(input)]),
    });

    const state = await loadOperationsSnapshot(client);

    expect(state.status).toBe("loaded");
    expect(state.snapshot).toEqual(sampleSnapshot);
    expect(state.errorMessage).toBeNull();
  });

  it("returns a safe fallback state when the backend is unavailable", async () => {
    const client = createReadApiClient({
      fetchImpl: async () => {
        throw new Error("secret-token-value should never render");
      },
    });

    const state = await loadOperationsSnapshot(client);

    expect(state).toEqual({
      status: "error",
      snapshot: safeFallbackOperationsSnapshot,
      errorMessage: "Read API request failed; showing safe local fallback.",
    });
    expect(state.snapshot.safety.live_trading_enabled).toBe(false);
    expect(state.snapshot.safety.broker_connectivity).toBe("not_configured");
    expect(state.snapshot.operatorSession.operator_id).toBe("human-operator-001");
    expect(state.snapshot.operatorSession.can_view_operations).toBe(true);
    expect(state.snapshot.operatorSession.can_approve_simulation).toBe(false);
    expect(state.snapshot.operatorSession.approval_role_required).toBe("approver");
    expect(state.snapshot.emergencyStop.active).toBe(false);
    expect(state.snapshot.emergencyStop.blocking_risk_increasing_actions).toBe(false);
    expect(state.snapshot.paperTrading.paper_mode).toBe("paper");
    expect(state.snapshot.paperTrading.live_trading_enabled).toBe(false);
    expect(state.snapshot.paperTrading.requires_reconciliation).toBe(true);
    expect(state.snapshot.liveReadinessEvidence.result).toBe("not_ready");
    expect(state.snapshot.liveReadinessEvidence.live_trading_enabled).toBe(false);
    expect(state.snapshot.liveReadinessEvidence.live_trading_authorized).toBe(false);
    expect(state.snapshot.liveReadinessEvidence.external_review_required).toBe(true);
    expect(state.snapshot.operationalControls.live_trading_enabled).toBe(false);
    expect(state.snapshot.operationalControls.production_rollout_authorized).toBe(false);
    expect(state.snapshot.operationalControls.backup_restore.external_storage_configured).toBe(
      false,
    );
    expect(JSON.stringify(state)).not.toContain("secret-token-value");
  });

  it("exposes no action, broker-network, credential, or secret affordance keys", () => {
    const keys = allPayloadKeys({
      initialReadApiState,
      safeFallbackOperationsSnapshot,
      sampleSnapshot,
    });

    expect(isDisjoint(forbiddenAffordanceKeys, keys)).toBe(true);
  });
});

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function allPayloadKeys(value: unknown): Set<string> {
  if (Array.isArray(value)) {
    return value.reduce((keys, item) => union(keys, allPayloadKeys(item)), new Set<string>());
  }
  if (value && typeof value === "object") {
    const keys = new Set(Object.keys(value));
    for (const nestedValue of Object.values(value)) {
      union(keys, allPayloadKeys(nestedValue));
    }
    return keys;
  }
  return new Set();
}

function union(target: Set<string>, source: Set<string>) {
  for (const key of source) {
    target.add(key);
  }
  return target;
}

function isDisjoint(left: Set<string>, right: Set<string>) {
  for (const value of left) {
    if (right.has(value)) {
      return false;
    }
  }
  return true;
}

const forbiddenAffordanceKeys = new Set([
  "account",
  "account_id",
  "api_key",
  "approve_action",
  "approve_url",
  "authorization",
  "broker_host",
  "broker_port",
  "cancel_action",
  "cancel_url",
  "certificate",
  "connect_action",
  "connect_url",
  "credential",
  "host",
  "password",
  "place_order_url",
  "port",
  "private_key",
  "reject_action",
  "reject_url",
  "route",
  "secret",
  "socket",
  "submit_action",
  "submit_url",
  "token",
  "transmit",
  "transmit_url",
]);
