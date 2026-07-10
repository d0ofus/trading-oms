import { useEffect, useMemo, useState } from "react";

import {
  buildApprovalDecisionRequest,
  defaultApprovalInboxFormState,
  safeApprovalInboxText,
  type ApprovalInboxAction,
  type ApprovalInboxFormState,
} from "./approvalInbox";
import {
  defaultAuditExplorerFilters,
  filterAuditEvents,
  safeAuditDisplayText,
  type AuditExplorerFilterState,
} from "./auditExplorer";
import {
  createReadApiClient,
  initialReadApiState,
  loadOperationsSnapshot,
  type AlertApiView,
  type ApprovalTicketApiView,
  type AuditEventApiView,
  type OperationsApiSnapshot,
  type OperatorSessionApiView,
  type PaperTradingApiView,
  type PositionApiView,
  type ReadApiClient,
  type ReadApiLoadState,
} from "./readApiClient";
import {
  createSimulationApprovalApiClient,
  type SimulationApprovalApiClient,
} from "./simulationApprovalApiClient";
import {
  buildOrderDetailView,
  buildPositionDetailView,
  safeOrderPositionDetailText,
  type OrderDetailView,
  type PositionDetailView,
} from "./orderPositionDetails";
import {
  buildProtectionMonitoringView,
  safeProtectionMonitoringText,
  type ProtectionMonitoringView,
  type ProtectionPositionView,
} from "./protectionMonitoring";
import {
  defaultStrategyBuilderState,
  formatStrategyDslPreview,
  updateStrategyBuilderState,
} from "./strategyBuilder";
import { VisualSimulationWorkflowCanvas } from "./visualSimulationWorkflowCanvas";
import {
  defaultVisualWorkflowDslCompileResult,
  formatVisualWorkflowDslPreview,
} from "./visualWorkflowDsl";

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
  simulationApprovalApiClient?: SimulationApprovalApiClient;
};

const visualBuilderSection = "Visual builder" as const;
const simulationRunSection = "Simulation run detail" as const;
const approvalInboxSection = "Approval inbox" as const;
const auditExplorerSection = "Audit explorer" as const;
const orderDetailSection = "Order detail" as const;
const positionDetailSection = "Position detail" as const;
const protectionMonitoringSection = "Protection monitor" as const;
const paperTradingSection = "Paper trading" as const;
const operatorAccessSection = "Operator access" as const;

const workflowSections = [
  "Signals",
  "Approval tickets",
  "Orders",
  "Positions",
  "Audit events",
  "Alerts",
] as const;

type WorkflowSection = (typeof workflowSections)[number];

const shellSections = [
  visualBuilderSection,
  simulationRunSection,
  approvalInboxSection,
  auditExplorerSection,
  orderDetailSection,
  positionDetailSection,
  protectionMonitoringSection,
  paperTradingSection,
  operatorAccessSection,
  ...workflowSections,
] as const;

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

export function App({
  initialReadState,
  readApiClient,
  simulationApprovalApiClient,
}: AppProps = {}) {
  const [builderState, setBuilderState] = useState(defaultStrategyBuilderState);
  const [auditFilters, setAuditFilters] = useState(defaultAuditExplorerFilters);
  const [approvalForms, setApprovalForms] = useState<Record<string, ApprovalInboxFormState>>({});
  const [approvalFeedback, setApprovalFeedback] = useState<Record<string, string>>({});
  const [readState, setReadState] = useState<ReadApiLoadState>(
    initialReadState ?? initialReadApiState,
  );
  const approvalClient = useMemo(
    () => simulationApprovalApiClient ?? createSimulationApprovalApiClient(),
    [simulationApprovalApiClient],
  );
  const dslPreview = useMemo(() => formatStrategyDslPreview(builderState), [builderState]);
  const workflowDslPreview = useMemo(
    () => formatVisualWorkflowDslPreview(defaultVisualWorkflowDslCompileResult),
    [],
  );
  const shouldLoadFromBackend = !initialReadState || initialReadState.status === "loading";
  const snapshot = readState.snapshot;
  const summaryPanels = useMemo(() => buildSummaryPanels(snapshot), [snapshot]);
  const workflowRows = useMemo(() => buildWorkflowRows(snapshot), [snapshot]);
  const pendingApprovalTickets = useMemo(
    () => snapshot.approvalTickets.filter((ticket) => ticket.status === "pending"),
    [snapshot.approvalTickets],
  );
  const orderDetail = useMemo(
    () => buildOrderDetailView(snapshot.orders[0], snapshot.auditEvents),
    [snapshot.auditEvents, snapshot.orders],
  );
  const positionDetail = useMemo(
    () => buildPositionDetailView(snapshot.positions[0], snapshot.auditEvents),
    [snapshot.auditEvents, snapshot.positions],
  );
  const protectionMonitoring = useMemo(
    () => buildProtectionMonitoringView(snapshot.positions, snapshot.alerts, snapshot.auditEvents),
    [snapshot.alerts, snapshot.auditEvents, snapshot.positions],
  );
  const auditExplorerEvents = useMemo(
    () => filterAuditEvents(snapshot.auditEvents, auditFilters),
    [auditFilters, snapshot.auditEvents],
  );
  const selectedAuditEvent = auditExplorerEvents[0] ?? null;

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

  const updateApprovalForm = (
    ticketId: string,
    patch: Partial<ApprovalInboxFormState>,
  ) => {
    setApprovalForms((current) => ({
      ...current,
      [ticketId]: {
        ...approvalFormState(current, ticketId),
        ...patch,
      },
    }));
  };

  const applySimulationDecision = async (
    event: { preventDefault: () => void },
    ticket: ApprovalTicketApiView,
    action: ApprovalInboxAction,
  ) => {
    event.preventDefault();
    const formState = approvalFormState(approvalForms, ticket.ticket_id);
    const request = buildApprovalDecisionRequest(ticket.ticket_id, action, formState);
    setApprovalFeedback((current) => ({
      ...current,
      [ticket.ticket_id]: `Sending simulation ${action} decision ${request.decision_id}`,
    }));

    try {
      const response =
        action === "approve"
          ? await approvalClient.approveTicket(ticket.ticket_id, request)
          : await approvalClient.rejectTicket(ticket.ticket_id, request);
      setApprovalFeedback((current) => ({
        ...current,
        [ticket.ticket_id]: `Simulation ${response.new_status} recorded; idempotency key ${response.decision_id}`,
      }));
    } catch {
      setApprovalFeedback((current) => ({
        ...current,
        [ticket.ticket_id]: "Simulation decision failed; ticket state was not changed locally",
      }));
    }
  };

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
          <StatusPill
            tone="neutral"
            label={`Operator ${formatIdentifier(snapshot.operatorSession.operator_id)}`}
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
              <PostureItem
                label="Operator"
                value={formatIdentifier(snapshot.operatorSession.operator_id)}
              />
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
              <VisualSimulationWorkflowCanvas />

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

              <div className="persistence-status" aria-label="Workflow persistence status">
                <div className="section-heading">
                  <h2>Workflow persistence</h2>
                  <span>versioned local storage</span>
                </div>
                <div className="persistence-grid">
                  <StatusPill tone="good" label="Local definition storage ready" />
                  <StatusPill tone="good" label="Simulation replay endpoint ready" />
                  <StatusPill tone="neutral" label="Validated DSL required" />
                  <StatusPill tone="neutral" label="Simulation definitions only" />
                  <StatusPill tone="neutral" label="Manual approval wait only" />
                </div>
              </div>

              <div className="dsl-preview" aria-label="Generated Strategy DSL preview">
                <div className="section-heading">
                  <h2>Generated DSL preview</h2>
                  <span>local only</span>
                </div>
                <div className="dsl-preview-block">
                  <h3>Strategy DSL</h3>
                  <pre>{dslPreview}</pre>
                </div>
                <div className="dsl-preview-block">
                  <h3>Simulation workflow DSL</h3>
                  <pre>{workflowDslPreview}</pre>
                </div>
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

          <section className="approval-inbox-section" id={sectionId(approvalInboxSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Approval inbox</p>
                <h2>Simulation ticket review</h2>
              </div>
              <StatusPill tone="warning" label={`${pendingApprovalTickets.length} pending`} />
            </div>
            <div className="approval-inbox-list" aria-label="Simulation approval inbox">
              {pendingApprovalTickets.length === 0 ? (
                <p className="empty-state">No pending simulation approvals</p>
              ) : (
                pendingApprovalTickets.map((ticket) => {
                  const formState = approvalFormState(approvalForms, ticket.ticket_id);
                  return (
                    <article className="approval-ticket-card" key={ticket.ticket_id}>
                      <div className="panel-heading">
                        <div>
                          <p className="eyebrow">Pending simulation approval</p>
                          <h3>{safeApprovalInboxText(ticket.ticket_id)}</h3>
                        </div>
                        <StatusPill tone="warning" label={ticket.status} />
                      </div>
                      <dl className="approval-ticket-facts">
                        <PostureItem label="Order" value={safeApprovalInboxText(ticket.order_id)} />
                        <PostureItem label="Symbol" value={ticket.symbol} />
                        <PostureItem label="Side" value={ticket.side} />
                        <PostureItem label="Quantity" value={`${ticket.quantity}`} />
                        <PostureItem label="Risk" value={safeApprovalInboxText(ticket.risk_decision_id)} />
                        <PostureItem label="Expires" value={ticket.expires_at} />
                      </dl>
                      <form
                        className="approval-form"
                        onSubmit={(event) => event.preventDefault()}
                      >
                        <label>
                          <span>Actor</span>
                          <input
                            aria-label={`Approval actor for ${ticket.ticket_id}`}
                            maxLength={80}
                            name={`${ticket.ticket_id}-actor`}
                            onChange={(event) =>
                              updateApprovalForm(ticket.ticket_id, {
                                actor: event.target.value,
                              })
                            }
                            value={formState.actor}
                          />
                        </label>
                        <label>
                          <span>Reason</span>
                          <textarea
                            aria-label={`Approval reason for ${ticket.ticket_id}`}
                            maxLength={240}
                            name={`${ticket.ticket_id}-reason`}
                            onChange={(event) =>
                              updateApprovalForm(ticket.ticket_id, {
                                reason: event.target.value,
                              })
                            }
                            value={formState.reason}
                          />
                        </label>
                        <div className="approval-actions">
                          <button
                            onClick={(event) =>
                              applySimulationDecision(event, ticket, "approve")
                            }
                            type="button"
                          >
                            Approve simulation
                          </button>
                          <button
                            onClick={(event) => applySimulationDecision(event, ticket, "reject")}
                            type="button"
                          >
                            Reject simulation
                          </button>
                        </div>
                        <p className="approval-feedback">
                          {approvalFeedback[ticket.ticket_id] ??
                            `Idempotency key ${ticket.ticket_id}-approve-decision or ${ticket.ticket_id}-reject-decision`}
                        </p>
                      </form>
                    </article>
                  );
                })
              )}
            </div>
          </section>

          <section className="audit-explorer-section" id={sectionId(auditExplorerSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Audit explorer</p>
                <h2>Filter audit events</h2>
              </div>
              <StatusPill tone="neutral" label="Read only" />
            </div>
            <div className="audit-explorer-layout">
              <div className="audit-filter-grid" aria-label="Audit event filters">
                <AuditFilterInput
                  label="Run"
                  name="auditRunId"
                  onChange={(value) =>
                    setAuditFilters((current) => ({ ...current, runId: value }))
                  }
                  value={auditFilters.runId}
                />
                <AuditFilterInput
                  label="Event type"
                  name="auditEventType"
                  onChange={(value) =>
                    setAuditFilters((current) => ({ ...current, eventType: value }))
                  }
                  value={auditFilters.eventType}
                />
                <AuditFilterInput
                  label="Symbol"
                  name="auditSymbol"
                  onChange={(value) =>
                    setAuditFilters((current) => ({ ...current, symbol: value }))
                  }
                  value={auditFilters.symbol}
                />
                <AuditFilterInput
                  label="Order ID"
                  name="auditOrderId"
                  onChange={(value) =>
                    setAuditFilters((current) => ({ ...current, orderId: value }))
                  }
                  value={auditFilters.orderId}
                />
                <AuditFilterInput
                  label="Ticket ID"
                  name="auditTicketId"
                  onChange={(value) =>
                    setAuditFilters((current) => ({ ...current, ticketId: value }))
                  }
                  value={auditFilters.ticketId}
                />
                <label>
                  <span>Severity</span>
                  <select
                    aria-label="Audit severity filter"
                    name="auditSeverity"
                    onChange={(event) =>
                      setAuditFilters((current) => ({
                        ...current,
                        severity: event.target.value,
                      }))
                    }
                    value={auditFilters.severity}
                  >
                    <option value="">Any severity</option>
                    <option value="informational">Informational</option>
                    <option value="warning">Warning</option>
                    <option value="critical">Critical</option>
                    <option value="emergency">Emergency</option>
                  </select>
                </label>
                <AuditFilterInput
                  label="Timestamp"
                  name="auditTimestamp"
                  onChange={(value) =>
                    setAuditFilters((current) => ({ ...current, timestamp: value }))
                  }
                  value={auditFilters.timestamp}
                />
              </div>

              <div className="audit-results" aria-label="Filtered audit events">
                <div className="section-heading">
                  <h3>Matching events</h3>
                  <span>{auditExplorerEvents.length} records</span>
                </div>
                {auditExplorerEvents.length === 0 ? (
                  <p className="empty-state">No matching audit events</p>
                ) : (
                  auditExplorerEvents.map((event) => (
                    <article className="record-row" key={`audit-explorer-${event.sequence}`}>
                      <div>
                        <h3>{safeAuditDisplayText(event.event_type)}</h3>
                        <p>{safeAuditDisplayText(event.summary)}</p>
                      </div>
                      <StatusPill
                        tone={auditSeverityTone(event)}
                        label={event.severity ?? `sequence ${event.sequence}`}
                      />
                    </article>
                  ))
                )}
              </div>

              <AuditEventDetail event={selectedAuditEvent} />
            </div>
          </section>

          <section className="detail-section" id={sectionId(orderDetailSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Order detail</p>
                <h2>OMS inspection</h2>
              </div>
              <StatusPill tone="neutral" label="Read only" />
            </div>
            <OrderDetailPanel detail={orderDetail} />
          </section>

          <section className="detail-section" id={sectionId(positionDetailSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Position detail</p>
                <h2>Protection inspection</h2>
              </div>
              <StatusPill tone="neutral" label="Read only" />
            </div>
            <PositionDetailPanel detail={positionDetail} />
          </section>

          <section
            className="protection-monitor-section"
            id={sectionId(protectionMonitoringSection)}
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">Protection monitor</p>
                <h2>Protection monitoring</h2>
              </div>
              <StatusPill
                tone={protectionMonitoring.emergencyConditions.length > 0 ? "critical" : "good"}
                label={formatCount(
                  protectionMonitoring.emergencyConditions.length,
                  "emergency",
                  "emergencies",
                )}
              />
            </div>
            <ProtectionMonitoringDashboard view={protectionMonitoring} />
          </section>

          <section className="paper-trading-section" id={sectionId(paperTradingSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Paper trading</p>
                <h2>IBKR paper operator</h2>
              </div>
              <div className="status-strip" aria-label="Paper trading safety posture">
                <StatusPill tone="good" label="Paper only" />
                <StatusPill tone="good" label="Live trading disabled" />
                <StatusPill tone="neutral" label="Read only" />
              </div>
            </div>
            <PaperTradingOperatorPanel view={snapshot.paperTrading} />
          </section>

          <section className="operator-access-section" id={sectionId(operatorAccessSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Operator access</p>
                <h2>Local development operator</h2>
              </div>
              <div className="status-strip" aria-label="Operator access posture">
                <StatusPill tone="good" label="Local auth foundation" />
                <StatusPill tone="neutral" label="No credential controls" />
                <StatusPill tone="neutral" label="No external identity provider" />
              </div>
            </div>
            <OperatorAccessPanel view={snapshot.operatorSession} />
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

function AuditFilterInput({
  label,
  name,
  onChange,
  value,
}: {
  label: string;
  name: keyof AuditExplorerFilterState | string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        aria-label={`Audit ${label.toLowerCase()} filter`}
        maxLength={80}
        name={name}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </label>
  );
}

function approvalFormState(
  forms: Record<string, ApprovalInboxFormState>,
  ticketId: string,
) {
  return forms[ticketId] ?? defaultApprovalInboxFormState;
}

function AuditEventDetail({ event }: { event: AuditEventApiView | null }) {
  if (!event) {
    return (
      <article className="audit-detail" aria-label="Audit event detail">
        <h3>Event detail</h3>
        <p>No matching audit event selected</p>
      </article>
    );
  }

  return (
    <article className="audit-detail" aria-label="Audit event detail">
      <h3>Event detail</h3>
      <AuditDetailRow label="Sequence" value={`sequence ${event.sequence}`} />
      <AuditDetailRow label="Type" value={event.event_type} />
      <AuditDetailRow label="Timestamp" value={event.timestamp} />
      <AuditDetailRow label="Run" value={event.run_id} />
      <AuditDetailRow label="Symbol" value={event.symbol} />
      <AuditDetailRow label="Order" value={event.order_id} />
      <AuditDetailRow label="Ticket" value={event.ticket_id} />
      <AuditDetailRow label="Severity" value={event.severity} />
      <AuditDetailRow label="Summary" value={event.summary} />
    </article>
  );
}

function AuditDetailRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{safeAuditDisplayText(value)}</strong>
    </div>
  );
}

function OrderDetailPanel({ detail }: { detail: OrderDetailView | null }) {
  if (!detail) {
    return <p className="empty-state detail-empty">No order detail available</p>;
  }

  const { order } = detail;
  return (
    <div className="detail-layout" aria-label="Order detail records">
      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Order</p>
            <h3>{safeOrderPositionDetailText(order.client_order_id)}</h3>
          </div>
          <StatusPill
            tone={order.requires_reconciliation ? "critical" : orderTone(order.state)}
            label={detail.stateLabel}
          />
        </div>
        <dl className="detail-facts">
          <PostureItem label="Order ID" value={safeOrderPositionDetailText(order.order_id)} />
          <PostureItem label="Symbol" value={order.symbol} />
          <PostureItem label="Side" value={order.side} />
          <PostureItem label="Quantity" value={`${order.quantity}`} />
          <PostureItem
            label="Risk decision"
            value={safeOrderPositionDetailText(order.risk_decision_id)}
          />
          <PostureItem
            label="Approval"
            value={safeOrderPositionDetailText(order.approval_reference)}
          />
          <PostureItem label="Updated" value={order.updated_at} />
          <PostureItem label="Reconciliation" value={detail.reconciliationLabel} />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Fills</p>
            <h3>Simulation fill summary</h3>
          </div>
          <StatusPill tone={order.leaves_quantity === 0 ? "good" : "warning"} label={detail.fillLabel} />
        </div>
        <dl className="detail-facts compact">
          <PostureItem
            label="Cumulative filled"
            value={`${order.cumulative_filled_quantity}`}
          />
          <PostureItem label="Leaves" value={`${order.leaves_quantity}`} />
          <PostureItem label="OMS state" value={detail.stateLabel} />
        </dl>
      </article>

      <DetailAuditEvents events={detail.linkedAuditEvents} title="Linked order audit records" />
    </div>
  );
}

function PositionDetailPanel({ detail }: { detail: PositionDetailView | null }) {
  if (!detail) {
    return <p className="empty-state detail-empty">No position detail available</p>;
  }

  const { position } = detail;
  return (
    <div className="detail-layout" aria-label="Position detail records">
      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Position</p>
            <h3>{safeOrderPositionDetailText(position.position_id)}</h3>
          </div>
          <StatusPill tone={positionTone(position)} label={detail.protectionLabel} />
        </div>
        <dl className="detail-facts">
          <PostureItem label="Symbol" value={position.symbol} />
          <PostureItem label="Quantity" value={`${position.quantity}`} />
          <PostureItem label="Average price" value={`${position.average_price}`} />
          <PostureItem label="Source" value={formatIdentifier(position.source)} />
          <PostureItem label="Updated" value={position.updated_at} />
          <PostureItem label="Protection state" value={detail.protectionLabel} />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Protection</p>
            <h3>{detail.quantityLabel}</h3>
          </div>
          <StatusPill tone={positionTone(position)} label={detail.protectionLabel} />
        </div>
        <p className="detail-note">
          Missing expected protection remains critical and must stay visible for operator review.
        </p>
      </article>

      <DetailAuditEvents events={detail.linkedAuditEvents} title="Linked position audit records" />
    </div>
  );
}

function DetailAuditEvents({
  events,
  title,
}: {
  events: AuditEventApiView[];
  title: string;
}) {
  return (
    <article className="detail-card detail-audit-card">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Audit</p>
          <h3>{title}</h3>
        </div>
        <StatusPill tone={events.length > 0 ? "info" : "neutral"} label={`${events.length} linked`} />
      </div>
      {events.length === 0 ? (
        <p className="empty-state">No linked audit records</p>
      ) : (
        <div className="detail-audit-list">
          {events.map((event) => (
            <article className="record-row" key={`detail-audit-${event.sequence}`}>
              <div>
                <h3>{safeOrderPositionDetailText(event.event_type)}</h3>
                <p>{safeOrderPositionDetailText(event.summary)}</p>
              </div>
              <StatusPill
                tone={auditSeverityTone(event)}
                label={event.severity ?? `sequence ${event.sequence}`}
              />
            </article>
          ))}
        </div>
      )}
    </article>
  );
}

function ProtectionMonitoringDashboard({ view }: { view: ProtectionMonitoringView }) {
  return (
    <div className="protection-monitor-layout" aria-label="Protection monitoring dashboard">
      <div className="protection-summary-grid">
        <ProtectionSummaryCard
          label="Expected protection"
          metric={formatCount(view.summary.protected, "position", "positions")}
          tone={view.summary.protected > 0 ? "good" : "neutral"}
        />
        <ProtectionSummaryCard
          label="Missing protection"
          metric={formatCount(view.summary.missingProtection, "position", "positions")}
          tone={view.summary.missingProtection > 0 ? "critical" : "good"}
        />
        <ProtectionSummaryCard
          label="Exception references"
          metric={formatCount(view.summary.exceptions, "position", "positions")}
          tone={view.summary.exceptions > 0 ? "warning" : "neutral"}
        />
        <ProtectionSummaryCard
          label="Critical local alerts"
          metric={formatCount(view.summary.criticalAlerts, "alert", "alerts")}
          tone={view.summary.criticalAlerts > 0 ? "critical" : "good"}
        />
      </div>

      <article className="protection-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Emergency conditions</p>
            <h3>Operator-visible protection conditions</h3>
          </div>
          <StatusPill
            tone={view.emergencyConditions.length > 0 ? "critical" : "good"}
            label={formatCount(view.emergencyConditions.length, "active", "active")}
          />
        </div>
        {view.emergencyConditions.length === 0 ? (
          <p className="empty-state">No emergency protection conditions</p>
        ) : (
          <div className="protection-row-list">
            {view.emergencyConditions.map((condition) => (
              <article className="record-row" key={condition}>
                <div>
                  <h3>{safeProtectionMonitoringText(condition)}</h3>
                  <p>Condition remains visible until the source read model changes.</p>
                </div>
                <StatusPill tone="critical" label="operator review" />
              </article>
            ))}
          </div>
        )}
      </article>

      <article className="protection-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Position protection</p>
            <h3>Protection state ledger</h3>
          </div>
          <StatusPill
            tone="neutral"
            label={formatCount(view.positionViews.length, "position", "positions")}
          />
        </div>
        {view.positionViews.length === 0 ? (
          <p className="empty-state">No position protection records</p>
        ) : (
          <div className="protection-position-grid">
            {view.positionViews.map((positionView) => (
              <ProtectionPositionCard
                key={positionView.position.position_id}
                positionView={positionView}
              />
            ))}
          </div>
        )}
      </article>

      <article className="protection-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Alert linkage</p>
            <h3>Critical and emergency local alerts</h3>
          </div>
          <StatusPill
            tone={view.criticalAlerts.length > 0 ? "critical" : "good"}
            label={formatCount(view.criticalAlerts.length, "linked", "linked")}
          />
        </div>
        {view.criticalAlerts.length === 0 ? (
          <p className="empty-state">No critical or emergency local alerts</p>
        ) : (
          <div className="protection-row-list">
            {view.criticalAlerts.map((alert) => (
              <article className="record-row" key={alert.alert_id}>
                <div>
                  <h3>{safeProtectionMonitoringText(alert.title)}</h3>
                  <p>{safeProtectionMonitoringText(alert.source_event_reference)}</p>
                </div>
                <StatusPill tone={alertTone(alert)} label={alert.severity} />
              </article>
            ))}
          </div>
        )}
      </article>
    </div>
  );
}

function OperatorAccessPanel({ view }: { view: OperatorSessionApiView }) {
  return (
    <div className="detail-layout" aria-label="Operator access records">
      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Operator</p>
            <h3>{formatIdentifier(view.operator_id)}</h3>
          </div>
          <StatusPill tone="good" label={formatIdentifier(view.auth_state)} />
        </div>
        <dl className="detail-facts">
          <PostureItem label="Auth method" value={formatIdentifier(view.auth_method)} />
          <PostureItem label="Roles" value={view.roles.map(formatIdentifier).join(", ")} />
          <PostureItem
            label="View operations"
            value={view.can_view_operations ? "Allowed" : "Denied"}
          />
          <PostureItem
            label="Approve simulation"
            value={view.can_approve_simulation ? "Allowed" : "Denied"}
          />
          <PostureItem
            label="Administer system"
            value={view.can_administer_system ? "Allowed" : "Denied"}
          />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Permissions</p>
            <h3>Audited local checks</h3>
          </div>
          <StatusPill tone="neutral" label={`${view.permissions.length} permissions`} />
        </div>
        <div className="record-list compact-list">
          {view.permissions.map((permission) => (
            <article className="record-row" key={permission}>
              <div>
                <h3>{formatIdentifier(permission)}</h3>
                <p>Permission is evaluated by the backend before privileged actions.</p>
              </div>
              <StatusPill tone="good" label="available" />
            </article>
          ))}
        </div>
      </article>
    </div>
  );
}

function PaperTradingOperatorPanel({ view }: { view: PaperTradingApiView }) {
  return (
    <div className="detail-layout" aria-label="Paper trading operator records">
      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Adapter state</p>
            <h3>{formatIdentifier(view.adapter_name)}</h3>
          </div>
          <StatusPill
            tone={view.requires_reconciliation ? "critical" : "good"}
            label={formatIdentifier(view.connection_state)}
          />
        </div>
        <dl className="detail-facts">
          <PostureItem label="Mode" value="Paper only" />
          <PostureItem
            label="Live trading"
            value={view.live_trading_enabled ? "Enabled" : "Live trading disabled"}
          />
          <PostureItem label="Connection" value={formatIdentifier(view.connection_state)} />
          <PostureItem label="Updated" value={view.updated_at} />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Reconciliation</p>
            <h3>{view.requires_reconciliation ? "Reconciliation required" : "Reconciliation clean"}</h3>
          </div>
          <StatusPill
            tone={view.requires_reconciliation ? "critical" : "good"}
            label={view.requires_reconciliation ? "review required" : "clean"}
          />
        </div>
        <dl className="detail-facts compact">
          <PostureItem label="State" value={formatIdentifier(view.connection_state)} />
          <PostureItem
            label="Summary"
            value={formatIdentifier(view.reconciliation_summary)}
          />
          <PostureItem
            label="Blocking"
            value={view.requires_reconciliation ? "Risk-increasing steps blocked" : "No block"}
          />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Paper order callbacks</p>
            <h3>{view.order_client_reference}</h3>
          </div>
          <StatusPill
            tone={view.leaves_quantity === 0 && !view.requires_reconciliation ? "good" : "warning"}
            label={view.order_status}
          />
        </div>
        <dl className="detail-facts compact">
          <PostureItem label="Status callback" value={formatIdentifier(view.status_callback_state)} />
          <PostureItem label="Fill callback" value={formatIdentifier(view.fill_callback_state)} />
          <PostureItem
            label="Fill summary"
            value={`${view.cumulative_filled_quantity} filled / ${view.leaves_quantity} leaves`}
          />
        </dl>
      </article>
    </div>
  );
}

function ProtectionSummaryCard({
  label,
  metric,
  tone,
}: {
  label: string;
  metric: string;
  tone: Tone;
}) {
  return (
    <article className="protection-summary-card">
      <div className="panel-heading">
        <h3>{label}</h3>
        <span className={`swatch swatch-${tone}`} aria-hidden="true" />
      </div>
      <p className="metric">{metric}</p>
    </article>
  );
}

function ProtectionPositionCard({
  positionView,
}: {
  positionView: ProtectionPositionView;
}) {
  const { position } = positionView;
  return (
    <article className="protection-position-card">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{safeProtectionMonitoringText(position.symbol)}</p>
          <h3>{safeProtectionMonitoringText(position.position_id)}</h3>
        </div>
        <StatusPill tone={positionTone(position)} label={positionView.statusLabel} />
      </div>
      <dl className="detail-facts compact">
        <PostureItem label="Quantity" value={`${position.quantity}`} />
        <PostureItem
          label="Exception"
          value={safeProtectionMonitoringText(positionView.exceptionReference)}
        />
        <PostureItem label="Linked alerts" value={`${positionView.linkedAlerts.length}`} />
        <PostureItem label="Linked audit" value={`${positionView.linkedAuditEvents.length}`} />
      </dl>
    </article>
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

function formatCount(count: number, singular: string, plural: string) {
  return `${count} ${count === 1 ? singular : plural}`;
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

function auditSeverityTone(event: AuditEventApiView): Tone {
  if (event.severity === "critical" || event.severity === "emergency") {
    return "critical";
  }
  if (event.severity === "warning") {
    return "warning";
  }
  if (event.severity === "informational") {
    return "info";
  }
  return event.event_type.includes("alert") ? "critical" : "info";
}
