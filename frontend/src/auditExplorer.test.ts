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
      runId: "run-001",
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
