import { useEffect, useState } from "react";
import {
  api,
  localTime,
  money,
  titleCase,
  type Check,
  type Snapshot,
} from "./api";
import { Badge, Modal, Panel } from "./components";

type Trial = {
  id: string;
  symbol: string;
  state: string;
  acknowledged_at?: string;
  started_at: string;
};
type Diagnostics = {
  checks: Check[];
  eligible: boolean;
  tests: Trial[];
  last_trade_at?: string;
  quotes: Record<string, { price: string; received_at: string }>;
};
type Preview = {
  id: string;
  eligible: boolean;
  checks: Check[];
  symbol: string;
  preview_expires_at: string;
  prices: { limit: string; stop: string; stop_limit?: string } | null;
};

export function ConnectionTestLauncher(props: {
  snapshot: Snapshot | null;
  refresh: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  if (props.snapshot?.mode === "simulation") return null;
  return (
    <>
      <button onClick={() => setOpen(true)}>Paper connection test</button>
      <Modal
        open={open}
        onOpenChange={setOpen}
        title="Paper connection test"
        description="Check paper connection and data, then review a supervised stock order test."
      >
        <ConnectionTest {...props} />
      </Modal>
    </>
  );
}

export function ConnectionTest({
  snapshot,
  refresh,
  notify,
}: {
  snapshot: Snapshot | null;
  refresh: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const [conid, setConid] = useState(0);
  const [hours, setHours] = useState("extended");
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const selected = conid || snapshot?.contracts[0]?.conid || 0;
  const hasDiagnostics = diagnostics !== null;
  useEffect(() => {
    if (!hasDiagnostics || !selected) return;
    let active = true;
    const timer = window.setInterval(() => {
      setClock(Date.now());
      void api<Diagnostics>(`/paper/diagnostics?conid=${selected}`)
        .then((value) => {
          if (active) setDiagnostics(value);
        })
        .catch(() => {});
    }, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [hasDiagnostics, selected]);
  async function act(kind: "check" | "preview" | "submit") {
    setBusy(true);
    try {
      if (kind === "check")
        setDiagnostics(
          await api<Diagnostics>(`/paper/diagnostics?conid=${selected}`),
        );
      else if (kind === "preview") {
        setPreview(
          await api<Preview>("/paper/order-tests/preview", "POST", {
            conid: selected,
            trading_hours: hours,
          }),
        );
        setClock(Date.now());
      } else if (preview) {
        await api("/paper/order-tests", "POST", { preview_id: preview.id });
        setPreview(null);
        notify(
          "Paper test submitted. Watch acknowledgement, cancellation and reconciliation.",
        );
      }
      await refresh();
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const checks = (items: Check[]) => (
    <ul className="ws-test-checks">
      {items.map((item) => (
        <li key={item.code}>
          <Badge tone={item.passed ? "success" : "warning"}>
            {item.passed ? "Passed" : "Blocked"}
          </Badge>{" "}
          <strong>{item.title}</strong>
          {!item.passed && <p>{item.detail}</p>}
        </li>
      ))}
    </ul>
  );
  return (
    <Panel
      className="ws-connection-test"
      title="Paper connection test"
      caption="Check quotes, then explicitly review a one-share limit order that cancels after acknowledgement."
    >
      <div className="ws-form-grid">
        <label>
          Test symbol
          <select
            value={selected}
            onChange={(e) => {
              setConid(Number(e.target.value));
              setDiagnostics(null);
            }}
          >
            <option value={0}>Resolve a symbol first</option>
            {snapshot?.contracts.map((c) => (
              <option value={c.conid} key={c.conid}>
                {c.symbol} · {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Test execution hours
          <select value={hours} onChange={(e) => setHours(e.target.value)}>
            <option value="regular">Regular hours only</option>
            <option value="extended">Regular + pre/post-market</option>
          </select>
        </label>
      </div>
      <p>
        Connection checks submit no orders. Order tests require an open broker
        session and fresh quotes, even when prices are unchanged.
      </p>
      <div className="ws-inline-actions">
        <button disabled={busy || !selected} onClick={() => void act("check")}>
          Check connection & data
        </button>
        <button
          disabled={busy || !diagnostics?.eligible}
          onClick={() => void act("preview")}
        >
          Review paper order test
        </button>
      </div>
      {diagnostics && (
        <>
          <details open>
            <summary>Connection and data results</summary>
            {checks(diagnostics.checks)}
            <dl className="ws-facts">
              {["bid", "ask"].map((side) => (
                <div key={side}>
                  <dt>{titleCase(side)}</dt>
                  <dd>
                    {money(diagnostics.quotes[side]?.price)} ·{" "}
                    {localTime(diagnostics.quotes[side]?.received_at)}
                  </dd>
                </div>
              ))}
              <dt>Last trade received</dt>
              <dd>{localTime(diagnostics.last_trade_at)}</dd>
            </dl>
          </details>
          {diagnostics.tests.map((trial) => (
            <div className="ws-incident" key={trial.id}>
              <div>
                <strong>
                  {trial.symbol} · {titleCase(trial.state)}
                </strong>
                <p>
                  {trial.acknowledged_at
                    ? `Broker acknowledgement: ${localTime(trial.acknowledged_at)}`
                    : "Awaiting broker evidence"}
                </p>
                {trial.state === "position_requires_attention" && (
                  <p>
                    Open Trading Desk, verify protection, and use Close owned
                    position.
                  </p>
                )}
              </div>
            </div>
          ))}
        </>
      )}
      <Modal
        open={!!preview}
        onOpenChange={(open) => {
          if (!open) setPreview(null);
        }}
        title="Review one-share paper order test"
        description="This action can submit and fill a real paper order. No price crossing is required."
      >
        {preview && (
          <>
            <h3>{preview.symbol} · BUY 1 share</h3>
            <dl className="ws-facts">
              <dt>Limit price</dt>
              <dd>{money(preview.prices?.limit)}</dd>
              <dt>Protective stop trigger</dt>
              <dd>{money(preview.prices?.stop)}</dd>
              {preview.prices?.stop_limit && (
                <>
                  <dt>Protective limit</dt>
                  <dd>{money(preview.prices.stop_limit)}</dd>
                </>
              )}
            </dl>
            <p>
              Cancel five seconds after acknowledgement, with a 30-second broker
              entry deadline. A fill is possible; protection and monitoring stay
              active until the position is closed. Stop-limit protection can
              trigger without filling.
            </p>
            {checks(preview.checks)}
            <p>Preview expires {localTime(preview.preview_expires_at)}.</p>
            <div className="ws-modal-actions">
              <button disabled={busy} onClick={() => void act("preview")}>
                Refresh preview
              </button>
              <button
                className="ws-primary"
                disabled={
                  busy ||
                  !preview.eligible ||
                  Date.parse(preview.preview_expires_at) <= clock
                }
                onClick={() => void act("submit")}
              >
                Submit paper test
              </button>
            </div>
          </>
        )}
      </Modal>
    </Panel>
  );
}
