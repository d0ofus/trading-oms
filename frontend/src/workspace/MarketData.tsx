import { useEffect, useState } from "react";
import {
  api,
  localTime,
  money,
  requestLabel,
  titleCase,
  type DataState,
} from "./api";
import { Badge } from "./components";
import { FeedRecovery } from "./FeedRecovery";

export function MarketDataDetails({ data }: { data: DataState }) {
  const fx = data.family === "spot_fx";
  const [timeframe, setTimeframe] = useState("60");
  const [open, setOpen] = useState(false);
  const [before, setBefore] = useState<string | null>(null);
  const [page, setPage] = useState<{
    items: NonNullable<DataState["candles"]>[string];
    next_cursor: string | null;
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) {
      setPage(null);
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let alive = true;
    setPage(null);
    async function load() {
      if (!document.hidden) {
        try {
          const parameters = new URLSearchParams({ seconds: timeframe });
          if (fx && data.signal_source)
            parameters.set("signal_source", data.signal_source);
          if (before) parameters.set("before", before);
          const result = await api<{
            items: NonNullable<DataState["candles"]>[string];
            next_cursor: string | null;
          }>(
            `/market-data/${data.conid}/candles?${parameters}`,
            "GET",
            undefined,
            controller.signal,
          );
          if (alive) {
            setPage(result);
            setError("");
          }
        } catch (failure) {
          if (alive) setError(String(failure));
        }
      }
      if (alive && !before) timer = setTimeout(() => void load(), 2000);
    }
    void load();
    return () => {
      alive = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [open, timeframe, before, data.conid, fx, data.signal_source]);
  const quote = (value?: string | null) =>
    value == null || value === ""
      ? "Unavailable"
      : fx
        ? `${value} ${data.currency} per ${data.base_currency}`
        : !data.currency || data.currency === "USD"
          ? money(value, data.currency, data.price_scale)
          : `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 8 }).format(Number(value) * Number(data.price_scale ?? "1"))} ${data.currency}`;
  const candlePrice = (value: string) =>
    !data.price_scale || data.price_scale === "1"
      ? value
      : new Intl.NumberFormat("en-US", { maximumFractionDigits: 8 }).format(
          Number(value) * Number(data.price_scale),
        );
  return (
    <div className="ws-market-detail">
      <div className="ws-inline-actions">
        <strong>{fx ? `${data.symbol}.${data.currency}` : data.symbol}</strong>
        <Badge
          tone={
            fx
              ? data.stream_health === "healthy"
                ? "success"
                : data.stream_health === "blocked"
                  ? "warning"
                  : "neutral"
              : data.ready
                ? "success"
                : "warning"
          }
        >
          {fx
            ? data.stream_health === "healthy"
              ? "Feed live"
              : data.stream_health === "blocked"
                ? "Feed needs attention"
                : "Connecting feed"
            : data.ready
              ? "Ready"
              : titleCase(data.feed_status ?? "waiting_for_trades")}
        </Badge>
        <Badge
          tone={
            data.history_status === "failed"
              ? "warning"
              : data.history_loaded
                ? "success"
                : "neutral"
          }
        >
          {data.history_status === "failed"
            ? "History failed"
            : data.history_loaded
              ? "History downloaded"
              : fx
                ? requestLabel(data.components?.history?.request_state)
                : "Downloading history"}
        </Badge>
      </div>
      <p>
        Quote data: {data.data_type ?? (data.live ? "Live" : "Unavailable")} |{" "}
        {data.subscription_status ?? "Subscribed"} | Candle source:{" "}
        {data.candle_source ?? "TRADES"}
      </p>
      {data.session_mode && (
        <p>
          {fx
            ? "FX broker session"
            : data.session_mode === "premarket_regular"
              ? "Pre-market + regular hours"
              : "Regular hours"}{" "}
          · {data.session_open ? "Session open" : "Session closed"} ·{" "}
          {data.history_ready
            ? fx
              ? data.candle_policy === "idealpro_broker_candles_v2"
                ? "Broker candle stream established"
                : "Optional chart history complete"
              : "Required history complete"
            : fx
              ? data.candle_policy === "idealpro_broker_candles_v2"
                ? "Waiting for broker candle stream"
                : "Optional chart history downloading"
              : "Waiting for required history"}
        </p>
      )}
      {data.execution_detail && <p>{data.execution_detail}</p>}
      {data.broker_reference && (
        <p>
          Completed IBKR reference: {localTime(data.broker_reference.candle)} |
          High {data.broker_reference.high}. Entry requires a new fresh live
          tick strictly above this high.
        </p>
      )}
      {data.price_scale && data.price_scale !== "1" && (
        <p>
          Display converted at {data.price_scale} {data.currency} per quoted
          unit. Strategy price constants remain in quoted units.
        </p>
      )}
      {data.ages && (
        <p>
          Observation age:{" "}
          {Object.entries(data.ages)
            .map(
              ([name, age]) =>
                `${name}: ${age === null ? "unavailable" : age < 0 ? `${Math.abs(age).toFixed(1)}s ahead of clock` : `${age.toFixed(1)}s`}`,
            )
            .join(" · ")}
        </p>
      )}
      {data.diagnostic && <p role="status">{data.diagnostic}</p>}
      {fx &&
        data.fx_sources?.map((source) => (
          <p key={source.source}>
            {source.source} history: {requestLabel(source.request_state)} ·{" "}
            {source.bars} bars. {source.detail}
          </p>
        ))}
      {fx &&
        data.fx_feeds?.map((feed) => (
          <p key={feed.kind}>
            {feed.kind === "fx_midpoint" ? "Midpoint" : "Timestamped bid/ask"}:{" "}
            {requestLabel(feed.request_state)}. {feed.detail}
          </p>
        ))}
      <FeedRecovery
        conid={data.conid}
        components={data.components}
        extendedHistory={data.extended_history}
      />
      <dl className="ws-quote-grid">
        <div>
          <dt>
            {fx
              ? `Signal price (${data.signal_source})`
              : "Last execution trade"}
          </dt>
          <dd>
            <span>{quote(fx ? data.signal_price : data.price)}</span>
            <small>
              {fx
                ? localTime(data.signal_at)
                : data.source_at
                  ? localTime(data.source_at)
                  : "No execution trade received"}
            </small>
          </dd>
        </div>
        {!fx && (
          <div>
            <dt>Sampled Last</dt>
            <dd>
              <span>{quote(data.quotes?.last?.price)}</span>
              <small>
                Received {localTime(data.quotes?.last?.received_at)}
              </small>
            </dd>
          </div>
        )}
        {(["bid", "ask"] as const).map((side) => (
          <div key={side}>
            <dt>{titleCase(side)}</dt>
            <dd>
              <span>{quote(data.quotes?.[side]?.price)}</span>
              <small>
                Received {localTime(data.quotes?.[side]?.received_at)}
              </small>
            </dd>
          </div>
        ))}
      </dl>
      {data.sizes && (
        <p>
          {Object.entries(data.sizes)
            .map(
              ([side, item]) =>
                `${titleCase(side)}: ${item.value} (${localTime(item.received_at)})`,
            )
            .join(" | ")}
        </p>
      )}
      <details onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary>View candles</summary>
        <label>
          Candle interval
          <select
            value={timeframe}
            onChange={(e) => {
              setTimeframe(e.target.value);
              setBefore(null);
            }}
          >
            {!fx && <option value="5">5 seconds</option>}
            <option value="60">1 minute</option>
            {!fx && <option value="300">5 minutes</option>}
          </select>
        </label>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Open</th>
              <th>High</th>
              <th>Low</th>
              <th>Close</th>
              <th>Volume</th>
              <th>Source / completeness</th>
            </tr>
          </thead>
          <tbody>
            {page?.items
              .slice()
              .reverse()
              .map((c) => (
                <tr key={c.timestamp}>
                  <td>{localTime(c.timestamp)}</td>
                  <td>{candlePrice(c.open)}</td>
                  <td>{candlePrice(c.high)}</td>
                  <td>{candlePrice(c.low)}</td>
                  <td>{candlePrice(c.close)}</td>
                  <td>{c.volume ?? "Unavailable"}</td>
                  <td>
                    {c.source} / {c.complete ? "complete" : "partial"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {!page?.items.length && (
          <p>No supported candles received for this interval.</p>
        )}
        {error && <p role="alert">{error}</p>}
        <p>
          Candle prices are in {data.currency ?? "the contract currency"}
          {fx ? ` per ${data.base_currency}` : ""}. Display candles include
          historical/repaired data.{" "}
          {data.candle_policy === "idealpro_broker_candles_v2"
            ? "The immediately preceding completed IBKR minute supplies the reference high. "
            : ""}
          Only validated live
          {fx ? ` ${data.signal_source} observations` : " trades"} can create
          entry signals.
        </p>
        <button
          disabled={!page?.next_cursor}
          onClick={() => setBefore(page!.next_cursor)}
        >
          Older candles
        </button>
        <button onClick={() => setBefore(null)}>Latest candles</button>
      </details>
      {data.history_progress && (
        <small>
          {data.history_progress.minute_bars.toLocaleString()} minute bars ·{" "}
          {data.history_progress.fine_bars.toLocaleString()} five-second bars ·{" "}
          {data.history_progress.complete_reference_sessions}/
          {data.history_progress.required_reference_sessions} complete reference
          sessions
        </small>
      )}
      {!fx && data.history_loaded && !data.warm && (
        <p className="ws-muted">
          History is downloaded. Waiting for fresh trades and a continuous
          history boundary.
        </p>
      )}
    </div>
  );
}
