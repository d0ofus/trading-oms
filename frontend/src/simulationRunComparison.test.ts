import { describe, expect, it, vi } from "vitest";

import {
  createSimulationRunComparisonClient,
  loadSelectedAuditBundle,
  loadSimulationRunComparison,
  type AuditBundleSelectionRequest,
  type SimulationRunComparisonApiView,
  type SimulationRunComparisonClient,
} from "./simulationRunComparison";

const left = { workflowId: "workflow-a", runId: "run-a" };
const right = { workflowId: "workflow-b", runId: "run-b" };

describe("simulation run comparison client", () => {
  it("uses GET-only exact selector and audit scope requests", async () => {
    const comparison = comparisonFixture();
    const bundle = auditBundleFixture();
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(comparison))
      .mockResolvedValueOnce(jsonResponse(bundle));
    const client = createSimulationRunComparisonClient({ fetchImpl });
    const compareRequest = { left, right };
    const auditRequest = auditSelectionRequest();

    await client.compare(compareRequest);
    await client.prepareAuditBundle(auditRequest);

    expect(fetchImpl).toHaveBeenNthCalledWith(
      1,
      "/api/simulation-run-comparison?left_workflow_id=workflow-a&left_run_id=run-a&right_workflow_id=workflow-b&right_run_id=run-b",
      expect.objectContaining({ method: "GET", body: undefined }),
    );
    expect(fetchImpl).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining(
        "/api/audit-export-bundle?workflow_id=workflow-b&run_id=run-b",
      ),
      expect.objectContaining({ method: "GET", body: undefined }),
    );
    expect(fetchImpl.mock.calls[1][0]).toContain(
      "expected_manifest_sha256=" + "b".repeat(64),
    );
    expect(fetchImpl.mock.calls[1][0]).toContain(
      "journal_scope=single_journal_event",
    );
    expect(fetchImpl.mock.calls[1][0]).toContain("journal_sequence=20");
  });

  it("returns explicit identical and differing states", async () => {
    const differing = await loadSimulationRunComparison(
      clientWithComparison(comparisonFixture()),
      { left, right },
    );
    const identicalFixture = comparisonFixture({
      selection_state: "same_run",
      right: snapshotFixture("workflow-a", "run-a", "a"),
      sections: sectionFixtures("unchanged"),
      summary: { added: 0, removed: 0, changed: 0, unchanged: 11 },
    });
    const identical = await loadSimulationRunComparison(
      clientWithComparison(identicalFixture),
      { left, right: left },
    );

    expect(differing.status).toBe("differing");
    expect(identical.status).toBe("identical");
  });

  it("fails closed on partial or mismatched comparison evidence", async () => {
    const partial = comparisonFixture({
      sections: sectionFixtures("differing").slice(0, 10),
    });
    const wrongSelector = comparisonFixture({
      right: snapshotFixture("workflow-other", "run-b", "b"),
    });

    expect(
      await loadSimulationRunComparison(clientWithComparison(partial), { left, right }),
    ).toEqual({
      status: "partial_unavailable",
      errorMessage: "Comparison evidence is incomplete and unavailable",
    });
    expect(
      await loadSimulationRunComparison(clientWithComparison(wrongSelector), {
        left,
        right,
      }),
    ).toEqual({
      status: "partial_unavailable",
      errorMessage: "Comparison evidence is incomplete and unavailable",
    });
  });

  it("rejects duplicate references, unsafe provenance, and inconsistent summaries", async () => {
    const duplicateReference = comparisonFixture();
    duplicateReference.right.journal_provenance.records[1] = {
      ...duplicateReference.right.journal_provenance.records[0],
    };
    const unsafe = comparisonFixture();
    unsafe.right.provenance.broker_derived = true as false;
    const badSummary = comparisonFixture({
      summary: { added: 0, removed: 0, changed: 0, unchanged: 11 },
    });

    for (const payload of [duplicateReference, unsafe, badSummary]) {
      const result = await loadSimulationRunComparison(
        clientWithComparison(payload),
        { left, right },
      );
      expect(result.status).toBe("partial_unavailable");
    }
  });

  it("returns unavailable for transport or HTTP failure without rendering details", async () => {
    const client: SimulationRunComparisonClient = {
      compare: vi.fn().mockRejectedValue(new Error("private sqlite path")),
      prepareAuditBundle: vi.fn(),
    };

    expect(await loadSimulationRunComparison(client, { left, right })).toEqual({
      status: "unavailable",
      errorMessage: "Simulation run comparison is unavailable",
    });
  });

  it("strictly validates selected audit bundle binding and safety posture", async () => {
    const request = auditSelectionRequest();
    const loaded = await loadSelectedAuditBundle(
      clientWithBundle(auditBundleFixture()),
      request,
    );
    const stale = auditBundleFixture();
    stale.manifest.selection.source_manifest_sha256 = "c".repeat(64);
    const partial = auditBundleFixture();
    partial.manifest.selection.selected_journal_references = [
      "journal_sequence:999",
    ];
    const unsafe = auditBundleFixture();
    unsafe.manifest.selection.externally_verified = true as false;

    expect(loaded.status).toBe("loaded");
    for (const payload of [stale, partial, unsafe]) {
      const result = await loadSelectedAuditBundle(clientWithBundle(payload), request);
      expect(result).toEqual({
        status: "partial_unavailable",
        errorMessage: "Selected audit bundle evidence is incomplete and unavailable",
      });
    }
  });

  it("never accepts arbitrary scope or a sequence outside the selected manifest", async () => {
    const client = clientWithBundle(auditBundleFixture());
    const invalidScope = {
      ...auditSelectionRequest(),
      journalScope: "arbitrary_range",
    } as unknown as AuditBundleSelectionRequest;
    const invalidSequence = {
      ...auditSelectionRequest(),
      journalSequence: 999,
    };

    expect(await loadSelectedAuditBundle(client, invalidScope)).toEqual({
      status: "partial_unavailable",
      errorMessage: "Selected audit bundle evidence is incomplete and unavailable",
    });
    expect(await loadSelectedAuditBundle(client, invalidSequence)).toEqual({
      status: "partial_unavailable",
      errorMessage: "Selected audit bundle evidence is incomplete and unavailable",
    });
  });
});

function clientWithComparison(
  payload: SimulationRunComparisonApiView,
): SimulationRunComparisonClient {
  return createSimulationRunComparisonClient({
    fetchImpl: vi.fn().mockResolvedValue(jsonResponse(payload)),
  });
}

function clientWithBundle(
  payload: ReturnType<typeof auditBundleFixture>,
): SimulationRunComparisonClient {
  return createSimulationRunComparisonClient({
    fetchImpl: vi.fn().mockResolvedValue(jsonResponse(payload)),
  });
}

function jsonResponse(payload: unknown) {
  return {
    ok: true,
    status: 200,
    json: vi.fn().mockResolvedValue(payload),
  } as unknown as Response;
}

function comparisonFixture(
  overrides: Partial<SimulationRunComparisonApiView> = {},
): SimulationRunComparisonApiView {
  return {
    schema_version: 1,
    selection_state: "different_runs",
    comparison_sha256: "c".repeat(64),
    summary: { added: 4, removed: 0, changed: 7, unchanged: 0 },
    left: snapshotFixture("workflow-a", "run-a", "a"),
    right: snapshotFixture("workflow-b", "run-b", "b"),
    sections: sectionFixtures("differing"),
    ...overrides,
  };
}

function snapshotFixture(workflowId: string, runId: string, digestCharacter: string) {
  const records = [10, 20].map((sequence) => ({
    sequence,
    journal_reference: `journal_sequence:${sequence}`,
    event_type:
      sequence === 10 ? "strategy.signal.generated" : "approval.ticket.created",
    timestamp: "2026-07-08T13:45:10Z",
    record_sha256: digestCharacter.repeat(64),
  }));
  return {
    schema_version: 1 as const,
    selector: { workflow_id: workflowId, run_id: runId },
    workflow: { workflow_id: workflowId, expected_workflow_version: 1 },
    run: {
      run_id: runId,
      status: "waiting_for_approval",
      created_at: "2026-07-08T13:45:00Z",
      updated_at: "2026-07-08T13:45:10Z",
      replay_input_reference: "fixtures/replay/aapl-session.jsonl",
      simulation_status: "completed",
    },
    signal: { strategy_id: "opening-breakout", signal: "long_entry_candidate" },
    order_intent: { proposal_id: `${runId}-intent`, symbol: "AAPL" },
    risk_decision: { request_id: `${runId}-risk`, result: "passed" },
    approval_ticket: {
      ticket_id: `${runId}-approval-ticket`,
      status: "pending",
    },
    approval_decision: null,
    execution: null,
    protection: null,
    alerts: [],
    journal_provenance: {
      manifest_sha256: digestCharacter.repeat(64),
      journal_references: records.map((record) => record.journal_reference),
      records,
    },
    provenance: {
      classifications: ["simulated", "local_only", "externally_unverified"],
      broker_derived: false as const,
      externally_verified: false as const,
    },
  };
}

function sectionFixtures(
  status: "differing" | "unchanged",
): SimulationRunComparisonApiView["sections"] {
  const sectionNames = [
    "workflow",
    "run",
    "signal",
    "order_intent",
    "risk_decision",
    "approval_ticket",
    "approval_decision",
    "execution",
    "protection",
    "alerts",
    "journal_provenance",
  ] as const;
  return sectionNames.map((name, index) => {
    const sectionStatus =
      status === "unchanged" ? "unchanged" : index < 4 ? "added" : "changed";
    return {
      name,
      status: sectionStatus,
      left_value: null,
      right_value: status === "differing" ? name : null,
      differences:
        status === "differing"
          ? [
              {
                path: "$",
                status: index < 4 ? "added" : "changed",
                left_value: null,
                right_value: name,
              },
            ]
          : [],
    };
  });
}

function auditSelectionRequest(): AuditBundleSelectionRequest {
  return {
    selector: right,
    expectedManifestSha256: "b".repeat(64),
    journalScope: "single_journal_event",
    journalSequence: 20,
  };
}

function auditBundleFixture() {
  const record = {
    sequence: 20,
    event_type: "approval.ticket.created",
    timestamp: "2026-07-08T13:45:10Z",
    payload: { schema_version: 1, run_id: "run-b" },
  };
  return {
    schema_version: 1,
    bundle_type: "audit_review_bundle",
    manifest: {
      schema_version: 1,
      export_id: "audit-export-001",
      generated_at: "2026-07-08T13:46:00Z",
      review_reference: "saved-simulation-run-review",
      mode: "local_review_only",
      external_delivery: "none",
      live_trading_enabled: false,
      live_trading_authorized: false,
      workflow_ids: ["workflow-b"],
      run_ids: ["run-b"],
      journal_references: ["journal_sequence:20"],
      counts: {
        workflow_definitions: 0,
        workflow_simulation_runs: 1,
        journal_records: 1,
        audit_events: 1,
      },
      safety_scan: { result: "passed", finding_count: 0 },
      selection: {
        schema_version: 1,
        workflow_id: "workflow-b",
        workflow_version: 1,
        run_id: "run-b",
        run_status: "waiting_for_approval",
        source_manifest_sha256: "b".repeat(64),
        source_manifest_journal_references: [
          "journal_sequence:10",
          "journal_sequence:20",
        ],
        journal_scope: "single_journal_event",
        selected_journal_references: ["journal_sequence:20"],
        selected_record_sha256: ["d".repeat(64)],
        classifications: ["simulated", "local_only", "externally_unverified"],
        broker_derived: false as const,
        externally_verified: false as const,
        selection_sha256: "e".repeat(64),
      },
    },
    operations_read_model: {
      schema_version: 1,
      audit_events: [{ sequence: 20 }],
    },
    workflow_definitions: [],
    workflow_simulation_runs: [
      {
        schema_version: 1,
        workflow_id: "workflow-b",
        expected_workflow_version: 1,
        run_id: "run-b",
        status: "waiting_for_approval",
      },
    ],
    journal_records: [record],
  };
}
