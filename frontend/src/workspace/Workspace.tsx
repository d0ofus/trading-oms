import { Fragment, useCallback, useEffect, useState } from "react";
import { AuditSearch } from "./AuditSearch";
import { ReplayCompare } from "./ReplayCompare";
import { useForm } from "react-hook-form";
import {
  Activity,
  ArrowUpRight,
  Bell,
  Cable,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  FlaskConical,
  LayoutDashboard,
  Moon,
  OctagonX,
  Play,
  Plus,
  RefreshCw,
  Settings as SettingsIcon,
  ShieldCheck,
  Sun,
  Workflow,
} from "lucide-react";
import {
  api,
  ApiError,
  exchangeTime,
  localTime,
  money,
  preference,
  readPreference,
  titleCase,
  type ArmPreview,
  type Dataset,
  type Draft,
  type Event,
  type Json,
  type Order,
  type Replay,
  type Run,
  type Snapshot,
  type Version,
} from "./api";
import { Badge, Empty, Grid, Modal, Panel, Readiness } from "./components";
import { Studio } from "./Studio";
import { ArmReview } from "./ArmReview";
import { RiskSettings, chosenProfile } from "./RiskSettings";
import { OrderInspector } from "./OrderInspector";
import { LegacyHistory } from "./LegacyHistory";
import "./workspace.css";

const nav = [
  {
    path: "/desk",
    label: "Trading Desk",
    icon: LayoutDashboard,
    caption: "Session control & execution",
  },
  {
    path: "/studio",
    label: "Strategy Studio",
    icon: Workflow,
    caption: "Configure, test & publish",
  },
  {
    path: "/testing",
    label: "Testing",
    icon: FlaskConical,
    caption: "Deterministic replay",
  },
  {
    path: "/activity",
    label: "Activity",
    icon: Activity,
    caption: "Events & incidents",
  },
  {
    path: "/settings",
    label: "Settings",
    icon: SettingsIcon,
    caption: "Connection & readiness",
  },
];
const runState: Record<string, string> = {
  ready: "Ready to arm",
  armed: "Armed · waiting",
  entry_working: "Entry working",
  position_open: "Position open",
  exiting: "Exiting",
  paused: "Paused",
  recovery_required: "Recovery required",
  completed: "Completed",
};

export function Workspace() {
  const [path, setPath] = useState(() =>
    nav.some((item) => item.path === window.location.pathname)
      ? window.location.pathname
      : "/desk",
  );
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [network, setNetwork] = useState("loading");
  const [auth, setAuth] = useState(true);
  const [theme, setTheme] = useState(() => readPreference("theme", "dark"));
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [clearEmergency, setClearEmergency] = useState(false);
  const [clock, setClock] = useState(new Date().toISOString());
  const notify = useCallback(
    (message: string, error = false) => setToast({ message, error }),
    [],
  );
  const navigate = useCallback((target: string) => {
    window.history.pushState(null, "", target);
    setPath(target);
  }, []);
  const refresh = useCallback(async () => {
    try {
      const state = await api<Snapshot>("/paper/session");
      setSnapshot(state);
      setNetwork("online");
      setAuth(true);
    } catch (error) {
      setNetwork("offline");
      if ((error as ApiError).status === 401) setAuth(false);
    }
  }, []);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | undefined;
    let alive = true;
    async function start() {
      const parameters = new URLSearchParams(window.location.hash.slice(1));
      const token = parameters.get("pair");
      if (token) {
        window.history.replaceState(null, "", window.location.pathname);
        try {
          await api("/auth/pair", "POST", { token });
        } catch (error) {
          notify((error as Error).message, true);
        }
      }
      if (!alive) return;
      await refresh();
      interval = setInterval(() => void refresh(), 2000);
    }
    void start();
    const back = () =>
      setPath(
        nav.some((item) => item.path === window.location.pathname)
          ? window.location.pathname
          : "/desk",
      );
    window.addEventListener("popstate", back);
    return () => {
      alive = false;
      clearInterval(interval);
      window.removeEventListener("popstate", back);
    };
  }, [refresh, notify]);
  useEffect(() => {
    window.document.documentElement.dataset.theme = theme;
    preference("theme", theme);
  }, [theme]);
  useEffect(() => {
    const interval = setInterval(
      () => setClock(new Date().toISOString()),
      1000,
    );
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    if (!toast || toast.error) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  async function act(path: string, body?: unknown) {
    setBusy(true);
    try {
      await api(path, "POST", body);
      await refresh();
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function createRun(version: Version) {
    const contract = snapshot?.contracts.find(
      (item) => item.symbol === version.document.settings.symbol,
    );
    if (!contract) {
      notify(
        "Resolve this strategy’s symbol in Settings before preparing a paper run.",
        true,
      );
      navigate("/settings");
      return;
    }
    try {
      await api("/runs", "POST", {
        strategy_id: version.strategy_id,
        version: version.version,
        conid: contract.conid,
      });
      await refresh();
      notify("Run prepared. Review readiness and explicitly arm its session.");
      navigate("/desk");
    } catch (error) {
      notify((error as Error).message, true);
    }
  }
  const current = nav.find((item) => item.path === path) ?? nav[0];
  const critical =
    snapshot?.incidents.filter((incident) => !incident.resolved) ?? [];
  const dataFresh =
    !!snapshot?.data.length &&
    snapshot.data.every(
      (data) =>
        data.live &&
        data.warm &&
        data.received_at &&
        Date.now() - new Date(data.received_at).getTime() <= 15000,
    );

  return (
    <div className="ws-app">
      <a className="ws-skip" href="#workspace-content">
        Skip to workspace
      </a>
      <aside className="ws-sidebar">
        <a
          className="ws-brand"
          aria-label="Trading workspace"
          href="/desk"
          onClick={(event) => {
            event.preventDefault();
            navigate("/desk");
          }}
        >
          <div className="ws-brand-mark">
            <Workflow size={22} />
          </div>
          <span>
            Trading<span className="ws-brand-sub">OPERATIONS WORKSPACE</span>
          </span>
        </a>
        <div className="ws-environment">
          <Badge tone="paper">PAPER ENVIRONMENT</Badge>
          <span>Local workspace · US equities</span>
        </div>
        <nav aria-label="Main navigation">
          {nav.map((item) => (
            <a
              key={item.path}
              aria-label={item.label}
              title={item.label}
              href={item.path}
              className={path === item.path ? "active" : ""}
              aria-current={path === item.path ? "page" : undefined}
              onClick={(event) => {
                event.preventDefault();
                navigate(item.path);
              }}
            >
              <item.icon size={19} />
              <span>{item.label}</span>
              {path === item.path && <ChevronRight size={14} />}
            </a>
          ))}
        </nav>
        <div className="ws-sidebar-bottom">
          <div className="ws-scope">
            <ShieldCheck size={18} />
            <div>
              <strong>Paper execution only</strong>
              <span>Long-only stocks & ETFs</span>
            </div>
          </div>
          <button
            className="ws-theme"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}Switch to{" "}
            {theme === "dark" ? "light" : "dark"} theme
          </button>
          <p>
            Internal paper release
            <br />
            <span>Supervised qualification</span>
          </p>
        </div>
      </aside>
      <div className="ws-shell">
        <header className="ws-topbar">
          <div className="ws-top-status">
            <Badge tone="paper">Paper</Badge>
            <Badge
              tone={
                network === "online" && snapshot?.connection === "connected"
                  ? "success"
                  : "warning"
              }
            >
              Gateway{" "}
              {network === "online"
                ? (snapshot?.connection ?? "unknown")
                : "unavailable"}
            </Badge>
            <Badge
              tone={dataFresh && network === "online" ? "success" : "neutral"}
            >
              Data {dataFresh && network === "online" ? "current" : "not ready"}
            </Badge>
            <Badge
              tone={
                snapshot?.entry_permission && network === "online"
                  ? "success"
                  : "warning"
              }
            >
              Entries{" "}
              {snapshot?.entry_permission && network === "online"
                ? "eligible for authorization"
                : "blocked"}
            </Badge>
          </div>
          <div className="ws-top-actions">
            <button
              className="ws-icon"
              aria-label={`${critical.length} critical incidents`}
              onClick={() => navigate("/activity")}
            >
              <Bell size={18} />
              {critical.length > 0 && (
                <span className="ws-alert-count">{critical.length}</span>
              )}
            </button>
            <button
              className={`ws-emergency ${snapshot?.emergency ? "active" : ""}`}
              disabled={busy || !auth}
              onClick={() => {
                if (snapshot?.emergency) setClearEmergency(true);
                else void act("/operations/emergency", { active: true });
              }}
            >
              <OctagonX size={17} />
              {busy
                ? "Action pending…"
                : snapshot?.emergency
                  ? "Emergency stop active"
                  : "Emergency stop"}
            </button>
          </div>
        </header>
        <main
          id="workspace-content"
          className={`ws-content ${path === "/studio" ? "studio-page" : ""}`}
        >
          <div className="ws-page-heading">
            <div>
              <span className="ws-eyebrow">{current.caption}</span>
              <h1>{current.label}</h1>
            </div>
            <div className="ws-session-label">
              <span className="ws-dot" />
              US regular session · Exchange calendar
            </div>
          </div>
          {network === "offline" && auth && (
            <div className="ws-banner danger" role="alert">
              <CircleAlert size={18} />
              <div>
                <strong>Application connection lost</strong>
                <span>
                  Last known values are retained from{" "}
                  {localTime(snapshot?.timestamp)}. Actions require a current
                  server response.
                </span>
              </div>
              <button onClick={() => void refresh()}>Retry connection</button>
            </div>
          )}
          {critical.length > 0 && path !== "/activity" && (
            <div className="ws-banner danger">
              <CircleAlert size={18} />
              <div>
                <strong>
                  {critical.length} critical{" "}
                  {critical.length === 1
                    ? "incident requires"
                    : "incidents require"}{" "}
                  attention
                </strong>
                <span>{critical[0].detail}</span>
              </div>
              <button onClick={() => navigate("/activity")}>
                Inspect incidents
              </button>
            </div>
          )}
          {!auth ? (
            <Panel title="Open an authenticated local session">
              <Empty title="Use the workspace launcher">
                Run <code>.\scripts\start-paper.ps1</code> on this PC. The
                launcher opens a private, one-time local pairing link. No broker
                password belongs in this application.
              </Empty>
            </Panel>
          ) : network === "loading" ? (
            <div className="ws-loading" role="status">
              Loading the local workspace…
            </div>
          ) : path === "/studio" ? (
            <Studio
              contracts={snapshot?.contracts ?? []}
              notify={notify}
              createRun={(version) => void createRun(version)}
            />
          ) : path === "/desk" ? (
            <Desk
              snapshot={snapshot}
              navigate={navigate}
              refresh={refresh}
              notify={notify}
            />
          ) : path === "/settings" ? (
            <Settings snapshot={snapshot} refresh={refresh} notify={notify} />
          ) : path === "/testing" ? (
            <Testing
              notify={notify}
              createRun={(version) => void createRun(version)}
            />
          ) : (
            <ActivityView
              snapshot={snapshot}
              notify={notify}
              refresh={refresh}
            />
          )}
        </main>
        <footer className="ws-footer">
          <span>
            <span
              className={`ws-dot ${network === "online" ? "online" : ""}`}
            />
            {network === "online"
              ? "Local service connected"
              : "Local service unavailable"}
          </span>
          <div>
            <span>Exchange: {exchangeTime(clock)}</span>
            <span>Local: {localTime(clock)}</span>
          </div>
        </footer>
      </div>
      {toast && (
        <div
          className={`ws-toast ${toast.error ? "error" : ""}`}
          role={toast.error ? "alert" : "status"}
        >
          {toast.error ? <CircleAlert size={19} /> : <CheckCircle2 size={19} />}
          <span>{toast.message}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            ×
          </button>
        </div>
      )}
      <Modal
        open={clearEmergency}
        onOpenChange={setClearEmergency}
        title="Review emergency-stop clearance"
        description="Clearing the stop permits a new readiness review. Every run remains disarmed, and existing protective orders stay in place."
      >
        <Readiness
          checks={
            snapshot?.checks.filter((check) => check.code !== "emergency") ?? []
          }
        />
        <div className="ws-modal-actions">
          <button onClick={() => setClearEmergency(false)}>
            Keep stop active
          </button>
          <button
            className="ws-primary"
            onClick={() => {
              void act("/operations/emergency", {
                active: false,
                reviewed: true,
              });
              setClearEmergency(false);
            }}
          >
            Clear stop · keep entries disarmed
          </button>
        </div>
      </Modal>
    </div>
  );
}

function Desk({
  snapshot,
  navigate,
  refresh,
  notify,
}: {
  snapshot: Snapshot | null;
  navigate: (path: string) => void;
  refresh: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const [selected, setSelected] = useState<string[]>(() =>
    readPreference("desk.selected", []),
  );
  const [detail, setDetail] = useState<string | null>(() =>
    readPreference("desk.detail", null),
  );
  const [preview, setPreview] = useState<ArmPreview | null>(null);
  const [orderIdentity, setOrderIdentity] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPreparation, setShowPreparation] = useState(false);
  const [strategies, setStrategies] = useState<Draft[]>([]);
  const [strategy, setStrategy] = useState("");
  const [closeRun, setCloseRun] = useState<Run | null>(null);
  const [checksExpanded, setChecksExpanded] = useState(false);
  const runs = snapshot?.runs ?? [];
  useEffect(() => {
    preference("desk.selected", selected);
    preference("desk.detail", detail);
  }, [selected, detail]);
  async function action(path: string, body?: unknown) {
    setBusy(true);
    try {
      await api(path, "POST", body);
      await refresh();
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function review() {
    setBusy(true);
    try {
      setPreview(
        await api<ArmPreview>("/runs/arm-preview", "POST", {
          ids: selected,
          profile_id: chosenProfile().id,
          profile_version: chosenProfile().version,
        }),
      );
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const run = runs.find((item) => item.id === detail);
  const blocking = snapshot?.checks.filter((check) => !check.passed) ?? [];
  const positionCount =
    snapshot?.positions.filter((position) => Number(position.quantity) > 0)
      .length ?? 0;
  return (
    <>
      <div className="ws-metrics">
        <div>
          <span>Session readiness</span>
          <strong>
            {blocking.length
              ? `${blocking.length} checks pending`
              : "Ready for review"}
          </strong>
          <button
            className="ws-link"
            onClick={() => setChecksExpanded(!checksExpanded)}
          >
            {checksExpanded ? "Hide checks" : "Inspect readiness"}
            <ChevronRight size={14} />
          </button>
        </div>
        <div>
          <span>Armed strategies</span>
          <strong>
            {runs.filter((item) => item.armed).length}
            <small> / 5 capacity</small>
          </strong>
          <span className="ws-muted">Bounded session authorization</span>
        </div>
        <div>
          <span>Owned positions</span>
          <strong>
            {positionCount}
            <small> / 5 capacity</small>
          </strong>
          <span className="ws-muted">
            {runs.some((item) => Number(item.position) > 0 && !item.protected)
              ? "Protection needs attention"
              : "Protection checked on reconciliation"}
          </span>
        </div>
        <div>
          <span>Broker gross exposure</span>
          <strong>{money(snapshot?.account_facts.GrossPositionValue)}</strong>
          <span className="ws-muted">$5,000 account ceiling</span>
        </div>
      </div>
      {checksExpanded && (
        <Panel
          title="Session readiness"
          caption="Connectivity, data health and permission are separate checks."
        >
          <Readiness checks={snapshot?.checks ?? []} navigate={navigate} />
        </Panel>
      )}
      <Panel
        title="Active runs"
        caption="Published strategies, explicit authorization, and current execution state."
        action={
          <div className="ws-inline-actions">
            <button
              onClick={() => {
                setShowPreparation(true);
                void api<Draft[]>("/strategies").then((items) => {
                  const published = items.filter(
                    (item) => item.published_version,
                  );
                  setStrategies(published);
                  setStrategy(published[0]?.id ?? "");
                });
              }}
            >
              <Plus size={15} />
              Prepare a run
            </button>
            <button
              className="ws-primary"
              disabled={!selected.length || busy}
              onClick={() => void review()}
            >
              <ShieldCheck size={16} />
              Review & arm {selected.length > 0 ? `(${selected.length})` : ""}
            </button>
          </div>
        }
      >
        {runs.length ? (
          <Grid<Run>
            name="runs"
            rows={runs}
            rowId={(row) => row.id}
            selected={detail ?? undefined}
            onSelect={(row) => setDetail(row.id)}
            columns={[
              {
                id: "selection",
                header: "Review",
                size: 82,
                cell: ({ row }) => (
                  <input
                    type="checkbox"
                    aria-label={`Select ${row.original.name} ${row.original.symbol}`}
                    checked={selected.includes(row.original.id)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) =>
                      setSelected((items) =>
                        event.target.checked
                          ? [...items, row.original.id]
                          : items.filter((item) => item !== row.original.id),
                      )
                    }
                  />
                ),
              },
              {
                accessorKey: "name",
                header: "Strategy",
                size: 240,
                cell: ({ row }) => (
                  <div className="ws-table-primary">
                    <strong>{row.original.name}</strong>
                    <small>Published v{row.original.version}</small>
                  </div>
                ),
              },
              { accessorKey: "symbol", header: "Symbol", size: 100 },
              {
                accessorKey: "state",
                header: "State",
                size: 200,
                cell: ({ row }) => (
                  <Badge
                    tone={
                      row.original.state === "recovery_required"
                        ? "danger"
                        : row.original.armed
                          ? "success"
                          : "neutral"
                    }
                  >
                    {runState[row.original.state] ??
                      titleCase(row.original.state)}
                  </Badge>
                ),
              },
              {
                accessorKey: "position",
                header: "Position",
                size: 100,
                cell: ({ row }) => (
                  <span className="ws-number">
                    {row.original.position} shares
                  </span>
                ),
              },
              {
                accessorKey: "risk",
                header: "Planned stop risk",
                size: 155,
                cell: ({ row }) => (
                  <span className="ws-number">{money(row.original.risk)}</span>
                ),
              },
              {
                accessorKey: "last_signal",
                header: "Last signal",
                size: 190,
                cell: ({ row }) => localTime(row.original.last_signal),
              },
              {
                accessorKey: "blocking_reason",
                header: "Blocking reason",
                size: 300,
                cell: ({ row }) =>
                  row.original.blocking_reason || "No recorded block",
              },
            ]}
          />
        ) : (
          <Empty
            title="Your desk is ready for a strategy"
            action={
              <button
                className="ws-primary"
                onClick={() => navigate("/studio")}
              >
                <Workflow size={16} />
                Open Strategy Studio
              </button>
            }
          >
            Configure a template, test it against recorded data, and publish a
            version. Prepare a run here when its symbol has been resolved by
            Gateway.
          </Empty>
        )}
      </Panel>
      <div className="ws-desk-bottom">
        <Panel
          title="Positions & protection"
          caption="Owned executions compared with broker positions."
        >
          {positionCount ? (
            snapshot?.positions
              .filter((item) => Number(item.quantity) > 0)
              .map((position) => {
                const owner = runs.find((item) => item.id === position.run_id);
                return (
                  <div className="ws-position" key={position.run_id}>
                    <div>
                      <strong>{position.symbol}</strong>
                      <span>
                        {position.quantity} shares · {owner?.name}
                      </span>
                    </div>
                    <Badge tone={owner?.protected ? "success" : "danger"}>
                      {owner?.protected
                        ? "Protection verified"
                        : "Protection requires review"}
                    </Badge>
                    <button onClick={() => owner && setCloseRun(owner)}>
                      Close owned position
                    </button>
                  </div>
                );
              })
          ) : (
            <Empty title="No owned positions">
              Positions appear after confirmed executions. Broker values are
              never replaced with sample holdings.
            </Empty>
          )}
        </Panel>
        <Panel
          title="Market data"
          caption="Last known trade values and their source timestamps."
        >
          {snapshot?.data.length ? (
            <div className="ws-data-list">
              {snapshot.data.map((data) => (
                <div key={data.conid}>
                  <strong>{data.symbol}</strong>
                  <span className="ws-number">{money(data.price)}</span>
                  <Badge
                    tone={
                      data.received_at &&
                      Date.now() - new Date(data.received_at).getTime() <
                        15000 &&
                      data.warm
                        ? "success"
                        : "warning"
                    }
                  >
                    {!data.warm
                      ? "Warming up"
                      : data.received_at &&
                          Date.now() - new Date(data.received_at).getTime() <
                            15000
                        ? "Current"
                        : "Stale"}
                  </Badge>
                  <small>{localTime(data.source_at)}</small>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="No active subscriptions"
              action={
                <button onClick={() => navigate("/settings")}>
                  Verify market data <ArrowUpRight size={14} />
                </button>
              }
            >
              Connect Gateway and resolve your symbols to see subscription and
              warm-up status.
            </Empty>
          )}
        </Panel>
      </div>
      <Panel
        title="Orders & executions"
        caption="A request remains pending until the broker confirms its outcome."
      >
        {snapshot?.orders.length ? (
          <Grid<Order>
            onSelect={(order) => setOrderIdentity(order.id)}
            name="orders"
            rows={snapshot.orders}
            rowId={(row) => row.id}
            columns={[
              {
                id: "symbol",
                header: "Symbol",
                accessorFn: (row) => row.payload.symbol,
              },
              {
                id: "purpose",
                header: "Purpose",
                accessorFn: (row) => titleCase(row.payload.purpose ?? "entry"),
              },
              {
                accessorKey: "state",
                header: "Broker outcome",
                cell: ({ row }) => (
                  <Badge
                    tone={
                      row.original.state === "unknown" ? "danger" : "neutral"
                    }
                  >
                    {titleCase(row.original.state)}
                  </Badge>
                ),
              },
              {
                id: "quantity",
                header: "Quantity",
                accessorFn: (row) => row.payload.quantity,
              },
              {
                id: "limit",
                header: "Limit",
                accessorFn: (row) => row.payload.limit,
                cell: ({ row }) => money(row.original.payload.limit),
              },
              {
                id: "stop",
                header: "Protective stop",
                accessorFn: (row) => row.payload.stop,
                cell: ({ row }) => money(row.original.payload.stop),
              },
              {
                accessorKey: "created_at",
                header: "Requested",
                size: 200,
                cell: ({ row }) => localTime(row.original.created_at),
              },
              {
                id: "actions",
                header: "Action",
                cell: ({ row }) =>
                  (row.original.payload.purpose ?? "entry") === "entry" &&
                  ["working", "dispatching", "unknown"].includes(
                    row.original.state,
                  ) ? (
                    <button
                      disabled={busy}
                      onClick={() =>
                        void action(
                          `/operations/orders/${row.original.id}/cancel`,
                        )
                      }
                    >
                      Cancel entry
                    </button>
                  ) : (
                    <span className="ws-muted">No pending action</span>
                  ),
              },
            ]}
          />
        ) : (
          <div className="ws-table-empty">
            No orders have been submitted by this workspace.
          </div>
        )}
      </Panel>
      {run && (
        <aside className="ws-detail-drawer" aria-label="Run details">
          <button
            className="ws-drawer-close"
            aria-label="Close run details"
            onClick={() => setDetail(null)}
          >
            ×
          </button>
          <span className="ws-eyebrow">RUN DETAILS</span>
          <h2>{run.name}</h2>
          <p>
            {run.symbol} · Published v{run.version}
          </p>
          <Badge tone={run.armed ? "success" : "neutral"}>
            {runState[run.state] ?? run.state}
          </Badge>
          <dl>
            <dt>Position</dt>
            <dd>{run.position} shares</dd>
            <dt>Planned stop risk</dt>
            <dd>{money(run.risk)}</dd>
            <dt>Session ends</dt>
            <dd>{exchangeTime(run.expires_at)}</dd>
            <dt>Local session end</dt>
            <dd>{localTime(run.expires_at)}</dd>
            <dt>Protection</dt>
            <dd>
              {Number(run.position)
                ? run.protected
                  ? "Verified at reconciliation"
                  : "Requires recovery"
                : "Required before entry"}
            </dd>
          </dl>
          {run.blocking_reason && (
            <div className="ws-banner warning">{run.blocking_reason}</div>
          )}
          <h3>Current rule values</h3>
          <p className="ws-muted">
            Last evaluated values. A missing value means the input has not
            warmed up; it is not zero.
          </p>
          {snapshot?.evaluations?.[run.id]?.length ? (
            <dl>
              {snapshot.evaluations[run.id].map((item) => (
                <Fragment key={item.node}>
                  <dt>{item.label}</dt>
                  <dd>
                    {item.value === null ? "Not available" : String(item.value)}
                  </dd>
                </Fragment>
              ))}
            </dl>
          ) : (
            <p className="ws-muted">Waiting for qualified market data.</p>
          )}
          <button
            disabled={!run.armed || busy}
            onClick={() => void action(`/runs/${run.id}/disarm`)}
          >
            Disarm strategy
          </button>
          <p className="ws-muted">
            Disarming cancels remaining entries. Position monitoring and
            protective orders remain in place.
          </p>
          <button className="ws-link" onClick={() => navigate("/activity")}>
            Inspect event history <ArrowUpRight size={14} />
          </button>
        </aside>
      )}
      <OrderInspector
        identity={orderIdentity}
        close={() => setOrderIdentity(null)}
      />
      <ArmReview
        preview={preview}
        setPreview={setPreview}
        notify={notify}
        refresh={refresh}
        navigate={navigate}
      />
      <Modal
        open={showPreparation}
        onOpenChange={setShowPreparation}
        title="Prepare a strategy run"
        description="Choose an immutable version. The symbol and limits come from its published configuration."
      >
        {strategies.length ? (
          <>
            <label>
              Published strategy
              <select
                value={strategy}
                onChange={(event) => setStrategy(event.target.value)}
              >
                {strategies.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {item.document.settings.symbol} · v
                    {item.published_version}
                  </option>
                ))}
              </select>
            </label>
            <p className="ws-muted">
              Preparing a run starts data warm-up. It does not authorize order
              submission.
            </p>
            <div className="ws-modal-actions">
              <button onClick={() => setShowPreparation(false)}>Cancel</button>
              <button
                className="ws-primary"
                disabled={busy || !strategy}
                onClick={async () => {
                  const draft = strategies.find((item) => item.id === strategy);
                  if (!draft) return;
                  setBusy(true);
                  try {
                    const published = await api<Version>(
                      `/strategies/${draft.id}/versions/${draft.published_version}`,
                    );
                    const contract = snapshot?.contracts.find(
                      (item) =>
                        item.symbol === published.document.settings.symbol,
                    );
                    if (!contract) {
                      notify(
                        "Resolve this strategy’s symbol in Settings first.",
                        true,
                      );
                      setBusy(false);
                      return;
                    }
                    setBusy(true);
                    void api("/runs", "POST", {
                      strategy_id: draft.id,
                      version: draft.published_version,
                      conid: contract.conid,
                    })
                      .then(async () => {
                        setShowPreparation(false);
                        await refresh();
                      })
                      .catch((error: Error) => notify(error.message, true))
                      .finally(() => setBusy(false));
                  } catch (error) {
                    notify((error as Error).message, true);
                    setBusy(false);
                  }
                }}
              >
                Prepare run
              </button>
            </div>
          </>
        ) : (
          <Empty
            title="Publish a strategy first"
            action={
              <button
                onClick={() => {
                  setShowPreparation(false);
                  navigate("/studio");
                }}
              >
                Open Strategy Studio
              </button>
            }
          >
            The strategy library does not contain a published executable version
            yet.
          </Empty>
        )}
      </Modal>
      <Modal
        open={!!closeRun}
        onOpenChange={(open) => {
          if (!open) setCloseRun(null);
        }}
        title="Close an owned paper position"
        description="The engine rechecks ownership and broker state. The existing protective order remains in its OCA group while the exit request is pending."
      >
        {closeRun && (
          <>
            <p>
              {closeRun.symbol} · {closeRun.position} shares · {closeRun.name}
            </p>
            <div className="ws-modal-actions">
              <button onClick={() => setCloseRun(null)}>Keep position</button>
              <button
                className="ws-primary"
                onClick={() => {
                  void action(`/operations/positions/${closeRun.id}/close`);
                  setCloseRun(null);
                }}
              >
                Request close of owned position
              </button>
            </div>
          </>
        )}
      </Modal>
    </>
  );
}

function Settings({
  snapshot,
  refresh,
  notify,
}: {
  snapshot: Snapshot | null;
  refresh: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const form = useForm<{ symbol: string; paper: boolean }>({
    defaultValues: { symbol: "AAPL", paper: false },
  });
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");
  const [chat, setChat] = useState("");
  const [heartbeat, setHeartbeat] = useState("");
  const [monitoring, setMonitoring] = useState<Record<string, Json> | null>(
    null,
  );
  useEffect(() => {
    void api<Record<string, Json>>("/notifications")
      .then(setMonitoring)
      .catch(() => setMonitoring(null));
  }, []);
  async function action(path: string, body?: unknown) {
    setBusy(true);
    try {
      const result = await api<Record<string, Json>>(path, "POST", body);
      await refresh();
      notify(
        typeof result.detail === "string"
          ? result.detail
          : "Request accepted. Check its reported state below.",
      );
      return result;
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ws-settings">
      <div className="ws-setup-intro">
        <div>
          <Badge tone="paper">FIRST-RUN SETUP & DAILY READINESS</Badge>
          <h2>Prepare your paper environment</h2>
          <p>
            Connect once, verify your data, then review a bounded session from
            the Trading Desk. Broker credentials stay inside IB Gateway.
          </p>
        </div>
        <Cable size={36} />
      </div>
      <div className="ws-settings-grid">
        <Panel
          title="1. Connect Gateway"
          caption="A dedicated local paper connection."
        >
          <dl className="ws-facts">
            <dt>Application</dt>
            <dd>IB Gateway · official offline build</dd>
            <dt>Endpoint</dt>
            <dd>127.0.0.1 · port 4002</dd>
            <dt>API client</dt>
            <dd>71 · dedicated to this workspace</dd>
            <dt>Login context</dt>
            <dd>
              {snapshot?.attested
                ? "Paper context verified"
                : "Verification required"}
            </dd>
          </dl>
          <details>
            <summary>Gateway setup instructions</summary>
            <ol>
              <li>Sign in to IB Gateway using the paper-trading login.</li>
              <li>
                Enable socket API clients in API settings and set port 4002.
              </li>
              <li>
                Restrict trusted clients to localhost. Keep the port private.
              </li>
              <li>
                For initial diagnostics, keep the API read-only. Disable
                read-only only for the explicitly authorized supervised paper
                execution trial.
              </li>
              <li>
                Use the pinned SDK installer and the compatible Gateway build
                recorded in the operating guide.
              </li>
            </ol>
          </details>
          <div className="ws-inline-actions">
            <button
              className="ws-primary"
              disabled={busy || snapshot?.connection === "connected"}
              onClick={() => void action("/paper/session/connect")}
            >
              <Cable size={16} />
              {snapshot?.connection === "connected"
                ? "Gateway connected"
                : "Connect paper Gateway"}
            </button>
            <button
              disabled={busy || !snapshot?.attested}
              onClick={() => void action("/paper/session/reconcile")}
            >
              <RefreshCw size={15} />
              Reconcile
            </button>
          </div>
          <form
            onSubmit={form.handleSubmit((values) => {
              if (values.paper)
                void action("/paper/session/attest", { confirmed: true });
            })}
          >
            <label className="ws-checkbox">
              <input type="checkbox" {...form.register("paper")} />I verified
              the paper login in Gateway on this PC.
            </label>
            <button
              type="submit"
              disabled={busy || snapshot?.connection !== "connected"}
            >
              Verify paper context
            </button>
          </form>
        </Panel>
        <Panel
          title="2. Verify market data"
          caption="Resolve a US equity contract and verify actual entitlements."
        >
          <form
            className="ws-inline-form"
            onSubmit={form.handleSubmit(
              (values) =>
                void action(
                  `/market-data/resolve?symbol=${encodeURIComponent(values.symbol)}`,
                ),
            )}
          >
            <label>
              Stock or ETF symbol
              <input
                {...form.register("symbol", {
                  required: true,
                  pattern: /^[A-Za-z][A-Za-z0-9. -]{0,14}$/,
                })}
                placeholder="e.g. AAPL"
                autoCapitalize="characters"
              />
            </label>
            <button
              type="submit"
              disabled={busy || snapshot?.connection !== "connected"}
            >
              Find symbol
            </button>
          </form>
          {form.formState.errors.symbol && (
            <p className="ws-field-error">
              Enter a supported stock or ETF symbol.
            </p>
          )}
          <div className="ws-contracts">
            {snapshot?.contracts.length ? (
              snapshot.contracts.map((contract) => {
                const subscribed = snapshot.data.some(
                  (item) => item.conid === contract.conid,
                );
                return (
                  <div key={contract.conid}>
                    <div>
                      <strong>{contract.symbol}</strong>
                      <span>
                        {contract.name} · {contract.exchange}
                      </span>
                    </div>
                    <button
                      disabled={subscribed || busy}
                      onClick={() =>
                        void action("/market-data/subscribe", {
                          conid: contract.conid,
                        })
                      }
                    >
                      {subscribed ? "Subscribed" : "Subscribe & warm up"}
                    </button>
                  </div>
                );
              })
            ) : (
              <p className="ws-muted">
                Resolved contracts will appear here after Gateway responds.
              </p>
            )}
          </div>
          <p className="ws-muted">
            Each symbol needs Last ticks and current bid/ask data. Relative
            volume requires ten complete reference sessions. Historical
            downloads do not trigger entries.
          </p>
          {snapshot?.data.map((data) => (
            <div className="ws-inline-actions" key={data.conid}>
              <strong>{data.symbol}</strong>
              <Badge tone={data.live ? "success" : "warning"}>
                {data.live ? "Live entitlement" : "Data entitlement pending"}
              </Badge>
              <Badge tone={data.warm ? "success" : "neutral"}>
                {data.warm ? "History loaded" : "Warming up"}
              </Badge>
              <button
                disabled={busy}
                onClick={() =>
                  void action("/market-data/unsubscribe", { conid: data.conid })
                }
              >
                Remove subscription
              </button>
            </div>
          ))}
        </Panel>
        <RiskSettings notify={notify} />
        <Panel
          title="4. Configure monitoring"
          caption="Secrets are stored in Windows Credential Manager."
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void action("/notifications/configure", {
                telegram_token: token,
                telegram_chat: chat,
                healthchecks_url: heartbeat,
              }).then((result) => {
                if (result) {
                  setToken("");
                  setChat("");
                  setHeartbeat("");
                  void api<Record<string, Json>>("/notifications").then(
                    setMonitoring,
                  );
                }
              });
            }}
          >
            <div className="ws-form-grid">
              <label>
                Telegram bot token
                <input
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder="Stored securely on this PC"
                />
              </label>
              <label>
                Telegram destination
                <input
                  type="password"
                  autoComplete="off"
                  value={chat}
                  onChange={(event) => setChat(event.target.value)}
                  placeholder="Private notification destination"
                />
              </label>
              <label className="ws-span-all">
                Healthchecks ping URL
                <input
                  type="password"
                  autoComplete="off"
                  value={heartbeat}
                  onChange={(event) => setHeartbeat(event.target.value)}
                  placeholder="https://hc-ping.com/…"
                />
              </label>
            </div>
            <button
              type="submit"
              disabled={busy || !token || !chat || !heartbeat}
            >
              Save monitoring credentials
            </button>
          </form>
          <div className="ws-inline-actions">
            <button
              disabled={busy || !monitoring?.configured}
              onClick={() =>
                void action("/notifications/test", { channel: "telegram" })
              }
            >
              Send Telegram test
            </button>
            <button
              disabled={busy || !monitoring?.configured}
              onClick={() =>
                void action("/notifications/test", { channel: "healthchecks" })
              }
            >
              Test external heartbeat
            </button>
            <button
              disabled={busy || !monitoring?.configured}
              onClick={() => void action("/notifications/retry")}
            >
              Retry failed alerts
            </button>
          </div>
          <p className="ws-muted">
            Configure Healthchecks with a one-minute period and two-minute
            grace. The service sends a minimal heartbeat every 30 seconds.
            Successful tests are required before unattended qualification.
          </p>
          <Badge tone={monitoring?.configured ? "success" : "warning"}>
            {monitoring?.configured
              ? "Credentials configured"
              : "Monitoring not configured"}
          </Badge>
        </Panel>
      </div>
      <Panel
        title="5. Review readiness"
        caption="Server-authoritative checks identify what blocks entry permission."
      >
        <Readiness checks={snapshot?.checks ?? []} />
      </Panel>
      <Panel
        title="Backup & recovery"
        caption="Keep recovery data separate from an active workspace."
      >
        <p className="ws-muted">
          Backups preserve the event ledger, order state and strategy versions.
          Restore into a recovery directory, verify integrity, and reconcile
          before any new authorization.
        </p>
        <button
          disabled={busy}
          onClick={() => void action("/operations/backup")}
        >
          Create verified backup
        </button>
        <button
          disabled={busy}
          onClick={() => void action("/operations/restore-test")}
        >
          Validate a separate restore
        </button>
      </Panel>
    </div>
  );
}

function Testing({
  notify,
  createRun,
}: {
  notify: (message: string, error?: boolean) => void;
  createRun: (version: Version) => void;
}) {
  const [strategies, setStrategies] = useState<Draft[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [results, setResults] = useState<Replay[]>([]);
  const [strategy, setStrategy] = useState("");
  const [version, setVersion] = useState(0);
  const [dataset, setDataset] = useState("");
  const [result, setResult] = useState<Replay | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void Promise.all([
      api<Draft[]>("/strategies"),
      api<Dataset[]>("/testing/datasets"),
      api<Replay[]>("/testing/results"),
    ])
      .then(([items, data, runs]) => {
        const published = items.filter((item) => item.published_version);
        setStrategies(published);
        setStrategy(published[0]?.id ?? "");
        setDatasets(data);
        setDataset(data[0]?.id ?? "");
        setResults(runs);
        setResult(runs[0] ?? null);
      })
      .catch((error: Error) => notify(error.message, true));
  }, [notify]);
  useEffect(() => {
    if (!strategy) return;
    let current = true;
    void api<Version[]>(`/strategies/${strategy}/versions`).then((items) => {
      if (current) {
        setVersions(items);
        setVersion(items[0]?.version ?? 0);
      }
    });
    return () => {
      current = false;
    };
  }, [strategy]);
  async function importDataset(file: File) {
    setBusy(true);
    try {
      if (file.size > 24 * 1024 * 1024)
        throw new Error("Choose a tick CSV smaller than 24 MB.");
      const text = await file.text();
      const lines = text.trim().split(/\r?\n/);
      const headers = lines
        .shift()
        ?.split(",")
        .map((value) => value.trim().toLowerCase());
      if (
        !headers ||
        !["timestamp", "price", "size"].every((key) => headers.includes(key))
      )
        throw new Error(
          "The CSV needs timestamp, price and size columns. Timestamps must include a timezone.",
        );
      const ticks = lines.filter(Boolean).map((line) => {
        const values = line
          .split(",")
          .map((value) => value.trim().replace(/^"|"$/g, ""));
        return Object.fromEntries(
          ["timestamp", "price", "size"].map((key) => [
            key,
            values[headers.indexOf(key)],
          ]),
        );
      });
      const item = await api<Dataset>("/testing/datasets", "POST", {
        name: file.name.replace(/\.csv$/i, ""),
        source: "recorded_ticks",
        ticks,
      });
      setDatasets((items) => [item, ...items]);
      setDataset(item.id);
      notify(`Imported ${item.ticks.toLocaleString()} recorded observations.`);
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function sample() {
    const start = Date.parse("2026-09-15T13:30:00Z");
    const ticks = Array.from({ length: 3600 }, (_, index) => ({
      timestamp: new Date(start + index * 1000).toISOString(),
      price: (100 + Math.sin(index / 100) * 2 + index / 10000).toFixed(2),
      size: String(10 + (index % 30)),
    }));
    try {
      const item = await api<Dataset>("/testing/datasets", "POST", {
        name: "Synthetic crossover exercise · Sep 15",
        source: "synthetic_fixture",
        ticks,
      });
      setDatasets((items) => [item, ...items]);
      setDataset(item.id);
      notify(
        "Synthetic practice dataset added. It is not broker or market evidence.",
      );
    } catch (error) {
      notify((error as Error).message, true);
    }
  }
  return (
    <>
      <div className="ws-banner info">
        <FlaskConical size={18} />
        <span>
          Replay uses the same executable graph with simulated fills. Results
          are separate from actual paper-broker qualification.
        </span>
      </div>
      <Panel
        title="Run a deterministic replay"
        caption="Choose a published version and timestamped trade observations."
      >
        <div className="ws-replay-controls">
          <label>
            Published strategy
            <select
              value={strategy}
              onChange={(event) => setStrategy(event.target.value)}
            >
              <option value="">Choose a strategy…</option>
              {strategies.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Version
            <select
              value={version}
              onChange={(event) => setVersion(Number(event.target.value))}
            >
              {versions.map((item) => (
                <option key={item.version} value={item.version}>
                  Version {item.version}
                </option>
              ))}
            </select>
          </label>
          <label>
            Tick dataset
            <select
              value={dataset}
              onChange={(event) => setDataset(event.target.value)}
            >
              <option value="">Choose a dataset…</option>
              {datasets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ·{" "}
                  {item.source === "synthetic_fixture"
                    ? "Synthetic"
                    : "Recorded"}
                </option>
              ))}
            </select>
          </label>
          <button
            className="ws-primary"
            disabled={busy || !strategy || !dataset || !version}
            onClick={() => {
              setBusy(true);
              void api<Replay>("/testing/replay", "POST", {
                strategy_id: strategy,
                version,
                dataset_id: dataset,
              })
                .then((item) => {
                  setResult(item);
                  setResults((items) => [item, ...items]);
                  notify(
                    "Replay completed. Inspect signals, trades and remaining positions.",
                  );
                })
                .catch((error: Error) => notify(error.message, true))
                .finally(() => setBusy(false));
            }}
          >
            <Play size={15} />
            {busy ? "Processing…" : "Run replay"}
          </button>
        </div>
        <div className="ws-inline-actions">
          <label className="ws-file-button">
            Import recorded tick CSV
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void importDataset(file);
                event.target.value = "";
              }}
            />
          </label>
          <button onClick={() => void sample()} disabled={busy}>
            Add synthetic practice data
          </button>
          <span className="ws-muted">
            CSV columns: timestamp, price, size · OHLCV alone cannot prove
            intrabar fills.
          </span>
        </div>
      </Panel>
      {result ? (
        <>
          <div className="ws-metrics">
            <div>
              <span>Replay result</span>
              <strong>{result.strategy_name}</strong>
              <span>
                Version {result.version} ·{" "}
                {result.dataset_source === "synthetic_fixture"
                  ? "Synthetic exercise"
                  : "Uploaded recorded ticks"}
              </span>
            </div>
            <div>
              <span>Entry intents</span>
              <strong>{result.signals.length}</strong>
              <span>
                {result.ticks.toLocaleString()} observations evaluated
              </span>
            </div>
            <div>
              <span>Completed simulated trades</span>
              <strong>{result.trades.length}</strong>
              <span>Fees and liquidity not modeled</span>
            </div>
            <div>
              <span>Realized simulated P/L</span>
              <strong>{money(result.realized_pnl)}</strong>
              <span>
                {result.open_position
                  ? `${result.open_position.quantity} shares still open`
                  : "No open simulated position"}
              </span>
            </div>
          </div>
          <Panel
            title="Replay trade ledger"
            caption={result.limitations.join(" ")}
            action={
              <button
                onClick={() => {
                  const selected = versions.find(
                    (item) =>
                      item.version === result.version &&
                      item.strategy_id === result.strategy_id,
                  );
                  if (selected) createRun(selected);
                  else
                    notify(
                      "Select the matching published strategy and version first.",
                      true,
                    );
                }}
              >
                Prepare paper run <ArrowUpRight size={14} />
              </button>
            }
          >
            {result.trades.length ? (
              <Grid
                name="replay-trades"
                rows={result.trades}
                rowId={(row) => row.entered_at}
                columns={[
                  {
                    accessorKey: "entered_at",
                    header: "Entry time",
                    size: 220,
                    cell: ({ row }) => localTime(row.original.entered_at),
                  },
                  { accessorKey: "quantity", header: "Shares" },
                  {
                    accessorKey: "entry",
                    header: "Entry",
                    cell: ({ row }) => money(row.original.entry),
                  },
                  {
                    accessorKey: "exit",
                    header: "Exit",
                    cell: ({ row }) => money(row.original.exit),
                  },
                  {
                    accessorKey: "pnl",
                    header: "Simulated P/L",
                    cell: ({ row }) => money(row.original.pnl),
                  },
                  {
                    accessorKey: "reason",
                    header: "Exit reason",
                    size: 180,
                    cell: ({ row }) => titleCase(row.original.reason),
                  },
                ]}
              />
            ) : (
              <div className="ws-table-empty">
                No completed trades. Inspect warm-up requirements, signal
                conditions and dataset coverage.
              </div>
            )}
          </Panel>
        </>
      ) : (
        <Empty title="Test the rules before arming">
          Publish a strategy, import recorded ticks, and inspect the exact
          signals and simulated outcomes. Practice data is clearly marked
          synthetic.
        </Empty>
      )}
      <Panel
        title="Replay history"
        caption="Select a result to compare versions and datasets."
      >
        <ReplayCompare results={results} />
        {results.length > 0 && (
          <Grid<Replay>
            name="replay-history"
            rows={results}
            rowId={(row) => row.id}
            onSelect={setResult}
            selected={result?.id}
            columns={[
              { accessorKey: "strategy_name", header: "Strategy", size: 220 },
              { accessorKey: "version", header: "Version" },
              { accessorKey: "dataset", header: "Dataset", size: 270 },
              {
                accessorKey: "dataset_source",
                header: "Evidence",
                size: 160,
                cell: ({ row }) => (
                  <Badge>
                    {row.original.dataset_source === "synthetic_fixture"
                      ? "Synthetic"
                      : "Recorded ticks"}
                  </Badge>
                ),
              },
              {
                accessorKey: "realized_pnl",
                header: "Simulated P/L",
                cell: ({ row }) => money(row.original.realized_pnl),
              },
              {
                accessorKey: "timestamp",
                header: "Run time",
                size: 220,
                cell: ({ row }) => localTime(row.original.timestamp),
              },
            ]}
          />
        )}
      </Panel>
    </>
  );
}

function ActivityView({
  snapshot,
  notify,
  refresh,
}: {
  snapshot: Snapshot | null;
  notify: (message: string, error?: boolean) => void;
  refresh: () => Promise<void>;
}) {
  const [events, setEvents] = useState<Event[]>([]);
  const [selected, setSelected] = useState<Event | null>(null);
  const [streaming, setStreaming] = useState(false);
  useEffect(() => {
    const stream = new EventSource("/api/events/stream");
    stream.onopen = () => setStreaming(true);
    stream.onerror = () => setStreaming(false);
    stream.addEventListener("journal", (message) => {
      const event = JSON.parse((message as MessageEvent<string>).data) as Event;
      setEvents((items) =>
        items.some((item) => item.sequence === event.sequence)
          ? items
          : [...items, event].slice(-5000),
      );
    });
    return () => stream.close();
  }, []);
  return (
    <>
      <Panel
        title="Incidents & recovery"
        caption="A connected Gateway does not clear a protection or reconciliation problem."
      >
        {snapshot?.incidents.some((incident) => !incident.resolved) ? (
          snapshot.incidents
            .filter((incident) => !incident.resolved)
            .map((incident) => (
              <div className="ws-incident" key={incident.id}>
                <CircleAlert size={20} />
                <div>
                  <strong>{titleCase(incident.id)}</strong>
                  <p>{incident.detail}</p>
                  <small>{localTime(incident.timestamp)}</small>
                </div>
                <button
                  onClick={() => {
                    void api(
                      `/operations/incidents/${incident.id}/review`,
                      "POST",
                    )
                      .then(async () => {
                        await refresh();
                        notify("Incident review completed.");
                      })
                      .catch((error: Error) => notify(error.message, true));
                  }}
                >
                  Review resolution
                </button>
              </div>
            ))
        ) : (
          <div className="ws-all-clear">
            <CheckCircle2 size={20} />
            <div>
              <strong>No recorded critical incidents</strong>
              <p>Readiness checks still apply before any new authorization.</p>
            </div>
          </div>
        )}
      </Panel>
      <Panel
        title="Audit history"
        caption="Append-only events with resumable streaming. Select a record for details."
        action={
          <Badge tone={streaming ? "success" : "warning"}>
            {streaming ? "Event stream connected" : "Stream reconnecting"}
          </Badge>
        }
      >
        <AuditSearch select={setSelected} />
        <Grid<Event>
          name="activity"
          rows={events}
          rowId={(row) => String(row.sequence)}
          onSelect={setSelected}
          selected={selected ? String(selected.sequence) : undefined}
          columns={[
            { accessorKey: "sequence", header: "Sequence", size: 95 },
            {
              accessorKey: "timestamp",
              header: "Time",
              size: 220,
              cell: ({ row }) => localTime(row.original.timestamp),
            },
            {
              accessorKey: "type",
              header: "Event",
              size: 270,
              cell: ({ row }) =>
                titleCase(row.original.type.replaceAll(".", " ")),
            },
            {
              id: "summary",
              header: "Details",
              size: 400,
              accessorFn: (row) =>
                String(
                  row.payload.reason ??
                    row.payload.detail ??
                    row.payload.name ??
                    (row.payload.ready !== undefined
                      ? `Ready: ${row.payload.ready}`
                      : "Recorded in event ledger"),
                ),
            },
          ]}
        />
      </Panel>
      <LegacyHistory notify={notify} />
      <Modal
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={
          selected
            ? titleCase(selected.type.replaceAll(".", " "))
            : "Event details"
        }
        description={
          selected
            ? `${localTime(selected.timestamp)} · Event ${selected.sequence}`
            : ""
        }
      >
        {selected && (
          <>
            <p>
              This record is immutable. Its payload is available for operational
              diagnosis.
            </p>
            <pre className="ws-event-payload">
              {JSON.stringify(selected.payload, null, 2)}
            </pre>
          </>
        )}
      </Modal>
    </>
  );
}
