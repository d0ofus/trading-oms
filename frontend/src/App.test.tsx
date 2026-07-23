import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import {
  safeFallbackOperationsSnapshot,
  type OperationsApiSnapshot,
  type ReadApiLoadState,
  type SimulationDecisionAttributionApiView,
  type SimulationExecutionAttributionApiView,
} from "./readApiClient";
import type { WorkflowRunInspectionState } from "./workflowRunInspector";
import {
  createInitialVisualWorkflowEditorState,
  removeVisualWorkflowNode,
} from "./visualWorkflowEditor";

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
    expect(text).toContain("Operator access");
    expect(text).toContain("Visual builder");
    expect(text).toContain("Simulation run detail");
    expect(text).toContain("Approval inbox");
    expect(text).toContain("Audit explorer");
    expect(text).toContain("Order detail");
    expect(text).toContain("Position detail");
    expect(text).toContain("Protection monitor");
    expect(text).toContain("Emergency stop");
    expect(text).toContain("Paper trading");
    expect(text).toContain("Live-readiness evidence");
    expect(text).toContain("Operational controls");
    expect(text).toContain("Signals");
    expect(text).toContain("Approval tickets");
    expect(text).toContain("Orders");
    expect(text).toContain("Positions");
    expect(text).toContain("Audit events");
    expect(text).toContain("Alerts");
  });

  it("renders the interactive visual builder and generated replay-only DSL", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(html).toContain('aria-label="Interactive simulation workflow editor"');
    expect(text).toContain("Node palette");
    expect(text).toContain("Remove selected");
    expect(text).toContain("Reset graph");
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
    expect(text).toContain("Required simulation safety path connected");
    expect(text).toContain("Local graph only");
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
    expect(text).toContain("Workflow library");
    expect(text).toContain("Validated simulation definitions");
    expect(text).toContain("Loading saved workflows");
    expect(text).toContain("Create workflow");
    expect(text).toContain("Update workflow");
    expect(text).toContain("Discard current edits before load");
    expect(text).toContain("Simulation run start");
    expect(text).toContain("SIMULATION ONLY");
    expect(text).toContain("Unavailable");
    expect(text).toContain("Simulation safety state is unavailable");
    expect(text).not.toContain("Start simulation");
    expect(text).not.toContain("Delete workflow");
    expect(text).not.toContain("Run workflow");
    expect(text).not.toContain("Run inspection statuses");
    expect(text).not.toContain("workflow-run-001");
    expect(html).toContain("&quot;workflow_id&quot;: &quot;visual-simulation-workflow&quot;");
    expect(html).toContain("&quot;mode&quot;: &quot;simulation&quot;");
    expect(html).toContain("&quot;runtime&quot;: &quot;preview_only&quot;");
    expect(html).toContain("&quot;live_trading_enabled&quot;: false");
  });

  it("blocks the workflow DSL document when the edited graph is invalid", () => {
    const initialEditorState = removeVisualWorkflowNode(
      createInitialVisualWorkflowEditorState(),
      "approval-ticket",
    ).state;
    const html = renderToStaticMarkup(
      <App
        initialReadState={loadedReadState}
        initialVisualWorkflowEditorState={initialEditorState}
      />,
    );
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Graph validation blocked");
    expect(text).toContain("Missing required approval ticket node");
    expect(text).toContain("Required simulation safety path is incomplete");
    expect(html).toContain('&quot;status&quot;: &quot;invalid&quot;');
    expect(html).not.toContain('&quot;broker&quot;: &quot;fake_broker_only&quot;');
  });

  it("renders the safety posture visibly", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Simulation mode");
    expect(text).toContain("Live trading disabled");
    expect(text).toContain("Broker connectivity not configured");
    expect(text).toContain("Manual approval required");
    expect(text).toContain("Append-only journal");
    expect(text).toContain("Alert delivery local noop");
    expect(text).toContain("Emergency stop active");
    expect(text).toContain("Risk-increasing steps blocked");
    expect(text).toContain("Local development operator");
    expect(text).toContain("human operator 001");
    expect(text).toContain("view operations");
    expect(text).toContain("Approve simulation");
    expect(text).toContain("administer system");
    expect(text).toContain("Admin");
    expect(text).toContain("Approver");
    expect(html).toContain('aria-label="Local operator role"');
    expect(html).toContain('aria-pressed="true"');
  });

  it("renders fail-closed provenance across API-backed operator views", () => {
    const text = renderedText();

    expect(text).toContain("Data provenance");
    expect(text).toContain("Representative");
    expect(text).toContain("Demo");
    expect(text).toContain("Simulated");
    expect(text).toContain("Local only");
    expect(text).toContain("Test double");
    expect(text).toContain("Adapter only");
    expect(text).toContain("Not broker-derived");
    expect(text).toContain("Externally unverified");
    expect(text).toContain("Not an authenticated IBKR paper session");
    expect(text).not.toContain("Externally verified");
    expect(text).not.toContain("Broker-derived");
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

  it("renders API-backed simulation run history and selected node evidence", () => {
    const html = renderToStaticMarkup(
      <App
        initialReadState={loadedReadState}
        initialWorkflowRunInspectionState={loadedWorkflowRunInspectionState}
      />,
    );
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Saved workflow runs");
    expect(text).toContain("Run workflow-run-backend-002");
    expect(text).toContain("First five-minute breakout workflow");
    expect(text).toContain("workflow-backend-001");
    expect(text).toContain("version 4");
    expect(text).toContain("fixture://breakout-session-002");
    expect(text).toContain("ticket-workflow-run-002");
    expect(text).toContain("Deterministic local replay was loaded");
    expect(text).toContain("Manual approval is required");
    expect(text).toContain("Downstream simulation node remains blocked until manual approval");
    expect(text).toContain("journal_sequence:72");
    expect(text).toContain("workflow-run-backend-001");
    expect(html).toContain('name="workflowSimulationRun"');
    expect(text).not.toContain("Fake broker filled");
    expect(text).not.toContain("Protection monitored");
    expect(text).not.toContain("Manual simulation approval recorded");
  });

  it("renders explicit loading, empty, and failed run-history states without a fabricated run", () => {
    const loadingText = renderedText(<App initialReadState={loadedReadState} />);
    const emptyText = renderedText(
      <App
        initialReadState={loadedReadState}
        initialWorkflowRunInspectionState={emptyWorkflowRunInspectionState}
      />,
    );
    const errorText = renderedText(
      <App
        initialReadState={loadedReadState}
        initialWorkflowRunInspectionState={failedWorkflowRunInspectionState}
      />,
    );

    expect(loadingText).toContain("Loading saved workflow simulation runs");
    expect(emptyText).toContain("No saved workflow simulation runs");
    expect(errorText).toContain("Workflow simulation run history is unavailable");
    expect(`${loadingText} ${emptyText} ${errorText}`).not.toContain("Fake broker filled");
    expect(`${loadingText} ${emptyText} ${errorText}`).not.toContain("Protection monitored");
  });

  it("renders an explicit simulation-only execution review for committed approval evidence", () => {
    const html = renderToStaticMarkup(
      <App
        initialReadState={executionReadyReadState}
        initialWorkflowRunInspectionState={approvedWorkflowRunInspectionState}
      />,
    );
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Durable simulation execution");
    expect(text).toContain("SIMULATION ONLY");
    expect(text).toContain("workflow-run-backend-002-approved-decision");
    expect(text).toContain("workflow-run-backend-002-risk");
    expect(text).toContain("workflow-run-backend-002-intent");
    expect(text).toContain("Persisted plan required by passed risk");
    expect(text).toContain("Expected protection is present in the deterministic simulation");
    expect(text).toContain("Review simulation execution");
    for (const forbiddenAction of ["Connect IBKR", "Execute live order", "Send external alert"]) {
      expect(text).not.toContain(forbiddenAction);
    }
  });

  it("renders read-only audit explorer filters and event detail", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Audit explorer");
    expect(text).toContain("Filter audit events");
    expect(html).toContain('name="auditWorkflowId"');
    expect(html).toContain('name="auditRunId"');
    expect(html).toContain('name="auditExecutionId"');
    expect(html).toContain('name="auditEventType"');
    expect(html).toContain('name="auditSymbol"');
    expect(html).toContain('name="auditOrderId"');
    expect(html).toContain('name="auditTicketId"');
    expect(html).toContain('name="auditSeverity"');
    expect(html).toContain('name="auditTimestamp"');
    expect(text).toContain("Matching events");
    expect(text).toContain("Event detail");
    expect(text).toContain("backend.audit.event");
    expect(text).toContain("sim-run-001");
    expect(text).toContain("TSLA");
    expect(text).toContain("order-backend-001");
    expect(text).toContain("ticket-backend-001");
    expect(text).toContain("informational");
  });

  it("renders simulation-only approval inbox forms with idempotency feedback", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Approval inbox");
    expect(text).toContain("Simulation ticket review");
    expect(text).toContain("ticket-backend-001");
    expect(text).toContain("Actor");
    expect(text).toContain("Reason");
    expect(text).toContain("Approve simulation");
    expect(text).toContain("Reject simulation");
    expect(html).toContain("<form");
    expect(html).toContain("<button");
    expect(html).toContain("disabled");
    expect(text).toContain("Approval requires approver");
    expect(text).not.toContain("transmit order");
    expect(text).not.toContain("connect broker");
  });

  it("keeps representative terminal approval tickets visible and non-actionable", () => {
    const terminalStatuses = ["approved", "rejected", "expired", "cancelled"] as const;
    const terminalState: ReadApiLoadState = {
      status: "loaded",
      snapshot: {
        ...backendSnapshot,
        approvalTickets: terminalStatuses.map((status) => ({
          ...backendSnapshot.approvalTickets[0],
          ticket_id: `ticket-${status}-001`,
          status,
        })),
      },
      errorMessage: null,
    };
    const html = renderToStaticMarkup(<App initialReadState={terminalState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    for (const status of terminalStatuses) {
      expect(text).toContain(`ticket-${status}-001`);
      expect(html).not.toContain(`name="ticket-${status}-001-actor"`);
    }
    expect(text).toContain("Historical ticket is terminal and read only");
    expect(html).not.toContain('class="approval-form"');
  });

  it("renders read-only order and position detail pages", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Order detail");
    expect(text).toContain("OMS inspection");
    expect(text).toContain("client-backend-001");
    expect(text).toContain("pending approval");
    expect(text).toContain("0 filled / 5 leaves");
    expect(text).toContain("Linked order audit records");
    expect(text).toContain("backend.audit.event");
    expect(text).toContain("Position detail");
    expect(text).toContain("Protection inspection");
    expect(text).toContain("position-backend-001");
    expect(text).toContain("expected protection present");
    expect(text).toContain("5 TSLA at 210.5");
    expect(text).toContain("Linked position audit records");
    expect(text).not.toContain("broker amendment");
  });

  it("renders durable simulation execution lineage across operator inspection views", () => {
    const html = renderToStaticMarkup(<App initialReadState={projectedExecutionReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Durable execution lineage");
    expect(text).toContain("workflow-projected-001");
    expect(text).toContain("version 3");
    expect(text).toContain("run-projected-001");
    expect(text).toContain("run-projected-001-execution");
    expect(text).toContain("run-projected-001-intent");
    expect(text).toContain("run-projected-001-risk");
    expect(text).toContain("run-projected-001-approval-ticket");
    expect(text).toContain("run-projected-001-approved-decision");
    expect(text).toContain("fake-run-projected-001-client");
    expect(text).toContain("run-projected-001-position");
    expect(text).toContain("missing expected protection");
    expect(text).toContain("alert-run-projected-001-missing-protection");
    expect(text).toContain("journal_sequence:201");
    expect(text).toContain("Fake broker derived");
    expect(text).toContain("Externally unverified");
    expect(text).toContain("Missing expected protection: TSLA");
    expect(text).toContain("critical local alert: Position protection missing");
    for (const forbiddenAction of [
      "Connect IBKR",
      "Transmit order",
      "Execute live order",
      "Send external alert",
      "Production rollout",
    ]) {
      expect(text).not.toContain(forbiddenAction);
    }
  });

  it("renders durable upstream decision lifecycle without generic approval forms", () => {
    const html = renderToStaticMarkup(<App initialReadState={durableDecisionReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Durable decision lineage");
    expect(text).toContain("workflow-projected-001 version 3");
    expect(text).toContain("run-projected-pending");
    expect(text).toContain("run-projected-rejected");
    expect(text).toContain("Waiting for approval");
    expect(text).toContain("Rejected");
    expect(text).toContain("reviewer-operator-002");
    expect(text).toContain("Replay evidence did not satisfy operator review");
    expect(text).toContain("2026-07-22T01:06:00Z");
    expect(text).toContain("signal-run-projected-pending");
    expect(text).toContain("run-projected-pending-intent");
    expect(text).toContain("run-projected-pending-risk");
    expect(text).toContain("run-projected-pending-approval-ticket");
    expect(text).toContain("journal_sequence:301 plus 3 linked");
    expect(text).toContain("Validated local saved-workflow simulation lifecycle evidence");
    expect(text).toContain("Risk decisions");
    expect(text).toContain("Inspect saved run");
    expect(html).not.toContain('name="run-projected-pending-approval-ticket-actor"');
    expect(html).not.toContain('name="run-projected-rejected-approval-ticket-actor"');
    expect(text).not.toContain("Fake broker derived");
    expect(text).not.toContain("Connect IBKR");
    expect(text).not.toContain("Transmit order");
  });

  it("renders read-only protection monitoring dashboard", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Protection monitor");
    expect(text).toContain("Protection monitoring");
    expect(text).toContain("Emergency conditions");
    expect(text).toContain("Expected protection");
    expect(text).toContain("1 position");
    expect(text).toContain("Missing protection");
    expect(text).toContain("0 positions");
    expect(text).toContain("Exception references");
    expect(text).toContain("Critical local alerts");
    expect(text).toContain("Backend protection review");
    expect(text).toContain("position-backend-001");
    expect(text).toContain("expected protection present");
    expect(text).not.toContain("external delivery control");
  });

  it("renders paper-only operator visibility without broker controls", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Paper trading");
    expect(text).toContain("IBKR paper operator");
    expect(text).toContain("Paper only");
    expect(text).toContain("Live trading disabled");
    expect(text).toContain("ibkr paper");
    expect(text).toContain("unknown requires reconciliation");
    expect(text).toContain("Reconciliation required");
    expect(text).toContain("stale callback requires review");
    expect(text).toContain("PARTIALLY_FILLED");
    expect(text).toContain("client-paper-001");
    expect(text).toContain("accepted status update");
    expect(text).toContain("accepted fill update");
    expect(text).toContain("4 filled / 6 leaves");
    expect(text).not.toContain("Connect broker");
    expect(text).not.toContain("Submit live");
    expect(text).not.toContain("Credential");
  });

  it("renders emergency stop visibility without broker or live controls", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Emergency stop");
    expect(text).toContain("Local emergency stop");
    expect(text).toContain("Emergency stop active");
    expect(text).toContain("Risk-increasing steps blocked");
    expect(text).toContain("operator review");
    expect(text).toContain("admin operator 001");
    expect(text).toContain("No broker controls");
    expect(text).not.toContain("Flatten");
    expect(text).not.toContain("Liquidate");
    expect(text).not.toContain("Cancel live");
    expect(text).not.toContain("Enable live trading");
  });

  it("renders operational controls without rollout or external backup controls", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Operational controls");
    expect(text).toContain("Observability");
    expect(text).toContain("Audit retention");
    expect(text).toContain("Backup and restore");
    expect(text).toContain("Incident response");
    expect(text).toContain("system health");
    expect(text).toContain("No destructive retention");
    expect(text).toContain("Append-only journal required");
    expect(text).toContain("Local backup verification");
    expect(text).toContain("No external storage configured");
    expect(text).toContain("No active incident");
    expect(text).toContain("Emergency stop required");
    expect(text).toContain("production rollout not authorized");
    expect(text).not.toContain("Upload backup");
    expect(text).not.toContain("External storage");
    expect(text).not.toContain("Credential");
  });

  it("renders live-readiness evidence without live controls", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Live-readiness evidence");
    expect(text).toContain("Evidence dashboard");
    expect(text).toContain("not ready");
    expect(text).toContain("Live trading disabled");
    expect(text).toContain("External review required");
    expect(text).toContain("Explicit human approval required");
    expect(text).toContain("Paper-trading history evidence");
    expect(text).toContain("Emergency-stop evidence");
    expect(text).toContain("Audit-retention evidence");
    expect(text).toContain("Backup and restore evidence");
    expect(text).toContain("Incident-response evidence");
    expect(text).toContain("External review evidence is missing");
    expect(text).toContain("Operator sign-off evidence is missing");
    expect(text).toContain("Blocking evidence");
    expect(text).toContain("Unverified");
    expect(text).not.toContain("Enable live trading");
    expect(text).not.toContain("Connect broker");
    expect(text).not.toContain("Transmit");
    expect(text).not.toContain("Credential");
  });

  it("renders operator access state without credential controls", () => {
    const html = renderToStaticMarkup(<App initialReadState={loadedReadState} />);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Operator access");
    expect(text).toContain("Local development operator");
    expect(text).toContain("human operator 001");
    expect(text).toContain("admin");
    expect(text).toContain("view operations");
    expect(text).toContain("Approve simulation");
    expect(text).toContain("administer system");
    expect(text).toContain("approver");
    expect(text).toContain("admin approver separated");
    expect(text).not.toContain("Password");
    expect(text).not.toContain("Token");
    expect(text).not.toContain("Sign in");
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
  });
});

const backendSnapshot: OperationsApiSnapshot = {
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
    app_mode: "simulation",
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
      sequence: 900,
      event_type: "backend.audit.event",
      timestamp: "2026-07-08T00:00:00Z",
      summary: "Backend audit event rendered from read API",
      run_id: "sim-run-001",
      symbol: "TSLA",
      order_id: "order-backend-001",
      ticket_id: "ticket-backend-001",
      severity: "informational",
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
  liveReadinessEvidence: safeFallbackOperationsSnapshot.liveReadinessEvidence,
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
      {
        schema_version: 1,
        metric_name: "audit_journal.health",
        metric_value: 1,
        unit: "status",
        status: "ok",
        observed_at: "2026-07-08T00:07:00Z",
        summary: "Append-only journal remains required",
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

const loadedReadState: ReadApiLoadState = {
  status: "loaded",
  snapshot: backendSnapshot,
  errorMessage: null,
};

const loadedWorkflowRunInspectionState: WorkflowRunInspectionState = {
  status: "loaded",
  items: [
    workflowRunItem("workflow-run-backend-002", "2026-07-15T02:00:00Z", 70),
    workflowRunItem("workflow-run-backend-001", "2026-07-15T01:00:00Z", 60),
  ],
  errorMessage: null,
};

const executionReadyReadState: ReadApiLoadState = {
  status: "loaded",
  snapshot: {
    ...backendSnapshot,
    emergencyStop: {
      ...backendSnapshot.emergencyStop,
      active: false,
      status: "inactive",
      blocking_risk_increasing_actions: false,
    },
  },
  errorMessage: null,
};

const projectedAttribution: SimulationExecutionAttributionApiView = {
  schema_version: 1,
  workflow_id: "workflow-projected-001",
  workflow_version: 3,
  run_id: "run-projected-001",
  execution_id: "run-projected-001-execution",
  order_intent_id: "run-projected-001-intent",
  risk_decision_id: "run-projected-001-risk",
  approval_ticket_id: "run-projected-001-approval-ticket",
  approval_decision_id: "run-projected-001-approved-decision",
  order_id: "run-projected-001-order",
  fill_reference: "fake-run-projected-001-client",
  position_id: "run-projected-001-position",
  protection_status: "missing_expected_protection",
  expected_protection_kind: "stop_loss",
  risk_increasing_actions_blocked: true,
  alert_id: "alert-run-projected-001-missing-protection",
  journal_references: ["journal_sequence:201", "journal_sequence:202"],
  execution_journal_references: ["journal_sequence:201", "journal_sequence:202"],
  evidence_source: "schema_v4_sqlite_digest_bound_jsonl",
  classifications: [
    "simulated",
    "local_only",
    "fake_broker_derived",
    "externally_unverified",
  ],
  broker_derived: false,
  externally_verified: false,
};

const pendingDecisionAttribution: SimulationDecisionAttributionApiView = {
  schema_version: 1,
  workflow_id: "workflow-projected-001",
  workflow_version: 3,
  run_id: "run-projected-pending",
  run_status: "waiting_for_approval",
  signal_id: "signal-run-projected-pending",
  order_intent_id: "run-projected-pending-intent",
  risk_decision_id: "run-projected-pending-risk",
  approval_ticket_id: "run-projected-pending-approval-ticket",
  approval_decision_id: null,
  approval_decision: null,
  approval_actor: null,
  approval_reason: null,
  approval_decided_at: null,
  signal_journal_reference: "journal_sequence:301",
  order_intent_journal_reference: "journal_sequence:302",
  risk_journal_reference: "journal_sequence:303",
  approval_ticket_journal_reference: "journal_sequence:304",
  approval_decision_journal_reference: null,
  journal_references: [
    "journal_sequence:301",
    "journal_sequence:302",
    "journal_sequence:303",
    "journal_sequence:304",
  ],
  evidence_source: "schema_v4_sqlite_digest_bound_jsonl",
  classifications: ["simulated", "local_only", "externally_unverified"],
  broker_derived: false,
  externally_verified: false,
};

const rejectedDecisionAttribution: SimulationDecisionAttributionApiView = {
  ...pendingDecisionAttribution,
  run_id: "run-projected-rejected",
  run_status: "rejected",
  signal_id: "signal-run-projected-rejected",
  order_intent_id: "run-projected-rejected-intent",
  risk_decision_id: "run-projected-rejected-risk",
  approval_ticket_id: "run-projected-rejected-approval-ticket",
  approval_decision_id: "run-projected-rejected-decision",
  approval_decision: "rejected",
  approval_actor: "reviewer-operator-002",
  approval_reason: "Replay evidence did not satisfy operator review",
  approval_decided_at: "2026-07-22T01:06:00Z",
  signal_journal_reference: "journal_sequence:311",
  order_intent_journal_reference: "journal_sequence:312",
  risk_journal_reference: "journal_sequence:313",
  approval_ticket_journal_reference: "journal_sequence:314",
  approval_decision_journal_reference: "journal_sequence:315",
  journal_references: [
    "journal_sequence:311",
    "journal_sequence:312",
    "journal_sequence:313",
    "journal_sequence:314",
    "journal_sequence:315",
  ],
};

const executedDecisionAttribution: SimulationDecisionAttributionApiView = {
  ...pendingDecisionAttribution,
  run_id: projectedAttribution.run_id,
  run_status: "executed_protection_missing",
  signal_id: "signal-run-projected-001",
  order_intent_id: projectedAttribution.order_intent_id,
  risk_decision_id: projectedAttribution.risk_decision_id,
  approval_ticket_id: projectedAttribution.approval_ticket_id,
  approval_decision_id: projectedAttribution.approval_decision_id,
  approval_decision: "approved",
  approval_actor: "reviewer-operator-001",
  approval_reason: "Deterministic simulation evidence reviewed",
  approval_decided_at: "2026-07-22T00:06:00Z",
  signal_journal_reference: "journal_sequence:197",
  order_intent_journal_reference: "journal_sequence:198",
  risk_journal_reference: "journal_sequence:199",
  approval_ticket_journal_reference: "journal_sequence:200",
  approval_decision_journal_reference: "journal_sequence:201",
  journal_references: [
    "journal_sequence:197",
    "journal_sequence:198",
    "journal_sequence:199",
    "journal_sequence:200",
    "journal_sequence:201",
    "journal_sequence:202",
  ],
};

const durableDecisionReadState: ReadApiLoadState = {
  status: "loaded",
  snapshot: {
    ...backendSnapshot,
    provenance: {
      ...backendSnapshot.provenance,
      ...Object.fromEntries(
        (
          [
            "audit_events",
            "signals",
            "risk_decisions",
            "approval_tickets",
            "orders",
            "positions",
            "alerts",
          ] as const
        ).map((resource) => [
          resource,
          {
            schema_version: 1 as const,
            resource,
            source: "durable_saved_workflow_simulation",
            classifications: pendingDecisionAttribution.classifications,
            broker_derived: false as const,
            externally_verified: false as const,
            summary: "Validated local saved-workflow simulation lifecycle evidence",
          },
        ]),
      ),
    },
    auditEvents: [
      {
        ...backendSnapshot.auditEvents[0],
        sequence: 301,
        event_type: "strategy.signal.generated",
        run_id: pendingDecisionAttribution.run_id,
        order_id: pendingDecisionAttribution.order_intent_id,
        ticket_id: pendingDecisionAttribution.approval_ticket_id,
        decision_attribution: pendingDecisionAttribution,
      },
      {
        ...backendSnapshot.auditEvents[0],
        sequence: 315,
        event_type: "approval.ticket.rejected",
        run_id: rejectedDecisionAttribution.run_id,
        order_id: rejectedDecisionAttribution.order_intent_id,
        ticket_id: rejectedDecisionAttribution.approval_ticket_id,
        decision_attribution: rejectedDecisionAttribution,
      },
    ],
    signals: [pendingDecisionAttribution, rejectedDecisionAttribution].map((attribution) => ({
      schema_version: 1 as const,
      signal_id: attribution.signal_id,
      strategy_id: "first-five-minute-breakout",
      symbol: "TSLA",
      signal: "long_entry_candidate" as const,
      reason: "breakout_and_volume_confirmed",
      bar_start_timestamp: "2026-07-22T01:00:00Z",
      bar_end_timestamp: "2026-07-22T01:05:00Z",
      decision_attribution: attribution,
    })),
    riskDecisions: [pendingDecisionAttribution, rejectedDecisionAttribution].map(
      (attribution) => ({
        schema_version: 1 as const,
        request_id: attribution.risk_decision_id,
        evaluated_at: "2026-07-22T01:05:00Z",
        symbol: "TSLA",
        risk_intent: "increase" as const,
        result: "passed" as const,
        failed_check_names: [],
        decision_attribution: attribution,
      }),
    ),
    approvalTickets: [
      {
        schema_version: 1,
        ticket_id: pendingDecisionAttribution.approval_ticket_id,
        order_id: pendingDecisionAttribution.order_intent_id,
        symbol: "TSLA",
        side: "buy",
        quantity: 5,
        status: "pending",
        risk_decision_id: pendingDecisionAttribution.risk_decision_id,
        created_at: "2026-07-22T01:05:00Z",
        expires_at: "2026-07-22T01:15:00Z",
        decision_attribution: pendingDecisionAttribution,
      },
      {
        schema_version: 1,
        ticket_id: rejectedDecisionAttribution.approval_ticket_id,
        order_id: rejectedDecisionAttribution.order_intent_id,
        symbol: "TSLA",
        side: "buy",
        quantity: 5,
        status: "rejected",
        risk_decision_id: rejectedDecisionAttribution.risk_decision_id,
        created_at: "2026-07-22T01:05:00Z",
        expires_at: "2026-07-22T01:15:00Z",
        decision_attribution: rejectedDecisionAttribution,
      },
    ],
    orders: [],
    positions: [],
    alerts: [],
  },
  errorMessage: null,
};

const projectedExecutionReadState: ReadApiLoadState = {
  status: "loaded",
  snapshot: {
    ...backendSnapshot,
    provenance: {
      ...backendSnapshot.provenance,
      ...Object.fromEntries(
        [
          ...(["audit_events", "signals", "risk_decisions", "approval_tickets"] as const).map(
            (resource) => [
              resource,
              {
                schema_version: 1 as const,
                resource,
                source: "durable_saved_workflow_simulation",
                classifications: executedDecisionAttribution.classifications,
                broker_derived: false as const,
                externally_verified: false as const,
                summary: "Validated local saved-workflow simulation lifecycle evidence",
              },
            ],
          ),
          ...(["orders", "positions", "alerts"] as const).map((resource) => [
            resource,
            {
              schema_version: 1 as const,
              resource,
              source: "durable_saved_workflow_simulation_execution",
              classifications: projectedAttribution.classifications,
              broker_derived: false as const,
              externally_verified: false as const,
              summary: "Validated local saved-workflow simulation execution evidence",
            },
          ]),
        ],
      ),
    },
    signals: [
      {
        ...backendSnapshot.signals[0],
        signal_id: executedDecisionAttribution.signal_id,
        signal: "long_entry_candidate",
        decision_attribution: executedDecisionAttribution,
      },
    ],
    riskDecisions: [
      {
        ...backendSnapshot.riskDecisions[0],
        request_id: executedDecisionAttribution.risk_decision_id,
        result: "passed",
        failed_check_names: [],
        decision_attribution: executedDecisionAttribution,
      },
    ],
    approvalTickets: [
      {
        ...backendSnapshot.approvalTickets[0],
        ticket_id: executedDecisionAttribution.approval_ticket_id,
        order_id: executedDecisionAttribution.order_intent_id,
        risk_decision_id: executedDecisionAttribution.risk_decision_id,
        status: "approved",
        decision_attribution: executedDecisionAttribution,
      },
    ],
    orders: [
      {
        ...backendSnapshot.orders[0],
        order_id: projectedAttribution.order_id,
        client_order_id: "run-projected-001-client",
        state: "FILLED",
        risk_decision_id: projectedAttribution.risk_decision_id,
        approval_reference: "run-projected-001-manual-review",
        cumulative_filled_quantity: 5,
        leaves_quantity: 0,
        execution_attribution: projectedAttribution,
      },
    ],
    positions: [
      {
        ...backendSnapshot.positions[0],
        position_id: projectedAttribution.position_id,
        protection_status: "missing_expected_protection",
        source: "durable_saved_workflow_simulation",
        execution_attribution: projectedAttribution,
      },
    ],
    alerts: [
      {
        ...backendSnapshot.alerts[0],
        alert_id: projectedAttribution.alert_id,
        severity: "critical",
        title: "Position protection missing",
        source_event_reference: "journal_sequence:201",
        execution_attribution: projectedAttribution,
      },
    ],
    auditEvents: [
      {
        ...backendSnapshot.auditEvents[0],
        sequence: 201,
        event_type: "workflow_simulation.execution_completed",
        run_id: projectedAttribution.run_id,
        order_id: projectedAttribution.order_id,
        ticket_id: projectedAttribution.approval_ticket_id,
        severity: "critical",
        decision_attribution: executedDecisionAttribution,
        execution_attribution: projectedAttribution,
      },
    ],
  },
  errorMessage: null,
};

const approvedWorkflowRun = workflowRunItem(
  "workflow-run-backend-002",
  "2026-07-15T02:00:00Z",
  70,
);

const approvedWorkflowRunInspectionState: WorkflowRunInspectionState = {
  status: "loaded",
  items: [
    {
      ...approvedWorkflowRun,
      run: {
        ...approvedWorkflowRun.run,
        status: "approved_not_executed",
        approval_decision: {
          schema_version: 1,
          decision_id: "workflow-run-backend-002-approved-decision",
          ticket_id: "ticket-workflow-run-002",
          previous_status: "pending",
          new_status: "approved",
          decided_at: "2026-07-15T02:01:00Z",
          actor: "approver-operator-001",
          decision_reference: "workflow-run-backend-002-manual-review",
          reason: "operator_reviewed_simulation_evidence",
          request: {},
          ticket: {},
        },
        execution: null,
      },
    },
  ],
  errorMessage: null,
};

const emptyWorkflowRunInspectionState: WorkflowRunInspectionState = {
  status: "loaded",
  items: [],
  errorMessage: null,
};

const failedWorkflowRunInspectionState: WorkflowRunInspectionState = {
  status: "error",
  items: [],
  errorMessage: "Workflow simulation run history is unavailable",
};

function workflowRunItem(runId: string, updatedAt: string, journalSequence: number) {
  return {
    key: `workflow-backend-001::${runId}`,
    workflowId: "workflow-backend-001",
    workflowName: "First five-minute breakout workflow",
    workflowVersion: 4,
    run: {
      schema_version: 1 as const,
      workflow_id: "workflow-backend-001",
      expected_workflow_version: 4,
      run_id: runId,
      status: "waiting_for_approval" as const,
      created_at: updatedAt,
      updated_at: updatedAt,
      approval_ticket_id: runId.endsWith("002") ? "ticket-workflow-run-002" : "ticket-workflow-run-001",
      simulation_run: {
        schema_version: 1 as const,
        run_id: runId,
        status: "waiting_for_approval",
        created_at: updatedAt,
        updated_at: updatedAt,
        replay_input_reference: runId.endsWith("002")
          ? "fixture://breakout-session-002"
          : "fixture://breakout-session-001",
        journal_references: [`journal_sequence:${journalSequence}`],
      },
      node_statuses: [
        {
          schema_version: 1 as const,
          node_id: "replay-source",
          node_type: "replay_source",
          status: "completed",
          detail: "Deterministic local replay was loaded",
          journal_reference: `journal_sequence:${journalSequence + 1}`,
        },
        {
          schema_version: 1 as const,
          node_id: "approval-ticket",
          node_type: "approval_ticket",
          status: "waiting_for_approval",
          detail: "Manual approval is required",
          journal_reference: `journal_sequence:${journalSequence + 2}`,
        },
        {
          schema_version: 1 as const,
          node_id: "fake-broker",
          node_type: "fake_broker",
          status: "blocked_waiting_for_approval",
          detail: "Downstream simulation node remains blocked until manual approval",
          journal_reference: `journal_sequence:${journalSequence + 3}`,
        },
      ],
      journal_references: [
        `journal_sequence:${journalSequence + 1}`,
        `journal_sequence:${journalSequence + 2}`,
        `journal_sequence:${journalSequence + 3}`,
      ],
    },
  };
}
