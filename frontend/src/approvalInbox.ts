export type ApprovalInboxAction = "approve" | "reject";

export type ApprovalInboxFormState = {
  actor: string;
  reason: string;
  decidedAt: string;
};

export type ApprovalDecisionRequest = {
  decision_id: string;
  decided_at: string;
  actor: string;
  decision_reference: string;
  reason: string;
};

export const defaultApprovalInboxFormState: ApprovalInboxFormState = {
  actor: "human-operator-001",
  reason: "operator_reviewed_simulation_ticket",
  decidedAt: "2026-07-08T13:46:00Z",
};

const unsafeApprovalTextFragments = [
  "api_key",
  "authorization:",
  "bearer ",
  "credential",
  "password:",
  "password=",
  "private_key",
  "secret:",
  "secret=",
  "token:",
  "token=",
];

export function buildApprovalDecisionRequest(
  ticketId: string,
  action: ApprovalInboxAction,
  formState: ApprovalInboxFormState,
): ApprovalDecisionRequest {
  const safeTicketId = ticketId.trim();
  return {
    decision_id: `${safeTicketId}-${action}-decision`,
    decided_at: formState.decidedAt,
    actor: formState.actor.trim(),
    decision_reference: `${safeTicketId}-${action}-manual-review`,
    reason: formState.reason.trim(),
  };
}

export function safeApprovalInboxText(value: string | null | undefined) {
  if (!value) {
    return "not recorded";
  }
  const normalized = value.toLowerCase().replaceAll("-", "_");
  if (unsafeApprovalTextFragments.some((fragment) => normalized.includes(fragment))) {
    return "[redacted unsafe approval text]";
  }
  return value;
}
