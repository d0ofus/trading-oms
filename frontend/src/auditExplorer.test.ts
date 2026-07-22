import { describe, expect, it } from "vitest";

import {
  defaultAuditExplorerFilters,
  filterAuditEvents,
  safeAuditDisplayText,
  type AuditExplorerFilterState,
} from "./auditExplorer";
import type { AuditEventApiView } from "./readApiClient";

describe("auditExplorer", () => {
  it("filters audit events by run, event type, symbol, order, ticket, severity, and timestamp", () => {
    const filters: AuditExplorerFilterState = {
      workflowId: "workflow-001",
      runId: "run-001",
      executionId: "execution-001",
      eventType: "risk.decision.evaluated",
      symbol: "AAPL",
      orderId: "order-001",
      ticketId: "ticket-001",
      severity: "warning",
      timestamp: "2026-07-08T13:45",
    };

    expect(filterAuditEvents(auditEvents, filters)).toEqual([auditEvents[0]]);
  });

  it("returns all events when filters are empty", () => {
    expect(filterAuditEvents(auditEvents, defaultAuditExplorerFilters)).toEqual(auditEvents);
  });

  it("redacts secret-shaped audit text before rendering", () => {
    expect(safeAuditDisplayText("normal audit summary")).toBe("normal audit summary");
    expect(safeAuditDisplayText("token=redacted")).toBe("[redacted unsafe audit text]");
    expect(safeAuditDisplayText("api_key: redacted")).toBe("[redacted unsafe audit text]");
    expect(safeAuditDisplayText(null)).toBe("not recorded");
  });
});

const auditEvents: AuditEventApiView[] = [
  {
    schema_version: 1,
    sequence: 1,
    event_type: "risk.decision.evaluated",
    timestamp: "2026-07-08T13:45:10Z",
    summary: "Risk decision evaluated",
    run_id: "run-001",
    symbol: "AAPL",
    order_id: "order-001",
    ticket_id: "ticket-001",
    severity: "warning",
    execution_attribution: {
      schema_version: 1,
      workflow_id: "workflow-001",
      workflow_version: 4,
      run_id: "run-001",
      execution_id: "execution-001",
      order_intent_id: "intent-001",
      risk_decision_id: "risk-001",
      approval_ticket_id: "ticket-001",
      approval_decision_id: "approval-001",
      order_id: "order-001",
      fill_reference: "fake-fill-001",
      position_id: "position-001",
      protection_status: "expected_protection_present",
      expected_protection_kind: "protective_stop",
      risk_increasing_actions_blocked: false,
      alert_id: "alert-001",
      journal_references: ["journal_sequence:1", "journal_sequence:2"],
      execution_journal_references: ["journal_sequence:2"],
      evidence_source: "schema_v4_sqlite_digest_bound_jsonl",
      classifications: [
        "simulated",
        "local_only",
        "fake_broker_derived",
        "externally_unverified",
      ],
      broker_derived: false,
      externally_verified: false,
    },
  },
  {
    schema_version: 1,
    sequence: 2,
    event_type: "alert.intent.created",
    timestamp: "2026-07-08T13:46:10Z",
    summary: "Protection review required",
    run_id: "run-002",
    symbol: "MSFT",
    order_id: "order-002",
    ticket_id: "ticket-002",
    severity: "critical",
  },
];
