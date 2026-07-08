import { safetyPosture } from "./safety";

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

const shellSections = [
  "Signals",
  "Approval tickets",
  "Orders",
  "Positions",
  "Audit events",
  "Alerts",
] as const;

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

const workflowRows: Record<(typeof shellSections)[number], WorkflowRow[]> = {
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

          <div className="section-grid">
            {shellSections.map((section) => (
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
