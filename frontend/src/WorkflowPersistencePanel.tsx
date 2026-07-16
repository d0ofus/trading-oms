import { FilePlus2, FolderOpen, RefreshCw, Save } from "lucide-react";

import type {
  WorkflowDefinitionListState,
  WorkflowPersistenceMetadata,
  WorkflowPersistenceOperationState,
} from "./workflowPersistence";

type WorkflowPersistencePanelProps = {
  canPersist: boolean;
  dirty: boolean;
  discardConfirmed: boolean;
  listState: WorkflowDefinitionListState;
  loadedWorkflowId: string | null;
  metadata: WorkflowPersistenceMetadata;
  operationState: WorkflowPersistenceOperationState;
  selectedWorkflowId: string | null;
  onCreate: () => void;
  onDiscardConfirmationChange: (confirmed: boolean) => void;
  onLoad: () => void;
  onMetadataChange: (metadata: WorkflowPersistenceMetadata) => void;
  onNew: () => void;
  onSelect: (workflowId: string | null) => void;
  onUpdate: () => void;
};

export const workflowPersistenceLayoutPolicy = {
  desktopColumns: 2,
  mobileColumns: 1,
  minControlHeightPx: 40,
  responsiveLayout: true,
  autosaveEnabled: false,
} as const;

export function WorkflowPersistencePanel({
  canPersist,
  dirty,
  discardConfirmed,
  listState,
  loadedWorkflowId,
  metadata,
  operationState,
  selectedWorkflowId,
  onCreate,
  onDiscardConfirmationChange,
  onLoad,
  onMetadataChange,
  onNew,
  onSelect,
  onUpdate,
}: WorkflowPersistencePanelProps) {
  const busy = operationState.status === "saving" || operationState.status === "loading";
  const selected =
    listState.status === "loaded"
      ? listState.items.find((item) => item.workflow_id === selectedWorkflowId) ?? null
      : null;
  const loadBlocked = dirty && !discardConfirmed;
  const draftState =
    loadedWorkflowId === null
      ? "New local definition"
      : dirty
        ? "Unsaved changes"
        : "Unchanged saved definition";

  return (
    <div className="workflow-persistence" aria-label="Validated workflow persistence">
      <div className="section-heading">
        <div>
          <h2>Workflow library</h2>
          <p>Validated simulation definitions</p>
        </div>
        <span className="workflow-persistence-mode">local versioned storage</span>
      </div>

      <p className="workflow-draft-state" aria-label="Workflow draft state">
        {draftState}
      </p>

      <div className="workflow-library-controls">
        <label>
          <span>Saved definition</span>
          <select
            aria-label="Saved workflow definition"
            disabled={listState.status !== "loaded" || busy}
            onChange={(event) => onSelect(event.target.value || null)}
            value={selectedWorkflowId ?? ""}
          >
            <option value="">Select a workflow</option>
            {listState.status === "loaded"
              ? listState.items.map((item) => (
                  <option key={item.workflow_id} value={item.workflow_id}>
                    {item.display_name} | version {item.version}
                  </option>
                ))
              : null}
          </select>
        </label>
        <div className="workflow-library-actions">
          <button
            disabled={!selected || loadBlocked || busy}
            onClick={onLoad}
            title="Load selected workflow"
            type="button"
          >
            <FolderOpen aria-hidden="true" size={16} />
            Load
          </button>
          <button
            disabled={busy || loadBlocked}
            onClick={onNew}
            title="Start a new workflow"
            type="button"
          >
            <FilePlus2 aria-hidden="true" size={16} />
            New
          </button>
        </div>
      </div>

      <label className="discard-confirmation">
        <input
          checked={discardConfirmed}
          onChange={(event) => onDiscardConfirmationChange(event.target.checked)}
          type="checkbox"
        />
        <span>Discard current edits before load</span>
      </label>

      <div className="workflow-metadata-fields">
        <label>
          <span>Workflow ID</span>
          <input
            disabled={selected !== null || busy}
            maxLength={120}
            onChange={(event) =>
              onMetadataChange({ ...metadata, workflowId: event.target.value })
            }
            value={metadata.workflowId}
          />
        </label>
        <label>
          <span>Display name</span>
          <input
            maxLength={160}
            onChange={(event) =>
              onMetadataChange({ ...metadata, displayName: event.target.value })
            }
            value={metadata.displayName}
          />
        </label>
        <label className="workflow-description-field">
          <span>Description</span>
          <textarea
            maxLength={500}
            onChange={(event) =>
              onMetadataChange({ ...metadata, description: event.target.value })
            }
            rows={3}
            value={metadata.description}
          />
        </label>
      </div>

      <div className="workflow-persistence-actions">
        <button
          disabled={!canPersist || loadedWorkflowId !== null || busy}
          onClick={onCreate}
          type="button"
        >
          <Save aria-hidden="true" size={16} />
          Create workflow
        </button>
        <button
          disabled={
            !canPersist ||
            !selected ||
            selected.workflow_id !== loadedWorkflowId ||
            !dirty ||
            busy
          }
          onClick={onUpdate}
          type="button"
        >
          <RefreshCw aria-hidden="true" size={16} />
          Update workflow
        </button>
        {selected?.workflow_id === loadedWorkflowId ? (
          <span>Loaded version {selected.version}</span>
        ) : null}
      </div>

      <PersistenceFeedback listState={listState} operationState={operationState} />
    </div>
  );
}

function PersistenceFeedback({
  listState,
  operationState,
}: {
  listState: WorkflowDefinitionListState;
  operationState: WorkflowPersistenceOperationState;
}) {
  if (listState.status === "loading") {
    return <p className="persistence-feedback">Loading saved workflows</p>;
  }
  if (listState.status === "unavailable") {
    return <p className="persistence-feedback persistence-feedback-error">{listState.errorMessage}</p>;
  }
  if (operationState.status === "saving") {
    return <p className="persistence-feedback">Saving workflow</p>;
  }
  if (operationState.status === "loading") {
    return <p className="persistence-feedback">Loading selected workflow</p>;
  }
  if (operationState.status === "saved") {
    return (
      <p className="persistence-feedback persistence-feedback-success">
        Workflow persisted as version {operationState.record.version}
      </p>
    );
  }
  if (
    operationState.status === "validation_error" ||
    operationState.status === "version_conflict" ||
    operationState.status === "unavailable"
  ) {
    return (
      <p className="persistence-feedback persistence-feedback-error">
        {operationState.errorMessage}
      </p>
    );
  }
  if (listState.items.length === 0) {
    return <p className="persistence-feedback">No saved workflows</p>;
  }
  return <p className="persistence-feedback">Select a saved workflow to load it deliberately</p>;
}
