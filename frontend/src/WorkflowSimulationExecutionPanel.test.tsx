import type { ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { WorkflowSimulationExecutionPanel } from "./WorkflowSimulationExecutionPanel";
import type { WorkflowSimulationRunApiView } from "./workflowApiClient";
import type { WorkflowRunInspectionItem } from "./workflowRunInspector";
import type {
  WorkflowSimulationExecutionEligibility,
  WorkflowSimulationExecutionState,
} from "./workflowSimulationExecution";

describe("WorkflowSimulationExecutionPanel", () => {
  it("shows exact committed evidence and requires review before confirmation", () => {
    const onReview = vi.fn();
    const html = renderPanel({ status: "idle" }, { status: "eligible" }, { onReview });
    const text = renderedText(html);

    expect(text).toContain("Durable simulation execution");
    expect(text).toContain("SIMULATION ONLY");
    expect(text).toContain("workflow-run-001-approve-decision");
    expect(text).toContain("workflow-run-001-risk");
    expect(text).toContain("workflow-run-001-intent");
    expect(text).toContain("version 1");
    expect(text).toContain("Persisted plan required by passed risk");
    expect(text).toContain("Expected protection is present in the deterministic simulation");
    expect(text).toContain("Review simulation execution");
    expect(onReview).not.toHaveBeenCalled();

    const lowerText = text.toLowerCase();
    for (const forbidden of ["ibkr", "credential", "account id", "live order", "external alert"]) {
      expect(lowerText).not.toContain(forbidden);
    }
  });

  it("requires a second explicit confirmation before execution", () => {
    const onConfirm = vi.fn();
    const onConfirmationChange = vi.fn();
    const unchecked = renderPanel(confirmingState(), { status: "eligible" }, {
      onConfirm,
      onConfirmationChange,
    });
    const checked = renderPanel(confirmingState(), { status: "eligible" }, {
      confirmed: true,
      onConfirm,
      onConfirmationChange,
    });

    expect(renderedText(unchecked)).toContain(
      "I confirm the exact approved simulation evidence above",
    );
    expect(renderedText(unchecked)).toContain("Execute simulation");
    expect(unchecked).toContain('disabled=""');
    expect(checked).not.toContain('disabled=""');
    expect(onConfirmationChange).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("shows executing, blocked, conflict, unavailable, and retry states", () => {
    expect(
      renderedText(
        renderPanel(
          { status: "executing", attempt: confirmingState().attempt },
          { status: "eligible" },
        ),
      ),
    ).toContain("Executing deterministic local simulation");

    for (const [status, message] of [
      ["authorization_blocked", "Simulation operator permission is required"],
      ["emergency_stop_blocked", "Emergency stop blocks execution"],
      ["conflict", "Execution state changed"],
      ["unavailable", "Durable evidence must be reloaded"],
    ] as const) {
      const html = renderPanel(
        { status, message, attempt: confirmingState().attempt },
        { status: "eligible" },
      );
      expect(renderedText(html)).toContain(message);
      if (status === "unavailable") {
        expect(renderedText(html)).toContain("Retry exact request");
      }
    }
  });

  it("shows committed position, protection, local alert, and recovery evidence", () => {
    const executed = executedItem();
    const success: WorkflowSimulationExecutionState = {
      status: "success",
      attempt: confirmingState().attempt,
      record: executed.run,
    };
    const committed = renderedText(
      renderPanel(success, { status: "eligible" }, { selected: executed }),
    );

    expect(committed).toContain("Simulation execution committed");
    expect(committed).toContain("AAPL | 10 @ 101.25");
    expect(committed).toContain("Expected protection present");
    expect(committed).toContain("Local no-op alert recorded");

    const recovered = renderedText(
      renderPanel(
        { status: "idle" },
        {
          status: "recovered",
          message: "Committed execution evidence recovered from local persistence",
        },
        { selected: executed },
      ),
    );
    expect(recovered).toContain("Recovered durable execution");
    expect(recovered).toContain(
      "Committed execution evidence recovered from local persistence",
    );
  });
});

function renderPanel(
  state: WorkflowSimulationExecutionState,
  eligibility: WorkflowSimulationExecutionEligibility,
  overrides: Partial<ComponentProps<typeof WorkflowSimulationExecutionPanel>> = {},
) {
  return renderToStaticMarkup(panel(state, eligibility, overrides));
}

function panel(
  state: WorkflowSimulationExecutionState,
  eligibility: WorkflowSimulationExecutionEligibility,
  overrides: Partial<ComponentProps<typeof WorkflowSimulationExecutionPanel>> = {},
) {
  return (
    <WorkflowSimulationExecutionPanel
      confirmed={false}
      eligibility={eligibility}
      expectedProtectionPresent={true}
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
      onConfirmationChange={vi.fn()}
      onExpectedProtectionChange={vi.fn()}
      onRetry={vi.fn()}
      onReview={vi.fn()}
      selected={item()}
      state={state}
      {...overrides}
    />
  );
}

function renderedText(html: string) {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

function confirmingState() {
  return {
    status: "confirming" as const,
    attempt: {
      workflowId: "workflow-001",
      workflowVersion: 1,
      runId: "workflow-run-001",
      request: {
        schema_version: 1 as const,
        expected_workflow_version: 1,
        approval_ticket_id: "workflow-run-001-approval-ticket",
        approval_decision_id: "workflow-run-001-approve-decision",
        order_intent_id: "workflow-run-001-intent",
        risk_decision_id: "workflow-run-001-risk",
        order_id: "workflow-run-001-order",
        execution_id: "workflow-run-001-execution",
        executed_at: "2026-07-08T13:47:00.000Z",
        actor: "human-operator-001",
        execution_reference: "workflow-run-001-admin-execution-review",
        reason: "operator_confirmed_simulation_execution",
        broker_state_known: true,
        expected_protection_present: true,
      },
    },
  };
}

function item(): WorkflowRunInspectionItem {
  const run: WorkflowSimulationRunApiView = {
    schema_version: 1,
    workflow_id: "workflow-001",
    expected_workflow_version: 1,
    run_id: "workflow-run-001",
    status: "approved_not_executed",
    created_at: "2026-07-08T13:29:55Z",
    updated_at: "2026-07-08T13:46:00Z",
    approval_ticket_id: "workflow-run-001-approval-ticket",
    approval_decision: {
      schema_version: 1,
      decision_id: "workflow-run-001-approve-decision",
      ticket_id: "workflow-run-001-approval-ticket",
      previous_status: "pending",
      new_status: "approved",
      decided_at: "2026-07-08T13:46:00Z",
      actor: "approver-operator-001",
      decision_reference: "workflow-run-001-approve-manual-review",
      reason: "operator_reviewed_simulation_evidence",
      request: {},
      ticket: {},
    },
    execution: null,
    simulation_run: {
      schema_version: 1,
      run_id: "workflow-run-001",
      status: "completed",
      created_at: "2026-07-08T13:29:55Z",
      updated_at: "2026-07-08T13:45:10Z",
      replay_input_reference: "fixtures/replay/aapl-session.jsonl",
      journal_references: ["journal_sequence:1"],
    },
    node_statuses: [],
    journal_references: ["journal_sequence:10"],
  };
  return {
    key: "workflow-001::workflow-run-001",
    workflowId: "workflow-001",
    workflowName: "Opening breakout simulation",
    workflowVersion: 1,
    run,
  };
}

function executedItem(): WorkflowRunInspectionItem {
  const base = item();
  return {
    ...base,
    run: {
      ...base.run,
      status: "executed",
      execution: {
        ...confirmingState().attempt.request,
        broker_state_known: true as const,
        workflow_id: "workflow-001",
        run_id: "workflow-run-001",
        protection_status: "expected_protection_present",
        risk_increasing_actions_blocked: false,
        oms_transitions: ["APPROVED", "SUBMITTED", "ACKNOWLEDGED", "FILLED"].map(
          (new_state) => ({ new_state }),
        ),
        broker_transitions: ["acknowledged", "filled"].map((state) => ({ state })),
        position: {
          schema_version: 1,
          position_id: "workflow-run-001-position",
          symbol: "AAPL",
          quantity: 10,
          average_price: 101.25,
          protection_status: "expected_protection_present",
          expected_protection_kind: "stop",
          updated_at: "2026-07-08T13:47:00.000Z",
          source_fill_reference: "workflow-run-001-fill",
          journal_references: ["journal_sequence:20"],
        },
        alert_intents: [
          {
            alert_id: "workflow-run-001-alert",
            channel: "local",
            severity: "informational",
          },
        ],
        alert_dispatches: [
          {
            alert_id: "workflow-run-001-alert",
            channel: "local",
            status: "recorded",
            dispatcher: "noop",
          },
        ],
        journal_references: ["journal_sequence:20"],
      },
    },
  };
}
