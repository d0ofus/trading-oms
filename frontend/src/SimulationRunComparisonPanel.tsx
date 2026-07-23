import {
  Download,
  FileJson,
  GitCompareArrows,
  LoaderCircle,
} from "lucide-react";

import type {
  AuditJournalScope,
  SimulationAuditBundleState,
  SimulationRunComparisonApiView,
  SimulationRunComparisonSectionApiView,
  SimulationRunComparisonState,
} from "./simulationRunComparison";
import type { WorkflowRunInspectionItem } from "./workflowRunInspector";

type Props = {
  auditJournalReference: string;
  auditScope: AuditJournalScope;
  auditState: SimulationAuditBundleState;
  auditTarget: "left" | "right";
  comparisonState: SimulationRunComparisonState;
  historyStatus: "loading" | "loaded" | "error";
  items: WorkflowRunInspectionItem[];
  leftKey: string;
  rightKey: string;
  onAuditJournalReferenceChange: (reference: string) => void;
  onAuditScopeChange: (scope: AuditJournalScope) => void;
  onAuditTargetChange: (target: "left" | "right") => void;
  onCompare: () => void;
  onLeftKeyChange: (key: string) => void;
  onPrepareAuditBundle: () => void;
  onRightKeyChange: (key: string) => void;
};

export function SimulationRunComparisonPanel({
  auditJournalReference,
  auditScope,
  auditState,
  auditTarget,
  comparisonState,
  historyStatus,
  items,
  leftKey,
  rightKey,
  onAuditJournalReferenceChange,
  onAuditScopeChange,
  onAuditTargetChange,
  onCompare,
  onLeftKeyChange,
  onPrepareAuditBundle,
  onRightKeyChange,
}: Props) {
  if (historyStatus === "loading") {
    return (
      <p className="empty-state" aria-live="polite">
        <LoaderCircle
          aria-hidden="true"
          className="status-spinner"
          size={16}
        />
        Loading comparison sources
      </p>
    );
  }
  if (historyStatus === "error") {
    return (
      <p className="empty-state state-note" role="alert">
        Saved-run comparison sources are unavailable
      </p>
    );
  }
  if (items.length === 0) {
    return (
      <p className="empty-state">
        No committed saved simulation runs are available for comparison
      </p>
    );
  }

  const comparison =
    comparisonState.status === "identical" ||
    comparisonState.status === "differing"
      ? comparisonState.comparison
      : null;
  const auditSnapshot = comparison?.[auditTarget] ?? null;
  const auditReferences =
    auditSnapshot?.journal_provenance.journal_references ?? [];

  return (
    <div
      className="run-comparison-panel"
      aria-label="Saved simulation run comparison"
    >
      <div className="run-comparison-selectors">
        <RunSelector
          ariaLabel="Left comparison run"
          items={items}
          onChange={onLeftKeyChange}
          value={leftKey}
        />
        <RunSelector
          ariaLabel="Right comparison run"
          items={items}
          onChange={onRightKeyChange}
          value={rightKey}
        />
        <button
          disabled={
            !leftKey ||
            !rightKey ||
            comparisonState.status === "loading"
          }
          onClick={onCompare}
          type="button"
        >
          <GitCompareArrows aria-hidden="true" size={16} />
          Compare committed evidence
        </button>
      </div>

      {comparisonState.status === "idle" ? (
        <p className="empty-state">
          Choose two committed run slots, then compare
        </p>
      ) : null}
      {comparisonState.status === "loading" ? (
        <p className="empty-state" aria-live="polite">
          <LoaderCircle
            aria-hidden="true"
            className="status-spinner"
            size={16}
          />
          Comparing exact committed evidence
        </p>
      ) : null}
      {comparisonState.status === "unavailable" ||
      comparisonState.status === "partial_unavailable" ? (
        <p className="empty-state state-note" role="alert">
          {comparisonState.errorMessage}
        </p>
      ) : null}

      {comparison ? (
        <>
          <ComparisonEvidence comparison={comparison} />
          <div className="audit-selection-band">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Exact audit selection</p>
                <h3>Selected local review bundle</h3>
              </div>
              <span className="simulation-only-label">LOCAL ONLY</span>
            </div>
            <div className="audit-selection-controls">
              <label>
                <span>Run target</span>
                <select
                  aria-label="Audit bundle run target"
                  onChange={(event) =>
                    onAuditTargetChange(
                      event.target.value === "left" ? "left" : "right",
                    )
                  }
                  value={auditTarget}
                >
                  <option value="left">
                    Left | {comparison.left.selector.run_id}
                  </option>
                  <option value="right">
                    Right | {comparison.right.selector.run_id}
                  </option>
                </select>
              </label>
              <label>
                <span>Journal scope</span>
                <select
                  aria-label="Audit journal scope"
                  onChange={(event) =>
                    onAuditScopeChange(
                      event.target.value === "single_journal_event"
                        ? "single_journal_event"
                        : "complete_run_manifest",
                    )
                  }
                  value={auditScope}
                >
                  <option value="complete_run_manifest">
                    Complete committed manifest
                  </option>
                  <option value="single_journal_event">
                    One exact manifest event
                  </option>
                </select>
              </label>
              {auditScope === "single_journal_event" ? (
                <label>
                  <span>Journal event</span>
                  <select
                    aria-label="Audit journal event"
                    onChange={(event) =>
                      onAuditJournalReferenceChange(event.target.value)
                    }
                    value={auditJournalReference}
                  >
                    {auditReferences.map((reference) => (
                      <option key={reference} value={reference}>
                        {reference}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                disabled={
                  !auditSnapshot ||
                  auditState.status === "loading" ||
                  (auditScope === "single_journal_event" &&
                    !auditReferences.includes(auditJournalReference))
                }
                onClick={onPrepareAuditBundle}
                type="button"
              >
                <FileJson aria-hidden="true" size={16} />
                Prepare audit bundle
              </button>
            </div>
            {auditSnapshot ? (
              <dl className="audit-selection-facts">
                <Fact label="Workflow" value={auditSnapshot.selector.workflow_id} />
                <Fact label="Run" value={auditSnapshot.selector.run_id} />
                <Fact
                  label="Manifest SHA-256"
                  value={auditSnapshot.journal_provenance.manifest_sha256}
                />
                <Fact
                  label="Journal evidence"
                  value={`${auditReferences.length} committed reference${
                    auditReferences.length === 1 ? "" : "s"
                  }`}
                />
              </dl>
            ) : null}
            <AuditBundleFeedback state={auditState} />
          </div>
        </>
      ) : null}
    </div>
  );
}

function RunSelector({
  ariaLabel,
  items,
  onChange,
  value,
}: {
  ariaLabel: string;
  items: WorkflowRunInspectionItem[];
  onChange: (key: string) => void;
  value: string;
}) {
  return (
    <label>
      <span>{ariaLabel.startsWith("Left") ? "Left run" : "Right run"}</span>
      <select
        aria-label={ariaLabel}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {items.map((item) => (
          <option key={item.key} value={item.key}>
            {item.run.run_id} | {item.workflowName} | v{item.workflowVersion}
          </option>
        ))}
      </select>
    </label>
  );
}

function ComparisonEvidence({
  comparison,
}: {
  comparison: SimulationRunComparisonApiView;
}) {
  const identical = comparison.selection_state === "same_run";
  return (
    <div className="comparison-evidence" role="status">
      <div className="comparison-summary">
        <div>
          <p className="eyebrow">Deterministic comparison</p>
          <h3>
            {identical ? "Identical committed run" : "Committed runs differ"}
          </h3>
        </div>
        <div className="comparison-counts" aria-label="Comparison summary">
          {(["added", "removed", "changed", "unchanged"] as const).map(
            (status) => (
              <span className={`comparison-count comparison-${status}`} key={status}>
                {comparison.summary[status]} {status}
              </span>
            ),
          )}
        </div>
      </div>
      <dl className="comparison-selector-facts">
        <Fact
          label="Left"
          value={`${comparison.left.selector.workflow_id} | ${comparison.left.selector.run_id}`}
        />
        <Fact
          label="Right"
          value={`${comparison.right.selector.workflow_id} | ${comparison.right.selector.run_id}`}
        />
        <Fact label="Comparison digest" value={comparison.comparison_sha256} />
        <Fact
          label="Provenance"
          value={comparison.right.provenance.classifications
            .map(formatLabel)
            .join(" | ")}
        />
      </dl>
      <div className="comparison-table" role="table" aria-label="Run evidence differences">
        <div className="comparison-table-heading" role="row">
          <span role="columnheader">Evidence</span>
          <span role="columnheader">Status</span>
          <span role="columnheader">Differences</span>
        </div>
        {comparison.sections.map((section) => (
          <ComparisonRow key={section.name} section={section} />
        ))}
      </div>
      <div className="comparison-journal-provenance">
        <h4>Journal provenance</h4>
        <div>
          <JournalManifest
            label="Left manifest"
            manifestSha256={
              comparison.left.journal_provenance.manifest_sha256
            }
            references={
              comparison.left.journal_provenance.journal_references
            }
          />
          <JournalManifest
            label="Right manifest"
            manifestSha256={
              comparison.right.journal_provenance.manifest_sha256
            }
            references={
              comparison.right.journal_provenance.journal_references
            }
          />
        </div>
      </div>
    </div>
  );
}

function ComparisonRow({
  section,
}: {
  section: SimulationRunComparisonSectionApiView;
}) {
  return (
    <div className="comparison-table-row" role="row">
      <strong role="cell">{formatLabel(section.name)}</strong>
      <span
        className={`comparison-status comparison-${section.status}`}
        role="cell"
      >
        {formatLabel(section.status)}
      </span>
      <span role="cell">
        {section.differences.length === 0
          ? "No differences"
          : `${section.differences.length} field difference${
              section.differences.length === 1 ? "" : "s"
            }`}
      </span>
    </div>
  );
}

function JournalManifest({
  label,
  manifestSha256,
  references,
}: {
  label: string;
  manifestSha256: string;
  references: string[];
}) {
  return (
    <div>
      <strong>{label}</strong>
      <code>{manifestSha256}</code>
      <p>{references.join(" | ")}</p>
    </div>
  );
}

function AuditBundleFeedback({ state }: { state: SimulationAuditBundleState }) {
  if (state.status === "idle") {
    return null;
  }
  if (state.status === "loading") {
    return (
      <p aria-live="polite">
        <LoaderCircle
          aria-hidden="true"
          className="status-spinner"
          size={16}
        />
        Preparing exact local audit bundle
      </p>
    );
  }
  if (
    state.status === "unavailable" ||
    state.status === "partial_unavailable"
  ) {
    return (
      <p className="state-note" role="alert">
        {state.errorMessage}
      </p>
    );
  }
  if (state.status !== "loaded") {
    return null;
  }
  const selection = state.bundle.manifest.selection;
  const filename = `audit-${selection.run_id}-${selection.journal_scope.replaceAll(
    "_",
    "-",
  )}.json`;
  const href = `data:application/json;charset=utf-8,${encodeURIComponent(
    state.stableJson,
  )}`;
  return (
    <div className="audit-bundle-ready" role="status">
      <div>
        <strong>Selected audit bundle ready</strong>
        <p>
          {selection.run_id} | {formatLabel(selection.journal_scope)}
        </p>
      </div>
      <dl className="audit-selection-facts">
        <Fact
          label="Journal references"
          value={selection.selected_journal_references.join(" | ")}
        />
        <Fact label="Selection SHA-256" value={selection.selection_sha256} />
      </dl>
      <a download={filename} href={href}>
        <Download aria-hidden="true" size={16} />
        Download JSON
      </a>
    </div>
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

function formatLabel(value: string) {
  const formatted = value.replaceAll("_", " ");
  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
}
