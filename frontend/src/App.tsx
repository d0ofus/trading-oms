import { useMemo, useState } from "react";

import { safetyPosture } from "./safety";
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

const visualBuilderSection = "Visual builder" as const;

const workflowSections = [
  "Signals",
  "Approval tickets",
  "Orders",
  "Positions",
  "Audit events",
  "Alerts",
] as const;

const shellSections = [visualBuilderSection, ...workflowSections] as const;

const summaryPanels: SummaryPanel[] = [
  {
    title: "Signals",
    metric: "2 replay-only",
    detail: "Deterministic local strategy output; no order intents.",
    tone: "info",
  },
  {
    title: "Approval tickets",
    metric: "1 pending",
    detail: "Manual review required before any future execution workflow.",
    tone: "warning",
  },
  {
    title: "Orders",
    metric: "0 live",
    detail: "Simulation records only; no broker route is configured.",
    tone: "good",
  },
  {
    title: "Alerts",
    metric: "1 critical",
    detail: "Local no-op dispatch recorded in the append-only journal.",
    tone: "critical",
  },
];

const workflowRows: Record<(typeof workflowSections)[number], WorkflowRow[]> = {
  Signals: [
    {
      label: "AAPL replay SMA",
      detail: "Long bias from local bars",
      status: "journaled",
      tone: "info",
    },
    {
      label: "MSFT replay SMA",
      detail: "Neutral bias from local bars",
      status: "journaled",
      tone: "neutral",
    },
  ],
  "Approval tickets": [
    {
      label: "approval-ticket-001",
      detail: "Passed risk decision awaiting explicit human decision",
      status: "pending",
      tone: "warning",
    },
  ],
  Orders: [
    {
      label: "client-001",
      detail: "Fake broker acknowledgement in simulation",
      status: "simulated",
      tone: "good",
    },
    {
      label: "client-002",
      detail: "OMS state requires manual approval",
      status: "pending approval",
      tone: "warning",
    },
  ],
  Positions: [
    {
      label: "AAPL simulated position",
      detail: "Expected protection plan present",
      status: "covered",
      tone: "good",
    },
    {
      label: "MSFT simulated position",
      detail: "Protection review alert recorded",
      status: "review",
      tone: "critical",
    },
  ],
  "Audit events": [
    {
      label: "risk.decision.evaluated",
      detail: "Risk decision appended to journal",
      status: "sequence 238",
      tone: "info",
    },
    {
      label: "approval.ticket.created",
      detail: "Manual approval ticket appended to journal",
      status: "sequence 239",
      tone: "info",
    },
    {
      label: "alert.intent.created",
      detail: "Critical local alert intent appended to journal",
      status: "sequence 240",
      tone: "critical",
    },
  ],
  Alerts: [
    {
      label: "Position protection missing",
      detail: "Local no-op alert dispatch; no real delivery configured",
      status: "critical",
      tone: "critical",
    },
    {
      label: "Replay completed",
      detail: "Informational local alert",
      status: "informational",
      tone: "info",
    },
  ],
};

export function App() {
  const [builderState, setBuilderState] = useState(defaultStrategyBuilderState);
  const dslPreview = useMemo(() => formatStrategyDslPreview(builderState), [builderState]);

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Read-only operations shell</p>
          <h1>Trading OMS</h1>
        </div>
        <div className="status-strip" aria-label="Safety posture">
          <StatusPill tone="good" label="Paper mode" />
          <StatusPill tone="good" label="Live trading disabled" />
          <StatusPill tone="neutral" label="Broker connectivity none" />
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
              <h2 id="console-heading">Local paper workflow</h2>
            </div>
            <dl className="posture-grid">
              <PostureItem label="Mode" value={`${titleCase(safetyPosture.appMode)} mode`} />
              <PostureItem
                label="Live trading"
                value={safetyPosture.liveTradingEnabled ? "Enabled" : "Live trading disabled"}
              />
              <PostureItem
                label="Broker connectivity"
                value={`Broker connectivity ${safetyPosture.brokerConnectivity}`}
              />
              <PostureItem label="Approval" value="Manual approval required" />
              <PostureItem label="Journal" value="Append-only journal" />
              <PostureItem
                label="Alert delivery"
                value={`Alert delivery ${safetyPosture.alertDelivery}`}
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

          <div className="section-grid">
            {workflowSections.map((section) => (
              <section className="workflow-section" id={sectionId(section)} key={section}>
                <div className="section-heading">
                  <h2>{section}</h2>
                  <span>{workflowRows[section].length} records</span>
                </div>
                <div className="record-list">
                  {workflowRows[section].map((row) => (
                    <article className="record-row" key={`${section}-${row.label}`}>
                      <div>
                        <h3>{row.label}</h3>
                        <p>{row.detail}</p>
                      </div>
                      <StatusPill tone={row.tone} label={row.status} />
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
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
