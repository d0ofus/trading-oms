import { useEffect, useState } from "react";
import { api } from "./api";
import { Modal } from "./components";

type Preview = {
  preview_id: string;
  items: {
    id: string;
    name: string;
    action: "delete" | "archive";
    runs: { id: string; name?: string; armed: boolean; position: string }[];
  }[];
};

export function RemoveStrategies({
  ids,
  close,
  removed,
}: {
  ids: string[];
  close: () => void;
  removed: (ids: string[]) => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mutation] = useState(() => crypto.randomUUID().replaceAll("-", ""));
  useEffect(() => {
    const controller = new AbortController();
    void api<Preview>(
      "/strategies/removal-preview",
      "POST",
      { ids },
      controller.signal,
    )
      .then((p) => {
        if (!controller.signal.aborted) setPreview(p);
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [ids]);
  return (
    <Modal
      open
      title="Remove selected strategies"
      description="Delete unused drafts; archive published or referenced strategies. Published versions and trading history are retained."
      onOpenChange={(open) => {
        if (!open && !busy) close();
      }}
    >
      {!preview && !error && <p role="status">Checking strategy references…</p>}
      {error && <p role="alert">{error}</p>}
      {preview?.items.map((item) => (
        <div key={item.id}>
          <strong>
            {item.name} —{" "}
            {item.action === "delete" ? "Delete unused draft" : "Archive"}
          </strong>
          {item.runs.map((run) => (
            <p key={run.id}>
              {run.name ?? run.id}: {run.armed ? "armed" : "disarmed"}, position{" "}
              {run.position ?? "0"}. This run continues unchanged.
            </p>
          ))}
        </div>
      ))}
      <p>
        Existing runs, orders and protection continue. This action does not stop
        trading. Deleted drafts cannot be restored here; archived strategies
        can.
      </p>
      <button disabled={busy} onClick={close}>
        Keep strategies
      </button>
      <button
        disabled={!preview || busy || Boolean(error)}
        onClick={async () => {
          if (!preview) return;
          setBusy(true);
          try {
            const result = await api<{ deleted: string[]; archived: string[] }>(
              "/strategies/removal-confirm",
              "POST",
              { preview_id: preview.preview_id, mutation_id: mutation },
            );
            removed([...result.deleted, ...result.archived]);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Confirm removal
      </button>
    </Modal>
  );
}
