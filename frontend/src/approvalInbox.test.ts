import { describe, expect, it } from "vitest";

import {
  buildApprovalDecisionRequest,
  defaultApprovalInboxFormState,
  safeApprovalInboxText,
} from "./approvalInbox";

describe("approvalInbox", () => {
  it("builds deterministic simulation approval decision requests", () => {
    expect(
      buildApprovalDecisionRequest(
        "approval-ticket-001",
        "approve",
        defaultApprovalInboxFormState,
      ),
    ).toEqual({
      decision_id: "approval-ticket-001-approve-decision",
      decided_at: "2026-07-08T13:46:00Z",
      actor: "human-operator-001",
      decision_reference: "approval-ticket-001-approve-manual-review",
      reason: "operator_reviewed_simulation_ticket",
    });
  });

  it("redacts unsafe approval inbox text", () => {
    expect(safeApprovalInboxText("human-operator-001")).toBe("human-operator-001");
    expect(safeApprovalInboxText("password=redacted")).toBe("[redacted unsafe approval text]");
    expect(safeApprovalInboxText("token: redacted")).toBe("[redacted unsafe approval text]");
  });
});
