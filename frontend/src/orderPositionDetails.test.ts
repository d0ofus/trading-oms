import { describe, expect, it } from "vitest";

import type { AuditEventApiView, OrderApiView, PositionApiView } from "./readApiClient";
import {
  buildOrderDetailView,
  buildPositionDetailView,
  safeOrderPositionDetailText,
} from "./orderPositionDetails";

describe("orderPositionDetails", () => {
  it("builds read-only order detail with fill and linked audit records", () => {
    const detail = buildOrderDetailView(order, auditEvents);

    expect(detail?.stateLabel).toBe("pending approval");
    expect(detail?.fillLabel).toBe("0 filled / 5 leaves");
    expect(detail?.linkedAuditEvents.map((event) => event.sequence)).toEqual([7]);
  });

  it("builds read-only position detail with protection state and linked audit records", () => {
    const detail = buildPositionDetailView(position, auditEvents);

    expect(detail?.protectionLabel).toBe("expected protection present");
    expect(detail?.quantityLabel).toBe("5 TSLA at 210.5");
    expect(detail?.linkedAuditEvents.map((event) => event.sequence)).toEqual([7, 8, 9]);
  });

  it("redacts unsafe order and position detail text", () => {
    expect(safeOrderPositionDetailText("order-001")).toBe("order-001");
    expect(safeOrderPositionDetailText("secret=value")).toBe("[redacted unsafe detail text]");
    expect(safeOrderPositionDetailText("token: value")).toBe("[redacted unsafe detail text]");
  });
});

const order: OrderApiView = {
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
};

const position: PositionApiView = {
  schema_version: 1,
  position_id: "position-backend-001",
  symbol: "TSLA",
  quantity: 5,
  average_price: 210.5,
  protection_status: "expected_protection_present",
  updated_at: "2026-07-08T00:03:00Z",
  source: "simulation",
};

const auditEvents: AuditEventApiView[] = [
  {
    schema_version: 1,
    sequence: 7,
    event_type: "order.transition",
    timestamp: "2026-07-08T00:02:00Z",
    summary: "Order moved to pending approval",
    run_id: "sim-run-001",
    symbol: "TSLA",
    order_id: "order-backend-001",
    ticket_id: "ticket-backend-001",
    severity: "informational",
  },
  {
    schema_version: 1,
    sequence: 8,
    event_type: "position.protection",
    timestamp: "2026-07-08T00:03:00Z",
    summary: "Protection present",
    run_id: "sim-run-001",
    symbol: "TSLA",
    order_id: null,
    ticket_id: null,
    severity: "informational",
  },
  {
    schema_version: 1,
    sequence: 9,
    event_type: "audit.note",
    timestamp: "2026-07-08T00:04:00Z",
    summary: "Symbol-level audit note",
    run_id: "sim-run-001",
    symbol: "TSLA",
    order_id: null,
    ticket_id: null,
    severity: "warning",
  },
  {
    schema_version: 1,
    sequence: 10,
    event_type: "unrelated",
    timestamp: "2026-07-08T00:05:00Z",
    summary: "Unrelated event",
    run_id: "sim-run-002",
    symbol: "MSFT",
    order_id: "other-order",
    ticket_id: null,
    severity: "informational",
  },
];
