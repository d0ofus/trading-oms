import { useEffect, useRef, useState } from "react";
import {
  api,
  localTime,
  requestLabel,
  titleCase,
  type FeedComponents,
} from "./api";
import { Badge } from "./components";

const labels = {
  quote: "Quotes",
  trade: "Execution trades",
  history: "Historical data",
};
export function FeedRecovery({
  conid,
  components,
  extendedHistory,
}: {
  conid: number;
  components?: FeedComponents;
  extendedHistory?: {
    status: string;
    detail?: string;
    minute_bars: number;
    retry_available: boolean;
  };
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  if (!components && !extendedHistory) return null;
  const entries = Object.entries(components ?? {}) as [
    keyof FeedComponents,
    NonNullable<FeedComponents[keyof FeedComponents]>,
  ][];
  const failed = entries
    .filter(([, state]) => state.retry_available)
    .map(([key]) => key);
  if (extendedHistory?.retry_available && !failed.includes("history"))
    failed.push("history");
  return (
    <div className="ws-feed-recovery">
      {extendedHistory && (
        <p>
          <strong>Pre-market history</strong>:{" "}
          {titleCase(extendedHistory.status)} · {extendedHistory.minute_bars}{" "}
          minute bars. {extendedHistory.detail}
        </p>
      )}
      {entries.map(([key, state]) => (
        <div key={key}>
          <p>
            <strong>
              {state.source?.startsWith("fx_")
                ? {
                    quote: "Timestamped bid/ask",
                    trade: `${titleCase(state.signal_source ?? "MIDPOINT")} signal`,
                    history: "FX source history",
                  }[key]
                : state.source === "realtime_bars"
                  ? "Live candle feed (display only)"
                  : labels[key]}
            </strong>{" "}
            <Badge tone={state.status === "healthy" ? "success" : "warning"}>
              {state.request_state
                ? requestLabel(state.request_state)
                : state.status === "failed"
                  ? "Request failed"
                  : titleCase(state.status)}
            </Badge>
          </p>
          {state.waiting_reason && <p>{state.waiting_reason}</p>}
          {state.next_eligible_at && (
            <p>Next eligible request: {localTime(state.next_eligible_at)}.</p>
          )}
          {state.diagnostic && (
            <p>
              {labels[key]}:{" "}
              {state.diagnostic.code
                ? `IBKR ${state.diagnostic.code}`
                : "Data request"}{" "}
              · {titleCase(state.diagnostic.reason)}. {state.diagnostic.detail}
            </p>
          )}
          {state.progress && (
            <p>
              {Object.entries(state.progress)
                .map(([name, count]) => `${count} ${name}`)
                .join(" · ")}{" "}
              requests
            </p>
          )}
          {state.retry_pending && (
            <p>
              Retry queued
              {state.retry_in_seconds !== null && state.retry_in_seconds > 0
                ? ` · cooldown ${Math.ceil(state.retry_in_seconds)}s`
                : ""}
              .
            </p>
          )}
        </div>
      ))}
      {(entries.some(([, state]) => state.status === "failed") ||
        extendedHistory?.retry_available) && (
        <button
          disabled={busy || !failed.length}
          onClick={async () => {
            if (request.current) return;
            const controller = new AbortController();
            request.current = controller;
            setBusy(true);
            try {
              await api(
                `/market-data/${conid}/retry`,
                "POST",
                {
                  components: failed,
                  mutation_id: crypto.randomUUID().replaceAll("-", ""),
                },
                controller.signal,
              );
              if (!controller.signal.aborted)
                setMessage(
                  "Failed feeds queued for paced retry. Healthy feeds continue; recovery review and arming remain separate.",
                );
            } catch (failure) {
              if (!controller.signal.aborted)
                setMessage((failure as Error).message);
            } finally {
              request.current = null;
              if (!controller.signal.aborted) setBusy(false);
            }
          }}
        >
          Retry failed feeds
        </button>
      )}
      {message && <p role="status">{message}</p>}
    </div>
  );
}
