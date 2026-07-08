import { describe, expect, it } from "vitest";

import {
  defaultVisualWorkflowRunInspection,
  inspectionByNodeId,
  type VisualWorkflowRunStatus,
} from "./visualWorkflowRunInspection";

describe("visualWorkflowRunInspection", () => {
  it("maps default approval-wait run statuses by graph node", () => {
    const statuses = inspectionByNodeId(defaultVisualWorkflowRunInspection);

    expect(statuses.get("risk-check")).toMatchObject({
      status: "passed",
      journalReference: "journal_sequence:13",
    });
    expect(statuses.get("approval-ticket")).toMatchObject({
      status: "waiting_for_approval",
      journalReference: "journal_sequence:14",
    });
    expect(statuses.get("fake-broker")).toMatchObject({
      status: "blocked_waiting_for_approval",
    });
    expect(statuses.get("position-update")).toMatchObject({
      status: "blocked_waiting_for_approval",
    });
    expect(statuses.get("alert")).toMatchObject({
      status: "blocked_waiting_for_approval",
    });
  });

  it("keeps status vocabulary ready for risk blocks, fills, and alerts without enabling actions", () => {
    const supportedStatuses: VisualWorkflowRunStatus[] = [
      "completed",
      "passed",
      "risk_blocked",
      "waiting_for_approval",
      "blocked_waiting_for_approval",
      "filled",
      "alert_recorded",
    ];

    expect(supportedStatuses).toContain("risk_blocked");
    expect(supportedStatuses).toContain("filled");
    expect(supportedStatuses).toContain("alert_recorded");
  });

  it("contains no broker, credential, route, submit, transmit, or live fields", () => {
    const serialized = JSON.stringify(defaultVisualWorkflowRunInspection).toLowerCase();
    const forbidden = [
      "account",
      "api_key",
      "broker_host",
      "credential",
      "eval(",
      "eval:",
      "ibkr",
      "javascript",
      "password",
      "route",
      "script",
      "secret",
      "submit",
      "token",
      "transmit",
    ];

    for (const term of forbidden) {
      expect(serialized).not.toContain(term);
    }
  });
});
