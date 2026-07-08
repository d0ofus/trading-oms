export type VisualWorkflowRunStatus =
  | "completed"
  | "passed"
  | "risk_blocked"
  | "waiting_for_approval"
  | "blocked_waiting_for_approval"
  | "filled"
  | "alert_recorded";

export type VisualWorkflowRunNodeInspection = {
  nodeId: string;
  nodeType: string;
  status: VisualWorkflowRunStatus;
  detail: string;
  journalReference: string;
};

export type VisualWorkflowRunInspection = {
  runId: string;
  workflowId: string;
  status: "waiting_for_approval" | "completed" | "blocked";
  nodes: VisualWorkflowRunNodeInspection[];
};

export const defaultVisualWorkflowRunInspection: VisualWorkflowRunInspection = {
  runId: "workflow-run-001",
  workflowId: "workflow-001",
  status: "waiting_for_approval",
  nodes: [
    {
      nodeId: "replay-source",
      nodeType: "replay_source",
      status: "completed",
      detail: "Deterministic local replay loaded",
      journalReference: "journal_sequence:10",
    },
    {
      nodeId: "bar-builder",
      nodeType: "bar_builder",
      status: "completed",
      detail: "Local 5-minute bars built",
      journalReference: "journal_sequence:11",
    },
    {
      nodeId: "strategy-trigger",
      nodeType: "strategy_trigger",
      status: "completed",
      detail: "Breakout trigger evaluated",
      journalReference: "journal_sequence:12",
    },
    {
      nodeId: "risk-check",
      nodeType: "risk_check",
      status: "passed",
      detail: "Risk checks passed",
      journalReference: "journal_sequence:13",
    },
    {
      nodeId: "approval-ticket",
      nodeType: "approval_ticket",
      status: "waiting_for_approval",
      detail: "Manual approval required",
      journalReference: "journal_sequence:14",
    },
    {
      nodeId: "fake-broker",
      nodeType: "fake_broker",
      status: "blocked_waiting_for_approval",
      detail: "Blocked until manual approval",
      journalReference: "journal_sequence:15",
    },
    {
      nodeId: "position-update",
      nodeType: "position_update",
      status: "blocked_waiting_for_approval",
      detail: "Position update blocked",
      journalReference: "journal_sequence:16",
    },
    {
      nodeId: "alert",
      nodeType: "alert",
      status: "blocked_waiting_for_approval",
      detail: "Alert node blocked",
      journalReference: "journal_sequence:17",
    },
    {
      nodeId: "audit-sink",
      nodeType: "audit_sink",
      status: "completed",
      detail: "Node statuses journaled",
      journalReference: "journal_sequence:18",
    },
  ],
};

export function inspectionByNodeId(inspection: VisualWorkflowRunInspection) {
  return new Map(inspection.nodes.map((node) => [node.nodeId, node]));
}
