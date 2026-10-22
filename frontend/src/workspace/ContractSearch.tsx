import { useEffect, useRef, useState } from "react";
import { api, type Contract, type Snapshot } from "./api";
import { contractLabel } from "./PrepareRun";

type Search = {
  search_id: string;
  state: string;
  detail: string;
  results: Contract[];
  truncated: boolean;
  query: Record<string, string | number>;
};

export function ContractSearch({
  snapshot,
  busy,
  action,
  selectContract,
}: {
  snapshot: Pick<Snapshot, "data" | "contracts" | "connection"> | null;
  selectContract?: (contract: Contract) => void;
  busy: boolean;
  action: (path: string, body?: unknown) => Promise<unknown>;
}) {
  const [symbol, setSymbol] = useState("");
  const [security, setSecurity] = useState("");
  const [exchange, setExchange] = useState("");
  const [currency, setCurrency] = useState("");
  const [conid, setConid] = useState("");
  const [search, setSearch] = useState<Search | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const startRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    function visibility() {
      if (document.hidden && startRequest.current) {
        startRequest.current.abort();
        startRequest.current = null;
        setStarting(false);
        setError("Search interrupted while hidden. Start a new search.");
      }
    }
    document.addEventListener("visibilitychange", visibility);
    return () => {
      startRequest.current?.abort();
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  async function find(query: URLSearchParams) {
    startRequest.current?.abort();
    const controller = new AbortController();
    startRequest.current = controller;
    setSearch(null);
    setError("");
    setStarting(true);
    try {
      const result = await api<Search>(
        `/market-data/resolve?${query}`,
        "POST",
        undefined,
        controller.signal,
      );
      if (!controller.signal.aborted) setSearch(result);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (startRequest.current === controller) startRequest.current = null;
      if (!controller.signal.aborted) setStarting(false);
    }
  }
  const searchId = search?.search_id;
  const pending = search?.state === "searching";
  useEffect(() => {
    if (!searchId || !pending) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    let disposed = false;
    async function poll() {
      if (document.hidden || disposed || controller) return;
      const request = new AbortController();
      controller = request;
      try {
        const next = await api<Search>(
          `/market-data/search/${searchId}`,
          "GET",
          undefined,
          request.signal,
        );
        if (!request.signal.aborted && !disposed) {
          setSearch(next);
          setError("");
        }
      } catch (e) {
        if (!request.signal.aborted && !disposed)
          setError((e as Error).message);
      } finally {
        if (controller === request) controller = undefined;
        if (!disposed && !document.hidden && !request.signal.aborted)
          timer = setTimeout(() => void poll(), 2000);
      }
    }
    function visibility() {
      clearTimeout(timer);
      if (document.hidden) {
        controller?.abort();
        controller = undefined;
      } else void poll();
    }
    void poll();
    document.addEventListener("visibilitychange", visibility);
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [searchId, pending]);
  function rows(contracts: Contract[]) {
    return contracts.map((c) => {
      const subscribed = snapshot?.data.some((d) => d.conid === c.conid);
      const route = exchange.trim() || c.routing_exchange || c.exchange;
      return (
        <div key={`${c.conid}:${c.exchange}`}>
          <div>
            <strong>{contractLabel(c)}</strong>
            <span>
              {c.name}
              {c.trading_class && ` · Trading class ${c.trading_class}`}
            </span>
            <small>
              {c.resolved === false
                ? "Resolve complete contract details before subscription"
                : (c.capabilities?.unsupported_reason ??
                  "Paper execution remains subject to contract qualification.")}
            </small>
          </div>
          <button
            disabled={
              busy ||
              starting ||
              (!selectContract && subscribed) ||
              (c.resolved === false && !route)
            }
            onClick={() => {
              if (c.resolved === false)
                void find(
                  new URLSearchParams({
                    conid: String(c.conid),
                    exchange: route,
                    sec_type: c.sec_type ?? "",
                    currency: c.currency ?? "",
                  }),
                );
              else if (selectContract) selectContract(c);
              else void action("/market-data/subscribe", { conid: c.conid });
            }}
          >
            {selectContract && c.resolved !== false
              ? "Select instrument"
              : subscribed
                ? "Subscribed"
                : c.resolved === false
                  ? "Resolve contract"
                  : "Subscribe & warm up"}
          </button>
          {c.resolved === false && !route && (
            <small>Enter the routing exchange to resolve this candidate.</small>
          )}
        </div>
      );
    });
  }
  return (
    <>
      <form
        className="ws-form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          const query = new URLSearchParams({
            symbol,
            sec_type: security,
            exchange,
            currency,
          });
          if (conid) query.set("conid", conid);
          void find(query);
        }}
      >
        <label>
          Symbol or name
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="Microsoft, BTC, EUR…"
          />
        </label>
        <label>
          Security type
          <select
            value={security}
            onChange={(e) => setSecurity(e.target.value)}
          >
            <option value="">Search across types</option>
            {[
              "STK",
              "CRYPTO",
              "CASH",
              "FUT",
              "OPT",
              "FOP",
              "IND",
              "BOND",
              "CFD",
              "CMDTY",
              "FUND",
              "WAR",
            ].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Routing exchange
          <input
            value={exchange}
            onChange={(e) => setExchange(e.target.value.toUpperCase())}
            placeholder="SMART / PAXOS / IDEALPRO"
          />
        </label>
        <label>
          Currency
          <input
            value={currency}
            onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            placeholder="USD"
          />
        </label>
        <label>
          Direct contract ID
          <input
            type="number"
            min={1}
            value={conid}
            onChange={(e) => setConid(e.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={
            busy ||
            starting ||
            snapshot?.connection !== "connected" ||
            (!symbol && !conid)
          }
        >
          Find contracts
        </button>
      </form>
      <section aria-label="Current contract search">
        {starting && <p role="status">Starting contract search?</p>}
        {error && (
          <p role="alert">Contract search status unavailable: {error}</p>
        )}
        {search && (
          <>
            <p role="status">
              <strong>{search.state.replaceAll("_", " ")}</strong> ?{" "}
              {search.detail}
            </p>
            <p>
              {Object.entries(search.query)
                .map(([key, value]) => `${key}: ${value}`)
                .join(" ? ")}
            </p>
            {search.truncated && (
              <p>Showing the first 200 results. Narrow the search filters.</p>
            )}
            <div className="ws-contracts">{rows(search.results)}</div>
          </>
        )}
      </section>
      <h3>Previously resolved contracts</h3>
      <div className="ws-contracts">
        {rows(
          (snapshot?.contracts ?? []).filter(
            (c) =>
              c.resolved !== false &&
              !search?.results.some((r) => r.conid === c.conid),
          ),
        )}
      </div>
      <p className="ws-muted">
        Market-data subscriptions are independent of the five active-run limit.
        Availability depends on API support and account entitlements. Only
        supported contracts can execute.
      </p>
    </>
  );
}
