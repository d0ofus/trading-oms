import type { AlertApiView, AuditEventApiView, PositionApiView } from "./readApiClient";

export type ProtectionPositionView = {
  position: PositionApiView;
  statusLabel: string;
  exceptionReference: string;
  linkedAlerts: AlertApiView[];
  linkedAuditEvents: AuditEventApiView[];
};

export type ProtectionMonitoringView = {
  positionViews: ProtectionPositionView[];
  protectedPositions: ProtectionPositionView[];
  unprotectedPositions: ProtectionPositionView[];
  exceptionPositions: ProtectionPositionView[];
  criticalAlerts: AlertApiView[];
  emergencyConditions: string[];
  summary: {
    protected: number;
    missingProtection: number;
    exceptions: number;
    criticalAlerts: number;
  };
};

const unsafeProtectionTextFragments = [
  "api_key",
  "authorization:",
  "bearer ",
  "credential",
  "password:",
  "password=",
  "private_key",
  "secret:",
  "secret=",
  "token:",
  "token=",
];

export function buildProtectionMonitoringView(
  positions: PositionApiView[],
  alerts: AlertApiView[],
  auditEvents: AuditEventApiView[],
): ProtectionMonitoringView {
  const positionViews = positions.map((position) => {
    return {
      position,
      statusLabel: formatIdentifier(position.protection_status),
      exceptionReference: buildExceptionReference(position),
      linkedAlerts: alerts.filter((alert) =>
        position.execution_attribution
          ? alert.execution_attribution?.position_id === position.position_id
          : alert.source_event_reference === position.position_id,
      ),
      linkedAuditEvents: auditEvents.filter((event) =>
        position.execution_attribution
          ? event.execution_attribution?.position_id === position.position_id
          : event.symbol === position.symbol,
      ),
    };
  });
  const protectedPositions = positionViews.filter(
    (view) => view.position.protection_status === "expected_protection_present",
  );
  const unprotectedPositions = positionViews.filter(
    (view) => view.position.protection_status === "missing_expected_protection",
  );
  const exceptionPositions = positionViews.filter((view) =>
    ["not_required", "review_required"].includes(view.position.protection_status),
  );
  const criticalAlerts = alerts.filter((alert) =>
    ["critical", "emergency"].includes(alert.severity),
  );

  return {
    positionViews,
    protectedPositions,
    unprotectedPositions,
    exceptionPositions,
    criticalAlerts,
    emergencyConditions: [
      ...unprotectedPositions.map(
        (view) => `Missing expected protection: ${view.position.symbol}`,
      ),
      ...criticalAlerts.map(
        (alert) => `${alert.severity} local alert: ${safeProtectionMonitoringText(alert.title)}`,
      ),
    ],
    summary: {
      protected: protectedPositions.length,
      missingProtection: unprotectedPositions.length,
      exceptions: exceptionPositions.length,
      criticalAlerts: criticalAlerts.length,
    },
  };
}

export function safeProtectionMonitoringText(value: string | null | undefined) {
  if (!value) {
    return "not recorded";
  }
  const normalized = value.toLowerCase().replaceAll("-", "_");
  if (unsafeProtectionTextFragments.some((fragment) => normalized.includes(fragment))) {
    return "[redacted unsafe protection text]";
  }
  return value;
}

function buildExceptionReference(position: PositionApiView) {
  if (position.protection_status === "expected_protection_present") {
    return "not required";
  }
  if (position.protection_status === "missing_expected_protection") {
    return "not recorded";
  }
  return `${position.position_id}-${position.protection_status}`;
}

function formatIdentifier(value: string) {
  return value.toLowerCase().replace(/[_-]+/g, " ");
}
