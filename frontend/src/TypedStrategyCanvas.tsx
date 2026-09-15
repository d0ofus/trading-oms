import "./typedStrategy.css";
import {
  addEdge,
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
  type OnSelectionChangeParams,
  type ReactFlowInstance,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { useCallback, useMemo, useState } from "react";

import "@xyflow/react/dist/style.css";

import {
  createVisualWorkflowNode,
  simulationWorkflowEdgeCatalog,
  simulationWorkflowNodeCatalog,
  visualWorkflowPalette,
  type VisualWorkflowEdgeDefinition,
  type VisualWorkflowNodeConfig,
  type VisualWorkflowNodeDefinition,
  type VisualWorkflowNodeRole,
  type VisualWorkflowNodeType,
} from "./typedWorkflowNodeCatalog";
import {
  compileVisualWorkflowDsl,
  formatVisualWorkflowDslPreview,
} from "./typedWorkflowDsl";
import {
  defaultVisualWorkflowRunInspection,
  type VisualWorkflowRunStatus,
} from "./visualWorkflowRunInspection";
import {
  isTypedConnectionValid,
  validateCatalogWorkflowGraph,
} from "./typedWorkflowValidation";
import {
  createWorkflowApiClient,
  type MarketDataDatasetApiView,
  type MarketDataDatasetRegistrationRequest,
  type RiskPolicyApiView,
  type StrategyRunApiView,
} from "./typedStrategyApiClient";

type StrategyNodeData = {
  definition: VisualWorkflowNodeDefinition;
  runStatus?: string;
};

type StrategyFlowNode = Node<StrategyNodeData, "typedStrategy">;

type PaletteDragPayload = {
  type: VisualWorkflowNodeType;
  label: string;
  config: VisualWorkflowNodeConfig;
};

const nodeTypes = { typedStrategy: TypedStrategyNode };

export const visualSimulationWorkflowNodeCatalog = simulationWorkflowNodeCatalog;

export const visualSimulationWorkflowEdges: Edge[] = simulationWorkflowEdgeCatalog.map(buildEdge);

export const visualSimulationWorkflowLayoutPolicy = {
  mode: "typed_drag_drop_builder",
  nodesDraggable: true,
  nodesConnectable: true,
  elementsSelectable: true,
  persistenceEnabled: true,
  executionEnabled: "fake_broker_only",
} as const;

export const visualSimulationWorkflowValidation = validateCatalogWorkflowGraph(
  visualSimulationWorkflowNodeCatalog,
  simulationWorkflowEdgeCatalog,
);

export const visualSimulationWorkflowRunInspection = defaultVisualWorkflowRunInspection;

export const visualSimulationWorkflowStatusLegend: VisualWorkflowRunStatus[] = [
  "completed",
  "passed",
  "risk_blocked",
  "waiting_for_approval",
  "blocked_waiting_for_approval",
  "filled",
  "alert_recorded",
];

export function VisualSimulationWorkflowCanvas() {
  const [nodes, setNodes, onNodesChange] = useNodesState<StrategyFlowNode>(
    simulationWorkflowNodeCatalog.map(toFlowNode),
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    simulationWorkflowEdgeCatalog.map(buildEdge),
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<StrategyFlowNode, Edge> | null>(
    null,
  );
  const [baseVersion, setBaseVersion] = useState<number | null>(null);
  const [savedVersion, setSavedVersion] = useState<number | null>(null);
  const [saveStatus, setSaveStatus] = useState("Not saved");
  const [symbol, setSymbol] = useState("AAPL");
  const [maximumDollarLoss, setMaximumDollarLoss] = useState("100.00");
  const [datasetId, setDatasetId] = useState("dataset-aapl-2026-07-08");
  const [runtimeMode, setRuntimeMode] = useState<
    "historical_simulation" | "live_simulation"
  >("historical_simulation");
  const [runId, setRunId] = useState("strategy-run-001");
  const [runExpiry, setRunExpiry] = useState(defaultExpiry());
  const [runRecord, setRunRecord] = useState<StrategyRunApiView | null>(null);
  const [datasetRecord, setDatasetRecord] = useState<MarketDataDatasetApiView | null>(null);
  const [riskPolicy, setRiskPolicy] = useState<RiskPolicyApiView | null>(null);
  const [datasetStatus, setDatasetStatus] = useState("No local fixture registered in this session");
  const [runStatus, setRunStatus] = useState("No draft run");

  const definitions = useMemo(
    () => nodes.map((node) => ({ ...node.data.definition, position: { ...node.position } })),
    [nodes],
  );
  const edgeDefinitions = useMemo(
    () => edges.map(toEdgeDefinition).filter((edge): edge is VisualWorkflowEdgeDefinition => !!edge),
    [edges],
  );
  const validation = useMemo(
    () => validateCatalogWorkflowGraph(definitions, edgeDefinitions),
    [definitions, edgeDefinitions],
  );
  const compilation = useMemo(
    () => compileVisualWorkflowDsl(definitions, edgeDefinitions),
    [definitions, edgeDefinitions],
  );
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const apiClient = useMemo(() => createWorkflowApiClient(), []);
  const displayedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          runStatus: nodeRunStatus(node.data.definition, runRecord),
        },
      })),
    [nodes, runRecord],
  );

  const invalidateWorkflowEdit = useCallback(() => {
    setSavedVersion(null);
    setSaveStatus("Unsaved workflow changes");
    setRunRecord(null);
    setRunStatus("Workflow changed : save a new version and create a new draft");
  }, []);

  const invalidateRuntimeInput = useCallback(() => {
    setRunRecord(null);
    setRunStatus("Runtime input changed : create and arm a new draft");
  }, []);

  const connectionIsValid = useCallback(
    (connection: Connection | Edge) =>
      isTypedConnectionValid(definitions, {
        source: connection.source,
        sourceHandle: connection.sourceHandle ?? null,
        target: connection.target,
        targetHandle: connection.targetHandle ?? null,
      }),
    [definitions],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connectionIsValid(connection)) return;
      setEdges((current) =>
        addEdge(
          {
            ...connection,
            id: `${connection.source}.${connection.sourceHandle}-to-${connection.target}.${connection.targetHandle}`,
            markerEnd: { type: MarkerType.ArrowClosed },
            type: "smoothstep",
          },
          current,
        ),
      );
      invalidateWorkflowEdit();
    },
    [connectionIsValid, invalidateWorkflowEdit, setEdges],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange<StrategyFlowNode>[]) => {
      onNodesChange(changes);
      if (changes.some((change) => change.type === "position" || change.type === "remove")) {
        invalidateWorkflowEdit();
      }
    },
    [invalidateWorkflowEdit, onNodesChange],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      onEdgesChange(changes);
      if (changes.some((change) => change.type === "remove" || change.type === "replace")) {
        invalidateWorkflowEdit();
      }
    },
    [invalidateWorkflowEdit, onEdgesChange],
  );

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData("application/trading-oms-node");
      if (!raw) return;
      const payload = JSON.parse(raw) as PaletteDragPayload;
      const position = flowInstance
        ? flowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY })
        : { x: event.clientX, y: event.clientY };
      const id = `${payload.type}-${crypto.randomUUID().slice(0, 8)}`;
      const definition = createVisualWorkflowNode(id, payload.type, position, payload.config);
      definition.title = payload.label;
      setNodes((current) => [...current, toFlowNode(definition)]);
      setSelectedNodeId(id);
      invalidateWorkflowEdit();
    },
    [flowInstance, invalidateWorkflowEdit, setNodes],
  );

  const updateSelectedConfig = useCallback(
    (config: VisualWorkflowNodeConfig) => {
      if (!selectedNodeId) return;
      setNodes((current) =>
        current.map((node) =>
          node.id === selectedNodeId
            ? {
                ...node,
                data: {
                  ...node.data,
                  definition: {
                    ...node.data.definition,
                    config: { ...config },
                  },
                },
              }
            : node,
        ),
      );
      invalidateWorkflowEdit();
    },
    [invalidateWorkflowEdit, selectedNodeId, setNodes],
  );

  const deleteSelectedNode = useCallback(() => {
    if (!selectedNodeId) return;
    setNodes((current) => current.filter((node) => node.id !== selectedNodeId));
    setEdges((current) =>
      current.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId),
    );
    setSelectedNodeId(null);
    invalidateWorkflowEdit();
  }, [invalidateWorkflowEdit, selectedNodeId, setEdges, setNodes]);

  const saveWorkflow = useCallback(async () => {
    if (compilation.status !== "compiled") {
      setSaveStatus("Blocked: resolve graph validation errors");
      return;
    }
    setSaveStatus("Validating...");
    try {
      await apiClient.validateWorkflow(compilation.document.workflow_id, compilation.document);
      const now = new Date().toISOString();
      const request = {
        schema_version: 2 as const,
        workflow_id: compilation.document.workflow_id,
        display_name: "First five minute breakout",
        description: "Typed deterministic simulation workflow",
        requested_at: now,
        document: compilation.document,
      };
      const saved = baseVersion === null
        ? await apiClient.createWorkflow(request)
        : await apiClient.updateWorkflow(compilation.document.workflow_id, {
            ...request, expected_version: baseVersion,
          });
      setBaseVersion(saved.version);
      setSavedVersion(saved.version);
      setSaveStatus(`Saved immutable version ${saved.version}`);
      setRunRecord(null);
      setRunStatus("Saved workflow changed : create a new draft");
    } catch {
      setSaveStatus("Save failed: check validation and permissions. Load the saved workflow to resolve a version conflict.");
    }
  }, [apiClient, compilation, baseVersion]);

  const loadWorkflow = useCallback(async () => {
    try {
      const saved = await apiClient.getWorkflow("first-five-minute-breakout");
      if (saved.document.schema_version !== 2) throw new Error("Unsupported workflow version");
      setNodes(saved.document.nodes.map((node) => toFlowNode(
        createVisualWorkflowNode(node.id, node.type, node.position, node.config),
      )));
      setEdges(saved.document.edges.map((edge) => buildEdge({
        id: edge.id, source: edge.source_node, sourcePort: edge.source_port,
        target: edge.target_node, targetPort: edge.target_port,
      })));
      setBaseVersion(saved.version);
      setSavedVersion(saved.version);
      setRunRecord(null);
      setSaveStatus(`Loaded immutable version ${saved.version}`);
      setRunStatus("Loaded workflow — create a new draft");
    } catch {
      setSaveStatus("Load failed — check whether a workflow has been saved and you can view it");
    }
  }, [apiClient, setNodes, setEdges]);

  const registerSampleDataset = useCallback(async () => {
    setDatasetStatus("Registering deterministic local fixture...");
    try {
      const dataset = await apiClient.registerDataset(sampleDatasetRegistration());
      setDatasetId(dataset.dataset_id);
      setSymbol(dataset.symbol);
      setDatasetRecord(dataset);
      setRunRecord(null);
      setRunStatus("Dataset changed : create and arm a new draft");
      setDatasetStatus(
        `Ready: ${dataset.trade_count} ${dataset.resolution} records, ${dataset.quality}, checksum ${dataset.checksum.slice(0, 12)}...`,
      );
    } catch {
      setDatasetStatus("Dataset registration failed : inspect backend validation and audit state");
    }
  }, [apiClient]);

  const createDraft = useCallback(async () => {
    if (!savedVersion) {
      setRunStatus("Save a valid workflow version first");
      return;
    }
    try {
      const [record, dataset, policy] = await Promise.all([
        apiClient.createStrategyRun("first-five-minute-breakout", {
          run_id: runId,
          workflow_version: savedVersion,
          symbol: symbol.toUpperCase(),
          maximum_dollar_loss: maximumDollarLoss,
          runtime_mode: runtimeMode,
          dataset_id: datasetId,
          expires_at: runExpiry,
          requested_at: new Date().toISOString(),
        }),
        apiClient.getDataset(datasetId),
        apiClient.getRiskPolicy(),
      ]);
      setRunRecord(record);
      setDatasetRecord(dataset);
      setRiskPolicy(policy);
      setRunStatus(`Draft ready : fingerprint ${record.fingerprint.slice(0, 12)}...`);
    } catch {
      setRunStatus("Draft failed : verify dataset, contract, inputs, and policy");
    }
  }, [apiClient, datasetId, maximumDollarLoss, runExpiry, runId, runtimeMode, savedVersion, symbol]);

  const armRun = useCallback(async () => {
    if (!runRecord || runRecord.state !== "draft") {
      setRunStatus("Create a draft before arming");
      return;
    }
    try {
      const record = await apiClient.armStrategyRun(runRecord.run_id, {
        authorized_at: new Date().toISOString(),
        expires_at: runExpiry,
      });
      setRunRecord(record);
      setRunStatus("Armed for the next explicit fake-broker simulation");
    } catch {
      setRunStatus("Arming blocked : review expiry, emergency stop, and permissions");
    }
  }, [apiClient, runExpiry, runRecord]);

  const simulateRun = useCallback(async () => {
    if (!runRecord || runRecord.state !== "armed") {
      setRunStatus("Arm the immutable draft before simulation");
      return;
    }
    try {
      const record = await apiClient.simulateStrategyRun(runRecord.run_id, {
        buying_power: "50000.00",
        concurrent_positions: 0,
        current_symbol_exposure: "0.00",
        daily_realized_loss: "0.00",
        reconciled: true,
        evaluated_at: new Date().toISOString(),
      });
      setRunRecord(record);
      setRunStatus(`Simulation ${record.result?.status ?? record.state}`);
    } catch {
      setRunStatus("Simulation blocked : inspect data, risk, reconciliation, and audit status");
    }
  }, [apiClient, runRecord]);

  return (
    <div className="typed-strategy-workspace typed-builder" aria-label="Typed breakout simulation builder">
      <aside className="node-palette" aria-label="Typed node palette">
        <h3>Node palette</h3>
        <p>Edit the supported opening-breakout template. Other wiring cannot run yet.</p>
        {Object.entries(groupPalette()).map(([category, items]) => (
          <section key={category}>
            <h4>{category}</h4>
            {items.map((item) => (
              <button
                draggable
                key={item.paletteId}
                onDragStart={(event) => {
                  const payload: PaletteDragPayload = {
                    type: item.type,
                    label: item.label,
                    config: item.defaultConfig,
                  };
                  event.dataTransfer.setData(
                    "application/trading-oms-node",
                    JSON.stringify(payload),
                  );
                  event.dataTransfer.effectAllowed = "copy";
                }}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </section>
        ))}
      </aside>

      <div className="typed-canvas-column">
        <div className="react-flow-frame typed-react-flow-frame" onDragOver={allowDrop} onDrop={onDrop}>
          <ReactFlow<StrategyFlowNode, Edge>
            deleteKeyCode={["Backspace", "Delete"]}
            edges={edges}
            elementsSelectable={visualSimulationWorkflowLayoutPolicy.elementsSelectable}
            fitView
            isValidConnection={connectionIsValid}
            nodeTypes={nodeTypes}
            nodes={displayedNodes}
            nodesConnectable={visualSimulationWorkflowLayoutPolicy.nodesConnectable}
            nodesDraggable={visualSimulationWorkflowLayoutPolicy.nodesDraggable}
            onConnect={onConnect}
            onEdgesChange={handleEdgesChange}
            onInit={setFlowInstance}
            onNodesChange={handleNodesChange}
            onSelectionChange={(selection: OnSelectionChangeParams) =>
              setSelectedNodeId(selection.nodes[0]?.id ?? null)
            }
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#cfdbd5" gap={18} variant={BackgroundVariant.Dots} />
          </ReactFlow>
        </div>

        <div className={`flow-validation flow-validation-${validation.status}`}>
          <strong>{validation.status === "valid" ? "Graph validation passed" : "Graph blocked"}</strong>
          <span>
            {validation.status === "valid"
              ? "Typed ports and every required safety path are complete."
              : `${validation.errors.length} validation issue(s) must be resolved.`}
          </span>
          {validation.errors.length > 0 && (
            <ul>
              {validation.errors.slice(0, 6).map((error, index) => (
                <li key={`${error.code}-${error.nodeId ?? error.edgeId ?? index}`}>{error.message}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="builder-actions" aria-label="Workflow save and version controls">
          <button onClick={loadWorkflow} type="button">Load saved workflow</button>
          <button disabled={validation.status !== "valid"} onClick={saveWorkflow} type="button">
            Save new version
          </button>
          <span>{saveStatus}</span>
          <span>{savedVersion ? `Current version ${savedVersion}` : "No persisted version"}</span>
        </div>

        <section className="run-arming-panel" aria-label="Strategy run and arming controls">
          <div className="section-heading">
            <div>
              <h3>Simulation run setup</h3>
              <p>Runtime dollar risk is fixed when the draft is armed. Dataset and run actions require the strategy_operator role.</p>
            </div>
            <span>fake broker only</span>
          </div>
          <div className="run-input-grid">
            <label>
              <span>Run ID</span>
              <input
                onChange={(event) => {
                  setRunId(event.target.value);
                  invalidateRuntimeInput();
                }}
                value={runId}
              />
            </label>
            <label>
              <span>Symbol</span>
              <input
                onChange={(event) => {
                  setSymbol(event.target.value.toUpperCase());
                  invalidateRuntimeInput();
                }}
                value={symbol}
              />
            </label>
            <label>
              <span>Maximum dollar loss</span>
              <input
                inputMode="decimal"
                onChange={(event) => {
                  setMaximumDollarLoss(event.target.value);
                  invalidateRuntimeInput();
                }}
                value={maximumDollarLoss}
              />
            </label>
            <label>
              <span>Dataset ID</span>
              <input
                onChange={(event) => {
                  setDatasetId(event.target.value);
                  invalidateRuntimeInput();
                }}
                value={datasetId}
              />
            </label>
            <label>
              <span>Runtime mode</span>
              <select
                onChange={(event) =>
                  {
                    setRuntimeMode(
                      event.target.value as "historical_simulation" | "live_simulation",
                    );
                    invalidateRuntimeInput();
                  }
                }
                value={runtimeMode}
              >
                <option value="historical_simulation">Historical simulation</option>
                <option value="live_simulation">Live-forward simulation</option>
              </select>
            </label>
            <label>
              <span>Authorization expiry (UTC)</span>
              <input
                onChange={(event) => {
                  setRunExpiry(event.target.value);
                  invalidateRuntimeInput();
                }}
                value={runExpiry}
              />
            </label>
          </div>
          <div className="dataset-fixture-row">
            <button onClick={registerSampleDataset} type="button">
              Register deterministic sample dataset
            </button>
            <span>{datasetStatus}</span>
          </div>
          <p>Sample execution scenario: $50,000 buying power, zero existing positions or loss, and simulated reconciliation. These are fixture inputs.</p>
          <p className="formula-line">
            Initial shares = floor(maximum dollar loss / (trigger + slippage - frozen day low)).
            Shares are reduced if the simulated fill would exceed that risk budget.
          </p>
          <div className="builder-actions">
            <button onClick={createDraft} type="button">Create draft</button>
            <button disabled={runRecord?.state !== "draft"} onClick={armRun} type="button">
              Review and arm
            </button>
            <button disabled={runRecord?.state !== "armed"} onClick={simulateRun} type="button">
              Run fake-broker simulation
            </button>
          </div>
          <p className="run-status-line">{runStatus}</p>
          {runRecord && (
            <RunSummary dataset={datasetRecord} policy={riskPolicy} record={runRecord} />
          )}
        </section>

        <details className="dsl-preview-inline">
          <summary>Workflow DSL v2 preview</summary>
          <pre>{formatVisualWorkflowDslPreview(compilation)}</pre>
        </details>
      </div>

      <aside className="property-inspector" aria-label="Node property inspector">
        <h3>Properties</h3>
        {selectedNode ? (
          <>
            <strong>{selectedNode.data.definition.title}</strong>
            <span>{selectedNode.data.definition.type}</span>
            <PortList definition={selectedNode.data.definition} />
            <ConfigEditor
              config={selectedNode.data.definition.config}
              nodeType={selectedNode.data.definition.type}
              onChange={updateSelectedConfig}
            />
            <button className="danger-outline" onClick={deleteSelectedNode} type="button">
              Delete selected node
            </button>
          </>
        ) : (
          <p>Select a node to inspect typed ports and edit validated properties.</p>
        )}
      </aside>
    </div>
  );
}

function TypedStrategyNode({ data, selected }: NodeProps<StrategyFlowNode>) {
  const inputEntries = Object.entries(data.definition.inputPorts);
  const outputEntries = Object.entries(data.definition.outputPorts);
  return (
    <div className={`typed-flow-node typed-flow-node-${data.definition.role} ${selected ? "selected" : ""}`}>
      {inputEntries.map(([port, type], index) => (
        <Handle
          id={port}
          key={port}
          position={Position.Left}
          style={{ top: `${((index + 1) / (inputEntries.length + 1)) * 100}%` }}
          title={`${port}: ${type}`}
          type="target"
        />
      ))}
      <span className={`flow-role flow-role-${data.definition.role}`}>{data.definition.badge}</span>
      <strong>{data.definition.title}</strong>
      <small>{data.definition.detail}</small>
      {data.runStatus && <span className="node-run-overlay">{data.runStatus}</span>}
      {outputEntries.map(([port, type], index) => (
        <Handle
          id={port}
          key={port}
          position={Position.Right}
          style={{ top: `${((index + 1) / (outputEntries.length + 1)) * 100}%` }}
          title={`${port}: ${type}`}
          type="source"
        />
      ))}
    </div>
  );
}

function PortList({ definition }: { definition: VisualWorkflowNodeDefinition }) {
  return (
    <div className="port-inspector">
      <h4>Typed ports</h4>
      {[...Object.entries(definition.inputPorts).map(([name, type]) => `in : ${name}: ${type}`),
        ...Object.entries(definition.outputPorts).map(([name, type]) => `out : ${name}: ${type}`),
      ].map((port) => <span key={port}>{port}</span>)}
    </div>
  );
}

function ConfigEditor({
  config,
  nodeType,
  onChange,
}: {
  config: VisualWorkflowNodeConfig;
  nodeType: VisualWorkflowNodeType;
  onChange: (config: VisualWorkflowNodeConfig) => void;
}) {
  if (nodeType === "opening_range_high" || nodeType === "opening_range_low") {
    return (
      <label>
        <span>Opening range minutes</span>
        <input
          max={60}
          min={1}
          onChange={(event) => onChange({ minutes: event.target.valueAsNumber })}
          type="number"
          value={Number(config.minutes ?? 5)}
        />
      </label>
    );
  }
  if (nodeType === "entry_lifetime") {
    return (
      <label>
        <span>Entry lifetime</span>
        <select onChange={(event) => onChange({ value: event.target.value })} value={String(config.value)}>
          <option value="DAY">DAY : expire at RTH close</option>
          <option value="GTC">GTC : reset each RTH session</option>
        </select>
      </label>
    );
  }
  if (nodeType === "position_lifetime") {
    return (
      <div className="config-field-stack">
        <label>
          <span>Position lifetime</span>
          <select
            onChange={(event) => {
              const kind = event.target.value;
              onChange(kind === "exit_at_time" ? { kind, time: "15:55:00" } : { kind });
            }}
            value={String(config.kind)}
          >
            <option value="hold_with_protective_stop">Hold with protective stop</option>
            <option value="exit_at_time">Exit at configured time</option>
            <option disabled value="exit_on_typed_condition">
              Exit on typed condition : runtime pending
            </option>
          </select>
        </label>
        {config.kind === "exit_at_time" && (
          <label>
            <span>Exchange-local exit time</span>
            <input
              onChange={(event) => onChange({ kind: "exit_at_time", time: event.target.value })}
              step="1"
              type="time"
              value={String(config.time ?? "15:55:00")}
            />
          </label>
        )}
      </div>
    );
  }
  return <pre>{JSON.stringify(config, null, 2)}</pre>;
}

function RunSummary({
  dataset,
  policy,
  record,
}: {
  dataset: MarketDataDatasetApiView | null;
  policy: RiskPolicyApiView | null;
  record: StrategyRunApiView;
}) {
  return (
    <div className="run-summary-grid">
      <span><strong>State</strong>{record.state}</span>
      <span><strong>Workflow</strong>v{record.envelope.workflow_version}</span>
      <span><strong>Fingerprint</strong>{record.fingerprint.slice(0, 16)}...</span>
      <span><strong>Risk</strong>${record.envelope.maximum_dollar_loss}</span>
      <span><strong>Contract</strong>{record.envelope.contract_id}</span>
      <span><strong>Venue</strong>{record.envelope.routing} / {record.envelope.primary_exchange}</span>
      <span><strong>Minimum tick</strong>{record.envelope.min_tick}</span>
      <span><strong>Opening range</strong>{record.envelope.opening_range_minutes} minute(s)</span>
      <span><strong>Data quality</strong>{dataset?.quality ?? "loading"}</span>
      <span><strong>Policy</strong>{record.envelope.risk_policy_version}</span>
      <span><strong>Policy risk cap</strong>${policy?.max_dollar_risk ?? "loading"}</span>
      <span><strong>Policy share cap</strong>{policy?.max_shares ?? "loading"}</span>
      <span><strong>Policy notional cap</strong>${policy?.max_notional ?? "loading"}</span>
      <span><strong>Shares</strong>{record.result?.shares ?? "pending"}</span>
      <span><strong>Protection</strong>{record.result?.protection_state ?? "planned"}</span>
    </div>
  );
}

function nodeRunStatus(
  definition: VisualWorkflowNodeDefinition,
  record: StrategyRunApiView | null,
): string | undefined {
  if (!record) return undefined;
  if (record.state === "disarmed") return definition.type === "armed_run_authorization" ? "disarmed" : undefined;
  if (record.state === "blocked") return "blocked";
  if (record.state === "draft") {
    return ["symbol_input", "dollar_risk_input", "historical_dataset", "live_trades"].includes(
      definition.type,
    )
      ? "bound"
      : undefined;
  }
  if (record.state === "armed") {
    return definition.type === "armed_run_authorization" ? "armed" : "waiting";
  }
  if (definition.type === "audit_sink") return "recorded";
  if (definition.type === "fake_broker") {
    return record.result?.entry_fill_price ? "filled" : record.result?.status ?? "completed";
  }
  if (definition.type === "protective_stop") return record.result?.protection_state ?? "planned";
  if (definition.type === "position_monitor") return record.result?.status ?? "completed";
  return "passed";
}

function toFlowNode(definition: VisualWorkflowNodeDefinition): StrategyFlowNode {
  return {
    id: definition.id,
    className: `simulation-flow-node simulation-flow-node-${definition.role}`,
    connectable: true,
    data: { definition },
    draggable: true,
    position: definition.position,
    selectable: true,
    type: "typedStrategy",
  };
}

function buildEdge(definition: VisualWorkflowEdgeDefinition): Edge {
  return {
    id: definition.id,
    markerEnd: { type: MarkerType.ArrowClosed },
    source: definition.source,
    sourceHandle: definition.sourcePort,
    target: definition.target,
    targetHandle: definition.targetPort,
    type: "smoothstep",
  };
}

function toEdgeDefinition(edge: Edge): VisualWorkflowEdgeDefinition | null {
  if (!edge.sourceHandle || !edge.targetHandle) return null;
  return {
    id: edge.id,
    source: edge.source,
    sourcePort: edge.sourceHandle,
    target: edge.target,
    targetPort: edge.targetHandle,
  };
}

function groupPalette() {
  return visualWorkflowPalette.reduce<Record<string, typeof visualWorkflowPalette>>((groups, item) => {
    groups[item.category] = [...(groups[item.category] ?? []), item];
    return groups;
  }, {});
}

function allowDrop(event: React.DragEvent<HTMLDivElement>) {
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
}

function defaultExpiry() {
  const expiry = new Date(Date.now() + 24 * 60 * 60 * 1000);
  return expiry.toISOString();
}

function sampleDatasetRegistration(): MarketDataDatasetRegistrationRequest {
  return {
    dataset_id: "dataset-aapl-2026-07-08",
    symbol: "AAPL",
    contract_id: "local-fixture-aapl",
    primary_exchange: "NASDAQ",
    currency: "USD",
    routing: "SMART",
    min_tick: "0.01",
    session_date: "2026-07-08",
    session_timezone: "America/New_York",
    rth_open: "09:30:00",
    rth_close: "16:00:00",
    source: "local_fixture",
    resolution: "trade_ticks",
    complete: true,
    quality: "complete",
    registered_at: "2026-07-08T12:30:00Z",
    trades: [
      { timestamp: "2026-07-08T13:30:00Z", price: "99.50", sequence: 1 },
      { timestamp: "2026-07-08T13:34:59Z", price: "101.00", sequence: 2 },
      { timestamp: "2026-07-08T13:35:01Z", price: "101.01", sequence: 3 },
      { timestamp: "2026-07-08T13:35:02Z", price: "101.03", sequence: 4 },
      { timestamp: "2026-07-08T13:35:03Z", price: "101.04", sequence: 5 },
    ],
  };
}

export type { VisualWorkflowNodeRole };
