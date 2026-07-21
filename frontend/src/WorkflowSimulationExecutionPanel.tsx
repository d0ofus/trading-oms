import { Play, RefreshCw, ShieldAlert, X } from "lucide-react";

import type { WorkflowRunInspectionItem } from "./workflowRunInspector";
import {
  canRetryWorkflowSimulationExecution,
  type WorkflowSimulationExecutionAttempt,
  type WorkflowSimulationExecutionEligibility,
  type WorkflowSimulationExecutionState,
} from "./workflowSimulationExecution";

type Props = {
  confirmed: boolean;
  eligibility: WorkflowSimulationExecutionEligibility;
  expectedProtectionPresent: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onConfirmationChange: (confirmed: boolean) => void;
  onExpectedProtectionChange: (present: boolean) => void;
  onRetry: () => void;
  onReview: () => void;
  selected: WorkflowRunInspectionItem | null;
  state: WorkflowSimulationExecutionState;
};

export function WorkflowSimulationExecutionPanel({
  confirmed,
  eligibility,
  expectedProtectionPresent,
  onCancel,
  onConfirm,
  onConfirmationChange,
  onExpectedProtectionChange,
  onRetry,
  onReview,
  selected,
  state,
}: Props) {
  const attempt = "attempt" in state ? state.attempt : undefined;
  const execution = selected?.run.execution ?? null;
  return (
    <div className="workflow-execution-panel" aria-label="Durable simulation execution">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Separate operator action</p>
          <h3>Durable simulation execution</h3>
        </div>
        <span className="simulation-only-label">SIMULATION ONLY</span>
      </div>

      {selected ? <SelectedEvidenceFacts selected={selected} /> : null}

      {state.status === "idle" && eligibility.status === "eligible" ? (
        <div className="workflow-execution-review">
          <label className="simulation-start-confirmation">
            <input
              checked={expectedProtectionPresent}
              onChange={(event) => onExpectedProtectionChange(event.target.checked)}
              type="checkbox"
            />
            <span>Expected protection is present in the deterministic simulation</span>
          </label>
          <p className="state-note">
            This review consumes committed approval evidence only after a second confirmation.
          </p>
          <button onClick={onReview} type="button">
            <ShieldAlert aria-hidden="true" size={16} />
            Review simulation execution
          </button>
        </div>
      ) : null}

      {state.status === "idle" && eligibility.status === "recovered" && execution ? (
        <div className="workflow-run-start-success" role="status">
          <strong>Recovered durable execution</strong>
          <p>{eligibility.message}</p>
          <CommittedExecutionFacts selected={selected!} />
        </div>
      ) : null}

      {state.status === "idle" && isBlockedEligibility(eligibility) ? (
        <p className="state-note">{eligibility.message}</p>
      ) : null}

      {state.status === "confirming" && attempt ? (
        <div className="workflow-run-confirmation">
          <strong>Confirm exact approved evidence</strong>
          <ExecutionAttemptFacts attempt={attempt} />
          <p>Execution advances deterministic local OMS, fill, position, and audit state.</p>
          <label className="simulation-start-confirmation">
            <input
              checked={confirmed}
              onChange={(event) => onConfirmationChange(event.target.checked)}
              type="checkbox"
            />
            <span>I confirm the exact approved simulation evidence above</span>
          </label>
          <div className="approval-actions">
            <button onClick={onCancel} type="button">
              <X aria-hidden="true" size={16} />
              Cancel
            </button>
            <button disabled={!confirmed} onClick={onConfirm} type="button">
              <Play aria-hidden="true" size={16} />
              Execute simulation
            </button>
          </div>
        </div>
      ) : null}

      {state.status === "executing" ? (
        <p aria-live="polite">Executing deterministic local simulation</p>
      ) : null}

      {state.status === "success" ? (
        <div className="workflow-run-start-success" role="status">
          <strong>
            {state.record.status === "executed"
              ? "Simulation execution committed"
              : "Simulation committed with protection block"}
          </strong>
          <CommittedExecutionFacts
            selected={{
              ...(selected ?? fallbackInspectionItem(state.record)),
              run: state.record,
            }}
          />
        </div>
      ) : null}

      {isBlockedState(state) ? (
        <div className="workflow-run-start-error" role="alert">
          <strong>Simulation execution not confirmed</strong>
          <p>{state.message}</p>
          {canRetryWorkflowSimulationExecution(state) ? (
            <button onClick={onRetry} type="button">
              <RefreshCw aria-hidden="true" size={16} />
              Retry exact request
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function SelectedEvidenceFacts({ selected }: { selected: WorkflowRunInspectionItem }) {
  const decision = selected.run.approval_decision;
  return (
    <dl className="workflow-execution-facts">
      <Fact label="Workflow" value={selected.workflowId} />
      <Fact label="Definition" value={`version ${selected.workflowVersion}`} />
      <Fact label="Run" value={selected.run.run_id} />
      <Fact label="Approval ticket" value={selected.run.approval_ticket_id ?? "unavailable"} />
      <Fact label="Approval decision" value={decision?.decision_id ?? "unavailable"} />
      <Fact label="Risk decision" value={`${selected.run.run_id}-risk`} />
      <Fact label="Order intent" value={`${selected.run.run_id}-intent`} />
      <Fact label="Protection plan" value="Persisted plan required by passed risk" />
    </dl>
  );
}

function ExecutionAttemptFacts({ attempt }: { attempt: WorkflowSimulationExecutionAttempt }) {
  return (
    <dl className="workflow-execution-facts">
      <Fact label="Workflow version" value={String(attempt.workflowVersion)} />
      <Fact label="Approval" value={attempt.request.approval_decision_id} />
      <Fact label="Risk" value={attempt.request.risk_decision_id} />
      <Fact label="Order intent" value={attempt.request.order_intent_id} />
      <Fact label="Order" value={attempt.request.order_id} />
      <Fact
        label="Protection observation"
        value={
          attempt.request.expected_protection_present
            ? "Expected protection present"
            : "Expected protection missing"
        }
      />
      <Fact label="Simulated state" value="Known" />
      <Fact label="Alert delivery" value="Local no-op only" />
    </dl>
  );
}

function CommittedExecutionFacts({ selected }: { selected: WorkflowRunInspectionItem }) {
  const execution = selected.run.execution;
  if (!execution) {
    return null;
  }
  return (
    <dl className="workflow-execution-facts committed-execution-facts">
      <Fact label="Execution" value={execution.execution_id} />
      <Fact
        label="Position"
        value={`${execution.position.symbol} | ${execution.position.quantity} @ ${execution.position.average_price}`}
      />
      <Fact
        label="Protection"
        value={
          execution.expected_protection_present
            ? "Expected protection present"
            : "Expected protection missing"
        }
      />
      <Fact
        label="Risk posture"
        value={
          execution.risk_increasing_actions_blocked
            ? "Further risk increase blocked"
            : "Protection check passed"
        }
      />
      <Fact label="Alert" value="Local no-op alert recorded" />
      <Fact label="Journal" value={`${execution.journal_references.length} references`} />
    </dl>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function fallbackInspectionItem(run: WorkflowRunInspectionItem["run"]): WorkflowRunInspectionItem {
  return {
    key: `${run.workflow_id}::${run.run_id}`,
    workflowId: run.workflow_id,
    workflowName: run.workflow_id,
    workflowVersion: run.execution?.expected_workflow_version ?? 1,
    run,
  };
}

function isBlockedEligibility(
  eligibility: WorkflowSimulationExecutionEligibility,
): eligibility is Exclude<
  WorkflowSimulationExecutionEligibility,
  { status: "eligible" | "recovered" }
> {
  return !["eligible", "recovered"].includes(eligibility.status);
}

function isBlockedState(
  state: WorkflowSimulationExecutionState,
): state is Extract<WorkflowSimulationExecutionState, { message: string }> {
  return "message" in state;
}
