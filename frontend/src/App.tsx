import { useEffect, useMemo, useState } from "react";

import {
  createReadApiClient,
  initialReadApiState,
  loadOperationsSnapshot,
  type AlertApiView,
  type OperationsApiSnapshot,
  type PositionApiView,
  type ReadApiClient,
  type ReadApiLoadState,
} from "./readApiClient";
import {
  defaultStrategyBuilderState,
  formatStrategyDslPreview,
  strategyBuilderNodes,
  updateStrategyBuilderState,
} from "./strategyBuilder";

type Tone = "neutral" | "good" | "warning" | "critical" | "info";

type SummaryPanel = {
  title: string;
  metric: string;
  detail: string;
  tone: Tone;
};

type WorkflowRow = {
  label: string;
  detail: string;
  status: string;
  tone: Tone;
};

type SimulationRunDetailItem = {
  group: string;
  label: string;
  detail: string;
  status: string;
  tone: Tone;
};

type AppProps = {
  initialReadState?: ReadApiLoadState;
  readApiClient?: ReadApiClient;
};

const visualBuilderSection = "Visual builder" as const;
const simulationRunSection = "Simulation run detail" as const;

const workflowSections = [
  "Signals",
  "Approval tickets",
  "Orders",
  "Positions",
  "Audit events",
  "Alerts",
] as const;

type WorkflowSection = (typeof workflowSections)[number];

const shellSections = [visualBuilderSection, simulationRunSection, ...workflowSections] as const;

const simulationRunTimeline: SimulationRunDetailItem[] = [
  {
    group: "Timeline",
    label: "Replay loaded",
    detail: "AAPL session replay built 5-minute bars",
    status: "completed",
    tone: "good",
  },
  {
    group: "Timeline",
    label: "Signal generated",
    detail: "First 5-minute breakout with 1.5x volume filter",
    status: "long entry candidate",
    tone: "info",
  },
  {
    group: "Timeline",
    label: "Risk evaluated",
    detail: "Fresh data, known simulation broker state, protection plan present",
    status: "passed",
    tone: "good",
  },
  {
    group: "Timeline",
    label: "Approval decided",
    detail: "Manual simulation approval recorded",
    status: "approved",
    tone: "good",
  },
  {
    group: "Timeline",
    label: "Fake broker filled",
    detail: "Local fake broker acknowledged and filled the simulation order",
    status: "filled",
    tone: "good",
  },
  {
    group: "Timeline",
    label: "Protection monitored",
    detail: "Missing expected stop-loss protection raised a local critical alert",
    status: "critical alert",
    tone: "critical",
  },
];

const simulationRunDetailItems: SimulationRunDetailItem[] = [
  {
    group: "Signal",
    label: "signal-001",
    detail: "AAPL breakout above first 5-minute high",
    status: "long entry candidate",
    tone: "info",
  },
  {
    group: "Risk",
    label: "risk-001",
    detail: "Duplicate, stale data, and unknown state checks passed",
    status: "passed",
    tone: "good",
  },
  {
    group: "Approval",
    label: "approval-ticket-001",
    detail: "Manual simulation approval captured with actor and reason",
    status: "approved",
    tone: "good",
  },
  {
    group: "OMS",
    label: "order-001",
    detail: "CREATED -> PENDING_APPROVAL -> APPROVED -> SUBMITTED -> FILLED",
    status: "filled",
    tone: "good",
  },
  {
    group: "Fake broker",
    label: "fake-client-001",
    detail: "Simulation-only acknowledgement and fill",
    status: "filled",
    tone: "good",
  },
  {
    group: "Fill",
    label: "fill-001",
    detail: "10 AAPL at 102.00 from local fake broker",
    status: "simulated",
    tone: "info",
  },
  {
    group: "Position",
    label: "position-AAPL",
    detail: "Quantity 10, expected stop-loss protection missing",
    status: "missing expected protection",
    tone: "critical",
  },
  {
    group: "Alert",
    label: "alert-position-update-001",
    detail: "Local no-op critical alert recorded",
    status: "critical",
    tone: "critical",
  },
  {
    group: "Audit",
    label: "journal",
    detail: "Signal, proposal, risk, approval, OMS, fill, position, and alert events",
    status: "append only",
    tone: "info",
  },
];

export function App({ initialReadState, readApiClient }: AppProps = {}) {
  const [builderState, setBuilderState] = useState(defaultStrategyBuilderState);
  const [readState, setReadState] = useState<ReadApiLoadState>(
    initialReadState ?? initialReadApiState,
  );
  const dslPreview = useMemo(() => formatStrategyDslPreview(builderState), [builderState]);
  const shouldLoadFromBackend = !initialReadState || initialReadState.status === "loading";
  const snapshot = readState.snapshot;
  const summaryPanels = useMemo(() => buildSummaryPanels(snapshot), [snapshot]);
  const workflowRows = useMemo(() => buildWorkflowRows(snapshot), [snapshot]);

  useEffect(() => {
    if (!shouldLoadFromBackend) {
      return;
    }

    let isCurrent = true;
    setReadState(initialReadApiState);

    loadOperationsSnapshot(readApiClient ?? createReadApiClient()).then((state) => {
      if (isCurrent) {
        setReadState(state);
      }
    });

    return () => {
      isCurrent = false;
    };
  }, [readApiClient, shouldLoadFromBackend]);

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Read-only operations shell</p>
          <h1>Trading OMS</h1>
        </div>
        <div className="status-strip" aria-label="Safety posture">
          <StatusPill tone="good" label={`${titleCase(formatIdentifier(snapshot.safety.app_mode))} mode`} />
          <StatusPill tone="good" label="Live trading disabled" />
          <StatusPill
            tone="neutral"
            label={`Broker connectivity ${formatIdentifier(snapshot.safety.broker_connectivity)}`}
          />
          <StatusPill tone={readStateTone(readState)} label={readStateLabel(readState)} />
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar" aria-label="Workflow navigation">
          <nav>
            {shellSections.map((section) => (
              <a key={section} href={`#${sectionId(section)}`}>
                {section}
              </a>
            ))}
          </nav>
        </aside>

        <main className="console" aria-labelledby="console-heading">
          <section className="safety-band" aria-labelledby="console-heading">
            <div>
              <p className="eyebrow">Safety posture</p>
              <h2 id="console-heading">
                {titleCase(formatIdentifier(snapshot.safety.app_mode))} workflow
              </h2>
              {readState.errorMessage ? <p className="state-note">{readState.errorMessage}</p> : null}
            </div>
            <dl className="posture-grid">
              <PostureItem
                label="Mode"
                value={`${titleCase(formatIdentifier(snapshot.safety.app_mode))} mode`}
              />
              <PostureItem
                label="Live trading"
                value={snapshot.safety.live_trading_enabled ? "Enabled" : "Live trading disabled"}
              />
              <PostureItem
                label="Broker connectivity"
                value={`Broker connectivity ${formatIdentifier(snapshot.safety.broker_connectivity)}`}
              />
              <PostureItem label="Approval" value={formatApprovalMode(snapshot.safety.approval_mode)} />
              <PostureItem label="Journal" value="Append-only journal" />
              <PostureItem
                label="Alert delivery"
                value={`Alert delivery ${formatIdentifier(snapshot.safety.alert_delivery)}`}
              />
            </dl>
          </section>

          <section className="summary-grid" aria-label="Workflow summary">
            {summaryPanels.map((panel) => (
              <article className="summary-panel" key={panel.title}>
                <div className="panel-heading">
                  <h3>{panel.title}</h3>
                  <span className={`swatch swatch-${panel.tone}`} aria-hidden="true" />
                </div>
                <p className="metric">{panel.metric}</p>
                <p>{panel.detail}</p>
              </article>
            ))}
          </section>

          <section className="builder-section" id={sectionId("Visual builder")}>
            <div className="builder-heading">
              <div>
                <p className="eyebrow">Visual builder</p>
                <h2>Replay strategy workflow</h2>
              </div>
              <div className="status-strip" aria-label="Builder safety posture">
                <StatusPill tone="good" label="Replay only" />
                <StatusPill tone="neutral" label="No broker connectivity" />
                <StatusPill tone="neutral" label="No order actions" />
                <StatusPill tone="neutral" label="No credential fields" />
              </div>
            </div>

            <div className="builder-layout">
              <div className="node-map" aria-label="Visual Strategy DSL workflow nodes">
                {strategyBuilderNodes.map((node, index) => (
                  <article className="builder-node" key={node.id}>
                    <span className="node-index" aria-label={`Node ${index + 1}`}>
                      {index + 1}
                    </span>
                    <div>
                      <h3>{node.label}</h3>
                      <p>{node.detail}</p>
                    </div>
                  </article>
                ))}
              </div>

              <div className="builder-controls" aria-label="Safe Strategy DSL controls">
                <label>
                  <span>Symbol</span>
                  <input
                    aria-label="Strategy symbol"
                    maxLength={12}
                    name="symbol"
                    onChange={(event) =>
                      setBuilderState((current) =>
                        updateStrategyBuilderState(current, { symbol: event.target.value }),
                      )
                    }
                    value={builderState.symbol}
                  />
                </label>
                <label>
                  <span>Lookback bars</span>
                  <input
                    aria-label="Strategy lookback bars"
                    min={2}
                    name="lookbackBars"
                    onChange={(event) =>
                      setBuilderState((current) =>
                        updateStrategyBuilderState(current, {
                          lookbackBars: event.target.valueAsNumber,
                        }),
                      )
                    }
                    type="number"
                    value={builderState.lookbackBars}
                  />
                </label>
                <label>
                  <span>Timeframe seconds</span>
                  <input
                    aria-label="Strategy timeframe seconds"
                    min={1}
                    name="timeframeSeconds"
                    onChange={(event) =>
                      setBuilderState((current) =>
                        updateStrategyBuilderState(current, {
                          timeframeSeconds: event.target.valueAsNumber,
                        }),
                      )
                    }
                    type="number"
                    value={builderState.timeframeSeconds}
                  />
                </label>
              </div>

              <div className="dsl-preview" aria-label="Generated Strategy DSL preview">
                <div className="section-heading">
                  <h2>Generated DSL preview</h2>
                  <span>local only</span>
                </div>
                <pre>{dslPreview}</pre>
              </div>
            </div>
          </section>

          <section className="run-detail-section" id={sectionId(simulationRunSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Simulation run</p>
                <h2>Run sim-run-001</h2>
              </div>
              <StatusPill tone="good" label="Simulation only" />
            </div>
            <div className="run-detail-layout">
              <div className="run-timeline" aria-label="Simulation run timeline">
                {simulationRunTimeline.map((item, index) => (
                  <article className="timeline-step" key={item.label}>
                    <span className="node-index" aria-label={`Timeline step ${index + 1}`}>
                      {index + 1}
                    </span>
                    <div>
                      <h3>{item.label}</h3>
                      <p>{item.detail}</p>
                    </div>
                    <StatusPill tone={item.tone} label={item.status} />
                  </article>
                ))}
              </div>
              <div className="run-detail-grid" aria-label="Simulation run detail records">
                {simulationRunDetailItems.map((item) => (
                  <article className="run-detail-card" key={`${item.group}-${item.label}`}>
                    <div className="panel-heading">
                      <div>
                        <p className="eyebrow">{item.group}</p>
                        <h3>{item.label}</h3>
                      </div>
                      <span className={`swatch swatch-${item.tone}`} aria-hidden="true" />
                    </div>
                    <p>{item.detail}</p>
                    <StatusPill tone={item.tone} label={item.status} />
                  </article>
                ))}
              </div>
            </div>
          </section>

          <div className="section-grid">
            {workflowSections.map((section) => {
              const rows = workflowRows[section];
              return (
                <section className="workflow-section" id={sectionId(section)} key={section}>
                  <div className="section-heading">
                    <h2>{section}</h2>
                    <span>{rows.length} records</span>
                  </div>
                  <div className="record-list">
                    {rows.length === 0 ? (
                      <p className="empty-state">No records</p>
                    ) : (
                      rows.map((row) => (
                        <article className="record-row" key={`${section}-${row.label}`}>
                          <div>
                            <h3>{row.label}</h3>
                            <p>{row.detail}</p>
                          </div>
                          <StatusPill tone={row.tone} label={row.status} />
                        </article>
                      ))
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
}

function buildSummaryPanels(snapshot: OperationsApiSnapshot): SummaryPanel[] {
  const pendingTickets = snapshot.approvalTickets.filter((ticket) => ticket.status === "pending").length;
  const criticalAlerts = snapshot.alerts.filter((alert) =>
    ["critical", "emergency"].includes(alert.severity),
  ).length;

  return [
    {
      title: "Signals",
      metric: `${snapshot.signals.length} read`,
      detail: "Backend read API signals; no order intents.",
      tone: snapshot.signals.length > 0 ? "info" : "neutral",
    },
    {
      title: "Approval tickets",
      metric: `${pendingTickets} pending`,
      detail: "Inspection only; no approval action endpoint.",
      tone: pendingTickets > 0 ? "warning" : "neutral",
    },
    {
      title: "Orders",
      metric: "0 live",
      detail: `${snapshot.orders.length} read records; no broker route is configured.`,
      tone: "good",
    },
    {
      title: "Alerts",
      metric: `${criticalAlerts} critical`,
      detail: "Read API alert records; no external delivery configured.",
      tone: criticalAlerts > 0 ? "critical" : "neutral",
    },
  ];
}

function buildWorkflowRows(snapshot: OperationsApiSnapshot): Record<WorkflowSection, WorkflowRow[]> {
  return {
    Signals: snapshot.signals.map((signal) => ({
      label: `${signal.symbol} ${signal.strategy_id}`,
      detail: `${formatIdentifier(signal.signal)} from ${formatIdentifier(signal.reason)}`,
      status: signal.signal,
      tone: signal.signal === "long_bias" ? "info" : "neutral",
    })),
    "Approval tickets": snapshot.approvalTickets.map((ticket) => ({
      label: ticket.ticket_id,
      detail: `${ticket.side} ${ticket.quantity} ${ticket.symbol}; risk ${ticket.risk_decision_id}`,
      status: ticket.status,
      tone: approvalTone(ticket.status),
    })),
    Orders: snapshot.orders.map((order) => ({
      label: order.client_order_id,
      detail: `${order.side} ${order.quantity} ${order.symbol}; leaves ${order.leaves_quantity}`,
      status: formatIdentifier(order.state),
      tone: order.requires_reconciliation ? "critical" : orderTone(order.state),
    })),
    Positions: snapshot.positions.map((position) => ({
      label: position.position_id,
      detail: `${position.symbol} quantity ${position.quantity} at ${position.average_price}`,
      status: formatIdentifier(position.protection_status),
      tone: positionTone(position),
    })),
    "Audit events": snapshot.auditEvents.map((event) => ({
      label: event.event_type,
      detail: event.summary,
      status: `sequence ${event.sequence}`,
      tone: event.event_type.includes("alert") ? "critical" : "info",
    })),
    Alerts: snapshot.alerts.map((alert) => ({
      label: alert.title,
      detail: `${formatIdentifier(alert.channel)} alert from ${alert.source_event_reference}`,
      status: alert.severity,
      tone: alertTone(alert),
    })),
  };
}

function StatusPill({ label, tone }: { label: string; tone: Tone }) {
  return <span className={`status-pill status-${tone}`}>{label}</span>;
}

function PostureItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function sectionId(section: string) {
  return section.toLowerCase().replace(/\s+/g, "-");
}

function titleCase(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatIdentifier(value: string) {
  return value.toLowerCase().replace(/[_-]+/g, " ");
}

function formatApprovalMode(value: string) {
  if (value === "manual_required") {
    return "Manual approval required";
  }
  return titleCase(formatIdentifier(value));
}

function readStateLabel(readState: ReadApiLoadState) {
  if (readState.status === "loading") {
    return "Read API loading";
  }
  if (readState.status === "error") {
    return "Read API fallback";
  }
  if (readState.status === "empty") {
    return "Read API empty";
  }
  return "Read API loaded";
}

function readStateTone(readState: ReadApiLoadState): Tone {
  if (readState.status === "error") {
    return "warning";
  }
  if (readState.status === "loading" || readState.status === "empty") {
    return "neutral";
  }
  return "good";
}

function approvalTone(status: string): Tone {
  if (status === "pending") {
    return "warning";
  }
  if (status === "approved") {
    return "good";
  }
  if (status === "rejected") {
    return "critical";
  }
  return "neutral";
}

function orderTone(state: string): Tone {
  if (state.includes("PENDING")) {
    return "warning";
  }
  if (state.includes("FILLED")) {
    return "good";
  }
  if (state.includes("REJECTED") || state.includes("UNKNOWN")) {
    return "critical";
  }
  return "info";
}

function positionTone(position: PositionApiView): Tone {
  if (position.protection_status === "expected_protection_present") {
    return "good";
  }
  if (position.protection_status === "missing_expected_protection") {
    return "critical";
  }
  if (position.protection_status === "review_required") {
    return "warning";
  }
  return "neutral";
}

function alertTone(alert: AlertApiView): Tone {
  if (alert.severity === "critical" || alert.severity === "emergency") {
    return "critical";
  }
  if (alert.severity === "warning") {
    return "warning";
  }
  return "info";
}
