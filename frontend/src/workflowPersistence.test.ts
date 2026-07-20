import { describe, expect, it } from "vitest";

import {
  WorkflowApiError,
  type WorkflowApiClient,
  type WorkflowDefinitionApiView,
  type WorkflowDefinitionSaveRequest,
  type WorkflowDefinitionUpdateRequest,
} from "./workflowApiClient";
import {
  canReplaceWorkflowDraft,
  loadWorkflowDefinitions,
  persistWorkflowDefinition,
  workflowDefinitionToEditorState,
  workflowDraftFingerprint,
  type WorkflowPersistenceMetadata,
} from "./workflowPersistence";
import {
  compileVisualWorkflowDsl,
  defaultVisualWorkflowDslCompileResult,
  type VisualWorkflowDslDocument,
} from "./visualWorkflowDsl";
import {
  createInitialVisualWorkflowEditorState,
  moveVisualWorkflowNode,
  removeVisualWorkflowNode,
} from "./visualWorkflowEditor";

const metadata: WorkflowPersistenceMetadata = {
  workflowId: "workflow-001",
  displayName: "Opening breakout simulation",
  description: "Validated visual simulation workflow",
};

const sampleDocument = compiledDocument();

describe("workflow persistence", () => {
  it("loads, validates, and sorts saved definitions before exposing them", async () => {
    const later = savedWorkflow({
      workflow_id: "workflow-002",
      display_name: "Second workflow",
      updated_at: "2026-07-16T00:10:00Z",
    });
    const earlier = savedWorkflow();
    const state = await loadWorkflowDefinitions(workflowClient({ listResult: [later, earlier] }));

    expect(state).toEqual({ status: "loaded", items: [earlier, later] });
    const editorState = workflowDefinitionToEditorState(earlier);
    expect(editorState.selection).toBeNull();
    expect(editorState.nodes.map((node) => node.id)).toEqual(sampleDocument.nodes.map((node) => node.id));
    expect(editorState.nodes[0].position).toEqual({ x: 0, y: 110 });
    expect(editorState.edges[0]).toEqual({
      id: "replay-source-to-bar-builder",
      source: "replay-source",
      target: "bar-builder",
      type: "workflow",
    });
  });

  it("fails closed when any untrusted list record is unsafe or malformed", async () => {
    const unsafe = {
      ...savedWorkflow(),
      display_name: "Credential workflow",
    } as WorkflowDefinitionApiView;
    const state = await loadWorkflowDefinitions(
      workflowClient({ listResult: [savedWorkflow(), unsafe] }),
    );

    expect(state).toEqual({
      status: "unavailable",
      items: [],
      errorMessage: "Saved workflows are unavailable",
    });

    const duplicateEdgeDocument = structuredClone(sampleDocument);
    duplicateEdgeDocument.edges.push({ ...duplicateEdgeDocument.edges[0] });
    const duplicateEdgeState = await loadWorkflowDefinitions(
      workflowClient({
        listResult: [savedWorkflow({ document: duplicateEdgeDocument })],
      }),
    );
    expect(duplicateEdgeState.status).toBe("unavailable");

    const edgeIdDocument = structuredClone(sampleDocument);
    edgeIdDocument.edges.forEach((edge, index) => Object.assign(edge, { id: `edge-${index}` }));
    const edgeIdState = await loadWorkflowDefinitions(
      workflowClient({ listResult: [savedWorkflow({ document: edgeIdDocument })] }),
    );
    expect(edgeIdState.status).toBe("loaded");

    Object.assign(edgeIdDocument.edges[1], { id: "edge-0" });
    const duplicateEdgeIdState = await loadWorkflowDefinitions(
      workflowClient({ listResult: [savedWorkflow({ document: edgeIdDocument })] }),
    );
    expect(duplicateEdgeIdState.status).toBe("unavailable");
  });

  it("blocks invalid or unsafe drafts before making an API request", async () => {
    let calls = 0;
    const client = workflowClient({ onMutation: () => calls++ });
    const invalidEditor = removeVisualWorkflowNode(
      createInitialVisualWorkflowEditorState(),
      "approval-ticket",
    ).state;

    const invalidResult = await persistWorkflowDefinition({
      client,
      intent: "create",
      metadata,
      compileResult: compileVisualWorkflowDsl(invalidEditor.nodes, invalidEditor.edges),
      requestedAt: "2026-07-16T00:00:00Z",
      currentRecord: null,
    });
    const unsafeResult = await persistWorkflowDefinition({
      client,
      intent: "create",
      metadata: { ...metadata, displayName: "Credential workflow" },
      compileResult: defaultVisualWorkflowDslCompileResult,
      requestedAt: "2026-07-16T00:00:00Z",
      currentRecord: null,
    });

    expect(invalidResult.status).toBe("validation_error");
    expect(unsafeResult.status).toBe("validation_error");
    expect(calls).toBe(0);
  });

  it("sends exact create and version-guarded update payloads", async () => {
    const createRequests: WorkflowDefinitionSaveRequest[] = [];
    const updateRequests: WorkflowDefinitionUpdateRequest[] = [];
    const createdRecord = savedWorkflow();
    const client = workflowClient({
      onCreate: (request) => createRequests.push(request),
      onUpdate: (request) => updateRequests.push(request),
      mutationResult: createdRecord,
    });

    const created = await persistWorkflowDefinition({
      client,
      intent: "create",
      metadata,
      compileResult: defaultVisualWorkflowDslCompileResult,
      requestedAt: "2026-07-16T00:00:00Z",
      currentRecord: null,
    });
    const updated = await persistWorkflowDefinition({
      client,
      intent: "update",
      metadata,
      compileResult: defaultVisualWorkflowDslCompileResult,
      requestedAt: "2026-07-16T00:05:00Z",
      currentRecord: { ...createdRecord, version: 7 },
    });

    expect(created.status).toBe("saved");
    expect(updated.status).toBe("saved");
    expect(createRequests).toEqual([
      {
        schema_version: 1,
        workflow_id: "workflow-001",
        display_name: "Opening breakout simulation",
        description: "Validated visual simulation workflow",
        requested_at: "2026-07-16T00:00:00Z",
        document: sampleDocument,
      },
    ]);
    expect(updateRequests).toEqual([
      {
        ...createRequests[0],
        requested_at: "2026-07-16T00:05:00Z",
        expected_version: 7,
      },
    ]);
  });

  it("classifies stale updates without mutating the user's draft", async () => {
    const draftBefore = JSON.stringify(metadata);
    const client = workflowClient({ mutationError: new WorkflowApiError("/api/workflows/x", 409) });

    const result = await persistWorkflowDefinition({
      client,
      intent: "update",
      metadata,
      compileResult: defaultVisualWorkflowDslCompileResult,
      requestedAt: "2026-07-16T00:05:00Z",
      currentRecord: savedWorkflow(),
    });

    expect(result).toEqual({
      status: "version_conflict",
      errorMessage: "Saved workflow changed; reload before updating",
    });
    expect(JSON.stringify(metadata)).toBe(draftBefore);
  });

  it("tracks semantic edits and requires deliberate discard before loading", () => {
    const initial = createInitialVisualWorkflowEditorState();
    const moved = moveVisualWorkflowNode(initial, "replay-source", { x: 75, y: 90 }).state;
    const edited = removeVisualWorkflowNode(initial, "alert").state;

    expect(workflowDraftFingerprint(metadata, moved)).toBe(
      workflowDraftFingerprint(metadata, initial),
    );
    expect(workflowDraftFingerprint(metadata, edited)).not.toBe(
      workflowDraftFingerprint(metadata, initial),
    );
    expect(canReplaceWorkflowDraft(true, false)).toBe(false);
    expect(canReplaceWorkflowDraft(true, true)).toBe(true);
    expect(canReplaceWorkflowDraft(false, false)).toBe(true);
  });
});

function savedWorkflow(overrides: Partial<WorkflowDefinitionApiView> = {}): WorkflowDefinitionApiView {
  return {
    schema_version: 1,
    workflow_id: "workflow-001",
    display_name: "Opening breakout simulation",
    description: "Validated visual simulation workflow",
    version: 1,
    created_at: "2026-07-16T00:00:00Z",
    updated_at: "2026-07-16T00:00:00Z",
    document: sampleDocument,
    ...overrides,
  };
}

function workflowClient(options: {
  listResult?: WorkflowDefinitionApiView[];
  mutationResult?: WorkflowDefinitionApiView;
  mutationError?: Error;
  onMutation?: () => void;
  onCreate?: (request: WorkflowDefinitionSaveRequest) => void;
  onUpdate?: (request: WorkflowDefinitionUpdateRequest) => void;
} = {}): WorkflowApiClient {
  const mutate = async () => {
    options.onMutation?.();
    if (options.mutationError) {
      throw options.mutationError;
    }
    return options.mutationResult ?? savedWorkflow();
  };
  return {
    listWorkflows: async () => options.listResult ?? [],
    getWorkflow: async () => savedWorkflow(),
    createWorkflow: async (request) => {
      options.onCreate?.(request);
      return mutate();
    },
    updateWorkflow: async (_workflowId, request) => {
      options.onUpdate?.(request);
      return mutate();
    },
    startSimulationRun: async () => {
      throw new Error("not used");
    },
    listSimulationRuns: async () => [],
    getSimulationRun: async () => {
      throw new Error("not used");
    },
    approveSimulationRun: async () => {
      throw new Error("not used");
    },
    rejectSimulationRun: async () => {
      throw new Error("not used");
    },
  };
}

function compiledDocument(): VisualWorkflowDslDocument {
  if (defaultVisualWorkflowDslCompileResult.status !== "compiled") {
    throw new Error("default visual workflow must compile");
  }
  return defaultVisualWorkflowDslCompileResult.document;
}
