import type {
  WorkflowApiClient,
  WorkflowDefinitionApiView,
  WorkflowSimulationRunApiView,
} from "./workflowApiClient";

export type WorkflowRunInspectionItem = {
  key: string;
  workflowId: string;
  workflowName: string;
  workflowVersion: number;
  run: WorkflowSimulationRunApiView;
};

export type WorkflowRunInspectionState = {
  status: "loading" | "loaded" | "error";
  items: WorkflowRunInspectionItem[];
  errorMessage: string | null;
};

export const initialWorkflowRunInspectionState: WorkflowRunInspectionState = {
  status: "loading",
  items: [],
  errorMessage: null,
};

export async function loadWorkflowRunInspection(
  client: WorkflowApiClient,
): Promise<WorkflowRunInspectionState> {
  try {
    const workflows = await client.listWorkflows();
    const runGroups = await Promise.all(
      workflows.map(async (workflow) => ({
        workflow,
        runs: await client.listSimulationRuns(workflow.workflow_id),
      })),
    );
    const items = validatedInspectionItems(runGroups).sort(compareInspectionItems);

    return {
      status: "loaded",
      items,
      errorMessage: null,
    };
  } catch {
    return {
      status: "error",
      items: [],
      errorMessage: "Workflow simulation run history is unavailable",
    };
  }
}

function validatedInspectionItems(
  runGroups: Array<{
    workflow: WorkflowDefinitionApiView;
    runs: WorkflowSimulationRunApiView[];
  }>,
) {
  const keys = new Set<string>();
  return runGroups.flatMap(({ workflow, runs }) =>
    runs.map((run) => {
      if (run.workflow_id !== workflow.workflow_id) {
        throw new Error("workflow simulation run attribution mismatch");
      }
      const item = inspectionItem(workflow, run);
      if (keys.has(item.key)) {
        throw new Error("duplicate workflow simulation run key");
      }
      keys.add(item.key);
      return item;
    }),
  );
}

function inspectionItem(
  workflow: WorkflowDefinitionApiView,
  run: WorkflowSimulationRunApiView,
): WorkflowRunInspectionItem {
  return {
    key: `${workflow.workflow_id}::${run.run_id}`,
    workflowId: workflow.workflow_id,
    workflowName: workflow.display_name,
    workflowVersion: run.expected_workflow_version,
    run,
  };
}

function compareInspectionItems(
  left: WorkflowRunInspectionItem,
  right: WorkflowRunInspectionItem,
) {
  const updatedOrder = Date.parse(right.run.updated_at) - Date.parse(left.run.updated_at);
  if (updatedOrder !== 0) {
    return updatedOrder;
  }
  const workflowOrder = compareText(left.workflowId, right.workflowId);
  return workflowOrder !== 0 ? workflowOrder : compareText(left.run.run_id, right.run.run_id);
}

function compareText(left: string, right: string) {
  if (left < right) {
    return -1;
  }
  return left > right ? 1 : 0;
}
