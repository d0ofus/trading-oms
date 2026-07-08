import type { AuditEventApiView, OrderApiView, PositionApiView } from "./readApiClient";

export type OrderDetailView = {
  order: OrderApiView;
  stateLabel: string;
  fillLabel: string;
  reconciliationLabel: string;
  linkedAuditEvents: AuditEventApiView[];
};

export type PositionDetailView = {
  position: PositionApiView;
  protectionLabel: string;
  quantityLabel: string;
  linkedAuditEvents: AuditEventApiView[];
};

const unsafeDetailTextFragments = [
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

export function buildOrderDetailView(
  order: OrderApiView | null | undefined,
  auditEvents: AuditEventApiView[],
): OrderDetailView | null {
  if (!order) {
    return null;
  }

  return {
    order,
    stateLabel: formatIdentifier(order.state),
    fillLabel: `${order.cumulative_filled_quantity} filled / ${order.leaves_quantity} leaves`,
    reconciliationLabel: order.requires_reconciliation
      ? "reconciliation required"
      : "reconciliation clean",
    linkedAuditEvents: auditEvents.filter((event) => event.order_id === order.order_id),
  };
}

export function buildPositionDetailView(
  position: PositionApiView | null | undefined,
  auditEvents: AuditEventApiView[],
): PositionDetailView | null {
  if (!position) {
    return null;
  }

  return {
    position,
    protectionLabel: formatIdentifier(position.protection_status),
    quantityLabel: `${position.quantity} ${position.symbol} at ${position.average_price}`,
    linkedAuditEvents: auditEvents.filter((event) => event.symbol === position.symbol),
  };
}

export function safeOrderPositionDetailText(value: string | null | undefined) {
  if (!value) {
    return "not recorded";
  }
  const normalized = value.toLowerCase().replaceAll("-", "_");
  if (unsafeDetailTextFragments.some((fragment) => normalized.includes(fragment))) {
    return "[redacted unsafe detail text]";
  }
  return value;
}

function formatIdentifier(value: string) {
  return value.toLowerCase().replace(/[_-]+/g, " ");
}
