import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WorkflowSimulationRunStartPanel } from "./WorkflowSimulationRunStartPanel";
import {
  LOCAL_SIMULATION_REPLAY_REFERENCE,
  prepareWorkflowSimulationRunStart,
  type WorkflowSimulationRunEligibility,
  type WorkflowSimulationRunStartState,
} from "./workflowSimulationRunStart";

describe("WorkflowSimulationRunStartPanel", () => {
  it("renders an explicit two-step simulation-only confirmation", () => {
    const html = renderPanel(confirmingState, { status: "eligible" }, false);
    const text = renderedText(html);

    expect(text).toContain("SIMULATION ONLY");
    expect(text).toContain("workflow-001");
    expect(text).toContain("version 3");
    expect(text).toContain(LOCAL_SIMULATION_REPLAY_REFERENCE);
    expect(text).toContain("I confirm this deterministic local simulation run");
    expect(text).toContain("Start simulation");
    expect(html).toContain("disabled");
    expect(text).not.toContain("Approve simulation");
    expect(text).not.toContain("Connect broker");
    expect(text).not.toContain("Transmit order");
  });

  it("enables the deliberate start command only after confirmation", () => {
    const html = renderPanel(confirmingState, { status: "eligible" }, true);

    expect(html).toContain("Start simulation");
    expect(html).not.toContain('disabled=""');
  });

  it.each([
    [
      { status: "validation_blocked", message: "Save an unchanged valid workflow first" },
      "Validation blocked",
    ],
    [
      { status: "authorization_blocked", message: "Local admin permission is required" },
      "Authorization blocked",
    ],
    [
      { status: "emergency_stop_blocked", message: "Emergency stop blocks simulation start" },
      "Emergency stop blocked",
    ],
    [
      { status: "conflict", message: "Saved workflow changed; reload before starting" },
      "Version conflict",
    ],
    [{ status: "unavailable", message: "Simulation start is unavailable" }, "Unavailable"],
  ] as [WorkflowSimulationRunEligibility, string][])(
    "renders fail-closed eligibility state %#",
    (eligibility, expected) => {
      const text = renderedText(renderPanel({ status: "idle" }, eligibility, false));

      expect(text).toContain(expected);
      expect(text).not.toContain("Start simulation");
    },
  );

  it.each([
    [{ status: "starting", attempt }, "Starting deterministic simulation"],
    [{ status: "success", attempt, record: successRecord }, "Waiting for manual approval"],
    [
      { status: "validation_blocked", message: "Simulation request was rejected", attempt },
      "Validation blocked",
    ],
    [
      { status: "authorization_blocked", message: "Local admin permission is required", attempt },
      "Authorization blocked",
    ],
    [
      {
        status: "emergency_stop_blocked",
        message: "Emergency stop blocks simulation start",
        attempt,
      },
      "Emergency stop blocked",
    ],
    [
      { status: "conflict", message: "Saved workflow changed; reload before starting", attempt },
      "Version conflict",
    ],
    [
      { status: "unavailable", message: "Simulation start is unavailable", attempt },
      "Unavailable",
    ],
  ] as [WorkflowSimulationRunStartState, string][])(
    "renders bounded operation state %#",
    (state, expected) => {
      const text = renderedText(renderPanel(state, { status: "eligible" }, false));

      expect(text).toContain(expected);
      expect(text).not.toContain("private-value");
    },
  );

  it("offers exact explicit retry only for retryable failed attempts", () => {
    const retryable = renderedText(
      renderPanel(
        { status: "unavailable", message: "Simulation start is unavailable", attempt },
        { status: "eligible" },
        false,
      ),
    );
    const conflict = renderedText(
      renderPanel(
        { status: "conflict", message: "Saved workflow changed; reload before starting", attempt },
        { status: "eligible" },
        false,
      ),
    );

    expect(retryable).toContain("Retry same request");
    expect(conflict).not.toContain("Retry same request");
  });
});

const confirmingState = prepareWorkflowSimulationRunStart(
  {
    loadedWorkflow: {
      schema_version: 1,
      workflow_id: "workflow-001",
      display_name: "Opening breakout simulation",
      description: "Validated visual simulation workflow",
      version: 3,
      created_at: "2026-07-16T06:00:00Z",
      updated_at: "2026-07-16T06:15:00Z",
      document: {
        schema_version: 1,
        workflow_id: "visual-simulation-workflow",
        mode: "simulation",
        runtime: "preview_only",
        broker: "fake_broker_only",
        nodes: [],
        edges: [],
        safety_gates: {
          risk_check_required: true,
          manual_approval_required: true,
          audit_sink_required: true,
          broker_transport_allowed: false,
          live_trading_enabled: false,
          arbitrary_code_allowed: false,
        },
      },
    },
    selectedWorkflowId: "workflow-001",
    draftDirty: false,
    graphValid: true,
    workflowListStatus: "loaded",
    persistenceStatus: "idle",
    readStateStatus: "loaded",
    canAdministerSystem: true,
    emergencyStopActive: false,
  },
  {
    createRunId: () => "fixed-id-001",
    now: () => new Date("2026-07-16T06:30:00.000Z"),
  },
);

if (confirmingState.status !== "confirming") {
  throw new Error("expected confirming state");
}
const attempt = confirmingState.attempt;
const successRecord = {
  schema_version: 1 as const,
  workflow_id: attempt.workflowId,
  run_id: attempt.request.run_id,
  status: "waiting_for_approval" as const,
  created_at: attempt.request.requested_at,
  updated_at: attempt.request.evaluated_at,
  approval_ticket_id: `${attempt.request.run_id}-approval-ticket`,
  simulation_run: {
    schema_version: 1 as const,
    run_id: attempt.request.run_id,
    status: "completed",
    created_at: attempt.request.requested_at,
    updated_at: attempt.request.evaluated_at,
    replay_input_reference: attempt.replayInputReference,
    journal_references: ["journal_sequence:1"],
  },
  node_statuses: [
    {
      schema_version: 1 as const,
      node_id: "approval-ticket",
      node_type: "approval_ticket",
      status: "waiting_for_approval",
      detail: "Manual approval is required",
      journal_reference: "journal_sequence:2",
    },
  ],
  journal_references: ["journal_sequence:2"],
};

function renderPanel(
  state: WorkflowSimulationRunStartState,
  eligibility: WorkflowSimulationRunEligibility,
  confirmed: boolean,
) {
  return renderToStaticMarkup(
    <WorkflowSimulationRunStartPanel
      confirmationChecked={confirmed}
      eligibility={eligibility}
      onCancel={() => undefined}
      onConfirmationChange={() => undefined}
      onConfirm={() => undefined}
      onRetry={() => undefined}
      onReview={() => undefined}
      state={state}
    />,
  );
}

function renderedText(html: string) {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}
