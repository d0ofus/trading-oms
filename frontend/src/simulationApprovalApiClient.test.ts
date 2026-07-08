import { describe, expect, it } from "vitest";

import { defaultApprovalInboxFormState, buildApprovalDecisionRequest } from "./approvalInbox";
import { createSimulationApprovalApiClient } from "./simulationApprovalApiClient";

describe("simulationApprovalApiClient", () => {
  it("posts approve and reject decisions only to simulation approval endpoints", async () => {
    const calls: { input: string; init: RequestInit }[] = [];
    const client = createSimulationApprovalApiClient({
      fetchImpl: async (input, init) => {
        calls.push({ input: String(input), init });
        return new Response(
          JSON.stringify({
            schema_version: 1,
            decision_id: "approval-ticket-001-approve-decision",
            new_status: "approved",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      },
    });

    const approveRequest = buildApprovalDecisionRequest(
      "approval-ticket-001",
      "approve",
      defaultApprovalInboxFormState,
    );
    const rejectRequest = buildApprovalDecisionRequest(
      "approval-ticket-001",
      "reject",
      defaultApprovalInboxFormState,
    );

    await client.approveTicket("approval-ticket-001", approveRequest);
    await client.rejectTicket("approval-ticket-001", rejectRequest);

    expect(calls.map((call) => call.input)).toEqual([
      "/api/approval-tickets/approval-ticket-001/approve",
      "/api/approval-tickets/approval-ticket-001/reject",
    ]);
    expect(calls.every((call) => call.init.method === "POST")).toBe(true);
    expect(JSON.stringify(calls)).not.toContain("transmit");
    expect(JSON.stringify(calls)).not.toContain("broker_host");
  });
});
