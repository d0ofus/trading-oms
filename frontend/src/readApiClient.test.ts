import { describe, expect, it } from "vitest";

import {
  READ_API_ENDPOINTS,
  createReadApiClient,
  initialReadApiState,
  loadOperationsSnapshot,
  safeFallbackOperationsSnapshot,
  type OperationsApiSnapshot,
} from "./readApiClient";

const sampleSnapshot: OperationsApiSnapshot = {
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
  auditEvents: [
    {
      schema_version: 1,
      sequence: 1,
      event_type: "strategy.signal.generated",
      timestamp: "2026-07-08T00:00:00Z",
      summary: "Replay strategy signal recorded",
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
};

const responseByEndpoint: Record<string, unknown> = {
  [READ_API_ENDPOINTS.safety]: sampleSnapshot.safety,
  [READ_API_ENDPOINTS.auditEvents]: sampleSnapshot.auditEvents,
  [READ_API_ENDPOINTS.signals]: sampleSnapshot.signals,
  [READ_API_ENDPOINTS.riskDecisions]: sampleSnapshot.riskDecisions,
  [READ_API_ENDPOINTS.approvalTickets]: sampleSnapshot.approvalTickets,
  [READ_API_ENDPOINTS.orders]: sampleSnapshot.orders,
  [READ_API_ENDPOINTS.positions]: sampleSnapshot.positions,
  [READ_API_ENDPOINTS.alerts]: sampleSnapshot.alerts,
  [READ_API_ENDPOINTS.readiness]: sampleSnapshot.readiness,
};

describe("read API client", () => {
  it("uses GET only for every read endpoint", async () => {
    const calls: { input: string; init?: RequestInit }[] = [];
    const client = createReadApiClient({
      fetchImpl: async (input, init) => {
        calls.push({ input: String(input), init });
        return jsonResponse(responseByEndpoint[String(input)]);
      },
    });

    await client.getSafety();
    await client.getAuditEvents();
    await client.getSignals();
    await client.getRiskDecisions();
    await client.getApprovalTickets();
    await client.getOrders();
    await client.getPositions();
    await client.getAlerts();
    await client.getReadiness();

    expect(calls.map((call) => call.input)).toEqual(Object.values(READ_API_ENDPOINTS));
    expect(calls.every((call) => call.init?.method === "GET")).toBe(true);
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
