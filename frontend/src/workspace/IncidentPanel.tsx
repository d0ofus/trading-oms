import { useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, localTime, titleCase, type Incident, type Snapshot } from "./api";
import { Badge, Grid, Modal, Panel } from "./components";
import { FeedRecovery } from "./FeedRecovery";
import { useIncidentDetail } from "./useIncidentDetail";

type Page = { items: Incident[]; next_cursor: number | null };
function scopeLabel(item: Incident) {
  return item.scope
    ? `${titleCase(item.scope.type)}${item.scope.key === "*" ? "" : ` · ${item.scope.key}`}`
    : "Workspace";
}
function statusLabel(item: Incident) {
  if (item.release_kind === "dependency_retired")
    return "Historical — unused dependency retired";
  if (item.restriction === "released" || item.resolved)
    return "Historical — restriction released";
  return item.restriction === "ready_for_release"
    ? "Recovery evidence verified"
    : item.severity === "critical"
      ? "Trading concern — inspect current evidence"
      : "Automatic recovery in progress";
}
const rowId = (item: Incident) => item.id;
const columns: ColumnDef<Incident>[] = [
  {
    id: "incident",
    header: "Incident",
    accessorFn: (item) => titleCase(item.code ?? item.id),
    size: 220,
  },
  {
    id: "status",
    header: "Trading restriction",
    accessorFn: statusLabel,
    size: 330,
  },
  { id: "scope", header: "Applies to", accessorFn: scopeLabel, size: 200 },
  {
    id: "last",
    header: "Latest occurrence",
    accessorFn: (item) => localTime(item.last_at ?? item.timestamp),
    size: 220,
  },
  {
    accessorKey: "recovery_detail",
    header: "Recovery requirements",
    size: 450,
  },
];

export function IncidentPanel({
  snapshot,
  notify,
  refresh,
}: {
  snapshot: Snapshot | null;
  notify: (message: string, error?: boolean) => void;
  refresh: () => Promise<void>;
}) {
  const [view, setView] = useState("current");
  const [before, setBefore] = useState<number | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [selected, setSelected] = useState<Incident | null>(null);
  const {
    detail,
    available,
    error: recoveryError,
    checking,
    recheck,
  } = useIncidentDetail(selected?.id);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setPage(null);
    if (view === "current" && before === null) return;
    const controller = new AbortController();
    void api<Page>(
      `/incidents?view=${view}${before === null ? "" : `&before=${before}`}`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) setPage(result);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) notify(error.message, true);
      });
    return () => controller.abort();
  }, [view, before, revision, notify]);
  useEffect(() => {
    setRationale("");
  }, [selected]);
  const recent = view === "current" && before === null;
  const rows = recent ? (snapshot?.incidents ?? []) : (page?.items ?? []);
  const next = recent ? snapshot?.incident_next_cursor : page?.next_cursor;
  return (
    <>
      <Panel
        title="Current attention"
        caption="Concerns affecting current operations. Background checks continue automatically; prior records remain in History."
      >
        {snapshot?.watchdog && (
          <div className="ws-inline-actions" role="status">
            <Badge tone={snapshot.watchdog.ready ? "success" : "warning"}>
              {snapshot.watchdog.ready
                ? "Watchdog healthy"
                : "Watchdog not ready"}
            </Badge>
            <span>{snapshot.watchdog.detail}</span>
            {snapshot.watchdog.age_seconds !== null && (
              <small>
                Heartbeat age: {snapshot.watchdog.age_seconds.toFixed(1)}s
              </small>
            )}
          </div>
        )}
        <div className="ws-inline-actions">
          <label>
            Activity view{" "}
            <select
              value={view}
              onChange={(event) => {
                setView(event.target.value);
                setBefore(null);
              }}
            >
              <option value="current">Current attention</option>
              <option value="history">History</option>
              <option value="diagnostics">All diagnostics</option>
              <option value="investigations">
                Investigations without a trading restriction
              </option>
            </select>
          </label>
          <span>
            {(snapshot?.incident_counts?.held ?? 0) +
              (snapshot?.incident_counts?.ready_for_release ?? 0)}{" "}
            current concerns
          </span>
        </div>
        {recent && rows.length === 0 ? (
          <p>
            No current concerns require attention. Preparation checks run
            automatically. Earlier records remain in History.
          </p>
        ) : (
          <Grid
            name="incidents"
            rows={rows}
            columns={columns}
            rowId={rowId}
            onSelect={setSelected}
            virtual
          />
        )}
        <div className="ws-inline-actions">
          <button disabled={!next} onClick={() => setBefore(next!)}>
            Older incident records
          </button>
          <button
            onClick={() => {
              setBefore(null);
              setRevision((value) => value + 1);
              void refresh();
            }}
          >
            Latest incident records
          </button>
          <small>
            Select a row to inspect evidence and available actions. Up to 200
            summaries per page.
          </small>
        </div>
      </Panel>
      <Modal
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title="Current condition details"
        description="Inspect current evidence and automatic recovery. Emergency stop and final authorization remain separate."
      >
        {recoveryError && (
          <p role="alert">
            Condition status unavailable: {recoveryError}. Use Recheck for
            current evidence.
          </p>
        )}
        <button disabled={checking} onClick={recheck}>
          Recheck recovery
        </button>
        {detail ? (
          <>
            <h3>{titleCase(detail.code ?? detail.id)}</h3>
            <p>{detail.detail}</p>
            {detail.order_context && (
              <p>
                Originating order: {detail.order_context.order_id} · Broker
                order ID: {detail.order_context.broker_id}
              </p>
            )}
            {detail.rejection && (
              <section aria-label="Broker rejection">
                <strong>Broker rejection {detail.rejection.code}</strong>
                <p>{detail.rejection.detail}</p>
                <p>
                  {detail.rejection.available
                    ? `Reason: ${titleCase(detail.rejection.category)}`
                    : "Specific rejection explanation unavailable"}
                </p>
                <p>
                  Recovery acknowledgment does not establish that the broker
                  will accept another order.
                </p>
              </section>
            )}
            <p>
              <strong>{statusLabel(detail)}</strong> · {scopeLabel(detail)}
            </p>
            <p>{detail.recovery_detail}</p>
            {detail.recovery && (
              <>
                <p role="status">
                  {available && detail.recovery.can_release
                    ? detail.automatic_release_enabled === false
                      ? "Verified recovery — ready to acknowledge"
                      : "Current recovery evidence verified"
                    : "Recovery not verified"}
                </p>
                <p>Last checked: {localTime(detail.recovery.checked_at)}</p>
                <ul>
                  {detail.recovery.checks.map((check) => (
                    <li key={check.code}>
                      <strong>
                        {check.passed ? "Passed" : "Pending"}: {check.title}
                      </strong>
                      {!check.passed && <> — {check.detail}</>}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {detail.feeds && (
              <FeedRecovery
                conid={detail.feeds.conid}
                components={detail.feeds.components}
              />
            )}
            <p>
              First: {localTime(detail.first_at ?? detail.timestamp)} · Latest:{" "}
              {localTime(detail.last_at ?? detail.timestamp)} · Occurrences:{" "}
              {detail.occurrences ?? 1}
            </p>
            <p>
              Investigation: {detail.investigation ?? "open"}. Releasing a
              trading restriction does not establish that an unknown root cause
              was fixed.
            </p>
            {detail.evidence && (
              <details>
                <summary>Verified recovery evidence</summary>
                <pre className="ws-event-payload">
                  {JSON.stringify(detail.evidence, null, 2)}
                </pre>
              </details>
            )}
            {detail.diagnostic && (
              <details>
                <summary>Sanitized fault diagnostics</summary>
                <pre className="ws-event-payload">
                  {JSON.stringify(detail.diagnostic, null, 2)}
                </pre>
              </details>
            )}
            {detail.release_evidence && (
              <details>
                <summary>Evidence rechecked at release</summary>
                <pre className="ws-event-payload">
                  {JSON.stringify(detail.release_evidence, null, 2)}
                </pre>
              </details>
            )}
            {detail.release_reason && (
              <p>Release rationale: {detail.release_reason}</p>
            )}
            {detail.investigation_outcome && (
              <p>Investigation outcome: {detail.investigation_outcome}</p>
            )}
            {detail.restriction !== "released" &&
              detail.release_policy === "automatic" &&
              detail.automatic_release_enabled !== false && (
                <p>
                  Recovery is evaluated automatically. Final authorization and
                  the approved resumption policy remain in force.
                </p>
              )}
            {detail.restriction !== "released" &&
              detail.automatic_release_enabled === false && (
                <>
                  {detail.review_policy === "arming" && (
                    <p>
                      Verified routine recovery can also be acknowledged in
                      Review & arm.
                    </p>
                  )}
                  <details>
                    <summary>Optional notes</summary>
                    <label>
                      Recovery notes (optional; do not include credentials or
                      account identifiers)
                      <textarea
                        value={rationale}
                        maxLength={1000}
                        onChange={(event) => setRationale(event.target.value)}
                      />
                    </label>
                  </details>
                  <button
                    className="ws-primary"
                    disabled={
                      busy ||
                      !available ||
                      detail.restriction !== "ready_for_release" ||
                      detail.recovery?.can_release === false
                    }
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await api(
                          `/operations/incidents/${detail.id}/review`,
                          "POST",
                          { revision: detail.revision, rationale },
                        );
                        setSelected(null);
                        setRevision((value) => value + 1);
                        await refresh();
                        notify(
                          "Trading restriction released. Investigation history is retained; affected runs remain unarmed.",
                        );
                      } catch (error) {
                        notify((error as Error).message, true);
                        recheck();
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Acknowledge recovery and release restriction
                  </button>
                </>
              )}
            {detail.restriction === "released" &&
              detail.investigation === "open" && (
                <>
                  <label>
                    Investigation outcome
                    <textarea
                      value={rationale}
                      maxLength={1000}
                      onChange={(event) => setRationale(event.target.value)}
                    />
                  </label>
                  <button
                    disabled={busy || rationale.trim().length < 10}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await api(
                          `/incidents/${detail.id}/investigation/close`,
                          "POST",
                          { revision: detail.revision, rationale },
                        );
                        setSelected(null);
                        setRevision((value) => value + 1);
                        await refresh();
                        notify(
                          "Investigation closed. Its immutable evidence is retained.",
                        );
                      } catch (error) {
                        notify((error as Error).message, true);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Close investigation
                  </button>
                </>
              )}
          </>
        ) : (
          <p>Loading current incident evidence…</p>
        )}
      </Modal>
    </>
  );
}
