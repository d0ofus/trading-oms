export const SIMULATION_RUN_COMPARISON_ENDPOINT =
  "/api/simulation-run-comparison";
export const SELECTED_AUDIT_BUNDLE_ENDPOINT = "/api/audit-export-bundle";

export const SIMULATION_RUN_COMPARISON_SECTIONS = [
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

export type SimulationRunComparisonSectionName =
  (typeof SIMULATION_RUN_COMPARISON_SECTIONS)[number];
export type SimulationRunComparisonStatus =
  | "added"
  | "removed"
  | "changed"
  | "unchanged";
export type AuditJournalScope =
  | "complete_run_manifest"
  | "single_journal_event";

export type SimulationRunSelector = {
  workflowId: string;
  runId: string;
};

type ApiSimulationRunSelector = {
  workflow_id: string;
  run_id: string;
};

export type SimulationRunComparisonRequest = {
  left: SimulationRunSelector;
  right: SimulationRunSelector;
};

export type SimulationRunJournalEvidenceApiView = {
  sequence: number;
  journal_reference: string;
  event_type: string;
  timestamp: string;
  record_sha256: string;
};

export type SimulationRunEvidenceSnapshotApiView = {
  schema_version: 1;
  selector: ApiSimulationRunSelector;
  workflow: Record<string, unknown>;
  run: Record<string, unknown>;
  signal: Record<string, unknown>;
  order_intent: Record<string, unknown>;
  risk_decision: Record<string, unknown>;
  approval_ticket: Record<string, unknown>;
  approval_decision: Record<string, unknown> | null;
  execution: Record<string, unknown> | null;
  protection: Record<string, unknown> | null;
  alerts: Array<Record<string, unknown>>;
  journal_provenance: {
    manifest_sha256: string;
    journal_references: string[];
    records: SimulationRunJournalEvidenceApiView[];
  };
  provenance: {
    classifications: string[];
    broker_derived: false;
    externally_verified: false;
  };
};

export type SimulationRunComparisonFieldApiView = {
  path: string;
  status: SimulationRunComparisonStatus;
  left_value: unknown;
  right_value: unknown;
};

export type SimulationRunComparisonSectionApiView = {
  name: SimulationRunComparisonSectionName;
  status: SimulationRunComparisonStatus;
  left_value: unknown;
  right_value: unknown;
  differences: SimulationRunComparisonFieldApiView[];
};

export type SimulationRunComparisonApiView = {
  schema_version: 1;
  selection_state: "same_run" | "different_runs";
  comparison_sha256: string;
  summary: Record<SimulationRunComparisonStatus, number>;
  left: SimulationRunEvidenceSnapshotApiView;
  right: SimulationRunEvidenceSnapshotApiView;
  sections: SimulationRunComparisonSectionApiView[];
};

export type AuditBundleSelectionRequest = {
  selector: SimulationRunSelector;
  expectedManifestSha256: string;
  journalScope: AuditJournalScope;
  journalSequence?: number;
};

export type SelectedAuditBundleSelectionApiView = {
  schema_version: 1;
  workflow_id: string;
  workflow_version: number;
  run_id: string;
  run_status: string;
  source_manifest_sha256: string;
  source_manifest_journal_references: string[];
  journal_scope: AuditJournalScope;
  selected_journal_references: string[];
  selected_record_sha256: string[];
  classifications: string[];
  broker_derived: false;
  externally_verified: false;
  selection_sha256: string;
};

export type SelectedAuditBundleApiView = {
  schema_version: 1;
  bundle_type: "audit_review_bundle";
  manifest: {
    schema_version: 1;
    export_id: string;
    generated_at: string;
    review_reference: string;
    mode: "local_review_only";
    external_delivery: "none";
    live_trading_enabled: false;
    live_trading_authorized: false;
    workflow_ids: string[];
    run_ids: string[];
    journal_references: string[];
    counts: {
      workflow_definitions: number;
      workflow_simulation_runs: number;
      journal_records: number;
      audit_events: number;
    };
    safety_scan: {
      result: "passed";
      finding_count: 0;
    };
    selection: SelectedAuditBundleSelectionApiView;
  };
  operations_read_model: {
    audit_events: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
  workflow_definitions: Array<Record<string, unknown>>;
  workflow_simulation_runs: Array<Record<string, unknown>>;
  journal_records: Array<Record<string, unknown>>;
};

export type SimulationRunComparisonState =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "identical";
      comparison: SimulationRunComparisonApiView;
    }
  | {
      status: "differing";
      comparison: SimulationRunComparisonApiView;
    }
  | {
      status: "partial_unavailable" | "unavailable";
      errorMessage: string;
    };

export type SimulationAuditBundleState =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "loaded";
      bundle: SelectedAuditBundleApiView;
      stableJson: string;
    }
  | {
      status: "partial_unavailable" | "unavailable";
      errorMessage: string;
    };

type ComparisonFetch = (
  input: string,
  init: RequestInit,
) => Promise<Response>;

export type SimulationRunComparisonClient = {
  compare: (
    request: SimulationRunComparisonRequest,
  ) => Promise<SimulationRunComparisonApiView>;
  prepareAuditBundle: (
    request: AuditBundleSelectionRequest,
  ) => Promise<SelectedAuditBundleApiView>;
};

type SimulationRunComparisonClientOptions = {
  baseUrl?: string;
  fetchImpl?: ComparisonFetch;
  headers?: Record<string, string>;
};

class SimulationRunComparisonResponseError extends Error {}
class SimulationRunComparisonTransportError extends Error {}

export function createSimulationRunComparisonClient(
  options: SimulationRunComparisonClientOptions = {},
): SimulationRunComparisonClient {
  const fetchImpl = options.fetchImpl ?? defaultFetch;
  const baseUrl = options.baseUrl ?? "";
  const headers = {
    Accept: "application/json",
    ...(options.headers ?? {}),
  };

  return {
    compare: async (request) => {
      validateComparisonRequest(request);
      const query = new URLSearchParams({
        left_workflow_id: request.left.workflowId,
        left_run_id: request.left.runId,
        right_workflow_id: request.right.workflowId,
        right_run_id: request.right.runId,
      });
      const payload = await getJson(
        fetchImpl,
        `${baseUrl}${SIMULATION_RUN_COMPARISON_ENDPOINT}?${query.toString()}`,
        headers,
      );
      return validateComparisonResponse(payload, request);
    },
    prepareAuditBundle: async (request) => {
      validateAuditRequest(request);
      const query = new URLSearchParams({
        workflow_id: request.selector.workflowId,
        run_id: request.selector.runId,
        expected_manifest_sha256: request.expectedManifestSha256,
        journal_scope: request.journalScope,
      });
      if (request.journalSequence !== undefined) {
        query.set("journal_sequence", String(request.journalSequence));
      }
      const payload = await getJson(
        fetchImpl,
        `${baseUrl}${SELECTED_AUDIT_BUNDLE_ENDPOINT}?${query.toString()}`,
        headers,
      );
      return validateSelectedAuditBundle(payload, request);
    },
  };
}

export async function loadSimulationRunComparison(
  client: SimulationRunComparisonClient,
  request: SimulationRunComparisonRequest,
): Promise<SimulationRunComparisonState> {
  try {
    validateComparisonRequest(request);
    const comparison = validateComparisonResponse(
      await client.compare(request),
      request,
    );
    return comparison.selection_state === "same_run"
      ? { status: "identical", comparison }
      : { status: "differing", comparison };
  } catch (error) {
    if (error instanceof SimulationRunComparisonResponseError) {
      return {
        status: "partial_unavailable",
        errorMessage: "Comparison evidence is incomplete and unavailable",
      };
    }
    return {
      status: "unavailable",
      errorMessage: "Simulation run comparison is unavailable",
    };
  }
}

export async function loadSelectedAuditBundle(
  client: SimulationRunComparisonClient,
  request: AuditBundleSelectionRequest,
): Promise<SimulationAuditBundleState> {
  try {
    validateAuditRequest(request);
    const bundle = validateSelectedAuditBundle(
      await client.prepareAuditBundle(request),
      request,
    );
    return {
      status: "loaded",
      bundle,
      stableJson: stableJson(bundle),
    };
  } catch (error) {
    if (error instanceof SimulationRunComparisonResponseError) {
      return {
        status: "partial_unavailable",
        errorMessage:
          "Selected audit bundle evidence is incomplete and unavailable",
      };
    }
    return {
      status: "unavailable",
      errorMessage: "Selected audit bundle is unavailable",
    };
  }
}

function validateComparisonRequest(
  request: SimulationRunComparisonRequest,
): void {
  if (!isObject(request)) {
    throw new SimulationRunComparisonResponseError(
      "comparison request is invalid",
    );
  }
  validateSelector(request.left);
  validateSelector(request.right);
}

function validateAuditRequest(request: AuditBundleSelectionRequest): void {
  if (!isObject(request)) {
    throw new SimulationRunComparisonResponseError(
      "audit selection is invalid",
    );
  }
  validateSelector(request.selector);
  requireSha256(request.expectedManifestSha256);
  if (
    request.journalScope !== "complete_run_manifest" &&
    request.journalScope !== "single_journal_event"
  ) {
    throw new SimulationRunComparisonResponseError(
      "audit journal scope is invalid",
    );
  }
  if (
    request.journalScope === "complete_run_manifest" &&
    request.journalSequence !== undefined
  ) {
    throw new SimulationRunComparisonResponseError(
      "complete manifest scope does not accept a sequence",
    );
  }
  if (
    request.journalScope === "single_journal_event" &&
    !isPositiveInteger(request.journalSequence)
  ) {
    throw new SimulationRunComparisonResponseError(
      "single-event scope requires a sequence",
    );
  }
}

function validateComparisonResponse(
  payload: unknown,
  request: SimulationRunComparisonRequest,
): SimulationRunComparisonApiView {
  if (
    !isObject(payload) ||
    payload.schema_version !== 1 ||
    (payload.selection_state !== "same_run" &&
      payload.selection_state !== "different_runs") ||
    !isSha256(payload.comparison_sha256) ||
    !isObject(payload.summary) ||
    !Array.isArray(payload.sections)
  ) {
    throw new SimulationRunComparisonResponseError(
      "comparison response is invalid",
    );
  }
  assertNoUnsafeKeys(payload);
  const left = validateSnapshot(payload.left, request.left);
  const right = validateSnapshot(payload.right, request.right);
  const sameSelector =
    request.left.workflowId === request.right.workflowId &&
    request.left.runId === request.right.runId;
  if (
    payload.selection_state !==
      (sameSelector ? "same_run" : "different_runs") ||
    (sameSelector && stableJson(left) !== stableJson(right))
  ) {
    throw new SimulationRunComparisonResponseError(
      "comparison selection is inconsistent",
    );
  }

  if (payload.sections.length !== SIMULATION_RUN_COMPARISON_SECTIONS.length) {
    throw new SimulationRunComparisonResponseError(
      "comparison sections are incomplete",
    );
  }
  const sections = payload.sections.map((section, index) =>
    validateSection(section, SIMULATION_RUN_COMPARISON_SECTIONS[index]),
  );
  const statuses: SimulationRunComparisonStatus[] = [
    "added",
    "removed",
    "changed",
    "unchanged",
  ];
  const summary = {} as Record<SimulationRunComparisonStatus, number>;
  for (const status of statuses) {
    const value = payload.summary[status];
    const expected = sections.filter((item) => item.status === status).length;
    if (!isNonNegativeInteger(value) || value !== expected) {
      throw new SimulationRunComparisonResponseError(
        "comparison summary is inconsistent",
      );
    }
    summary[status] = value;
  }
  if (
    (payload.selection_state === "same_run" &&
      (summary.unchanged !== sections.length ||
        summary.added !== 0 ||
        summary.removed !== 0 ||
        summary.changed !== 0)) ||
    (payload.selection_state === "different_runs" &&
      summary.added + summary.removed + summary.changed === 0)
  ) {
    throw new SimulationRunComparisonResponseError(
      "comparison result is contradictory",
    );
  }
  return {
    schema_version: 1,
    selection_state: payload.selection_state,
    comparison_sha256: payload.comparison_sha256,
    summary,
    left,
    right,
    sections,
  };
}

function validateSnapshot(
  value: unknown,
  expectedSelector: SimulationRunSelector,
): SimulationRunEvidenceSnapshotApiView {
  if (
    !isObject(value) ||
    value.schema_version !== 1 ||
    !isObject(value.selector) ||
    value.selector.workflow_id !== expectedSelector.workflowId ||
    value.selector.run_id !== expectedSelector.runId ||
    !isObject(value.workflow) ||
    value.workflow.workflow_id !== expectedSelector.workflowId ||
    !isPositiveInteger(value.workflow.expected_workflow_version) ||
    !isObject(value.run) ||
    value.run.run_id !== expectedSelector.runId ||
    !isObject(value.signal) ||
    !isObject(value.order_intent) ||
    !isObject(value.risk_decision) ||
    !isObject(value.approval_ticket) ||
    !isNullableObject(value.approval_decision) ||
    !isNullableObject(value.execution) ||
    !isNullableObject(value.protection) ||
    !Array.isArray(value.alerts) ||
    value.alerts.some((item) => !isObject(item)) ||
    !isObject(value.journal_provenance) ||
    !isObject(value.provenance)
  ) {
    throw new SimulationRunComparisonResponseError(
      "comparison snapshot is invalid",
    );
  }
  const journalProvenance = value.journal_provenance;
  if (
    !isSha256(journalProvenance.manifest_sha256) ||
    !Array.isArray(journalProvenance.journal_references) ||
    !Array.isArray(journalProvenance.records) ||
    journalProvenance.journal_references.length === 0 ||
    journalProvenance.journal_references.length !==
      journalProvenance.records.length
  ) {
    throw new SimulationRunComparisonResponseError(
      "journal provenance is incomplete",
    );
  }
  const references = journalProvenance.journal_references.map((item) =>
    requireJournalReference(item),
  );
  if (new Set(references).size !== references.length) {
    throw new SimulationRunComparisonResponseError(
      "journal references are duplicated",
    );
  }
  const records = journalProvenance.records.map((record, index) =>
    validateJournalEvidence(record, references[index]),
  );
  const sequences = records.map((record) => record.sequence);
  if (
    sequences.some(
      (sequence, index) => index > 0 && sequence <= sequences[index - 1],
    )
  ) {
    throw new SimulationRunComparisonResponseError(
      "journal evidence is not ordered",
    );
  }
  const expectedClassifications =
    value.execution === null
      ? ["simulated", "local_only", "externally_unverified"]
      : [
          "simulated",
          "local_only",
          "fake_broker_derived",
          "externally_unverified",
        ];
  if (
    !Array.isArray(value.provenance.classifications) ||
    stableJson(value.provenance.classifications) !==
      stableJson(expectedClassifications) ||
    value.provenance.broker_derived !== false ||
    value.provenance.externally_verified !== false
  ) {
    throw new SimulationRunComparisonResponseError(
      "comparison provenance is unsafe",
    );
  }
  return value as SimulationRunEvidenceSnapshotApiView;
}

function validateJournalEvidence(
  value: unknown,
  expectedReference: string,
): SimulationRunJournalEvidenceApiView {
  if (
    !isObject(value) ||
    !isPositiveInteger(value.sequence) ||
    value.journal_reference !== expectedReference ||
    expectedReference !== `journal_sequence:${value.sequence}` ||
    !isNonEmptyText(value.event_type) ||
    !isNonEmptyText(value.timestamp) ||
    !isSha256(value.record_sha256)
  ) {
    throw new SimulationRunComparisonResponseError(
      "journal evidence is invalid",
    );
  }
  return value as SimulationRunJournalEvidenceApiView;
}

function validateSection(
  value: unknown,
  expectedName: SimulationRunComparisonSectionName,
): SimulationRunComparisonSectionApiView {
  if (
    !isObject(value) ||
    value.name !== expectedName ||
    !isComparisonStatus(value.status) ||
    !Array.isArray(value.differences)
  ) {
    throw new SimulationRunComparisonResponseError(
      "comparison section is invalid",
    );
  }
  const differences = value.differences.map((item) => {
    if (
      !isObject(item) ||
      !isNonEmptyText(item.path) ||
      !isComparisonStatus(item.status) ||
      item.status === "unchanged"
    ) {
      throw new SimulationRunComparisonResponseError(
        "comparison difference is invalid",
      );
    }
    return item as SimulationRunComparisonFieldApiView;
  });
  const paths = differences.map((item) => item.path);
  if (
    new Set(paths).size !== paths.length ||
    stableJson(paths) !== stableJson([...paths].sort()) ||
    (value.status === "unchanged" && differences.length !== 0) ||
    (value.status !== "unchanged" && differences.length === 0)
  ) {
    throw new SimulationRunComparisonResponseError(
      "comparison differences are inconsistent",
    );
  }
  return {
    name: expectedName,
    status: value.status,
    left_value: value.left_value,
    right_value: value.right_value,
    differences,
  };
}

function validateSelectedAuditBundle(
  payload: unknown,
  request: AuditBundleSelectionRequest,
): SelectedAuditBundleApiView {
  if (
    !isObject(payload) ||
    payload.schema_version !== 1 ||
    payload.bundle_type !== "audit_review_bundle" ||
    !isObject(payload.manifest) ||
    !isObject(payload.operations_read_model) ||
    !Array.isArray(payload.workflow_definitions) ||
    !Array.isArray(payload.workflow_simulation_runs) ||
    !Array.isArray(payload.journal_records)
  ) {
    throw new SimulationRunComparisonResponseError(
      "selected audit bundle is invalid",
    );
  }
  assertNoUnsafeKeys(payload);
  const manifest = payload.manifest;
  if (
    manifest.schema_version !== 1 ||
    manifest.mode !== "local_review_only" ||
    manifest.external_delivery !== "none" ||
    manifest.live_trading_enabled !== false ||
    manifest.live_trading_authorized !== false ||
    !Array.isArray(manifest.workflow_ids) ||
    stableJson(manifest.workflow_ids) !==
      stableJson([request.selector.workflowId]) ||
    !Array.isArray(manifest.run_ids) ||
    stableJson(manifest.run_ids) !== stableJson([request.selector.runId]) ||
    !Array.isArray(manifest.journal_references) ||
    !isObject(manifest.counts) ||
    !isObject(manifest.safety_scan) ||
    manifest.safety_scan.result !== "passed" ||
    manifest.safety_scan.finding_count !== 0 ||
    !isObject(manifest.selection)
  ) {
    throw new SimulationRunComparisonResponseError(
      "selected audit manifest is invalid",
    );
  }
  const selection = validateAuditSelection(manifest.selection, request);
  const selectedReferences = selection.selected_journal_references;
  if (
    stableJson(manifest.journal_references) !==
      stableJson(selectedReferences) ||
    manifest.counts.workflow_definitions !==
      payload.workflow_definitions.length ||
    manifest.counts.workflow_simulation_runs !== 1 ||
    manifest.counts.workflow_simulation_runs !==
      payload.workflow_simulation_runs.length ||
    manifest.counts.journal_records !== selectedReferences.length ||
    manifest.counts.journal_records !== payload.journal_records.length ||
    !Array.isArray(payload.operations_read_model.audit_events) ||
    manifest.counts.audit_events !==
      payload.operations_read_model.audit_events.length
  ) {
    throw new SimulationRunComparisonResponseError(
      "selected audit counts are inconsistent",
    );
  }
  const selectedSequences = selectedReferences.map(journalSequence);
  const recordSequences = payload.journal_records.map((record) => {
    if (!isObject(record) || !isPositiveInteger(record.sequence)) {
      throw new SimulationRunComparisonResponseError(
        "selected journal record is invalid",
      );
    }
    return record.sequence;
  });
  const eventSequences = payload.operations_read_model.audit_events.map(
    (event) => {
      if (!isObject(event) || !isPositiveInteger(event.sequence)) {
        throw new SimulationRunComparisonResponseError(
          "selected audit event is invalid",
        );
      }
      return event.sequence;
    },
  );
  if (
    stableJson(recordSequences) !== stableJson(selectedSequences) ||
    stableJson(eventSequences) !== stableJson(selectedSequences)
  ) {
    throw new SimulationRunComparisonResponseError(
      "selected audit evidence is inconsistent",
    );
  }
  const run = payload.workflow_simulation_runs[0];
  if (
    !isObject(run) ||
    run.workflow_id !== request.selector.workflowId ||
    run.run_id !== request.selector.runId
  ) {
    throw new SimulationRunComparisonResponseError(
      "selected run attribution is invalid",
    );
  }
  return payload as SelectedAuditBundleApiView;
}

function validateAuditSelection(
  value: Record<string, unknown>,
  request: AuditBundleSelectionRequest,
): SelectedAuditBundleSelectionApiView {
  if (
    value.schema_version !== 1 ||
    value.workflow_id !== request.selector.workflowId ||
    value.run_id !== request.selector.runId ||
    !isPositiveInteger(value.workflow_version) ||
    !isNonEmptyText(value.run_status) ||
    value.source_manifest_sha256 !== request.expectedManifestSha256 ||
    value.journal_scope !== request.journalScope ||
    !Array.isArray(value.source_manifest_journal_references) ||
    !Array.isArray(value.selected_journal_references) ||
    !Array.isArray(value.selected_record_sha256) ||
    !Array.isArray(value.classifications) ||
    value.broker_derived !== false ||
    value.externally_verified !== false ||
    !isSha256(value.selection_sha256)
  ) {
    throw new SimulationRunComparisonResponseError(
      "audit selection binding is invalid",
    );
  }
  const sourceReferences = value.source_manifest_journal_references.map(
    requireJournalReference,
  );
  const selectedReferences = value.selected_journal_references.map(
    requireJournalReference,
  );
  if (
    sourceReferences.length === 0 ||
    new Set(sourceReferences).size !== sourceReferences.length ||
    new Set(selectedReferences).size !== selectedReferences.length ||
    selectedReferences.length === 0 ||
    !selectedReferences.every((reference) =>
      sourceReferences.includes(reference),
    ) ||
    value.selected_record_sha256.length !== selectedReferences.length ||
    !value.selected_record_sha256.every(isSha256)
  ) {
    throw new SimulationRunComparisonResponseError(
      "audit selection references are invalid",
    );
  }
  if (
    (request.journalScope === "complete_run_manifest" &&
      stableJson(selectedReferences) !== stableJson(sourceReferences)) ||
    (request.journalScope === "single_journal_event" &&
      (selectedReferences.length !== 1 ||
        selectedReferences[0] !==
          `journal_sequence:${request.journalSequence}`))
  ) {
    throw new SimulationRunComparisonResponseError(
      "audit selection scope is inconsistent",
    );
  }
  const allowedClassifications = [
    ["simulated", "local_only", "externally_unverified"],
    [
      "simulated",
      "local_only",
      "fake_broker_derived",
      "externally_unverified",
    ],
  ];
  if (
    !allowedClassifications.some(
      (item) => stableJson(item) === stableJson(value.classifications),
    )
  ) {
    throw new SimulationRunComparisonResponseError(
      "audit selection provenance is invalid",
    );
  }
  return value as SelectedAuditBundleSelectionApiView;
}

function validateSelector(selector: SimulationRunSelector): void {
  if (
    !isObject(selector) ||
    !isSafeIdentifier(selector.workflowId) ||
    !isSafeIdentifier(selector.runId)
  ) {
    throw new SimulationRunComparisonResponseError(
      "simulation run selector is invalid",
    );
  }
}

async function getJson(
  fetchImpl: ComparisonFetch,
  url: string,
  headers: Record<string, string>,
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers,
      body: undefined,
    });
  } catch {
    throw new SimulationRunComparisonTransportError(
      "comparison service is unavailable",
    );
  }
  if (!response.ok) {
    throw new SimulationRunComparisonTransportError(
      "comparison service rejected the request",
    );
  }
  try {
    return await response.json();
  } catch {
    throw new SimulationRunComparisonResponseError(
      "comparison response is not JSON",
    );
  }
}

function defaultFetch(input: string, init: RequestInit) {
  return fetch(input, init);
}

function stableJson(value: unknown): string {
  return JSON.stringify(normalizeJson(value));
}

function normalizeJson(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(normalizeJson);
  }
  if (isObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, normalizeJson(value[key])]),
    );
  }
  return value;
}

function assertNoUnsafeKeys(value: unknown): void {
  const forbidden = new Set([
    "account_id",
    "api_key",
    "authorization",
    "broker_host",
    "broker_port",
    "certificate",
    "credential",
    "github_token",
    "openai_key",
    "password",
    "private_key",
    "secret",
    "telegram_token",
    "token",
  ]);
  const visit = (current: unknown) => {
    if (Array.isArray(current)) {
      current.forEach(visit);
      return;
    }
    if (!isObject(current)) {
      return;
    }
    for (const [key, nested] of Object.entries(current)) {
      if (forbidden.has(key.toLowerCase())) {
        throw new SimulationRunComparisonResponseError(
          "unsafe field is present",
        );
      }
      visit(nested);
    }
  };
  visit(value);
}

function requireJournalReference(value: unknown): string {
  if (
    typeof value !== "string" ||
    !/^journal_sequence:[1-9][0-9]*$/.test(value)
  ) {
    throw new SimulationRunComparisonResponseError(
      "journal reference is invalid",
    );
  }
  return value;
}

function journalSequence(reference: string): number {
  const sequence = Number(reference.slice("journal_sequence:".length));
  if (!isPositiveInteger(sequence)) {
    throw new SimulationRunComparisonResponseError(
      "journal sequence is invalid",
    );
  }
  return sequence;
}

function requireSha256(value: unknown): string {
  if (!isSha256(value)) {
    throw new SimulationRunComparisonResponseError("SHA-256 is invalid");
  }
  return value;
}

function isSha256(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{64}$/.test(value)
  );
}

function isSafeIdentifier(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 160 &&
    value.trim() === value &&
    !containsControlCharacter(value)
  );
}

function isNonEmptyText(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.trim() === value &&
    !containsControlCharacter(value)
  );
}

function containsControlCharacter(value: string) {
  return [...value].some((character) => {
    const code = character.charCodeAt(0);
    return code < 32 || code === 127;
  });
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableObject(
  value: unknown,
): value is Record<string, unknown> | null {
  return value === null || isObject(value);
}

function isPositiveInteger(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value > 0
  );
}

function isNonNegativeInteger(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 0
  );
}

function isComparisonStatus(
  value: unknown,
): value is SimulationRunComparisonStatus {
  return (
    value === "added" ||
    value === "removed" ||
    value === "changed" ||
    value === "unchanged"
  );
}
