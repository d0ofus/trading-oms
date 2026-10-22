import { useEffect, useState } from "react";
import { api } from "./api";
import { Modal } from "./components";

type Preview = {
  preview_id: string;
  eligible: boolean;
  items: { id: string; name: string; reasons: string[] }[];
};

export function ArchiveRuns({
  ids,
  close,
  refresh,
  notify,
}: {
  ids: string[];
  close: () => void;
  refresh: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mutation] = useState(() => crypto.randomUUID().replaceAll("-", ""));
  useEffect(() => {
    const controller = new AbortController();
    void api<Preview>(
      "/runs/archive-preview",
      "POST",
      { ids },
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) setPreview(value);
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [ids]);
  return (
    <Modal
      open
      title="Archive inactive runs"
      description="Hide inactive runs from the Desk. Orders, executions, approvals and run history are retained."
      onOpenChange={(open) => {
        if (!open && !busy) close();
      }}
    >
      {error && <p role="alert">{error}</p>}
      {!preview && !error && <p role="status">Checking archive eligibility…</p>}
      {preview?.items.map((item) => (
        <div key={item.id}>
          <strong>{item.name}</strong>
          <p>
            {item.reasons.length
              ? item.reasons.join(" ")
              : "Eligible — disarmed, flat and no unresolved operations."}
          </p>
        </div>
      ))}
      <p>
        This action does not cancel orders, close positions, unsubscribe data or
        release incidents.
      </p>
      <button disabled={busy} onClick={close}>
        Keep runs
      </button>
      <button
        disabled={!preview?.eligible || busy || Boolean(error)}
        onClick={async () => {
          if (!preview) return;
          setBusy(true);
          try {
            await api("/runs/archive-confirm", "POST", {
              preview_id: preview.preview_id,
              mutation_id: mutation,
            });
            await refresh();
            close();
            notify("Runs archived. Inspect them in Run & order history.");
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Confirm archive
      </button>
    </Modal>
  );
}
