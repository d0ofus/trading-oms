import { Play, RotateCcw, ShieldCheck, X } from "lucide-react";

import {
  canRetryWorkflowSimulationRunStart,
  type WorkflowSimulationRunAttempt,
  type WorkflowSimulationRunEligibility,
  type WorkflowSimulationRunStartState,
} from "./workflowSimulationRunStart";

type WorkflowSimulationRunStartPanelProps = {
  confirmationChecked: boolean;
  eligibility: WorkflowSimulationRunEligibility;
  onCancel: () => void;
  onConfirmationChange: (checked: boolean) => void;
  onConfirm: () => void;
  onRetry: () => void;
  onReview: () => void;
  state: WorkflowSimulationRunStartState;
};

type PanelBlockingState = {
  status:
    | "validation_blocked"
    | "authorization_blocked"
    | "emergency_stop_blocked"
    | "conflict"
    | "unavailable";
  message: string;
  attempt?: WorkflowSimulationRunAttempt;
};

export function WorkflowSimulationRunStartPanel({
  confirmationChecked,
  eligibility,
  onCancel,
  onConfirmationChange,
  onConfirm,
  onRetry,
  onReview,
  state,
}: WorkflowSimulationRunStartPanelProps) {
  const attempt = attemptFromState(state);

  return (
    <div className="workflow-run-start" aria-label="Saved workflow simulation start">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Saved workflow run</p>
          <h2>Simulation run start</h2>
        </div>
        <span className="simulation-only-label">SIMULATION ONLY</span>
      </div>

      {state.status === "idle" ? (
        eligibility.status === "eligible" ? (
          <div className="workflow-run-start-ready">
            <p>Saved workflow is ready for deliberate simulation review</p>
            <button onClick={onReview} type="button">
              <ShieldCheck aria-hidden="true" size={16} />
              Review simulation start
            </button>
          </div>
        ) : (
          <RunStartFeedback eligibility={eligibility} />
        )
      ) : null}

      {state.status === "confirming" ? (
        <div className="workflow-run-confirmation">
          <AttemptFacts attempt={state.attempt} />
          <label className="simulation-start-confirmation">
            <input
              checked={confirmationChecked}
              onChange={(event) => onConfirmationChange(event.target.checked)}
              type="checkbox"
            />
            <span>I confirm this deterministic local simulation run</span>
          </label>
          <div className="workflow-run-start-actions">
            <button onClick={onCancel} type="button">
              <X aria-hidden="true" size={16} />
              Cancel
            </button>
            <button disabled={!confirmationChecked} onClick={onConfirm} type="button">
              <Play aria-hidden="true" size={16} />
              Start simulation
            </button>
          </div>
        </div>
      ) : null}

      {state.status === "starting" ? (
        <div aria-live="polite" className="workflow-run-start-feedback">
          <p>Starting deterministic simulation</p>
          <AttemptFacts attempt={state.attempt} />
        </div>
      ) : null}

      {state.status === "success" ? (
        <div className="workflow-run-start-feedback workflow-run-start-success" role="status">
          <strong>Waiting for manual approval</strong>
          <p>Run {state.record.run_id} is selected in the inspector</p>
          <p>Approval ticket {state.record.approval_ticket_id ?? "not created"}</p>
        </div>
      ) : null}

      {isBlockingState(state) ? (
        <div className="workflow-run-start-feedback workflow-run-start-error" role="alert">
          <strong>{statusLabel(state.status)}</strong>
          <p>{state.message}</p>
          {attempt ? <AttemptFacts attempt={attempt} /> : null}
          {canRetryWorkflowSimulationRunStart(state) ? (
            <button onClick={onRetry} type="button">
              <RotateCcw aria-hidden="true" size={16} />
              Retry same request
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function RunStartFeedback({
  eligibility,
}: {
  eligibility: Exclude<WorkflowSimulationRunEligibility, { status: "eligible" }>;
}) {
  return (
    <div className="workflow-run-start-feedback workflow-run-start-error">
      <strong>{statusLabel(eligibility.status)}</strong>
      <p>{eligibility.message}</p>
    </div>
  );
}

function AttemptFacts({ attempt }: { attempt: WorkflowSimulationRunAttempt }) {
  return (
    <dl className="workflow-run-start-facts">
      <div>
        <dt>Workflow ID</dt>
        <dd>{attempt.workflowId}</dd>
      </div>
      <div>
        <dt>Saved definition</dt>
        <dd>version {attempt.workflowVersion}</dd>
      </div>
      <div>
        <dt>Replay input</dt>
        <dd>{attempt.replayInputReference}</dd>
      </div>
    </dl>
  );
}

function attemptFromState(state: WorkflowSimulationRunStartState) {
  return "attempt" in state ? state.attempt : undefined;
}

function isBlockingState(
  state: WorkflowSimulationRunStartState,
): state is PanelBlockingState {
  return [
    "validation_blocked",
    "authorization_blocked",
    "emergency_stop_blocked",
    "conflict",
    "unavailable",
  ].includes(state.status);
}

function statusLabel(status: Exclude<WorkflowSimulationRunEligibility["status"], "eligible">) {
  const labels = {
    validation_blocked: "Validation blocked",
    authorization_blocked: "Authorization blocked",
    emergency_stop_blocked: "Emergency stop blocked",
    conflict: "Version conflict",
    unavailable: "Unavailable",
  } as const;
  return labels[status];
}
