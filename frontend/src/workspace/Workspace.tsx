import { useDeskSelection } from "./useDeskSelection";
import { protectionStatus } from "./protectionStatus";
import { ArchiveRuns } from "./ArchiveRuns";
import { IncidentPanel } from "./IncidentPanel";
import { WorkspaceBuild, WorkspaceClock } from "./WorkspaceStatus";
import { RecordHistory } from "./RecordHistory";
import { PrepareRun, PreparationForm } from "./PrepareRun";
import { ContractSearch } from "./ContractSearch";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { AuditHistory } from "./AuditHistory";
import { ReplayCompare } from "./ReplayCompare";
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
  policyLabel,
  readPreference,
  titleCase,
  type ArmPreview,
  type Dataset,
  type Draft,
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
import { RiskSettings, chosenProfile, type RiskProfile } from "./RiskSettings";
import { OrderInspector } from "./OrderInspector";
import { MarketDataDetails } from "./MarketData";
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
  suspended: "Suspended · automatic recovery",
  recovery_required: "Recovery required",
  completed: "Completed",
};

function runTone(run: Run) {
  if (
    run.state === "recovery_required" ||
    run.signal_outcome?.state === "uncertain"
  )
    return "danger";
  if (["blocked", "broker_rejected"].includes(run.signal_outcome?.state ?? ""))
    return "warning";
  if (run.signal_outcome?.state === "checking") return "neutral";
  return run.armed ? "success" : "neutral";
}

export function Workspace() {
  const selection = useDeskSelection();
  const [path, setPath] = useState(() =>
    nav.some((item) => item.path === window.location.pathname)
      ? window.location.pathname
      : "/desk",
  );
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [network, setNetwork] = useState("loading");
  const [environmentMode, setEnvironmentMode] = useState("paper");
  const [auth, setAuth] = useState(true);
  const [theme, setTheme] = useState(() => readPreference("theme", "dark"));
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [preparing, setPreparing] = useState<Version | null>(null);
  const [preparedReview, setPreparedReview] = useState<ArmPreview | null>(null);
  const [clearEmergency, setClearEmergency] = useState(false);
  const notify = useCallback(
    (message: string, error = false) => setToast({ message, error }),
    [],
  );
  const navigate = useCallback((target: string) => {
    window.history.pushState(null, "", target);
    setPath(target);
  }, []);
  const refreshPending = useRef<Promise<void> | null>(null);
  const refreshController = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    if (refreshPending.current) return refreshPending.current;
    const controller = new AbortController();
    refreshController.current = controller;
    const pending = api<Snapshot>(
      "/workspace/overview",
      "GET",
      undefined,
      controller.signal,
    )
      .then((state) => {
        if (!controller.signal.aborted) {
          setSnapshot(state);
          setNetwork("online");
          setAuth(true);
        }
      })
      .catch((error: ApiError) => {
        if (!controller.signal.aborted) {
          setNetwork("offline");
          if (error.status === 401) setAuth(false);
        }
      })
      .finally(() => {
        refreshPending.current = null;
      });
    refreshPending.current = pending;
    return pending;
  }, []);

  useEffect(() => {
    let interval: ReturnType<typeof setTimeout> | undefined;
    let alive = true;
    async function start() {
      try {
        const response = await fetch("/healthz");
        const health = await response.json();
        if (alive) setEnvironmentMode(health.mode);
      } catch {
        /* Session readiness reports unavailable service. */
      }
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
      async function poll() {
        if (!alive) return;
        if (!document.hidden) await refresh();
        if (alive) interval = setTimeout(() => void poll(), 2000);
      }
      await poll();
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
      clearTimeout(interval);
      refreshController.current?.abort();
      window.removeEventListener("popstate", back);
    };
  }, [refresh, notify]);
  useEffect(() => {
    window.document.documentElement.dataset.theme = theme;
    preference("theme", theme);
  }, [theme]);
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
  function createRun(version: Version) {
    setPreparing(version);
  }
  const crypto = (snapshot?.mode ?? environmentMode) === "simulation";
  const current = nav.find((item) => item.path === path) ?? nav[0];
  const critical =
    snapshot?.incidents.filter(
      (incident) =>
        !incident.resolved &&
        incident.severity === "critical" &&
        incident.actionable !== false,
    ) ?? [];
  const armedRuns = snapshot?.runs.filter((r) => r.armed && !r.archived) ?? [];
  const selectedRuns =
    snapshot?.runs.filter(
      (r) => !r.archived && selection.selected.includes(r.id),
    ) ?? [];
  const statusRuns = selectedRuns.length ? selectedRuns : armedRuns;
  const dataFresh =
    statusRuns.length > 0 && statusRuns.every((r) => r.required_inputs?.ready);

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
          <Badge tone="paper">
            {crypto ? "SIMULATION ENVIRONMENT" : "PAPER ENVIRONMENT"}
          </Badge>
          <span>
            {crypto
              ? "Live Paxos data · local fills"
              : "IBKR contracts · Paper execution"}
          </span>
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
              <strong>
                {crypto ? "Local simulated execution" : "Paper execution only"}
              </strong>
              <span>
                {crypto
                  ? "BTC & ETH · fractional units"
                  : "Equities and PAXOS crypto"}
              </span>
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
            {crypto ? "Crypto simulation" : "Internal paper release"}
            <br />
            <span>
              {crypto ? "No broker orders" : "Supervised qualification"}
            </span>
          </p>
        </div>
      </aside>
      <div className="ws-shell">
        <header className="ws-topbar">
          <div className="ws-top-status">
            <Badge tone="paper">
              {crypto
                ? "Simulation — live Paxos data — local fills"
                : "IBKR Paper"}
            </Badge>
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
              {statusRuns.length
                ? `Run inputs ${dataFresh && network === "online" ? "current" : "waiting"}`
                : "Select a run to check inputs"}
            </Badge>
            <Badge
              tone={
                armedRuns.length > 0 && network === "online"
                  ? "success"
                  : "neutral"
              }
            >
              {network !== "online"
                ? "Authorization status unavailable"
                : armedRuns.length
                  ? `${armedRuns.length} armed run${armedRuns.length === 1 ? "" : "s"}`
                  : "No runs armed"}
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
              {crypto
                ? "24/7 crypto data · UTC daily sessions"
                : "Session policy follows the selected contract"}
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
          {snapshot?.migration?.pending && path !== "/settings" && (
            <div className="ws-banner warning" role="status">
              <CircleAlert size={18} />
              <div>
                <strong>
                  Execution disabled until workspace migration completes
                </strong>
                <span>
                  You can browse now and connect paper Gateway later in
                  Settings.
                </span>
              </div>
              <button onClick={() => navigate("/settings")}>
                Open migration setup
              </button>
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
                Run{" "}
                <code>
                  {crypto
                    ? ".\\scripts\\start-crypto-sim.ps1"
                    : ".\\scripts\\start-paper.ps1"}
                </code>{" "}
                on this PC. The launcher opens a private, one-time local pairing
                link. No broker password belongs in this application.
              </Empty>
            </Panel>
          ) : network === "loading" ? (
            <div className="ws-loading" role="status">
              Loading the local workspace…
            </div>
          ) : path === "/studio" ? (
            <Studio
              contracts={snapshot?.contracts ?? []}
              simulation={crypto}
              notify={notify}
              createRun={(version) => void createRun(version)}
            />
          ) : path === "/desk" ? (
            <Desk
              selection={selection}
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
          <WorkspaceClock />
          <WorkspaceBuild build={snapshot?.build} />
        </footer>
      </div>
      <ArmReview
        selectRuns={selection.selectRuns}
        preview={preparedReview}
        contracts={snapshot?.contracts ?? []}
        connection={snapshot?.connection}
        setPreview={setPreparedReview}
        notify={notify}
        refresh={refresh}
        navigate={navigate}
      />
      {preparing && (
        <PrepareRun
          version={preparing}
          connection={snapshot?.connection}
          simulation={crypto}
          contracts={snapshot?.contracts ?? []}
          close={() => setPreparing(null)}
          notify={notify}
          prepared={async (run) => {
            selection.selectRuns([run.id]);
            await refresh();
            setPreparedReview(
              await api<ArmPreview>("/runs/arm-preview", "POST", {
                ids: [run.id],
              }),
            );
          }}
        />
      )}
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
  selection,
  snapshot,
  navigate,
  refresh,
  notify,
}: {
  selection: ReturnType<typeof useDeskSelection>;
  snapshot: Snapshot | null;
  navigate: (path: string) => void;
  refresh: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const { selected, setSelected, detail, setDetail, selectRuns } = selection;
  const reviewRequest = useRef<AbortController | null>(null);
  const selectionKey = selected.join(",");
  useEffect(() => {
    const hidden = () => {
      if (document.hidden) reviewRequest.current?.abort();
    };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      reviewRequest.current?.abort();
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [selectionKey]);
  const [preview, setPreview] = useState<ArmPreview | null>(null);
  const [orderIdentity, setOrderIdentity] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPreparation, setShowPreparation] = useState(false);
  const [archiveIds, setArchiveIds] = useState<string[] | null>(null);
  const [strategies, setStrategies] = useState<Draft[]>([]);
  const [strategy, setStrategy] = useState("");
  const [published, setPublished] = useState<Version | null>(null);
  const [preparationError, setPreparationError] = useState("");
  useEffect(() => {
    setPublished(null);
    setPreparationError("");
    const draft = strategies.find((item) => item.id === strategy);
    if (!showPreparation || !draft) return;
    const controller = new AbortController();
    void api<Version>(
      `/strategies/${draft.id}/versions/${draft.published_version}`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) setPublished(value);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setPreparationError(error.message);
      });
    return () => controller.abort();
  }, [strategy, strategies, showPreparation]);
  const [closeRun, setCloseRun] = useState<Run | null>(null);
  const [checksExpanded, setChecksExpanded] = useState(false);
  const [historicalRun, setHistoricalRun] = useState<Run | null>(null);
  const runs =
    historicalRun && !snapshot?.runs.some((run) => run.id === historicalRun.id)
      ? [...(snapshot?.runs ?? []), historicalRun]
      : (snapshot?.runs ?? []);
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
    reviewRequest.current?.abort();
    const request = new AbortController();
    reviewRequest.current = request;
    setBusy(true);
    try {
      const stockSelection = selected.every(
        (id) => runs.find((r) => r.id === id)?.binding?.execution_plan,
      );
      const profiles = (
        await api<RiskProfile[]>(
          "/risk-profiles",
          "GET",
          undefined,
          request.signal,
        )
      ).filter(
        (p) =>
          (p.stock_units !== undefined) === stockSelection &&
          (p.risk_policy === "paper_stock_v2") ===
            selected.every(
              (id) =>
                runs.find((r) => r.id === id)?.binding?.execution_plan
                  ?.risk_policy === "paper_stock_v2",
            ),
      );
      const chosen = chosenProfile();
      const current =
        profiles.find(
          (p) =>
            p.id === chosen.id &&
            p.version === chosen.version &&
            p.daily_loss === undefined,
        ) ??
        profiles
          .filter((p) => p.id === chosen.id && p.daily_loss === undefined)
          .sort((a, b) => b.version - a.version)[0];
      const value = await api<ArmPreview>(
        "/runs/arm-preview",
        "POST",
        {
          ids: selected,
          profile_id: current?.id ?? "smoke",
          profile_version: current?.version ?? null,
        },
        request.signal,
      );
      if (!request.signal.aborted) setPreview(value);
    } catch (error) {
      if (!request.signal.aborted) notify((error as Error).message, true);
    } finally {
      if (reviewRequest.current === request) setBusy(false);
    }
  }
  const run = runs.find((item) => item.id === detail);
  const blocking = snapshot?.checks.filter((check) => !check.passed) ?? [];
  const positionCount =
    snapshot?.positions.filter((position) => Number(position.quantity) !== 0)
      .length ?? 0;
  return (
    <>
      {archiveIds && (
        <ArchiveRuns
          ids={archiveIds}
          notify={notify}
          refresh={refresh}
          close={() => {
            setArchiveIds(null);
            setSelected([]);
            setHistoricalRun(null);
          }}
        />
      )}

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
            <small> / {snapshot?.mode === "simulation" ? 2 : 5} capacity</small>
          </strong>
          <span className="ws-muted">Bounded session authorization</span>
        </div>
        <div>
          <span>Owned positions</span>
          <strong>
            {positionCount}
            <small> / {snapshot?.mode === "simulation" ? 2 : 5} capacity</small>
          </strong>
          <span className="ws-muted">
            {runs.some(
              (item) =>
                Number(item.position) > 0 &&
                !item.protected &&
                !["checking", "exit_pending"].includes(
                  item.protection_verification?.state ?? "",
                ),
            )
              ? "Protection needs attention"
              : runs.some(
                    (item) =>
                      Number(item.position) > 0 &&
                      item.protection_verification?.state === "checking",
                  )
                ? "Checking broker protection"
                : "Protection checked on reconciliation"}
          </span>
        </div>
        <div>
          <span>
            {snapshot?.mode === "simulation"
              ? "Simulated gross exposure"
              : "Broker gross exposure"}
          </span>
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
              disabled={!selected.length || selected.length > 50 || busy}
              onClick={() => setArchiveIds([...selected])}
            >
              Archive selected
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
                    disabled={row.original.archived}
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
                    {row.original.binding?.execution_plan && (
                      <small>
                        {policyLabel(row.original)} |{" "}
                        {row.original.id.slice(0, 8)}
                      </small>
                    )}
                  </div>
                ),
              },
              { accessorKey: "symbol", header: "Symbol", size: 100 },
              {
                accessorKey: "state",
                header: "State",
                size: 200,
                cell: ({ row }) => (
                  <span className="ws-run-status">
                    <Badge tone={runTone(row.original)}>
                      {row.original.display_state ??
                        runState[row.original.state] ??
                        titleCase(row.original.state)}
                    </Badge>
                  </span>
                ),
              },
              {
                accessorKey: "position",
                header: "Position",
                size: 100,
                cell: ({ row }) => (
                  <span className="ws-number">
                    {row.original.position} units
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
          caption={
            snapshot?.mode === "simulation"
              ? "Owned executions compared with the durable local ledger."
              : runs.some(
                    (r) => r.binding?.execution_plan?.family === "spot_fx",
                  )
                ? "Owned executions compared with broker positions and real currency balances."
                : "Owned executions compared with broker positions."
          }
        >
          {positionCount ? (
            snapshot?.positions
              .filter((item) => Number(item.quantity) !== 0)
              .map((position) => {
                const owner = runs.find((item) => item.id === position.run_id);
                const verification = owner?.protection_verification;
                const protection = verification
                  ? protectionStatus(
                      verification,
                      owner?.protection_type === "locally_monitored",
                    )
                  : null;
                return (
                  <div className="ws-position" key={position.run_id}>
                    <div>
                      <strong>{position.symbol}</strong>
                      <span>
                        {Number(position.quantity) < 0 ? "Short" : "Long"} ·{" "}
                        {Math.abs(Number(position.quantity))}{" "}
                        {owner?.binding?.execution_plan?.family === "spot_fx"
                          ? owner.binding.contract.symbol
                          : "units"}{" "}
                        · {owner?.name}
                      </span>
                    </div>
                    <div>
                      <Badge
                        tone={
                          protection?.tone ??
                          (owner?.protected ? "success" : "danger")
                        }
                      >
                        {protection?.label ??
                          (owner?.protected
                            ? "Protection verified"
                            : "Protection requires review")}
                      </Badge>
                      {verification?.reasons.map((reason) => (
                        <small key={reason}>{reason}</small>
                      ))}
                      {verification?.state === "active" &&
                        verification.broker_status && (
                          <small>
                            SELL {position.quantity} {owner?.symbol} · Stop{" "}
                            {verification.stop} · {verification.broker_status}
                          </small>
                        )}
                    </div>
                    <button onClick={() => owner && setCloseRun(owner)}>
                      {Number(position.quantity) < 0
                        ? "Buy to cover"
                        : "Close owned position"}
                    </button>
                  </div>
                );
              })
          ) : (
            <Empty title="No owned positions">
              Positions appear after confirmed executions and reconciliation.
            </Empty>
          )}
        </Panel>
        <Panel
          title="Market data"
          caption="Last, bid and ask with timestamps and historical warm-up progress."
        >
          {snapshot?.data.length ? (
            <div className="ws-data-list">
              {snapshot.data.map((data) => (
                <MarketDataDetails key={data.conid} data={data} />
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
        caption="A request remains pending until the execution provider confirms its outcome."
      >
        {snapshot?.outage?.active && (
          <div role="status" className="ws-banner">
            Recovery in progress. Positions are retained; local protection may
            be suspended. New entries require fresh review.
          </div>
        )}
        {[
          ...(snapshot?.crypto_triggers ?? []),
          ...(snapshot?.stock_triggers ?? []),
        ].map((trigger) => (
          <div key={trigger.run_id} aria-label="Long-only trigger status">
            <strong>Previous-minute long-only breakout</strong>
            <p>
              {titleCase(trigger.state)} | High {trigger.high ?? "unavailable"}{" "}
              | Candle {localTime(trigger.candle)}
            </p>
            {trigger.reason && <p>{trigger.reason}</p>}
          </div>
        ))}
        {[
          ...(snapshot?.local_protection ?? []).map((p) => ({
            ...p,
            type: "locally_monitored",
            currency: "USD",
            price_scale: "1",
          })),
          ...(snapshot?.stock_protection ?? []),
          ...(snapshot?.fx_protection ?? []),
        ].map((plan) => (
          <div key={plan.run_id} aria-label="Local protection status">
            <strong>
              {plan.type === "broker_held"
                ? "Broker-held protection"
                : "Locally monitored protection"}
            </strong>
            <p>
              {titleCase(plan.status)} | {plan.quantity}{" "}
              {"base_currency" in plan ? plan.base_currency : "units"} | Entry{" "}
              {plan.average
                ? "family" in plan && plan.family === "spot_fx"
                  ? `${plan.average} ${plan.currency} per ${plan.base_currency}`
                  : money(plan.average, plan.currency, plan.price_scale)
                : "awaiting fill"}{" "}
              | Stop{" "}
              {"family" in plan && plan.family === "spot_fx"
                ? `${plan.stop} ${plan.currency} per ${plan.base_currency}`
                : money(plan.stop, plan.currency, plan.price_scale)}{" "}
              {plan.currency}
            </p>
            {plan.type === "locally_monitored" && (
              <p>
                This stop cannot execute while the application or connection is
                unavailable.
              </p>
            )}
          </div>
        ))}
        {snapshot?.oca_groups?.map((group) => (
          <div
            key={group.id}
            className="ws-position"
            aria-label="OCA group status"
          >
            <div>
              <strong>
                OCA · {titleCase(group.state)}
                {group.winner
                  ? ` · ${titleCase(group.winner)}`
                  : " · Awaiting direction"}
              </strong>
              <span>
                Candle {localTime(group.candle)} · Protection:{" "}
                {titleCase(group.protection)}
              </span>
              {group.average && (
                <span>
                  Average fill{" "}
                  {money(group.average, group.currency, group.price_scale)} ·
                  Fixed stop{" "}
                  {money(group.stop, group.currency, group.price_scale)}
                </span>
              )}
            </div>
          </div>
        ))}
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
                accessorFn: (row) =>
                  row.payload.execution === "oca_breakout"
                    ? "OCA entry pair"
                    : titleCase(row.payload.purpose ?? "entry"),
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
                    {row.original.diagnostics?.rejection
                      ? "Broker rejected"
                      : (row.original.diagnostics?.status_label ??
                        titleCase(row.original.state))}
                  </Badge>
                ),
              },
              {
                id: "quantity",
                header: "Quantity",
                accessorFn: (row) =>
                  row.payload.cash_quantity
                    ? `${money(row.payload.cash_quantity)} budget`
                    : row.payload.quantity,
              },
              {
                id: "limit",
                header: "Entry price",
                accessorFn: (row) => row.payload.limit,
                cell: ({ row }) =>
                  row.original.payload.prices
                    ? `Buy ${money(row.original.payload.prices.long_entry, row.original.payload.currency, row.original.payload.price_scale)} / Short ${money(row.original.payload.prices.short_entry, row.original.payload.currency, row.original.payload.price_scale)}`
                    : money(
                        row.original.payload.limit,
                        row.original.payload.currency,
                        row.original.payload.price_scale,
                      ),
              },
              {
                id: "stop",
                header: "Protective stop",
                accessorFn: (row) => row.payload.stop,
                cell: ({ row }) =>
                  row.original.payload.prices
                    ? "1% from actual fill"
                    : money(
                        row.original.payload.stop,
                        row.original.payload.currency,
                        row.original.payload.price_scale,
                      ),
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
          <div className="ws-run-status">
            <Badge tone={runTone(run)}>
              {run.display_state ?? runState[run.state] ?? run.state}
            </Badge>
          </div>
          <dl>
            <dt>Position</dt>
            <dd>{run.position} units</dd>
            <dt>Planned stop risk</dt>
            <dd>{money(run.risk)}</dd>
            <dt>Session ends</dt>
            <dd>{exchangeTime(run.expires_at)}</dd>
            <dt>Local session end</dt>
            <dd>{localTime(run.expires_at)}</dd>
            <dt>Protection</dt>
            <dd>
              {Number(run.position)
                ? run.protection_verification
                  ? protectionStatus(
                      run.protection_verification,
                      run.protection_type === "locally_monitored",
                    ).label
                  : run.protected
                    ? "Verified at reconciliation"
                    : "Requires recovery"
                : run.binding?.execution_plan &&
                    run.protection_type === "broker_held"
                  ? "Protection plan approved; stop submitted for confirmed fills."
                  : run.binding?.execution_plan
                    ? "Local protection plan selected; monitors confirmed fills."
                    : "Required before entry"}
              {run.protection_verification?.reasons.map((reason) => (
                <p key={reason}>{reason}</p>
              ))}
            </dd>
          </dl>
          {run.blocking_reason && (
            <div className="ws-banner warning">{run.blocking_reason}</div>
          )}
          <h3>Current rule values</h3>
          {run.signal_progress && (
            <dl>
              <dt>Reference minute</dt>
              <dd>
                {localTime(run.signal_progress.reference_candle ?? undefined)}
              </dd>
              <dt>Reference high</dt>
              <dd>
                {run.signal_progress.reference_high ??
                  "Waiting for a complete live minute"}
              </dd>
              <dt>Current {run.signal_progress.source}</dt>
              <dd>{run.signal_progress.price}</dd>
              <dt>Price strictly above reference high</dt>
              <dd>
                {run.signal_progress.above_high == null
                  ? "Waiting"
                  : String(run.signal_progress.above_high)}
              </dd>
            </dl>
          )}
          {run.signal_outcome && (
            <section aria-label="Latest signal outcome">
              <h3>Latest signal outcome</h3>
              <p>{run.signal_outcome.detail}</p>
              {run.signal_outcome.last_reason && (
                <p>Last entry check: {run.signal_outcome.last_reason}</p>
              )}
              <p className="ws-muted">
                {localTime(run.signal_outcome.updated_at)}
              </p>
              {run.signal_outcome.rejection && (
                <p>
                  IBKR {run.signal_outcome.rejection.code}:{" "}
                  {run.signal_outcome.rejection.detail}
                </p>
              )}
            </section>
          )}
          {!run.signal_progress && (
            <>
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
                        {item.value === null
                          ? "Not available"
                          : String(item.value)}
                      </dd>
                    </Fragment>
                  ))}
                </dl>
              ) : (
                <p className="ws-muted">Waiting for qualified market data.</p>
              )}
            </>
          )}
          <button
            disabled={!run.armed || busy || run.archived}
            onClick={() => void action(`/runs/${run.id}/disarm`)}
          >
            {run.archived ? "Archived run" : "Disarm strategy"}
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
      <RecordHistory
        selectOrder={setOrderIdentity}
        selectRun={(run) => {
          setHistoricalRun(run);
          setDetail(run.id);
        }}
      />
      <OrderInspector
        identity={orderIdentity}
        close={() => setOrderIdentity(null)}
      />

      <ArmReview
        selectRuns={selectRuns}
        preview={preview}
        contracts={snapshot?.contracts ?? []}
        connection={snapshot?.connection}
        setPreview={setPreview}
        notify={notify}
        refresh={refresh}
        navigate={navigate}
      />
      <Modal
        open={showPreparation}
        onOpenChange={setShowPreparation}
        title="Prepare a strategy run"
        description="Choose a published strategy, then bind its immutable rules and limits to an exact resolved contract."
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
                    {item.name} ·{" "}
                    {item.document.schema_version === 9
                      ? "Reusable FX"
                      : [7, 8].includes(item.document.schema_version)
                        ? "Reusable stock"
                        : item.document.nodes.some(
                              (n) => n.kind === "long_breakout",
                            )
                          ? "Legacy crypto"
                          : item.document.settings.symbol || "Legacy"}{" "}
                    · v{item.published_version}
                  </option>
                ))}
              </select>
            </label>
            <p className="ws-muted">
              Preparing a run starts data warm-up. It does not authorize order
              submission.
            </p>
            {preparationError && <p role="alert">{preparationError}</p>}
            {published && published.strategy_id === strategy ? (
              <PreparationForm
                connection={snapshot?.connection}
                key={`${published.strategy_id}:${published.version}`}
                version={published}
                contracts={snapshot?.contracts ?? []}
                close={() => setShowPreparation(false)}
                prepared={async (run) => {
                  selectRuns([run.id]);
                  await refresh();
                  setPreview(
                    await api<ArmPreview>("/runs/arm-preview", "POST", {
                      ids: [run.id],
                    }),
                  );
                }}
                notify={notify}
                simulation={snapshot?.mode === "simulation"}
              />
            ) : (
              !preparationError && (
                <p role="status">Loading immutable published version?</p>
              )
            )}
            <button onClick={() => setShowPreparation(false)}>Cancel</button>
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
        title={
          closeRun && Number(closeRun.position) < 0
            ? "Buy to cover an owned short position"
            : "Close an owned position"
        }
        description="The engine rechecks ownership and broker state. The existing protective order remains in its OCA group while the exit request is pending."
      >
        {closeRun && (
          <>
            <p>
              {closeRun.symbol} · {closeRun.position} units · {closeRun.name}
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
  const crypto = snapshot?.mode === "simulation";
  const [busy, setBusy] = useState(false);
  const [subscriptionDependencies, setSubscriptionDependencies] = useState<
    ApiError["dependencies"]
  >([]);
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
    if (path === "/market-data/unsubscribe") setSubscriptionDependencies([]);
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
      if (path === "/market-data/unsubscribe" && error instanceof ApiError)
        setSubscriptionDependencies(error.dependencies);
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
          <h2>
            {crypto
              ? "Prepare your crypto simulation"
              : "Prepare your paper environment"}
          </h2>
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
          {snapshot?.migration?.pending && (
            <div className="ws-banner warning" role="status">
              <div>
                <strong>
                  {snapshot.migration.status === "checking"
                    ? "Checking workspace migration"
                    : "Workspace migration pending"}
                </strong>
                <p>{snapshot.migration.detail}</p>
                <p>
                  You can browse the app and edit strategies while Gateway is
                  closed. Execution stays disabled. When ready, sign in to the
                  paper Gateway and click Connect paper Gateway. After the check
                  succeeds, paper context is verified automatically.
                </p>
              </div>
            </div>
          )}
          <dl className="ws-facts">
            <dt>Application</dt>
            <dd>IB Gateway · official offline build</dd>
            <dt>Endpoint</dt>
            <dd>127.0.0.1 · port 4002</dd>
            <dt>API client</dt>
            <dd>{crypto ? 72 : 71} · dedicated to this workspace</dd>
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
                {crypto
                  ? "Keep Read-Only API enabled. This workspace uses Gateway only for data; all orders and protection are local simulations."
                  : "For initial diagnostics, keep the API read-only. Disable read-only only for the explicitly authorized supervised paper execution trial."}
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
              disabled={
                busy ||
                snapshot?.connection === "connected" ||
                snapshot?.migration?.status === "checking"
              }
              onClick={() => void action("/workspace/session/connect")}
            >
              <Cable size={16} />
              {snapshot?.migration?.status === "checking"
                ? "Checking migration…"
                : snapshot?.connection === "connected"
                  ? "Gateway connected"
                  : "Connect paper Gateway"}
            </button>
            <button
              disabled={busy || !snapshot?.attested}
              onClick={() => void action("/workspace/session/reconcile")}
            >
              <RefreshCw size={15} />
              Recheck
            </button>
          </div>
          <p>
            Paper context is verified automatically from the broker handshake.
            Reconciliation refreshes automatically; Recheck remains available
            for diagnostics.
          </p>
        </Panel>
        <Panel
          title="2. Verify market data"
          caption={
            crypto
              ? "Resolve BTC or ETH on PAXOS and verify live data."
              : "Search IBKR contracts across asset classes and verify account data entitlements."
          }
        >
          <ContractSearch snapshot={snapshot} busy={busy} action={action} />
          {subscriptionDependencies.length > 0 && (
            <div role="alert">
              <strong>This subscription is currently needed:</strong>
              <ul>
                {subscriptionDependencies.map((dependency, index) => (
                  <li key={`${dependency.code}-${index}`}>
                    {dependency.run_name ? `${dependency.run_name}: ` : ""}
                    {dependency.detail}{" "}
                    <a
                      href={
                        dependency.action === "activity" ? "/activity" : "/desk"
                      }
                    >
                      Inspect {dependency.run_name ?? "current operations"}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {snapshot?.data.map((data) => (
            <div className="ws-inline-actions" key={data.conid}>
              <strong>{data.symbol}</strong>
              <Badge tone={data.live ? "success" : "warning"}>
                {data.live ? "Live entitlement" : "Data entitlement pending"}
              </Badge>
              <Badge tone={data.warm ? "success" : "neutral"}>
                {data.history_loaded
                  ? "History downloaded"
                  : "Downloading history"}
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
        <RiskSettings notify={notify} simulation={crypto} />
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
                Healthchecks ping URL (optional)
                <input
                  type="password"
                  autoComplete="off"
                  value={heartbeat}
                  onChange={(event) => setHeartbeat(event.target.value)}
                  placeholder="https://hc-ping.com/…"
                />
              </label>
            </div>
            <button type="submit" disabled={busy || !token || !chat}>
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
        <Panel
          title="Account diagnostics"
          caption="Daily P/L is informational and never blocks entries."
        >
          <p>
            Daily P/L:{" "}
            <strong>
              {snapshot?.pnl?.currency
                ? money(snapshot.pnl.value ?? undefined, snapshot.pnl.currency)
                : "Unavailable currency"}
            </strong>{" "}
            - {snapshot?.pnl?.status ?? "unavailable"}
          </p>
          <small>Last updated {localTime(snapshot?.pnl?.received_at)}</small>
          {snapshot?.pnl?.diagnostic && <p>{snapshot.pnl.diagnostic}</p>}
          <p>{snapshot?.reconciliation?.detail}</p>
          {snapshot?.currency_positions?.map((position) => (
            <p key={position.conid}>
              {position.symbol}/{position.currency}: {position.quantity} -{" "}
              {position.exchange} currency position
            </p>
          ))}
          {snapshot?.simulation_assumptions?.map((item) => (
            <p key={item}>{item}</p>
          ))}
        </Panel>
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
    setVersions([]);
    setVersion(0);
    const controller = new AbortController();
    void api<Version[]>(
      `/strategies/${strategy}/versions`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((items) => {
        if (!controller.signal.aborted) {
          setVersions(items);
          setVersion(items[0]?.version ?? 0);
        }
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) notify(error.message, true);
      });
    return () => controller.abort();
  }, [strategy, notify]);
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
                  ? `${result.open_position.quantity} units still open`
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
                Prepare a run <ArrowUpRight size={14} />
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
  return (
    <>
      <IncidentPanel snapshot={snapshot} notify={notify} refresh={refresh} />
      <AuditHistory />
      <LegacyHistory notify={notify} />
    </>
  );
}
