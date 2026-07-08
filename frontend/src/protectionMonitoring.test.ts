import { describe, expect, it } from "vitest";

import type { AlertApiView, AuditEventApiView, PositionApiView } from "./readApiClient";
import {
  buildProtectionMonitoringView,
  safeProtectionMonitoringText,
} from "./protectionMonitoring";

describe("protectionMonitoring", () => {
  it("classifies protected, missing, and exception positions", () => {
    const view = buildProtectionMonitoringView(positions, alerts, auditEvents);

    expect(view.protectedPositions.map((item) => item.position.position_id)).toEqual([
      "position-protected",
    ]);
    expect(view.unprotectedPositions.map((item) => item.position.position_id)).toEqual([
      "position-missing",
    ]);
    expect(view.exceptionPositions.map((item) => item.position.position_id)).toEqual([
      "position-review",
      "position-not-required",
    ]);
    expect(view.summary.missingProtection).toBe(1);
    expect(view.summary.exceptions).toBe(2);
  });

  it("links critical alerts and emergency conditions", () => {
    const view = buildProtectionMonitoringView(positions, alerts, auditEvents);

    expect(view.criticalAlerts.map((alert) => alert.alert_id)).toEqual([
      "alert-missing",
      "alert-emergency",
    ]);
    expect(view.emergencyConditions).toEqual([
      "Missing expected protection: TSLA",
      "critical local alert: Missing protection alert",
      "emergency local alert: Emergency review alert",
    ]);
    expect(view.unprotectedPositions[0]?.linkedAlerts.map((alert) => alert.alert_id)).toEqual([
      "alert-missing",
    ]);
  });

  it("redacts unsafe dashboard text", () => {
    expect(safeProtectionMonitoringText("position-001")).toBe("position-001");
    expect(safeProtectionMonitoringText("secret=value")).toBe("[redacted unsafe protection text]");
    expect(safeProtectionMonitoringText("token: value")).toBe("[redacted unsafe protection text]");
  });
});

const positions: PositionApiView[] = [
  {
    schema_version: 1,
    position_id: "position-protected",
    symbol: "AAPL",
    quantity: 10,
    average_price: 100,
    protection_status: "expected_protection_present",
    updated_at: "2026-07-08T00:00:00Z",
    source: "simulation",
  },
  {
    schema_version: 1,
    position_id: "position-missing",
    symbol: "TSLA",
    quantity: 5,
    average_price: 210.5,
    protection_status: "missing_expected_protection",
    updated_at: "2026-07-08T00:01:00Z",
    source: "simulation",
  },
  {
    schema_version: 1,
    position_id: "position-review",
    symbol: "MSFT",
    quantity: 3,
    average_price: 310.25,
    protection_status: "review_required",
    updated_at: "2026-07-08T00:02:00Z",
    source: "simulation",
  },
  {
    schema_version: 1,
    position_id: "position-not-required",
    symbol: "CASH",
    quantity: 1,
    average_price: 1,
    protection_status: "not_required",
    updated_at: "2026-07-08T00:03:00Z",
    source: "simulation",
  },
];

const alerts: AlertApiView[] = [
  {
    schema_version: 1,
    alert_id: "alert-missing",
    severity: "critical",
    channel: "local",
    status: "recorded",
    title: "Missing protection alert",
    created_at: "2026-07-08T00:04:00Z",
    source_event_reference: "position-missing",
  },
  {
    schema_version: 1,
    alert_id: "alert-emergency",
    severity: "emergency",
    channel: "local",
    status: "recorded",
    title: "Emergency review alert",
    created_at: "2026-07-08T00:05:00Z",
    source_event_reference: "position-review",
  },
  {
    schema_version: 1,
    alert_id: "alert-info",
    severity: "informational",
    channel: "local",
    status: "recorded",
    title: "Informational alert",
    created_at: "2026-07-08T00:06:00Z",
    source_event_reference: "position-protected",
  },
];

const auditEvents: AuditEventApiView[] = [
  {
    schema_version: 1,
    sequence: 1,
    event_type: "position.protection",
    timestamp: "2026-07-08T00:04:00Z",
    summary: "Protection missing",
    run_id: "sim-run-001",
    symbol: "TSLA",
    order_id: null,
    ticket_id: null,
    severity: "critical",
  },
];
