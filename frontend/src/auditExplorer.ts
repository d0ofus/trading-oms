import type { AuditEventApiView } from "./readApiClient";

export type AuditExplorerFilterState = {
  workflowId: string;
  runId: string;
  executionId: string;
  eventType: string;
  symbol: string;
  orderId: string;
  ticketId: string;
  severity: string;
  timestamp: string;
};

export const defaultAuditExplorerFilters: AuditExplorerFilterState = {
  workflowId: "",
  runId: "",
  executionId: "",
  eventType: "",
  symbol: "",
  orderId: "",
  ticketId: "",
  severity: "",
  timestamp: "",
};

const unsafeAuditTextFragments = [
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

export function filterAuditEvents(
  events: AuditEventApiView[],
  filters: AuditExplorerFilterState,
) {
  return events.filter((event) => {
    return (
      matchesFilter(event.execution_attribution?.workflow_id, filters.workflowId) &&
      matchesFilter(event.run_id, filters.runId) &&
      matchesFilter(event.execution_attribution?.execution_id, filters.executionId) &&
      matchesFilter(event.event_type, filters.eventType) &&
      matchesFilter(event.symbol, filters.symbol) &&
      matchesFilter(event.order_id, filters.orderId) &&
      matchesFilter(event.ticket_id, filters.ticketId) &&
      matchesFilter(event.severity, filters.severity) &&
      matchesFilter(event.timestamp, filters.timestamp)
    );
  });
}

export function safeAuditDisplayText(value: string | null | undefined) {
  if (!value) {
    return "not recorded";
  }
  const normalized = value.toLowerCase().replaceAll("-", "_");
  if (unsafeAuditTextFragments.some((fragment) => normalized.includes(fragment))) {
    return "[redacted unsafe audit text]";
  }
  return value;
}

function matchesFilter(value: string | null | undefined, filter: string) {
  const normalizedFilter = filter.trim().toLowerCase();
  if (!normalizedFilter) {
    return true;
  }
  return (value ?? "").toLowerCase().includes(normalizedFilter);
}
