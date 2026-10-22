import { useEffect, useState } from "react";
import { api, titleCase, type Incident } from "./api";
import { Modal } from "./components";

type Status = { items: Incident[]; automatic: boolean };
export function RecoveryBatch({
  close,
}: {
  close: () => void;
  refresh: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    let controller: AbortController | null = null;
    let timer: number | undefined;
    let closed = false;
    const read = async () => {
      if (closed || document.hidden || controller) return;
      const request = new AbortController();
      controller = request;
      try {
        const value = await api<Status>(
          "/incidents/recovery-status",
          "GET",
          undefined,
          request.signal,
        );
        if (!closed && !request.signal.aborted) {
          setStatus(value);
          setError("");
        }
      } catch (e) {
        if (!closed && !request.signal.aborted) setError((e as Error).message);
      } finally {
        controller = null;
        if (!closed && !document.hidden)
          timer = window.setTimeout(() => void read(), 2000);
      }
    };
    const visibility = () => {
      window.clearTimeout(timer);
      if (document.hidden) controller?.abort();
      else void read();
    };
    void read();
    document.addEventListener("visibilitychange", visibility);
    return () => {
      closed = true;
      window.clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [generation]);
  return (
    <Modal
      open
      title="Routine recovery status"
      description="Routine restrictions release automatically after current recovery is verified. Dedicated safety reviews remain separate."
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      {error && <p role="alert">Recovery status unavailable: {error}</p>}
      {!status && !error && <p role="status">Checking recovery evidence…</p>}
      {status?.automatic === false && (
        <p>
          Automatic recovery is disabled by the rollback setting. Verified
          episodes can be released through their individual incident review.
        </p>
      )}
      {status?.items
        .filter((i) => i.release_policy === "automatic")
        .map((i) => (
          <div key={i.id}>
            <strong>{titleCase(i.code ?? i.id)}</strong>
            <p>{i.recovery_detail}</p>
            {i.remaining_seconds !== undefined && (
              <p>
                Healthy observation remaining: {Math.ceil(i.remaining_seconds)}
                s.
              </p>
            )}
          </div>
        ))}
      {status &&
        !status.items.some((i) => i.release_policy === "automatic") && (
          <p>
            No routine restrictions remain in this page. Released and retired
            episodes are retained in history.
          </p>
        )}
      {status?.items.some((i) => i.release_policy !== "automatic") && (
        <p>
          Dedicated order, account, protection or engine reviews remain
          available in the incident table.
        </p>
      )}
      <p>
        Automatic recovery does not clear emergency stop or arm a run. Fresh
        authorization is required after restart or revocation. Only an existing
        authorization that explicitly permits routine resumption can resume.
      </p>
      <button onClick={() => setGeneration((g) => g + 1)}>
        Refresh recovery status
      </button>
    </Modal>
  );
}
