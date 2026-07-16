import { useEffect, useMemo, useRef, useState } from "react";

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
  OPERATIONS_PROVENANCE_RESOURCES,
  createReadApiClient,
  initialReadApiState,
  loadOperationsSnapshot,
  type AlertApiView,
  type ApprovalTicketApiView,
  type AuditEventApiView,
  type EmergencyStopApiView,
  type LiveReadinessEvidenceApiView,
  type OperationsApiSnapshot,
  type OperationalControlsApiView,
  type OperatorSessionApiView,
  type PaperTradingApiView,
  type PositionApiView,
  type ReadApiClient,
  type ReadApiLoadState,
  type ReadModelProvenanceApiView,
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
import { WorkflowPersistencePanel } from "./WorkflowPersistencePanel";
import { WorkflowSimulationRunStartPanel } from "./WorkflowSimulationRunStartPanel";
import {
  compileVisualWorkflowDsl,
  formatVisualWorkflowDslPreview,
} from "./visualWorkflowDsl";
import {
  createInitialVisualWorkflowEditorState,
  type VisualWorkflowEditorState,
} from "./visualWorkflowEditor";
import {
  createWorkflowApiClient,
  type WorkflowApiClient,
  type WorkflowDefinitionApiView,
  type WorkflowNodeRunStatusApiView,
} from "./workflowApiClient";
import {
  initialWorkflowRunInspectionState as initialWorkflowRunInspectionLoadState,
  loadWorkflowRunInspection,
  type WorkflowRunInspectionState,
} from "./workflowRunInspector";
import {
  canReplaceWorkflowDraft,
  loadWorkflowDefinition,
  loadWorkflowDefinitions,
  persistWorkflowDefinition,
  workflowDefinitionToEditorState,
  workflowDraftFingerprint,
  type WorkflowDefinitionListState,
  type WorkflowPersistenceMetadata,
  type WorkflowPersistenceOperationState,
} from "./workflowPersistence";
import {
  executeWorkflowSimulationRunStart,
  prepareWorkflowSimulationRunStart,
  workflowSimulationRunEligibility,
  type WorkflowSimulationRunAttempt,
  type WorkflowSimulationRunStartState,
} from "./workflowSimulationRunStart";

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

type AppProps = {
  initialReadState?: ReadApiLoadState;
  initialVisualWorkflowEditorState?: VisualWorkflowEditorState;
  initialWorkflowDefinitionListState?: WorkflowDefinitionListState;
  initialWorkflowRunInspectionState?: WorkflowRunInspectionState;
  readApiClient?: ReadApiClient;
  simulationApprovalApiClient?: SimulationApprovalApiClient;
  workflowApiClient?: WorkflowApiClient;
};

const defaultWorkflowMetadata: WorkflowPersistenceMetadata = {
  workflowId: "workflow-local-001",
  displayName: "Opening breakout simulation",
  description: "Validated visual simulation workflow",
};

const visualBuilderSection = "Visual builder" as const;
const simulationRunSection = "Simulation run detail" as const;
const approvalInboxSection = "Approval inbox" as const;
const auditExplorerSection = "Audit explorer" as const;
const orderDetailSection = "Order detail" as const;
const positionDetailSection = "Position detail" as const;
const protectionMonitoringSection = "Protection monitor" as const;
const emergencyStopSection = "Emergency stop" as const;
const paperTradingSection = "Paper trading" as const;
const liveReadinessEvidenceSection = "Live-readiness evidence" as const;
const operationalControlsSection = "Operational controls" as const;
const operatorAccessSection = "Operator access" as const;
const dataProvenanceSection = "Data provenance" as const;

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
  dataProvenanceSection,
  visualBuilderSection,
  simulationRunSection,
  approvalInboxSection,
  auditExplorerSection,
  orderDetailSection,
  positionDetailSection,
  protectionMonitoringSection,
  emergencyStopSection,
  paperTradingSection,
  liveReadinessEvidenceSection,
  operationalControlsSection,
  operatorAccessSection,
  ...workflowSections,
] as const;

export function App({
  initialReadState,
  initialVisualWorkflowEditorState,
  initialWorkflowDefinitionListState,
  initialWorkflowRunInspectionState,
  readApiClient,
  simulationApprovalApiClient,
  workflowApiClient,
}: AppProps = {}) {
  const [builderState, setBuilderState] = useState(defaultStrategyBuilderState);
  const [auditFilters, setAuditFilters] = useState(defaultAuditExplorerFilters);
  const [approvalForms, setApprovalForms] = useState<Record<string, ApprovalInboxFormState>>({});
  const [approvalFeedback, setApprovalFeedback] = useState<Record<string, string>>({});
  const [visualWorkflowEditorState, setVisualWorkflowEditorState] =
    useState<VisualWorkflowEditorState>(() =>
      initialVisualWorkflowEditorState ?? createInitialVisualWorkflowEditorState(),
    );
  const [workflowMetadata, setWorkflowMetadata] = useState<WorkflowPersistenceMetadata>(
    defaultWorkflowMetadata,
  );
  const [workflowDefinitionList, setWorkflowDefinitionList] =
    useState<WorkflowDefinitionListState>(
      initialWorkflowDefinitionListState ?? { status: "loading", items: [] },
    );
  const [workflowPersistenceOperation, setWorkflowPersistenceOperation] =
    useState<WorkflowPersistenceOperationState>({ status: "idle" });
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [loadedWorkflowRecord, setLoadedWorkflowRecord] =
    useState<WorkflowDefinitionApiView | null>(null);
  const [discardWorkflowEditsConfirmed, setDiscardWorkflowEditsConfirmed] = useState(false);
  const [workflowBaselineFingerprint, setWorkflowBaselineFingerprint] = useState(() =>
    workflowDraftFingerprint(
      defaultWorkflowMetadata,
      initialVisualWorkflowEditorState ?? createInitialVisualWorkflowEditorState(),
    ),
  );
  const workflowPersistenceAttempt = useRef<{
    key: string;
    requestedAt: string;
  } | null>(null);
  const [workflowSimulationRunStart, setWorkflowSimulationRunStart] =
    useState<WorkflowSimulationRunStartState>({ status: "idle" });
  const [workflowSimulationRunConfirmed, setWorkflowSimulationRunConfirmed] = useState(false);
  const [readState, setReadState] = useState<ReadApiLoadState>(
    initialReadState ?? initialReadApiState,
  );
  const [workflowRunInspection, setWorkflowRunInspection] = useState<WorkflowRunInspectionState>(
    initialWorkflowRunInspectionState ?? initialWorkflowRunInspectionLoadState,
  );
  const [selectedWorkflowRunKey, setSelectedWorkflowRunKey] = useState<string | null>(null);
  const approvalClient = useMemo(
    () => simulationApprovalApiClient ?? createSimulationApprovalApiClient(),
    [simulationApprovalApiClient],
  );
  const workflowClient = useMemo(
    () => workflowApiClient ?? createWorkflowApiClient(),
    [workflowApiClient],
  );
  const dslPreview = useMemo(() => formatStrategyDslPreview(builderState), [builderState]);
  const workflowDslCompileResult = useMemo(
    () =>
      compileVisualWorkflowDsl(
        visualWorkflowEditorState.nodes,
        visualWorkflowEditorState.edges,
      ),
    [visualWorkflowEditorState.edges, visualWorkflowEditorState.nodes],
  );
  const workflowDslPreview = useMemo(
    () => formatVisualWorkflowDslPreview(workflowDslCompileResult),
    [workflowDslCompileResult],
  );
  const currentWorkflowFingerprint = useMemo(
    () => workflowDraftFingerprint(workflowMetadata, visualWorkflowEditorState),
    [visualWorkflowEditorState, workflowMetadata],
  );
  const workflowDraftDirty = currentWorkflowFingerprint !== workflowBaselineFingerprint;
  const shouldLoadFromBackend = !initialReadState || initialReadState.status === "loading";
  const shouldLoadWorkflowRuns =
    !initialWorkflowRunInspectionState || initialWorkflowRunInspectionState.status === "loading";
  const shouldLoadWorkflowDefinitions =
    !initialWorkflowDefinitionListState || initialWorkflowDefinitionListState.status === "loading";
  const snapshot = readState.snapshot;
  const workflowSimulationRunStartContext = {
    loadedWorkflow: loadedWorkflowRecord,
    selectedWorkflowId,
    draftDirty: workflowDraftDirty,
    graphValid: workflowDslCompileResult.status === "compiled",
    workflowListStatus: workflowDefinitionList.status,
    persistenceStatus: workflowPersistenceOperation.status,
    readStateStatus: readState.status,
    canAdministerSystem: snapshot.operatorSession.can_administer_system,
    emergencyStopActive: snapshot.emergencyStop.active,
  } as const;
  const workflowSimulationRunStartEligibility = workflowSimulationRunEligibility(
    workflowSimulationRunStartContext,
  );
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
  const selectedWorkflowRun = useMemo(
    () =>
      workflowRunInspection.items.find((item) => item.key === selectedWorkflowRunKey) ??
      workflowRunInspection.items[0] ??
      null,
    [selectedWorkflowRunKey, workflowRunInspection.items],
  );

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

  useEffect(() => {
    if (!shouldLoadWorkflowRuns) {
      return;
    }

    let isCurrent = true;
    setWorkflowRunInspection(initialWorkflowRunInspectionLoadState);

    loadWorkflowRunInspection(workflowClient).then((state) => {
      if (isCurrent) {
        setWorkflowRunInspection(state);
      }
    });

    return () => {
      isCurrent = false;
    };
  }, [shouldLoadWorkflowRuns, workflowClient]);

  useEffect(() => {
    if (!shouldLoadWorkflowDefinitions) {
      return;
    }

    let isCurrent = true;
    setWorkflowDefinitionList({ status: "loading", items: [] });
    loadWorkflowDefinitions(workflowClient).then((state) => {
      if (isCurrent) {
        setWorkflowDefinitionList(state);
      }
    });

    return () => {
      isCurrent = false;
    };
  }, [shouldLoadWorkflowDefinitions, workflowClient]);

  const resetWorkflowSimulationRunStart = () => {
    setWorkflowSimulationRunStart({ status: "idle" });
    setWorkflowSimulationRunConfirmed(false);
  };

  const reviewWorkflowSimulationRunStart = () => {
    setWorkflowSimulationRunConfirmed(false);
    setWorkflowSimulationRunStart(
      prepareWorkflowSimulationRunStart(workflowSimulationRunStartContext),
    );
  };

  const applyWorkflowSimulationRunStart = async (
    attempt: WorkflowSimulationRunAttempt,
  ) => {
    const currentEligibility = workflowSimulationRunEligibility(
      workflowSimulationRunStartContext,
    );
    if (currentEligibility.status !== "eligible") {
      setWorkflowSimulationRunStart({ ...currentEligibility, attempt });
      return;
    }
    if (
      loadedWorkflowRecord?.workflow_id !== attempt.workflowId ||
      loadedWorkflowRecord.version !== attempt.workflowVersion
    ) {
      setWorkflowSimulationRunStart({
        status: "conflict",
        message: "Saved workflow changed; reload before starting",
        attempt,
      });
      return;
    }

    setWorkflowSimulationRunStart({ status: "starting", attempt });
    const result = await executeWorkflowSimulationRunStart(workflowClient, attempt);
    if (result.status !== "success") {
      setWorkflowSimulationRunStart(result);
      return;
    }

    const refreshedInspection = await loadWorkflowRunInspection(workflowClient);
    setWorkflowRunInspection(refreshedInspection);
    const selectedKey = `${attempt.workflowId}::${attempt.request.run_id}`;
    if (
      refreshedInspection.status !== "loaded" ||
      !refreshedInspection.items.some((item) => item.key === selectedKey)
    ) {
      setWorkflowSimulationRunStart({
        status: "unavailable",
        message: "Run was created but inspection refresh is unavailable",
        attempt,
      });
      return;
    }

    setSelectedWorkflowRunKey(selectedKey);
    setWorkflowSimulationRunConfirmed(false);
    setWorkflowSimulationRunStart(result);
  };

  const confirmWorkflowSimulationRunStart = () => {
    if (
      workflowSimulationRunStart.status !== "confirming" ||
      !workflowSimulationRunConfirmed
    ) {
      return;
    }
    void applyWorkflowSimulationRunStart(workflowSimulationRunStart.attempt);
  };

  const retryWorkflowSimulationRunStart = () => {
    if (
      workflowSimulationRunStart.status !== "unavailable" ||
      !workflowSimulationRunStart.attempt
    ) {
      return;
    }
    void applyWorkflowSimulationRunStart(workflowSimulationRunStart.attempt);
  };

  const selectWorkflowDefinition = (workflowId: string | null) => {
    resetWorkflowSimulationRunStart();
    setSelectedWorkflowId(workflowId);
    setWorkflowPersistenceOperation({ status: "idle" });
  };

  const loadSelectedWorkflowDefinition = async () => {
    if (
      !selectedWorkflowId ||
      !canReplaceWorkflowDraft(workflowDraftDirty, discardWorkflowEditsConfirmed)
    ) {
      return;
    }
    resetWorkflowSimulationRunStart();
    setWorkflowPersistenceOperation({ status: "loading" });
    const result = await loadWorkflowDefinition(workflowClient, selectedWorkflowId);
    if (result.status === "unavailable") {
      setWorkflowPersistenceOperation(result);
      return;
    }
    try {
      const editorState = workflowDefinitionToEditorState(result.record);
      const metadata = {
        workflowId: result.record.workflow_id,
        displayName: result.record.display_name,
        description: result.record.description,
      };
      setVisualWorkflowEditorState(editorState);
      setWorkflowMetadata(metadata);
      setLoadedWorkflowRecord(result.record);
      setWorkflowBaselineFingerprint(workflowDraftFingerprint(metadata, editorState));
      setDiscardWorkflowEditsConfirmed(false);
      setWorkflowPersistenceOperation({ status: "idle" });
      workflowPersistenceAttempt.current = null;
    } catch {
      setWorkflowPersistenceOperation({
        status: "unavailable",
        errorMessage: "Selected workflow is unavailable; current edits were kept",
      });
    }
  };

  const startNewWorkflowDefinition = () => {
    if (!canReplaceWorkflowDraft(workflowDraftDirty, discardWorkflowEditsConfirmed)) {
      return;
    }
    resetWorkflowSimulationRunStart();
    const editorState = createInitialVisualWorkflowEditorState();
    setVisualWorkflowEditorState(editorState);
    setWorkflowMetadata(defaultWorkflowMetadata);
    setSelectedWorkflowId(null);
    setLoadedWorkflowRecord(null);
    setWorkflowBaselineFingerprint(
      workflowDraftFingerprint(defaultWorkflowMetadata, editorState),
    );
    setDiscardWorkflowEditsConfirmed(false);
    setWorkflowPersistenceOperation({ status: "idle" });
    workflowPersistenceAttempt.current = null;
  };

  const applyWorkflowPersistence = async (intent: "create" | "update") => {
    resetWorkflowSimulationRunStart();
    const expectedVersion = intent === "update" ? loadedWorkflowRecord?.version ?? null : null;
    const attemptKey = `${intent}:${expectedVersion ?? "new"}:${currentWorkflowFingerprint}`;
    const requestedAt =
      workflowPersistenceAttempt.current?.key === attemptKey
        ? workflowPersistenceAttempt.current.requestedAt
        : new Date().toISOString();
    workflowPersistenceAttempt.current = { key: attemptKey, requestedAt };
    setWorkflowPersistenceOperation({ status: "saving", intent });

    const result = await persistWorkflowDefinition({
      client: workflowClient,
      intent,
      metadata: workflowMetadata,
      compileResult: workflowDslCompileResult,
      requestedAt,
      currentRecord: loadedWorkflowRecord,
    });
    setWorkflowPersistenceOperation(result);
    if (result.status !== "saved") {
      return;
    }

    setWorkflowDefinitionList((current) => {
      const existing = current.status === "loaded" ? current.items : [];
      const items = [
        ...existing.filter((item) => item.workflow_id !== result.record.workflow_id),
        result.record,
      ].sort((left, right) => left.workflow_id.localeCompare(right.workflow_id));
      return { status: "loaded", items };
    });
    setSelectedWorkflowId(result.record.workflow_id);
    setLoadedWorkflowRecord(result.record);
    setWorkflowBaselineFingerprint(currentWorkflowFingerprint);
    setDiscardWorkflowEditsConfirmed(false);
    workflowPersistenceAttempt.current = null;
  };

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
          <p className="eyebrow">Local simulation operations console</p>
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
          <StatusPill
            tone={emergencyStopTone(snapshot.emergencyStop)}
            label={
              snapshot.emergencyStop.active ? "Emergency stop active" : "Emergency stop inactive"
            }
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
                label="Emergency stop"
                value={
                  snapshot.emergencyStop.active
                    ? "Emergency stop active"
                    : "Emergency stop inactive"
                }
              />
              <PostureItem
                label="Alert delivery"
                value={`Alert delivery ${formatIdentifier(snapshot.safety.alert_delivery)}`}
              />
            </dl>
          </section>

          <section className="provenance-section" id={sectionId(dataProvenanceSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Data provenance</p>
                <h2>Evidence boundaries by read view</h2>
              </div>
              <div className="status-strip" aria-label="Data provenance posture">
                <StatusPill tone="good" label="Not broker-derived" />
                <StatusPill tone="warning" label="Externally unverified" />
              </div>
            </div>
            <div className="provenance-grid">
              {OPERATIONS_PROVENANCE_RESOURCES.map((resource) => (
                <ProvenanceNotice
                  key={resource}
                  view={snapshot.provenance[resource]}
                />
              ))}
            </div>
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
              <VisualSimulationWorkflowCanvas
                editorState={visualWorkflowEditorState}
                onEditorStateChange={(state) => {
                  resetWorkflowSimulationRunStart();
                  setVisualWorkflowEditorState(state);
                  setWorkflowPersistenceOperation({ status: "idle" });
                }}
              />

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

              <WorkflowPersistencePanel
                canPersist={workflowDslCompileResult.status === "compiled"}
                dirty={workflowDraftDirty}
                discardConfirmed={discardWorkflowEditsConfirmed}
                listState={workflowDefinitionList}
                loadedWorkflowId={loadedWorkflowRecord?.workflow_id ?? null}
                metadata={workflowMetadata}
                onCreate={() => void applyWorkflowPersistence("create")}
                onDiscardConfirmationChange={setDiscardWorkflowEditsConfirmed}
                onLoad={() => void loadSelectedWorkflowDefinition()}
                onMetadataChange={(metadata) => {
                  resetWorkflowSimulationRunStart();
                  setWorkflowMetadata(metadata);
                  setWorkflowPersistenceOperation({ status: "idle" });
                }}
                onNew={startNewWorkflowDefinition}
                onSelect={selectWorkflowDefinition}
                onUpdate={() => void applyWorkflowPersistence("update")}
                operationState={workflowPersistenceOperation}
                selectedWorkflowId={selectedWorkflowId}
              />

              <WorkflowSimulationRunStartPanel
                confirmationChecked={workflowSimulationRunConfirmed}
                eligibility={workflowSimulationRunStartEligibility}
                onCancel={resetWorkflowSimulationRunStart}
                onConfirmationChange={setWorkflowSimulationRunConfirmed}
                onConfirm={confirmWorkflowSimulationRunStart}
                onRetry={retryWorkflowSimulationRunStart}
                onReview={reviewWorkflowSimulationRunStart}
                state={workflowSimulationRunStart}
              />

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
                <p className="eyebrow">Saved workflow runs</p>
                <h2>
                  {selectedWorkflowRun
                    ? `Run ${selectedWorkflowRun.run.run_id}`
                    : "Saved workflow runs"}
                </h2>
              </div>
              <div className="status-strip" aria-label="Simulation run inspection posture">
                <StatusPill tone="good" label="Simulation only" />
                <StatusPill
                  tone={workflowRunInspectionTone(workflowRunInspection)}
                  label={workflowRunInspectionLabel(workflowRunInspection)}
                />
              </div>
            </div>
            {workflowRunInspection.status === "loading" ? (
              <p className="empty-state" aria-live="polite">
                Loading saved workflow simulation runs
              </p>
            ) : null}
            {workflowRunInspection.status === "error" ? (
              <p className="empty-state state-note" role="alert">
                {workflowRunInspection.errorMessage}
              </p>
            ) : null}
            {workflowRunInspection.status === "loaded" && !selectedWorkflowRun ? (
              <p className="empty-state">No saved workflow simulation runs</p>
            ) : null}
            {workflowRunInspection.status === "loaded" && selectedWorkflowRun ? (
              <div className="run-detail-layout">
                <div className="run-inspector-toolbar">
                  <label>
                    <span>Inspect run</span>
                    <select
                      name="workflowSimulationRun"
                      onChange={(event) => setSelectedWorkflowRunKey(event.target.value)}
                      value={selectedWorkflowRun.key}
                    >
                      {workflowRunInspection.items.map((item) => (
                        <option key={item.key} value={item.key}>
                          {item.run.run_id} | {item.workflowName} | {formatIdentifier(item.run.status)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <StatusPill
                    tone={workflowNodeStatusTone(selectedWorkflowRun.run.status)}
                    label={formatIdentifier(selectedWorkflowRun.run.status)}
                  />
                </div>

                <dl className="posture-grid run-inspector-facts">
                  <PostureItem label="Workflow" value={selectedWorkflowRun.workflowName} />
                  <PostureItem label="Workflow ID" value={selectedWorkflowRun.workflowId} />
                  <PostureItem
                    label="Definition"
                    value={`version ${selectedWorkflowRun.workflowVersion}`}
                  />
                  <PostureItem label="Run ID" value={selectedWorkflowRun.run.run_id} />
                  <PostureItem
                    label="Replay input"
                    value={selectedWorkflowRun.run.simulation_run.replay_input_reference}
                  />
                  <PostureItem
                    label="Approval ticket"
                    value={selectedWorkflowRun.run.approval_ticket_id ?? "not created"}
                  />
                  <PostureItem label="Created" value={selectedWorkflowRun.run.created_at} />
                  <PostureItem label="Updated" value={selectedWorkflowRun.run.updated_at} />
                  <PostureItem
                    label="Journal references"
                    value={formatCount(
                      selectedWorkflowRun.run.journal_references.length,
                      "reference",
                      "references",
                    )}
                  />
                </dl>

                <div className="run-history" aria-label="Saved workflow simulation run history">
                  {workflowRunInspection.items.map((item) => (
                    <div
                      className={
                        item.key === selectedWorkflowRun.key
                          ? "run-history-row run-history-row-selected"
                          : "run-history-row"
                      }
                      key={item.key}
                    >
                      <div>
                        <h3>{item.run.run_id}</h3>
                        <p>
                          {item.workflowName} | version {item.workflowVersion} | {item.run.updated_at}
                        </p>
                      </div>
                      <StatusPill
                        tone={workflowNodeStatusTone(item.run.status)}
                        label={formatIdentifier(item.run.status)}
                      />
                    </div>
                  ))}
                </div>

                <div className="run-timeline" aria-label="Simulation run node status timeline">
                  {selectedWorkflowRun.run.node_statuses.map((node, index) => (
                    <WorkflowRunTimelineStep index={index} key={node.node_id} node={node} />
                  ))}
                </div>
              </div>
            ) : null}
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
                  const canApproveSimulation = snapshot.operatorSession.can_approve_simulation;
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
                        <PostureItem
                          label="Approval role"
                          value={
                            canApproveSimulation
                              ? "Dedicated approver allowed"
                              : "Approval requires approver"
                          }
                        />
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
                            disabled={!canApproveSimulation}
                            onClick={(event) =>
                              applySimulationDecision(event, ticket, "approve")
                            }
                            type="button"
                          >
                            Approve simulation
                          </button>
                          <button
                            disabled={!canApproveSimulation}
                            onClick={(event) => applySimulationDecision(event, ticket, "reject")}
                            type="button"
                          >
                            Reject simulation
                          </button>
                        </div>
                        <p className="approval-feedback">
                          {!canApproveSimulation
                            ? "Approval requires approver"
                            : approvalFeedback[ticket.ticket_id] ??
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

          <section className="emergency-stop-section" id={sectionId(emergencyStopSection)}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Emergency stop</p>
                <h2>Local emergency stop</h2>
              </div>
              <div className="status-strip" aria-label="Emergency stop posture">
                <StatusPill
                  tone={emergencyStopTone(snapshot.emergencyStop)}
                  label={
                    snapshot.emergencyStop.active
                      ? "Emergency stop active"
                      : "Emergency stop inactive"
                  }
                />
                <StatusPill
                  tone={
                    snapshot.emergencyStop.blocking_risk_increasing_actions
                      ? "critical"
                      : "good"
                  }
                  label={
                    snapshot.emergencyStop.blocking_risk_increasing_actions
                      ? "Risk-increasing steps blocked"
                      : "Risk-increasing steps available"
                  }
                />
                <StatusPill tone="neutral" label="No broker controls" />
              </div>
            </div>
            <EmergencyStopPanel view={snapshot.emergencyStop} />
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
            <ProvenanceNotice view={snapshot.provenance.paper_trading} />
            <PaperTradingOperatorPanel view={snapshot.paperTrading} />
          </section>

          <section
            className="live-readiness-evidence-section"
            id={sectionId(liveReadinessEvidenceSection)}
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">Live-readiness evidence</p>
                <h2>Evidence dashboard</h2>
              </div>
              <div className="status-strip" aria-label="Live-readiness evidence posture">
                <StatusPill tone="good" label="Live trading disabled" />
                <StatusPill
                  tone={
                    snapshot.liveReadinessEvidence.external_review_required
                      ? "warning"
                      : "good"
                  }
                  label={
                    snapshot.liveReadinessEvidence.external_review_required
                      ? "External review required"
                      : "External review recorded"
                  }
                />
                <StatusPill
                  tone={
                    snapshot.liveReadinessEvidence.explicit_human_approval_required
                      ? "warning"
                      : "good"
                  }
                  label={
                    snapshot.liveReadinessEvidence.explicit_human_approval_required
                      ? "Explicit human approval required"
                      : "Explicit human approval recorded"
                  }
                />
              </div>
            </div>
            <ProvenanceNotice view={snapshot.provenance.live_readiness_evidence} />
            <LiveReadinessEvidencePanel view={snapshot.liveReadinessEvidence} />
          </section>

          <section
            className="operational-controls-section"
            id={sectionId(operationalControlsSection)}
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">Operational controls</p>
                <h2>Observability and response posture</h2>
              </div>
              <div className="status-strip" aria-label="Operational controls posture">
                <StatusPill tone="good" label="Read only" />
                <StatusPill tone="neutral" label="Local verification" />
                <StatusPill tone="good" label="production rollout not authorized" />
              </div>
            </div>
            <ProvenanceNotice view={snapshot.provenance.operational_controls} />
            <OperationalControlsPanel view={snapshot.operationalControls} />
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
          <PostureItem label="Approval role" value={formatIdentifier(view.approval_role_required)} />
          <PostureItem label="Role separation" value={formatIdentifier(view.role_separation)} />
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

function EmergencyStopPanel({ view }: { view: EmergencyStopApiView }) {
  return (
    <div className="detail-layout" aria-label="Emergency stop records">
      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">State</p>
            <h3>{view.active ? "Emergency stop active" : "Emergency stop inactive"}</h3>
          </div>
          <StatusPill tone={emergencyStopTone(view)} label={formatIdentifier(view.status)} />
        </div>
        <dl className="detail-facts">
          <PostureItem
            label="Blocking"
            value={
              view.blocking_risk_increasing_actions
                ? "Risk-increasing steps blocked"
                : "Risk-increasing steps available"
            }
          />
          <PostureItem label="Updated" value={view.updated_at} />
          <PostureItem
            label="Activated"
            value={view.activated_at ? view.activated_at : "No activation recorded"}
          />
          <PostureItem
            label="Activated by"
            value={view.activated_by ? formatIdentifier(view.activated_by) : "No activation actor"}
          />
          <PostureItem
            label="Reason"
            value={
              view.activation_reason
                ? formatIdentifier(view.activation_reason)
                : "No activation reason"
            }
          />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Boundary</p>
            <h3>Simulation and paper safety gate</h3>
          </div>
          <StatusPill tone="neutral" label="No broker controls" />
        </div>
        <dl className="detail-facts compact">
          <PostureItem label="Live trading" value="Live trading disabled" />
          <PostureItem label="Broker transport" value="No broker connectivity" />
          <PostureItem
            label="Deactivated"
            value={view.deactivated_at ? view.deactivated_at : "No deactivation recorded"}
          />
          <PostureItem
            label="Deactivated by"
            value={
              view.deactivated_by
                ? formatIdentifier(view.deactivated_by)
                : "No deactivation actor"
            }
          />
          <PostureItem
            label="Deactivation reason"
            value={
              view.deactivation_reason
                ? formatIdentifier(view.deactivation_reason)
                : "No deactivation reason"
            }
          />
        </dl>
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

function LiveReadinessEvidencePanel({ view }: { view: LiveReadinessEvidenceApiView }) {
  const unresolvedEvidence = view.evidence_items.filter((item) => item.status !== "verified");

  return (
    <div className="detail-layout" aria-label="Live-readiness evidence records">
      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Readiness result</p>
            <h3>{formatIdentifier(view.result)}</h3>
          </div>
          <StatusPill
            tone={view.result === "not_ready" ? "warning" : "info"}
            label={formatIdentifier(view.result)}
          />
        </div>
        <dl className="detail-facts compact">
          <PostureItem label="Dashboard" value={formatIdentifier(view.dashboard_id)} />
          <PostureItem label="Evaluated" value={view.evaluated_at} />
          <PostureItem
            label="Verified evidence"
            value={`${view.verified_evidence_count}`}
          />
          <PostureItem
            label="Missing evidence"
            value={`${view.missing_evidence_count}`}
          />
          <PostureItem
            label="Unverified evidence"
            value={`${view.unverified_evidence_count}`}
          />
          <PostureItem
            label="Expired evidence"
            value={`${view.expired_evidence_count}`}
          />
          <PostureItem
            label="Contradictory evidence"
            value={`${view.contradictory_evidence_count}`}
          />
          <PostureItem
            label="Blocking evidence"
            value={`${view.blocking_evidence_count}`}
          />
          <PostureItem label="Blocking reason" value={formatIdentifier(view.blocking_reason)} />
          <PostureItem
            label="Live trading"
            value={view.live_trading_enabled ? "Review required" : "Live trading disabled"}
          />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Blocking evidence</p>
            <h3>{formatCount(unresolvedEvidence.length, "item", "items")}</h3>
          </div>
          <StatusPill
            tone={unresolvedEvidence.length > 0 ? "warning" : "good"}
            label={unresolvedEvidence.length > 0 ? "Review required" : "Verified for final review"}
          />
        </div>
        <div className="record-list compact-list">
          {unresolvedEvidence.map((item) => (
            <article className="record-row" key={item.evidence_id}>
              <div>
                <h3>{item.label}</h3>
                <p>{item.summary}</p>
              </div>
              <StatusPill tone={evidenceStatusTone(item.status)} label={formatIdentifier(item.status)} />
            </article>
          ))}
        </div>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Evidence checklist</p>
            <h3>{formatCount(view.evidence_items.length, "record", "records")}</h3>
          </div>
          <StatusPill tone="neutral" label="Read only" />
        </div>
        <div className="record-list compact-list">
          {view.evidence_items.map((item) => (
            <article className="record-row" key={item.evidence_id}>
              <div>
                <h3>{item.label}</h3>
                <p>{item.summary}</p>
              </div>
              <StatusPill tone={evidenceStatusTone(item.status)} label={formatIdentifier(item.status)} />
            </article>
          ))}
        </div>
      </article>
    </div>
  );
}

function OperationalControlsPanel({ view }: { view: OperationalControlsApiView }) {
  return (
    <div className="detail-layout" aria-label="Operational control records">
      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Observability</p>
            <h3>Local metrics and events</h3>
          </div>
          <StatusPill tone="neutral" label={`${view.metrics.length} metrics`} />
        </div>
        <div className="record-list compact-list">
          {view.metrics.map((metric) => (
            <article className="record-row" key={metric.metric_name}>
              <div>
                <h3>{formatOperationalLabel(metric.metric_name)}</h3>
                <p>{metric.summary}</p>
              </div>
              <StatusPill tone={operationalStatusTone(metric.status)} label={metric.status} />
            </article>
          ))}
        </div>
        <div className="record-list compact-list">
          {view.events.map((event) => (
            <article className="record-row" key={event.event_id}>
              <div>
                <h3>{formatOperationalLabel(event.event_type)}</h3>
                <p>{event.summary}</p>
              </div>
              <StatusPill tone={alertSeverityTone(event.severity)} label={event.severity} />
            </article>
          ))}
        </div>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Audit retention</p>
            <h3>{formatIdentifier(view.retention.policy_id)}</h3>
          </div>
          <StatusPill tone="good" label="No destructive retention" />
        </div>
        <dl className="detail-facts compact">
          <PostureItem label="Mode" value={formatIdentifier(view.retention.mode)} />
          <PostureItem
            label="Minimum days"
            value={`${view.retention.minimum_retention_days}`}
          />
          <PostureItem
            label="Journal"
            value={
              view.retention.append_only_journal_required
                ? "Append-only journal required"
                : "Journal review required"
            }
          />
          <PostureItem label="Next review" value={view.retention.next_review_due_at} />
          <PostureItem label="Status" value={formatIdentifier(view.retention.status)} />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Backup and restore</p>
            <h3>Local backup verification</h3>
          </div>
          <StatusPill
            tone={view.backup_restore.external_storage_configured ? "critical" : "good"}
            label={
              view.backup_restore.external_storage_configured
                ? "review required"
                : "No external storage configured"
            }
          />
        </div>
        <dl className="detail-facts compact">
          <PostureItem
            label="Backup"
            value={formatIdentifier(view.backup_restore.backup_status)}
          />
          <PostureItem
            label="Restore"
            value={formatIdentifier(view.backup_restore.restore_verification_status)}
          />
          <PostureItem
            label="Storage"
            value={formatIdentifier(view.backup_restore.storage_mode)}
          />
          <PostureItem
            label="Redaction"
            value={formatIdentifier(view.backup_restore.redaction_status)}
          />
          <PostureItem label="Verified" value={view.backup_restore.last_verified_at} />
        </dl>
      </article>

      <article className="detail-card">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Incident response</p>
            <h3>
              {view.incident_response.active_incident_state === "none_declared"
                ? "No active incident"
                : formatIdentifier(view.incident_response.active_incident_state)}
            </h3>
          </div>
          <StatusPill tone="good" label="Emergency stop required" />
        </div>
        <dl className="detail-facts compact">
          <PostureItem
            label="Review floor"
            value={view.incident_response.severity_floor_for_operator_review}
          />
          <PostureItem
            label="Stop rule"
            value={
              view.incident_response.emergency_stop_required_for_critical_incidents
                ? "Emergency stop required"
                : "Operator review required"
            }
          />
          <PostureItem
            label="Post review"
            value={
              view.incident_response.post_incident_review_required
                ? "Post-incident review required"
                : "Review missing"
            }
          />
          <PostureItem
            label="Runbook"
            value={formatIdentifier(view.incident_response.current_runbook_status)}
          />
          <PostureItem label="Reviewed" value={view.incident_response.last_reviewed_at} />
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

function WorkflowRunTimelineStep({
  index,
  node,
}: {
  index: number;
  node: WorkflowNodeRunStatusApiView;
}) {
  return (
    <article className="timeline-step">
      <span className="node-index" aria-label={`Timeline step ${index + 1}`}>
        {index + 1}
      </span>
      <div>
        <h3>{sentenceCaseIdentifier(node.node_type)}</h3>
        <p>{node.detail}</p>
        <span className="journal-reference">{node.journal_reference}</span>
      </div>
      <StatusPill tone={workflowNodeStatusTone(node.status)} label={formatIdentifier(node.status)} />
    </article>
  );
}

function StatusPill({ label, tone }: { label: string; tone: Tone }) {
  return <span className={`status-pill status-${tone}`}>{label}</span>;
}

function ProvenanceNotice({ view }: { view: ReadModelProvenanceApiView }) {
  return (
    <article className="provenance-notice" aria-label={`${view.resource} data provenance`}>
      <div>
        <p className="eyebrow">{formatIdentifier(view.resource)}</p>
        <p>{view.summary}</p>
        {view.resource === "paper_trading" ? (
          <strong>Not an authenticated IBKR paper session</strong>
        ) : null}
      </div>
      <div className="status-strip" aria-label={`${view.resource} provenance classifications`}>
        {view.classifications.map((classification) => (
          <StatusPill
            key={classification}
            tone={classification === "externally_unverified" ? "warning" : "neutral"}
            label={sentenceCaseIdentifier(classification)}
          />
        ))}
        <StatusPill tone="good" label="Not broker-derived" />
      </div>
    </article>
  );
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

function sentenceCaseIdentifier(value: string) {
  const formatted = formatIdentifier(value);
  return `${formatted.charAt(0).toUpperCase()}${formatted.slice(1)}`;
}

function formatOperationalLabel(value: string) {
  return value.toLowerCase().replace(/[._-]+/g, " ");
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

function workflowRunInspectionLabel(state: WorkflowRunInspectionState) {
  if (state.status === "loading") {
    return "Run history loading";
  }
  if (state.status === "error") {
    return "Run history unavailable";
  }
  return formatCount(state.items.length, "saved run", "saved runs");
}

function workflowRunInspectionTone(state: WorkflowRunInspectionState): Tone {
  if (state.status === "error") {
    return "warning";
  }
  return state.status === "loaded" && state.items.length > 0 ? "info" : "neutral";
}

function workflowNodeStatusTone(status: string): Tone {
  if (status === "completed" || status === "passed" || status === "filled") {
    return "good";
  }
  if (status === "risk_blocked" || status === "failed" || status === "rejected") {
    return "critical";
  }
  if (status.includes("waiting_for_approval") || status === "not_created") {
    return "warning";
  }
  return "neutral";
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

function operationalStatusTone(status: string): Tone {
  if (status === "critical") {
    return "critical";
  }
  if (status === "warning") {
    return "warning";
  }
  return "good";
}

function evidenceStatusTone(status: string): Tone {
  if (status === "contradictory" || status === "expired") {
    return "critical";
  }
  if (status === "missing" || status === "unverified") {
    return "warning";
  }
  return "good";
}

function alertSeverityTone(severity: string): Tone {
  if (severity === "critical" || severity === "emergency") {
    return "critical";
  }
  if (severity === "warning") {
    return "warning";
  }
  return "info";
}

function emergencyStopTone(view: EmergencyStopApiView): Tone {
  return view.active ? "critical" : "good";
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
