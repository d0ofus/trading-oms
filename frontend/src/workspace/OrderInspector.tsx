import { useEffect, useState } from "react";
import {
  api,
  localTime,
  money,
  titleCase,
  type Json,
  type Order,
  type Run,
} from "./api";
import { Badge, Grid, Modal } from "./components";
import { protectionStatus } from "./protectionStatus";

type Detail = {
  fx_allocation?: {
    quantity: string;
    flows: Record<string, string>;
    fees: Record<string, string>;
  };
  commissions?: ({
    execution_id: string;
    currency: string;
    amount: string;
  } | null)[];
  fx_protection?: { stop: string; type: string };
  stock_protection?: { stop: string; type: string; currency: string };
  order: Order;
  run: Run | null;
  executions: {
    execution_id: string;
    side: string;
    quantity: string;
    price: string;
  }[];
  broker_observations: (Record<string, Json> | null)[];
  timeline: {
    timestamp: string;
    type: string;
    payload: Record<string, Json>;
  }[];
};

export function OrderInspector({
  identity,
  close,
}: {
  identity: string | null;
  close: () => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setDetail(null);
    if (!identity) return;
    let active = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const value = await api<Detail>(
          `/operations/orders/${identity}`,
          "GET",
          undefined,
          controller.signal,
        );
        if (active) {
          setDetail(value);
          setError("");
        }
      } catch (issue) {
        if (active) setError((issue as Error).message);
      }
      if (active) timer = setTimeout(() => void load(), 2000);
    }
    void load();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [identity]);
  const current = detail?.order.id === identity ? detail : null;
  return (
    <Modal
      open={!!identity}
      onOpenChange={(open) => {
        if (!open) close();
      }}
      title={
        current
          ? `${current.order.payload.symbol} · ${titleCase(current.order.payload.purpose ?? "entry")}`
          : "Order details"
      }
      description="Durable intent, broker observations, executions and the original session authorization."
      wide
    >
      {error && (
        <p role="alert">{error} Last known observations remain visible.</p>
      )}
      {!current && <p>Loading order history…</p>}
      {current && (
        <>
          <Badge
            tone={current.order.state === "unknown" ? "danger" : "neutral"}
          >
            {current.order.diagnostics?.rejection
              ? "Broker rejected"
              : (current.order.diagnostics?.status_label ??
                titleCase(current.order.state))}
          </Badge>
          {current.order.diagnostics?.rejection && (
            <p>{current.order.diagnostics.status_label}</p>
          )}
          {current.order.diagnostics?.acknowledgment_pending && (
            <p role="status">
              Pending acknowledgment does not confirm acceptance or a fill. Risk
              remains reserved; the application will not resend this order.
            </p>
          )}
          {current.order.diagnostics?.status_conflict && (
            <p role="alert">
              Conflicting broker status requires fresh reconciliation.
            </p>
          )}
          {current.order.diagnostics?.warning && (
            <p>
              Broker message {current.order.diagnostics.warning.code}:{" "}
              {titleCase(current.order.diagnostics.warning.state)}.{" "}
              {current.order.diagnostics.warning.detail}
            </p>
          )}
          {current.order.diagnostics?.quantity_evidence?.basis ===
            "accepted_quantity_and_executions" && (
            <p>
              Completed callback quantity:{" "}
              {current.order.diagnostics.quantity_evidence.reported}. Verified
              filled order quantity:{" "}
              {current.order.diagnostics.quantity_evidence.effective}, matched
              to accepted order and executions.
            </p>
          )}
          {current.order.diagnostics?.rejection && (
            <section aria-label="Broker rejection">
              <h3>
                Broker rejection {current.order.diagnostics.rejection.code}
              </h3>
              <p>{current.order.diagnostics.rejection.detail}</p>
              <p>
                {current.order.diagnostics.rejection.available
                  ? `Reason: ${titleCase(current.order.diagnostics.rejection.category)}`
                  : "Specific rejection explanation unavailable"}
              </p>
              <p>
                Recovery acknowledgment does not establish that the broker will
                accept another order.
              </p>
            </section>
          )}
          <dl className="ws-facts">
            {current.order.diagnostics && (
              <>
                <dt>Broker status</dt>
                <dd>
                  {current.order.diagnostics.broker_status ??
                    "Awaiting first broker observation"}
                </dd>
                {current.order.diagnostics.identity_status !==
                  "not_evaluated" && (
                  <>
                    <dt>Order identity</dt>
                    <dd>
                      {current.order.diagnostics.identity_status === "verified"
                        ? "Verified against durable intent"
                        : current.order.diagnostics.identity_status ===
                            "mismatch"
                          ? "Broker order details differ from durable intent; reconciliation required"
                          : "Awaiting complete broker order details"}
                    </dd>
                  </>
                )}
                {current.order.diagnostics.cancellation_detail && (
                  <>
                    <dt>Cancellation reason</dt>
                    <dd>{current.order.diagnostics.cancellation_detail}</dd>
                  </>
                )}
              </>
            )}
            <dt>Strategy</dt>
            <dd>
              {current.run?.name ?? "Historical run"} · v{current.run?.version}
            </dd>
            <dt>
              {current.order.payload.cash_quantity ? "Cash budget" : "Quantity"}
            </dt>
            <dd>
              {current.order.payload.cash_quantity
                ? money(current.order.payload.cash_quantity)
                : `${current.order.payload.quantity} ${current.order.payload.execution === "fx_breakout" ? current.run?.binding?.contract.symbol : "units"}`}
              {current.order.payload.prices ? " per entry branch" : ""}
            </dd>
            <dt>
              {["crypto_breakout", "fx_breakout"].includes(
                current.order.payload.execution ?? "",
              )
                ? "Order type"
                : "Limit"}
            </dt>
            <dd>
              {current.order.payload.execution === "fx_breakout"
                ? current.order.payload.purpose === "entry"
                  ? "Market, IOC"
                  : current.order.payload.purpose === "protection"
                    ? "Stop, GTC — bid/ask trigger"
                    : `Limit ${current.order.payload.limit} ${current.order.payload.currency} per ${current.run?.binding?.contract.symbol}, GTD`
                : current.order.payload.execution === "crypto_breakout"
                  ? "Market, IOC"
                  : current.order.payload.prices
                    ? `Buy stop ${money(current.order.payload.prices.long_entry, current.order.payload.currency, current.order.payload.price_scale)} / Short stop ${money(current.order.payload.prices.short_entry, current.order.payload.currency, current.order.payload.price_scale)}`
                    : current.order.payload.execution === "stock_breakout"
                      ? "Market shares, DAY"
                      : money(
                          current.order.payload.limit,
                          current.order.payload.currency,
                          current.order.payload.price_scale,
                        )}
            </dd>
            <dt>Protective stop</dt>
            <dd>
              {current.order.payload.execution === "fx_breakout"
                ? `${current.fx_protection?.stop ?? current.order.payload.stop} ${current.order.payload.currency} per ${current.run?.binding?.contract.symbol}`
                : current.order.payload.prices
                  ? "Fixed 1% from actual average entry"
                  : money(
                      current.stock_protection?.stop ??
                        current.order.payload.stop,
                      current.order.payload.currency,
                      current.order.payload.price_scale,
                    )}
            </dd>
            <dt>Entry authorization expires</dt>
            <dd>{localTime(current.run?.expires_at)}</dd>
            <dt>
              {current.run?.protection_type === "locally_monitored"
                ? "Locally monitored protection"
                : "Broker-held protection"}
            </dt>
            <dd>
              {current.run?.protection_verification
                ? protectionStatus(
                    current.run.protection_verification,
                    current.run.protection_type === "locally_monitored",
                  ).label
                : current.run?.protected
                  ? "Verified at reconciliation"
                  : "Not currently verified"}
            </dd>
          </dl>
          <h3>Confirmed executions</h3>
          <Grid
            name="order-executions"
            rows={current.executions}
            rowId={(row) => row.execution_id}
            columns={[
              { accessorKey: "side", header: "Side" },
              { accessorKey: "quantity", header: "Units" },
              {
                accessorKey: "price",
                header: "Price",
                cell: ({ row }) =>
                  current.order.payload.execution === "fx_breakout"
                    ? `${row.original.price} ${current.order.payload.currency} per ${current.order.payload.symbol}`
                    : money(
                        row.original.price,
                        current.order.payload.currency,
                        current.order.payload.price_scale,
                      ),
              },
            ]}
          />
          {current.fx_allocation && (
            <section aria-label="FX currency allocation">
              <h3>Run currency allocation</h3>
              <p>
                Remaining owned: {current.fx_allocation.quantity}{" "}
                {current.order.payload.symbol}. Pre-existing cash and other runs
                are excluded.
              </p>
              <p>
                Recorded cash flows before fees:{" "}
                {Object.entries(current.fx_allocation.flows)
                  .map(([currency, amount]) => `${amount} ${currency}`)
                  .join("; ")}
                .
              </p>
              <p>
                Recorded fees:{" "}
                {Object.entries(current.fx_allocation.fees)
                  .map(([currency, amount]) => `${amount} ${currency}`)
                  .join("; ") || "Awaiting broker commission reports"}
                .
              </p>
              {current.commissions?.some((c) => c === null) && (
                <p>Commission evidence remains pending for an execution.</p>
              )}
            </section>
          )}
          <h3>Event timeline</h3>
          <ol className="ws-timeline">
            {current.timeline.map((event, index) => (
              <li key={`${event.timestamp}-${index}`}>
                <strong>{titleCase(event.type.replaceAll(".", " "))}</strong>
                <time>{localTime(event.timestamp)}</time>
                {typeof event.payload.reason === "string" && (
                  <p>{event.payload.reason}</p>
                )}
              </li>
            ))}
          </ol>
          <details>
            <summary>Advanced broker diagnostics</summary>
            <pre>{JSON.stringify(current.broker_observations, null, 2)}</pre>
          </details>
        </>
      )}
    </Modal>
  );
}
