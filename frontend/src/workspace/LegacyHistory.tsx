import { useEffect, useState } from "react";
import { api, localTime, titleCase, type Event, type Json } from "./api";
import { Grid, Modal, Panel } from "./components";

type Import = {
  id: string;
  name: string;
  records: number;
  imported_at: string;
};

export function LegacyHistory({
  notify,
}: {
  notify: (message: string, error?: boolean) => void;
}) {
  const [imports, setImports] = useState<Import[]>([]);
  const [records, setRecords] = useState<Event[]>([]);
  const [selected, setSelected] = useState<Import | null>(null);
  const [record, setRecord] = useState<Event | null>(null);
  const [busy, setBusy] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [next, setNext] = useState<number | null>(null);
  const [recordSequence, setRecordSequence] = useState<number | null>(null);
  useEffect(() => {
    setRecords([]);
    if (!selected) return;
    const controller = new AbortController();
    void api<{ items: Event[]; next_cursor: number | null }>(
      `/events/legacy/${selected.id}/page?after=${cursor}`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((page) => {
        setRecords(page.items);
        setNext(page.next_cursor);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) notify(error.message, true);
      });
    return () => controller.abort();
  }, [selected, cursor, notify]);
  useEffect(() => {
    setRecord(null);
    if (!selected || recordSequence === null) return;
    const controller = new AbortController();
    void api<Event>(
      `/events/legacy/${selected.id}/detail/${recordSequence}`,
      "GET",
      undefined,
      controller.signal,
    )
      .then(setRecord)
      .catch((error: Error) => {
        if (!controller.signal.aborted) notify(error.message, true);
      });
    return () => controller.abort();
  }, [selected, recordSequence, notify]);
  useEffect(() => {
    const controller = new AbortController();
    void api<Import[]>("/events/legacy", "GET", undefined, controller.signal)
      .then(setImports)
      .catch((error: Error) => {
        if (!controller.signal.aborted) notify(error.message, true);
      });
    return () => controller.abort();
  }, [notify]);
  async function importFile(file: File, definition: boolean) {
    setBusy(true);
    try {
      if (file.size > 24 * 1024 * 1024)
        throw new Error("Import files smaller than 24 MB.");
      const text = await file.text();
      const name = file.name.replace(/\.(jsonl?|ndjson)$/i, "").slice(0, 100);
      if (definition) {
        await api("/strategies/import-legacy", "POST", {
          name,
          document: JSON.parse(text) as Json,
        });
        notify(
          "Entry rules migrated to a draft. Configure protection and review exits in Strategy Studio before publishing.",
        );
      } else {
        const items = text.trim().startsWith("[")
          ? (JSON.parse(text) as Json[])
          : text
              .trim()
              .split(/\r?\n/)
              .map((line) => JSON.parse(line) as Json);
        await api("/events/legacy", "POST", { name, records: items });
        setImports(await api("/events/legacy"));
        notify(
          "Historical journal imported as read-only evidence. No authorization was transferred.",
        );
      }
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title="Historical evidence"
      caption="Legacy approvals remain read-only and never authorize paper execution."
    >
      <details>
        <summary>
          Import historical records or a supported replay definition
        </summary>
        <div className="ws-form-grid">
          <label>
            Historical journal (.jsonl or .json)
            <input
              disabled={busy}
              type="file"
              accept=".json,.jsonl,.ndjson"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void importFile(file, false);
                event.target.value = "";
              }}
            />
          </label>
          <label>
            Legacy close-above-SMA definition (.json)
            <input
              disabled={busy}
              type="file"
              accept=".json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void importFile(file, true);
                event.target.value = "";
              }}
            />
          </label>
        </div>
        <p className="ws-muted">
          The original files are retained. Imports redact credential and account
          fields. Unsupported visual definitions remain historical evidence;
          they are never silently translated into executable rules.
        </p>
      </details>
      {imports.length > 0 && (
        <Grid<Import>
          name="legacy-imports"
          rows={imports}
          rowId={(row) => row.id}
          onSelect={(item) => {
            setSelected(item);
            setCursor(0);
            setRecordSequence(null);
          }}
          columns={[
            { accessorKey: "name", header: "Historical journal", size: 300 },
            { accessorKey: "records", header: "Records" },
            {
              accessorKey: "imported_at",
              header: "Imported",
              size: 240,
              cell: ({ row }) => localTime(row.original.imported_at),
            },
          ]}
        />
      )}
      {selected && (
        <>
          <h3>{selected.name} · read-only</h3>
          <Grid<Event>
            name="legacy-records"
            virtual
            rows={records}
            rowId={(row) => String(row.sequence)}
            onSelect={(item) => setRecordSequence(item.sequence)}
            columns={[
              { accessorKey: "sequence", header: "Sequence" },
              {
                accessorKey: "type",
                header: "Event",
                size: 300,
                cell: ({ row }) =>
                  titleCase(row.original.type.replaceAll(".", " ")),
              },
              {
                accessorKey: "timestamp",
                header: "Time",
                size: 240,
                cell: ({ row }) => localTime(row.original.timestamp),
              },
            ]}
          />
          <button disabled={next === null} onClick={() => setCursor(next!)}>
            Next historical page
          </button>
          <button onClick={() => setCursor(0)}>First historical page</button>
          <button
            onClick={() => {
              setSelected(null);
              setRecords([]);
            }}
          >
            Close historical records
          </button>
        </>
      )}
      <Modal
        open={recordSequence !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRecordSequence(null);
            setRecord(null);
          }
        }}
        title="Historical event"
        description="Read-only compatibility view. Historical approvals have no paper execution authority."
      >
        <pre>{JSON.stringify(record?.payload, null, 2)}</pre>
      </Modal>
    </Panel>
  );
}
