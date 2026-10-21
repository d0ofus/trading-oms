import { useEffect, useState } from "react";
import { api, localTime, titleCase, type Incident, type Snapshot } from "./api";
import { Badge, Modal, Panel } from "./components";

type Detail = Incident & {
  can_resolve: boolean;
  remediation: string;
  occurrences?: number;
  diagnostic?: {
    reason?: string;
    exception?: string;
    operation?: string;
    frames?: { file: string; function: string; line: number }[];
  };
};

export function IncidentRecovery({
  snapshot,
  refresh,
  notify,
}: {
  snapshot: Snapshot | null;
  refresh: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [busy, setBusy] = useState(false);
  const identity = detail?.id;
  useEffect(() => {
    if (!identity) return;
    let active = true;
    const timer = window.setInterval(() => {
      void api<Detail>(`/operations/incidents/${identity}`)
        .then((value) => {
          if (active) setDetail(value);
        })
        .catch(() => {});
    }, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [identity]);
  async function view(id: string) {
    try {
      setDetail(await api<Detail>(`/operations/incidents/${id}`));
    } catch (error) {
      notify((error as Error).message, true);
    }
  }
  async function action(suffix: string) {
    if (!detail) return;
    setBusy(true);
    try {
      await api(`/operations/incidents/${detail.id}/${suffix}`, "POST");
      await refresh();
      if (suffix === "review") setDetail(null);
      else await view(detail.id);
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const incidents = snapshot?.incidents.filter((i) => !i.resolved) ?? [];
  return (
    <>
      <Panel
        title="Incidents & recovery"
        caption="Inspect evidence and recheck recovery before acknowledging a critical incident."
      >
        {incidents.length ? (
          incidents.map((item) => (
            <div className="ws-incident" key={item.id}>
              <Badge tone={item.severity === "critical" ? "danger" : "neutral"}>
                {titleCase(item.severity)}
              </Badge>
              <div>
                <strong>{titleCase(item.id)}</strong>
                <p>{item.detail}</p>
                <small>{localTime(item.timestamp)}</small>
              </div>
              <button onClick={() => void view(item.id)}>View incident</button>
            </div>
          ))
        ) : (
          <div className="ws-all-clear">
            <div>
              <strong>No recorded critical incidents</strong>
              <p>Readiness checks still apply before any new authorization.</p>
            </div>
          </div>
        )}
      </Panel>
      <Modal
        open={!!detail}
        onOpenChange={(open) => {
          if (!open) setDetail(null);
        }}
        title={detail ? titleCase(detail.id) : "Incident"}
        description="Rechecking does not submit or resend orders."
      >
        {detail && (
          <>
            <p>{detail.detail}</p>
            <p className="ws-banner warning">{detail.remediation}</p>
            <dl className="ws-facts">
              <dt>Diagnostic reference</dt>
              <dd>{detail.id}</dd>
              <dt>Occurrences</dt>
              <dd>{detail.occurrences ?? 1}</dd>
              <dt>Recovery</dt>
              <dd>
                {detail.can_resolve
                  ? "Checks passed; ready for operator review"
                  : "Recovery evidence required"}
              </dd>
            </dl>
            <details>
              <summary>Safe diagnostic details</summary>
              <p>
                {detail.diagnostic?.reason &&
                  titleCase(detail.diagnostic.reason)}{" "}
                {detail.diagnostic?.exception} {detail.diagnostic?.operation}
              </p>
              {detail.diagnostic?.frames?.map((frame, i) => (
                <p key={i}>
                  {frame.file}:{frame.line} · {frame.function}
                </p>
              ))}
            </details>
            <div className="ws-modal-actions">
              <button disabled={busy} onClick={() => void action("recheck")}>
                Recheck recovery
              </button>
              <button
                disabled={busy || !detail.can_resolve}
                onClick={() => void action("review")}
              >
                Mark resolved
              </button>
            </div>
          </>
        )}
      </Modal>
    </>
  );
}
