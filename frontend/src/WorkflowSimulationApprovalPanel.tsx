import { Check, ShieldAlert, X } from "lucide-react";

import type { WorkflowRunInspectionItem } from "./workflowRunInspector";
import type {
  WorkflowSimulationDecisionAction,
  WorkflowSimulationDecisionEligibility,
  WorkflowSimulationDecisionState,
} from "./workflowSimulationApproval";

type Props = {
  confirmed: boolean;
  eligibility: WorkflowSimulationDecisionEligibility;
  onCancel: () => void;
  onConfirm: () => void;
  onConfirmationChange: (confirmed: boolean) => void;
  onReasonChange: (reason: string) => void;
  onReview: (action: WorkflowSimulationDecisionAction) => void;
  reason: string;
  selected: WorkflowRunInspectionItem | null;
  state: WorkflowSimulationDecisionState;
};

export function WorkflowSimulationApprovalPanel({
  confirmed,
  eligibility,
  onCancel,
  onConfirm,
  onConfirmationChange,
  onReasonChange,
  onReview,
  reason,
  selected,
  state,
}: Props) {
  const attempt = "attempt" in state ? state.attempt : undefined;
  return (
    <div className="workflow-approval-panel" aria-label="Saved workflow manual approval">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Manual decision</p>
          <h3>Saved run approval</h3>
        </div>
        <span className="simulation-only-label">SIMULATION ONLY</span>
      </div>

      {selected ? (
        <dl className="workflow-run-start-facts">
          <div>
            <dt>Workflow</dt>
            <dd>{selected.workflowId}</dd>
          </div>
          <div>
            <dt>Run</dt>
            <dd>{selected.run.run_id}</dd>
          </div>
          <div>
            <dt>Ticket</dt>
            <dd>{selected.run.approval_ticket_id ?? "not available"}</dd>
          </div>
        </dl>
      ) : null}

      {state.status === "idle" ? (
        eligibility.status === "eligible" ? (
          <>
            <label>
              <span>Decision reason</span>
              <textarea
                aria-label="Saved workflow decision reason"
                maxLength={240}
                onChange={(event) => onReasonChange(event.target.value)}
                value={reason}
              />
            </label>
            <div className="approval-actions">
              <button onClick={() => onReview("approve")} type="button">
                <Check aria-hidden="true" size={16} />
                Review approval
              </button>
              <button onClick={() => onReview("reject")} type="button">
                <X aria-hidden="true" size={16} />
                Review rejection
              </button>
            </div>
          </>
        ) : (
          <p className="state-note">{eligibility.message}</p>
        )
      ) : null}

      {state.status === "confirming" && attempt ? (
        <div className="workflow-run-confirmation">
          <strong>
            Confirm simulation {attempt.action === "approve" ? "approval" : "rejection"}
          </strong>
          <p>No OMS or fake-broker execution occurs in this step.</p>
          <label className="simulation-start-confirmation">
            <input
              checked={confirmed}
              onChange={(event) => onConfirmationChange(event.target.checked)}
              type="checkbox"
            />
            <span>I confirm this manual simulation decision</span>
          </label>
          <div className="approval-actions">
            <button onClick={onCancel} type="button">
              <X aria-hidden="true" size={16} />
              Cancel
            </button>
            <button disabled={!confirmed} onClick={onConfirm} type="button">
              <ShieldAlert aria-hidden="true" size={16} />
              Record {attempt.action === "approve" ? "approval" : "rejection"}
            </button>
          </div>
        </div>
      ) : null}

      {state.status === "deciding" ? (
        <p aria-live="polite">Recording durable simulation decision</p>
      ) : null}

      {state.status === "success" ? (
        <div className="workflow-run-start-success" role="status">
          <strong>
            {state.record.status === "approved_not_executed"
              ? "Approved, not executed"
              : "Simulation rejected"}
          </strong>
          <p>Durable decision evidence is selected in the inspector.</p>
        </div>
      ) : null}

      {isBlocked(state) ? (
        <div className="workflow-run-start-error" role="alert">
          <strong>Decision not recorded</strong>
          <p>{state.message}</p>
        </div>
      ) : null}
    </div>
  );
}

function isBlocked(
  state: WorkflowSimulationDecisionState,
): state is Extract<WorkflowSimulationDecisionState, { message: string }> {
  return "message" in state;
}
