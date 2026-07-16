import { simulationWorkflowNodeCatalog } from "./visualWorkflowNodeCatalog";
import type {
  VisualWorkflowEdgeDefinition,
  VisualWorkflowNodeDefinition,
  VisualWorkflowNodeType,
} from "./visualWorkflowNodeCatalog";
import {
  WorkflowApiError,
  type WorkflowApiClient,
  type WorkflowDefinitionApiView,
  type WorkflowDefinitionSaveRequest,
  type WorkflowDefinitionUpdateRequest,
} from "./workflowApiClient";
import type {
  VisualWorkflowDslCompileResult,
  VisualWorkflowDslDocument,
} from "./visualWorkflowDsl";
import type { VisualWorkflowEditorState } from "./visualWorkflowEditor";
import { validateVisualWorkflowGraph } from "./visualWorkflowValidation";

export type WorkflowPersistenceMetadata = {
  workflowId: string;
  displayName: string;
  description: string;
};

export type WorkflowDefinitionListState =
  | { status: "loading"; items: [] }
  | { status: "loaded"; items: WorkflowDefinitionApiView[] }
  | { status: "unavailable"; items: []; errorMessage: string };

export type WorkflowPersistenceOperationState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "saving"; intent: "create" | "update" }
  | { status: "saved"; record: WorkflowDefinitionApiView }
  | { status: "validation_error"; errorMessage: string }
  | { status: "version_conflict"; errorMessage: string }
  | { status: "unavailable"; errorMessage: string };

export type WorkflowPersistenceResult = Exclude<
  WorkflowPersistenceOperationState,
  { status: "idle" | "saving" }
>;

const forbiddenTokens = [
  "account",
  "api_key",
  "broker_host",
  "credential",
  "eval",
  "ibkr",
  "import",
  "javascript",
  "live_mode",
  "live trading",
  "password",
  "route",
  "script",
  "secret",
  "submit",
  "token",
  "transmit",
] as const;

const nodeTypes = new Set<VisualWorkflowNodeType>(
  simulationWorkflowNodeCatalog.map((node) => node.type),
);
const catalogByType = new Map(simulationWorkflowNodeCatalog.map((node) => [node.type, node]));
const catalogOrder = new Map(
  simulationWorkflowNodeCatalog.map((node, index) => [node.type, index] as const),
);

export async function loadWorkflowDefinitions(
  client: WorkflowApiClient,
): Promise<WorkflowDefinitionListState> {
  try {
    const payload = await client.listWorkflows();
    if (!Array.isArray(payload)) {
      throw new Error("workflow list must be an array");
    }
    const items = payload.map(validateWorkflowDefinitionApiView).sort((left, right) =>
      left.workflow_id.localeCompare(right.workflow_id),
    );
    return { status: "loaded", items };
  } catch {
    return {
      status: "unavailable",
      items: [],
      errorMessage: "Saved workflows are unavailable",
    };
  }
}

export function validateWorkflowDefinitionApiView(value: unknown): WorkflowDefinitionApiView {
  const record = requireExactObject(value, "workflow record", [
    "schema_version",
    "workflow_id",
    "display_name",
    "description",
    "version",
    "created_at",
    "updated_at",
    "document",
  ]);
  if (record.schema_version !== 1) {
    throw new Error("workflow schema version is invalid");
  }
  const workflowId = requireIdentifier(record.workflow_id, "workflow_id");
  const displayName = requireMetadata(record.display_name, "display_name");
  const description = requireMetadata(record.description, "description");
  const version = requirePositiveInteger(record.version, "version");
  const createdAt = requireTimestamp(record.created_at, "created_at");
  const updatedAt = requireTimestamp(record.updated_at, "updated_at");
  if (Date.parse(updatedAt) < Date.parse(createdAt)) {
    throw new Error("workflow timestamps are invalid");
  }
  return {
    schema_version: 1,
    workflow_id: workflowId,
    display_name: displayName,
    description,
    version,
    created_at: createdAt,
    updated_at: updatedAt,
    document: validateDslDocument(record.document),
  };
}

export async function loadWorkflowDefinition(
  client: WorkflowApiClient,
  workflowId: string,
): Promise<
  | { status: "loaded"; record: WorkflowDefinitionApiView }
  | { status: "unavailable"; errorMessage: string }
> {
  try {
    requireIdentifier(workflowId, "workflow_id");
    return {
      status: "loaded",
      record: validateWorkflowDefinitionApiView(await client.getWorkflow(workflowId)),
    };
  } catch {
    return {
      status: "unavailable",
      errorMessage: "Selected workflow is unavailable; current edits were kept",
    };
  }
}

export function workflowDefinitionToEditorState(
  record: WorkflowDefinitionApiView,
): VisualWorkflowEditorState {
  const safeRecord = validateWorkflowDefinitionApiView(record);
  const nodes = safeRecord.document.nodes
    .map((node): VisualWorkflowNodeDefinition => {
      const template = catalogByType.get(node.type);
      if (!template) {
        throw new Error("unsupported workflow node");
      }
      return {
        ...template,
        id: node.id,
        requiredForRiskIncreasingPath: node.required_for_risk_increasing_path,
        position: { ...template.position },
      };
    })
    .sort((left, right) =>
      (catalogOrder.get(left.type) ?? Number.MAX_SAFE_INTEGER) -
      (catalogOrder.get(right.type) ?? Number.MAX_SAFE_INTEGER),
    );
  const edges = safeRecord.document.edges.map(
    (edge): VisualWorkflowEdgeDefinition => ({
      id: `${edge.source}-to-${edge.target}`,
      source: edge.source,
      target: edge.target,
      type: "workflow",
    }),
  );
  return { nodes, edges, selection: null };
}

export async function persistWorkflowDefinition(input: {
  client: WorkflowApiClient;
  intent: "create" | "update";
  metadata: WorkflowPersistenceMetadata;
  compileResult: VisualWorkflowDslCompileResult;
  requestedAt: string;
  currentRecord: WorkflowDefinitionApiView | null;
}): Promise<WorkflowPersistenceResult> {
  const request = buildWorkflowPersistenceRequest(
    input.metadata,
    input.compileResult,
    input.requestedAt,
  );
  if (!request) {
    return {
      status: "validation_error",
      errorMessage: "Workflow validation blocked persistence",
    };
  }
  if (input.intent === "update" && !input.currentRecord) {
    return {
      status: "validation_error",
      errorMessage: "Load a saved workflow before updating",
    };
  }

  try {
    const response =
      input.intent === "create"
        ? await input.client.createWorkflow(request)
        : await input.client.updateWorkflow(input.metadata.workflowId, {
            ...request,
            expected_version: input.currentRecord!.version,
          });
    return { status: "saved", record: validateWorkflowDefinitionApiView(response) };
  } catch (error) {
    if (error instanceof WorkflowApiError && error.status === 409) {
      return {
        status: "version_conflict",
        errorMessage: "Saved workflow changed; reload before updating",
      };
    }
    return {
      status: "unavailable",
      errorMessage: "Workflow persistence is unavailable; current edits were kept",
    };
  }
}

export function buildWorkflowPersistenceRequest(
  metadata: WorkflowPersistenceMetadata,
  compileResult: VisualWorkflowDslCompileResult,
  requestedAt: string,
): WorkflowDefinitionSaveRequest | null {
  try {
    if (compileResult.status !== "compiled") {
      return null;
    }
    const workflowId = requireIdentifier(metadata.workflowId, "workflow_id");
    const displayName = requireMetadata(metadata.displayName, "display_name");
    const description = requireMetadata(metadata.description, "description");
    const safeTimestamp = requireTimestamp(requestedAt, "requested_at");
    const document = validateDslDocument(compileResult.document);
    return {
      schema_version: 1,
      workflow_id: workflowId,
      display_name: displayName,
      description,
      requested_at: safeTimestamp,
      document,
    };
  } catch {
    return null;
  }
}

export function workflowDraftFingerprint(
  metadata: WorkflowPersistenceMetadata,
  editorState: VisualWorkflowEditorState,
) {
  const semanticGraph = {
    metadata,
    nodes: editorState.nodes
      .map((node) => ({
        id: node.id,
        type: node.type,
        required: node.requiredForRiskIncreasingPath,
      }))
      .sort((left, right) => left.id.localeCompare(right.id)),
    edges: editorState.edges
      .map((edge) => ({ source: edge.source, target: edge.target, type: edge.type }))
      .sort((left, right) =>
        `${left.source}->${left.target}`.localeCompare(`${right.source}->${right.target}`),
      ),
  };
  return JSON.stringify(semanticGraph);
}

export function canReplaceWorkflowDraft(dirty: boolean, discardConfirmed: boolean) {
  return !dirty || discardConfirmed;
}

function validateDslDocument(value: unknown): VisualWorkflowDslDocument {
  const document = requireExactObject(value, "workflow document", [
    "schema_version",
    "workflow_id",
    "mode",
    "runtime",
    "broker",
    "nodes",
    "edges",
    "safety_gates",
  ]);
  rejectForbiddenContent(document);
  if (
    document.schema_version !== 1 ||
    document.workflow_id !== "visual-simulation-workflow" ||
    document.mode !== "simulation" ||
    document.runtime !== "preview_only" ||
    document.broker !== "fake_broker_only"
  ) {
    throw new Error("workflow document safety posture is invalid");
  }
  if (!Array.isArray(document.nodes) || !Array.isArray(document.edges)) {
    throw new Error("workflow graph is invalid");
  }
  const nodes = document.nodes.map((value) => {
    const node = requireExactObject(value, "workflow node", [
      "id",
      "type",
      "required_for_risk_increasing_path",
    ]);
    const type = requireString(node.type, "node.type");
    if (!nodeTypes.has(type as VisualWorkflowNodeType)) {
      throw new Error("unsupported workflow node");
    }
    if (node.required_for_risk_increasing_path !== true) {
      throw new Error("workflow node safety flag is invalid");
    }
    return {
      id: requireString(node.id, "node.id"),
      type: type as VisualWorkflowNodeType,
      required_for_risk_increasing_path: true as const,
    };
  });
  const edgeIds: string[] = [];
  const edges = document.edges.map((value) => {
    const edge = requireObjectWithOptionalFields(
      value,
      "workflow edge",
      ["source", "target"],
      ["id"],
    );
    if (edge.id !== undefined) {
      edgeIds.push(requireString(edge.id, "edge.id"));
    }
    return {
      source: requireString(edge.source, "edge.source"),
      target: requireString(edge.target, "edge.target"),
    };
  });
  if (new Set(edgeIds).size !== edgeIds.length) {
    throw new Error("duplicate workflow edge id");
  }
  const validation = validateVisualWorkflowGraph(nodes, edges);
  if (validation.status !== "valid") {
    throw new Error("workflow graph is unsafe");
  }
  const gates = requireExactObject(document.safety_gates, "safety gates", [
    "risk_check_required",
    "manual_approval_required",
    "audit_sink_required",
    "broker_transport_allowed",
    "live_trading_enabled",
    "arbitrary_code_allowed",
  ]);
  if (
    gates.risk_check_required !== true ||
    gates.manual_approval_required !== true ||
    gates.audit_sink_required !== true ||
    gates.broker_transport_allowed !== false ||
    gates.live_trading_enabled !== false ||
    gates.arbitrary_code_allowed !== false
  ) {
    throw new Error("workflow safety gates are invalid");
  }
  return {
    schema_version: 1,
    workflow_id: "visual-simulation-workflow",
    mode: "simulation",
    runtime: "preview_only",
    broker: "fake_broker_only",
    nodes,
    edges,
    safety_gates: {
      risk_check_required: true,
      manual_approval_required: true,
      audit_sink_required: true,
      broker_transport_allowed: false,
      live_trading_enabled: false,
      arbitrary_code_allowed: false,
    },
  };
}

function requireExactObject(value: unknown, field: string, keys: string[]) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const actualKeys = Object.keys(record).sort();
  const expectedKeys = [...keys].sort();
  if (JSON.stringify(actualKeys) !== JSON.stringify(expectedKeys)) {
    throw new Error(`${field} has an invalid shape`);
  }
  return record;
}

function requireObjectWithOptionalFields(
  value: unknown,
  field: string,
  requiredKeys: string[],
  optionalKeys: string[],
) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const actualKeys = new Set(Object.keys(record));
  if (
    requiredKeys.some((key) => !actualKeys.has(key)) ||
    [...actualKeys].some((key) => !requiredKeys.includes(key) && !optionalKeys.includes(key))
  ) {
    throw new Error(`${field} has an invalid shape`);
  }
  return record;
}

function requireString(value: unknown, field: string) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${field} must be a non-empty string`);
  }
  rejectForbiddenText(value);
  return value;
}

function requireIdentifier(value: unknown, field: string) {
  const result = requireString(value, field);
  if (result.trim() !== result) {
    throw new Error(`${field} has surrounding whitespace`);
  }
  return result;
}

function requireMetadata(value: unknown, field: string) {
  return requireString(value, field);
}

function requirePositiveInteger(value: unknown, field: string) {
  if (!Number.isInteger(value) || (value as number) < 1) {
    throw new Error(`${field} must be a positive integer`);
  }
  return value as number;
}

function requireTimestamp(value: unknown, field: string) {
  const timestamp = requireString(value, field);
  if (!/(?:Z|[+-]\d\d:\d\d)$/.test(timestamp) || Number.isNaN(Date.parse(timestamp))) {
    throw new Error(`${field} must be a timezone-aware timestamp`);
  }
  return timestamp;
}

function rejectForbiddenContent(value: unknown): void {
  if (Array.isArray(value)) {
    value.forEach(rejectForbiddenContent);
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, nested] of Object.entries(value)) {
      rejectForbiddenText(key);
      rejectForbiddenContent(nested);
    }
    return;
  }
  if (typeof value === "string") {
    rejectForbiddenText(value);
  }
}

function rejectForbiddenText(value: string) {
  const normalized = value.toLowerCase().replaceAll("-", "_");
  for (const token of forbiddenTokens) {
    if (normalized.includes(token)) {
      throw new Error("workflow content is forbidden");
    }
  }
}

export type { WorkflowDefinitionUpdateRequest };
