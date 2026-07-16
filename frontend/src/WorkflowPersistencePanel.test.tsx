import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WorkflowPersistencePanel } from "./WorkflowPersistencePanel";
import type {
  WorkflowDefinitionListState,
  WorkflowPersistenceMetadata,
  WorkflowPersistenceOperationState,
} from "./workflowPersistence";

const metadata: WorkflowPersistenceMetadata = {
  workflowId: "workflow-001",
  displayName: "Opening breakout simulation",
  description: "Validated visual simulation workflow",
};

describe("WorkflowPersistencePanel", () => {
  it.each([
    [{ status: "loading", items: [] }, { status: "idle" }, "Loading saved workflows"],
    [{ status: "loaded", items: [] }, { status: "idle" }, "No saved workflows"],
    [{ status: "loaded", items: [] }, { status: "saving", intent: "create" }, "Saving workflow"],
    [
      { status: "loaded", items: [] },
      { status: "validation_error", errorMessage: "Workflow validation blocked persistence" },
      "Workflow validation blocked persistence",
    ],
    [
      { status: "loaded", items: [] },
      { status: "version_conflict", errorMessage: "Saved workflow changed; reload before updating" },
      "Saved workflow changed; reload before updating",
    ],
    [
      { status: "unavailable", items: [], errorMessage: "Saved workflows are unavailable" },
      { status: "idle" },
      "Saved workflows are unavailable",
    ],
  ] as [WorkflowDefinitionListState, WorkflowPersistenceOperationState, string][]) (
    "renders bounded persistence state %#",
    (listState, operationState, expectedText) => {
      const html = renderToStaticMarkup(
        <WorkflowPersistencePanel
          canPersist={false}
          dirty={false}
          discardConfirmed={false}
          listState={listState}
          loadedWorkflowId={null}
          metadata={metadata}
          onCreate={() => undefined}
          onDiscardConfirmationChange={() => undefined}
          onLoad={() => undefined}
          onMetadataChange={() => undefined}
          onNew={() => undefined}
          onSelect={() => undefined}
          onUpdate={() => undefined}
          operationState={operationState}
          selectedWorkflowId={null}
        />,
      );

      expect(html).toContain(expectedText);
      expect(html).toContain("Create workflow");
      expect(html).toContain("Update workflow");
      expect(html).toContain("Discard current edits before load");
      expect(html).not.toContain("Run workflow");
      expect(html).not.toContain("Delete workflow");
      expect(html).not.toContain("Connect broker");
    },
  );
});
