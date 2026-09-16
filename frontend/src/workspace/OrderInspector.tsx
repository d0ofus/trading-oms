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

type Detail = {
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
    if (!identity) return;
    let active = true;
    const load = () => {
      void api<Detail>(`/operations/orders/${identity}`)
        .then((value) => {
          if (active) {
            setDetail(value);
            setError("");
          }
        })
        .catch((issue: Error) => {
          if (active) setError(issue.message);
        });
    };
    load();
    const timer = setInterval(load, 2000);
    return () => {
      active = false;
      clearInterval(timer);
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
            {titleCase(current.order.state)}
          </Badge>
          <dl className="ws-facts">
            <dt>Strategy</dt>
            <dd>
              {current.run?.name ?? "Historical run"} · v{current.run?.version}
            </dd>
            <dt>Quantity</dt>
            <dd>{current.order.payload.quantity} shares</dd>
            <dt>Limit</dt>
            <dd>{money(current.order.payload.limit)}</dd>
            <dt>Protective stop</dt>
            <dd>{money(current.order.payload.stop)}</dd>
            <dt>Entry authorization expires</dt>
            <dd>{localTime(current.run?.expires_at)}</dd>
            <dt>Position protection</dt>
            <dd>
              {current.run?.protected
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
              { accessorKey: "quantity", header: "Shares" },
              {
                accessorKey: "price",
                header: "Price",
                cell: ({ row }) => money(row.original.price),
              },
            ]}
          />
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
