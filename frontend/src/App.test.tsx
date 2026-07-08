import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import {
  safeFallbackOperationsSnapshot,
  type OperationsApiSnapshot,
  type ReadApiLoadState,
} from "./readApiClient";

function renderedText(element = <App />) {
  return renderToStaticMarkup(element)
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

describe("App", () => {
  it("renders the read-only operations shell sections", () => {
    const text = renderedText();

    expect(text).toContain("Trading OMS");
    expect(text).toContain("Visual builder");
    expect(text).toContain("Simulation run detail");
    expect(text).toContain("Signals");
    expect(text).toContain("Approval tickets");
    expect(text).toContain("Orders");
    expect(text).toContain("Positions");
    expect(text).toContain("Audit events");
    expect(text).toContain("Alerts");
  });

  it("renders the visual builder nodes and generated replay-only DSL", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(html).toContain('aria-label="React Flow simulation workflow scaffold"');
    expect(text).toContain("Replay source");
    expect(text).toContain("Bar builder");
    expect(text).toContain("Strategy trigger");
    expect(text).toContain("Risk check");
    expect(text).toContain("Approval ticket");
    expect(text).toContain("Fake broker");
    expect(text).toContain("Position update");
    expect(text).toContain("Applies simulated fills to local positions");
    expect(text).toContain("Alert");
    expect(text).toContain("Records local protection and safety alerts");
    expect(text).toContain("Audit sink");
    expect(text).toContain("Graph validation passed");
    expect(text).toContain("Risk, approval, audit, and supported-node checks passed");
    expect(text).toContain("Editable layout");
    expect(text).toContain("Node movement changes only local canvas positions");
    expect(text).toContain("no transport");
    expect(text).toContain("No broker connectivity");
    expect(text).toContain("No order actions");
    expect(text).toContain("No credential fields");
    expect(html).toContain('name="symbol"');
    expect(html).toContain('name="lookbackBars"');
    expect(html).toContain('name="timeframeSeconds"');
    expect(html).toContain("&quot;schema_version&quot;: 1");
    expect(html).toContain("&quot;mode&quot;: &quot;replay&quot;");
    expect(html).toContain("&quot;strategy_type&quot;: &quot;close_above_sma&quot;");
    expect(text).toContain("Simulation workflow DSL");
    expect(text).toContain("Workflow persistence");
    expect(text).toContain("Local definition storage ready");
    expect(text).toContain("Simulation replay endpoint ready");
    expect(text).toContain("Manual approval wait only");
    expect(text).toContain("waiting for approval");
    expect(text).toContain("blocked waiting for approval");
    expect(text).toContain("risk blocked");
    expect(text).toContain("filled");
    expect(text).toContain("alert recorded");
    expect(text).toContain("journal_sequence:14");
    expect(html).toContain("&quot;workflow_id&quot;: &quot;visual-simulation-workflow&quot;");
    expect(html).toContain("&quot;mode&quot;: &quot;simulation&quot;");
    expect(html).toContain("&quot;runtime&quot;: &quot;preview_only&quot;");
    expect(html).toContain("&quot;live_trading_enabled&quot;: false");
  });

  it("renders the safety posture visibly", () => {
    const text = renderedText(<App initialReadState={loadedReadState} />);

    expect(text).toContain("Simulation mode");
    expect(text).toContain("Live trading disabled");
    expect(text).toContain("Broker connectivity not configured");
    expect(text).toContain("Manual approval required");
    expect(text).toContain("Append-only journal");
    expect(text).toContain("Alert delivery local noop");
  });

  it("renders backend-derived workflow records when read data is loaded", () => {
    const text = renderedText(<App initialReadState={loadedReadState} />);

    expect(text).toContain("TSLA visual-close-above-sma");
    expect(text).toContain("ticket-backend-001");
    expect(text).toContain("client-backend-001");
    expect(text).toContain("position-backend-001");
    expect(text).toContain("backend.audit.event");
    expect(text).toContain("Backend protection review");
    expect(text).not.toContain("AAPL replay SMA");
    expect(text).not.toContain("MSFT replay SMA");
  });

  it("renders the simulation run detail timeline and safety records", () => {
    const text = renderedText(<App initialReadState={loadedReadState} />);

    expect(text).toContain("Run sim-run-001");
    expect(text).toContain("Replay loaded");
    expect(text).toContain("Signal generated");
    expect(text).toContain("Risk evaluated");
    expect(text).toContain("Approval decided");
    expect(text).toContain("Fake broker filled");
    expect(text).toContain("Protection monitored");
    expect(text).toContain("signal-001");
    expect(text).toContain("risk-001");
    expect(text).toContain("approval-ticket-001");
    expect(text).toContain("order-001");
    expect(text).toContain("fake-client-001");
    expect(text).toContain("fill-001");
    expect(text).toContain("position-AAPL");
    expect(text).toContain("alert-position-update-001");
    expect(text).toContain("append only");
  });

  it("renders a safe fallback when backend read APIs are unavailable", () => {
    const fallbackState: ReadApiLoadState = {
      status: "error",
      snapshot: safeFallbackOperationsSnapshot,
      errorMessage: "Read API request failed; showing safe local fallback.",
    };
    const text = renderedText(<App initialReadState={fallbackState} />);

    expect(text).toContain("Read API fallback");
    expect(text).toContain("Live trading disabled");
    expect(text).toContain("Broker connectivity not configured");
    expect(text).toContain("0 records");
    expect(text).not.toContain("secret-token-value");
  });

  it("does not render live-action affordances", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />).toLowerCase();
    const forbiddenPhrases = [
      "submit order",
      "place order",
      "transmit order",
      "connect broker",
      "enable live trading",
      "send telegram",
      "add credential",
      "ibkr connect",
      "import workflow",
      "export workflow",
      "save workflow",
      "run workflow",
      "execute workflow",
      "run script",
      "custom code",
      "javascript",
      "eval(",
      "eval:",
      "broker host",
      "account id",
      "live mode",
      "route order",
      "api key",
      "password",
    ];

    for (const phrase of forbiddenPhrases) {
      expect(html).not.toContain(phrase);
    }
    expect(html).not.toContain("<button");
    expect(html).not.toContain("<form");
  });
});

const backendSnapshot: OperationsApiSnapshot = {
  safety: {
    schema_version: 1,
    app_env: "development",
    app_mode: "simulation",
    live_trading_enabled: false,
    broker_connectivity: "not_configured",
    alert_delivery: "local_noop",
    approval_mode: "manual_required",
    data_source: "local_read_model",
  },
  auditEvents: [
    {
      schema_version: 1,
      sequence: 900,
      event_type: "backend.audit.event",
      timestamp: "2026-07-08T00:00:00Z",
      summary: "Backend audit event rendered from read API",
    },
  ],
  signals: [
    {
      schema_version: 1,
      signal_id: "signal-backend-001",
      strategy_id: "visual-close-above-sma",
      symbol: "TSLA",
      signal: "long_bias",
      reason: "close_above_sma",
      bar_start_timestamp: "2026-07-08T00:00:00Z",
      bar_end_timestamp: "2026-07-08T00:01:00Z",
    },
  ],
  riskDecisions: [
    {
      schema_version: 1,
      request_id: "risk-backend-001",
      evaluated_at: "2026-07-08T00:01:00Z",
      symbol: "TSLA",
      risk_intent: "increase",
      result: "blocked",
      failed_check_names: ["market_data_freshness"],
    },
  ],
  approvalTickets: [
    {
      schema_version: 1,
      ticket_id: "ticket-backend-001",
      order_id: "order-backend-001",
      symbol: "TSLA",
      side: "buy",
      quantity: 5,
      status: "pending",
      risk_decision_id: "risk-backend-001",
      created_at: "2026-07-08T00:02:00Z",
      expires_at: "2026-07-08T00:12:00Z",
    },
  ],
  orders: [
    {
      schema_version: 1,
      order_id: "order-backend-001",
      client_order_id: "client-backend-001",
      symbol: "TSLA",
      side: "buy",
      quantity: 5,
      state: "PENDING_APPROVAL",
      updated_at: "2026-07-08T00:02:00Z",
      risk_decision_id: "risk-backend-001",
      approval_reference: null,
      requires_reconciliation: false,
      cumulative_filled_quantity: 0,
      leaves_quantity: 5,
    },
  ],
  positions: [
    {
      schema_version: 1,
      position_id: "position-backend-001",
      symbol: "TSLA",
      quantity: 5,
      average_price: 210.5,
      protection_status: "expected_protection_present",
      updated_at: "2026-07-08T00:03:00Z",
      source: "simulation",
    },
  ],
  alerts: [
    {
      schema_version: 1,
      alert_id: "alert-backend-001",
      severity: "critical",
      channel: "local",
      status: "recorded",
      title: "Backend protection review",
      created_at: "2026-07-08T00:04:00Z",
      source_event_reference: "position-backend-001",
    },
  ],
  readiness: {
    schema_version: 1,
    evaluation_id: "readiness-backend-001",
    evaluated_at: "2026-07-08T00:05:00Z",
    result: "not_ready",
    failed_checks: ["emergency_stop_implemented"],
    required_human_action: "collect_missing_evidence",
    live_trading_enabled: false,
    live_trading_authorized: false,
  },
};

const loadedReadState: ReadApiLoadState = {
  status: "loaded",
  snapshot: backendSnapshot,
  errorMessage: null,
};
