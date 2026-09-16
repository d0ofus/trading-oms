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
  useEffect(() => {
    void api<Import[]>("/events/legacy")
      .then(setImports)
      .catch((error: Error) => notify(error.message, true));
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
            void api<Event[]>(`/events/legacy/${item.id}`)
              .then(setRecords)
              .catch((error: Error) => notify(error.message, true));
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
            rows={records}
            rowId={(row) => String(row.sequence)}
            onSelect={setRecord}
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
        </>
      )}
      <Modal
        open={!!record}
        onOpenChange={(open) => {
          if (!open) setRecord(null);
        }}
        title="Historical event"
        description="Read-only compatibility view. Historical approvals have no paper execution authority."
      >
        <pre>{JSON.stringify(record?.payload, null, 2)}</pre>
      </Modal>
    </Panel>
  );
}
