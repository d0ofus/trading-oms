import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { SimulationRunComparisonPanel } from "./SimulationRunComparisonPanel";
import type {
  SelectedAuditBundleApiView,
  SimulationRunComparisonApiView,
} from "./simulationRunComparison";
import type { WorkflowRunInspectionItem } from "./workflowRunInspector";

describe("SimulationRunComparisonPanel", () => {
  it("renders loading, empty, and source-unavailable states without fabricated evidence", () => {
    const loading = renderedText(renderPanel({ historyStatus: "loading" }));
    const empty = renderedText(renderPanel({ items: [] }));
    const failed = renderedText(renderPanel({ historyStatus: "error", items: [] }));

    expect(loading).toContain("Loading comparison sources");
    expect(empty).toContain("No committed saved simulation runs are available for comparison");
    expect(failed).toContain("Saved-run comparison sources are unavailable");
    for (const text of [loading, empty, failed]) {
      expect(text).not.toContain("Comparison digest");
      expect(text).not.toContain("Prepare audit bundle");
    }
  });

  it("renders idle, active loading, failure, and partial-unavailable comparison states", () => {
    expect(renderedText(renderPanel())).toContain(
      "Choose two committed run slots, then compare",
    );
    expect(
      renderedText(renderPanel({ comparisonState: { status: "loading" } })),
    ).toContain("Comparing exact committed evidence");
    expect(
      renderedText(
        renderPanel({
          comparisonState: {
            status: "unavailable",
            errorMessage: "Simulation run comparison is unavailable",
          },
        }),
      ),
    ).toContain("Simulation run comparison is unavailable");
    expect(
      renderedText(
        renderPanel({
          comparisonState: {
            status: "partial_unavailable",
            errorMessage: "Comparison evidence is incomplete and unavailable",
          },
        }),
      ),
    ).toContain("Comparison evidence is incomplete and unavailable");
  });

  it("renders explicit identical and differing evidence summaries", () => {
    const identical = comparisonFixture("same_run");
    const differing = comparisonFixture("different_runs");
    const identicalText = renderedText(
      renderPanel({
        comparisonState: { status: "identical", comparison: identical },
      }),
    );
    const differingText = renderedText(
      renderPanel({
        comparisonState: { status: "differing", comparison: differing },
      }),
    );

    expect(identicalText).toContain("Identical committed run");
    expect(identicalText).toContain("11 unchanged");
    expect(differingText).toContain("Committed runs differ");
    expect(differingText).toContain("4 added");
    expect(differingText).toContain("7 changed");
    expect(differingText).toContain("Comparison digest");
    expect(differingText).toContain("Workflow");
    expect(differingText).toContain("Order intent");
    expect(differingText).toContain("Journal provenance");
    expect(differingText).toContain("journal_sequence:20");
    expect(differingText).toContain("Local only");
    expect(differingText).toContain("Externally unverified");
  });

  it("renders exact audit target and journal scope controls only after comparison", () => {
    const html = renderPanel({
      comparisonState: {
        status: "differing",
        comparison: comparisonFixture("different_runs"),
      },
    });
    const text = renderedText(html);

    expect(html).toContain('aria-label="Audit bundle run target"');
    expect(html).toContain('aria-label="Audit journal scope"');
    expect(html).toContain('aria-label="Audit journal event"');
    expect(text).toContain("Complete committed manifest");
    expect(text).toContain("One exact manifest event");
    expect(text).toContain("Prepare audit bundle");
    expect(text).toContain("Manifest SHA-256");
  });

  it("renders selected bundle success and keeps download local", () => {
    const html = renderPanel({
      comparisonState: {
        status: "differing",
        comparison: comparisonFixture("different_runs"),
      },
      auditState: {
        status: "loaded",
        bundle: auditBundleFixture(),
        stableJson: "{\"bundle_type\":\"audit_review_bundle\"}",
      },
    });
    const text = renderedText(html);

    expect(text).toContain("Selected audit bundle ready");
    expect(text).toContain("run-b");
    expect(text).toContain("Single journal event");
    expect(text).toContain("journal_sequence:20");
    expect(text).toContain("Selection SHA-256");
    expect(text).toContain("Download JSON");
    expect(html).toContain('download="audit-run-b-single-journal-event.json"');
    expect(html).toContain("data:application/json");
  });

  it("contains no approval, execution, broker, credential, or live action controls", () => {
    const text = renderedText(
      renderPanel({
        comparisonState: {
          status: "differing",
          comparison: comparisonFixture("different_runs"),
        },
      }),
    ).toLowerCase();

    for (const forbidden of [
      "approve run",
      "reject run",
      "execute run",
      "retry run",
      "repair",
      "connect broker",
      "account id",
      "credential",
      "live mode",
      "deploy",
      "rollout",
    ]) {
      expect(text).not.toContain(forbidden);
    }
  });
});

function renderPanel(
  overrides: Partial<Parameters<typeof SimulationRunComparisonPanel>[0]> = {},
) {
  return renderToStaticMarkup(
    <SimulationRunComparisonPanel
      auditJournalReference="journal_sequence:20"
      auditScope="single_journal_event"
      auditState={{ status: "idle" }}
      auditTarget="right"
      comparisonState={{ status: "idle" }}
      historyStatus="loaded"
      items={items()}
      leftKey="workflow-a::run-a"
      onAuditJournalReferenceChange={vi.fn()}
      onAuditScopeChange={vi.fn()}
      onAuditTargetChange={vi.fn()}
      onCompare={vi.fn()}
      onLeftKeyChange={vi.fn()}
      onPrepareAuditBundle={vi.fn()}
      onRightKeyChange={vi.fn()}
      rightKey="workflow-b::run-b"
      {...overrides}
    />,
  );
}

function renderedText(html: string) {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

function items(): WorkflowRunInspectionItem[] {
  const first: WorkflowRunInspectionItem = {
    key: "workflow-a::run-a",
    workflowId: "workflow-a",
    workflowName: "Workflow A",
    workflowVersion: 1,
    run: {
      schema_version: 1,
      workflow_id: "workflow-a",
      expected_workflow_version: 1,
      run_id: "run-a",
      status: "waiting_for_approval",
      created_at: "2026-07-08T13:45:00Z",
      updated_at: "2026-07-08T13:45:10Z",
      approval_ticket_id: "run-a-approval-ticket",
      approval_decision: null,
      execution: null,
      simulation_run: {
        schema_version: 1,
        run_id: "run-a",
        status: "completed",
        created_at: "2026-07-08T13:45:00Z",
        updated_at: "2026-07-08T13:45:10Z",
        replay_input_reference: "fixtures/replay/aapl-session.jsonl",
        journal_references: ["journal_sequence:10"],
      },
      node_statuses: [],
      journal_references: ["journal_sequence:10"],
    },
  };
  return [
    first,
    {
      ...first,
      key: "workflow-b::run-b",
      workflowId: "workflow-b",
      workflowName: "Workflow B",
      run: {
        ...first.run,
        workflow_id: "workflow-b",
        run_id: "run-b",
        approval_ticket_id: "run-b-approval-ticket",
        journal_references: ["journal_sequence:20"],
      },
    },
  ];
}

function comparisonFixture(
  selectionState: "same_run" | "different_runs",
): SimulationRunComparisonApiView {
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
  const left = snapshot("workflow-a", "run-a", "a");
  const right =
    selectionState === "same_run" ? left : snapshot("workflow-b", "run-b", "b");
  return {
    schema_version: 1,
    selection_state: selectionState,
    comparison_sha256: "c".repeat(64),
    summary:
      selectionState === "same_run"
        ? { added: 0, removed: 0, changed: 0, unchanged: 11 }
        : { added: 4, removed: 0, changed: 7, unchanged: 0 },
    left,
    right,
    sections: sectionNames.map((name, index) => ({
      name,
      status: selectionState === "same_run" ? "unchanged" : index < 4 ? "added" : "changed",
      left_value: null,
      right_value: selectionState === "same_run" ? null : name,
      differences:
        selectionState === "same_run"
          ? []
          : [
              {
                path: "$",
                status: index < 4 ? "added" : "changed",
                left_value: null,
                right_value: name,
              },
            ],
    })),
  };
}

function snapshot(workflowId: string, runId: string, character: string) {
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
    signal: { strategy_id: "opening-breakout" },
    order_intent: { proposal_id: `${runId}-intent` },
    risk_decision: { request_id: `${runId}-risk` },
    approval_ticket: { ticket_id: `${runId}-approval-ticket` },
    approval_decision: null,
    execution: null,
    protection: null,
    alerts: [],
    journal_provenance: {
      manifest_sha256: character.repeat(64),
      journal_references: ["journal_sequence:10", "journal_sequence:20"],
      records: [10, 20].map((sequence) => ({
        sequence,
        journal_reference: `journal_sequence:${sequence}`,
        event_type: "workflow_simulation.node_status",
        timestamp: "2026-07-08T13:45:10Z",
        record_sha256: character.repeat(64),
      })),
    },
    provenance: {
      classifications: ["simulated", "local_only", "externally_unverified"],
      broker_derived: false as const,
      externally_verified: false as const,
    },
  };
}

function auditBundleFixture(): SelectedAuditBundleApiView {
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
        broker_derived: false,
        externally_verified: false,
        selection_sha256: "e".repeat(64),
      },
    },
    operations_read_model: { audit_events: [{ sequence: 20 }] },
    workflow_definitions: [],
    workflow_simulation_runs: [{ workflow_id: "workflow-b", run_id: "run-b" }],
    journal_records: [
      {
        sequence: 20,
        event_type: "approval.ticket.created",
        timestamp: "2026-07-08T13:45:10Z",
        payload: { run_id: "run-b" },
      },
    ],
  };
}
