import { memo, useEffect, useRef, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, localTime, titleCase, type Event } from "./api";
import { Badge, Grid, Modal, Panel } from "./components";

export type AuditSummary = {
  sequence: number;
  timestamp: string;
  type: string;
  summary: string;
};
type Page = {
  items: AuditSummary[];
  watermark: number;
  next_cursor: number | null;
  scanned_through: number;
  older_cursor?: number | null;
  newer_cursor?: number | null;
};
type Query = { before?: number; after?: number; q?: string };

const rowId = (row: AuditSummary) => String(row.sequence);
const emptyRows: AuditSummary[] = [];
const columns: ColumnDef<AuditSummary, unknown>[] = [
  { accessorKey: "sequence", header: "Sequence", size: 95 },
  {
    accessorKey: "timestamp",
    header: "Time",
    size: 220,
    cell: ({ row }) => localTime(row.original.timestamp),
  },
  {
    accessorKey: "type",
    header: "Event",
    size: 270,
    cell: ({ row }) => titleCase(row.original.type.replaceAll(".", " ")),
  },
  { accessorKey: "summary", header: "Details", size: 400 },
];

export function mergeSummaries(
  current: AuditSummary[],
  incoming: AuditSummary[],
) {
  const unique = new Map(current.map((event) => [event.sequence, event]));
  for (const event of incoming) unique.set(event.sequence, event);
  return [...unique.values()]
    .sort((a, b) => b.sequence - a.sequence)
    .slice(0, 200);
}

function AuditHistoryView() {
  const [page, setPage] = useState<Page | null>(null);
  const [query, setQuery] = useState<Query>({});
  const [term, setTerm] = useState("");
  const [live, setLive] = useState(true);
  const [revision, setRevision] = useState(0);
  const [visible, setVisible] = useState(!document.hidden);
  const [streaming, setStreaming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<Event | null>(null);
  const cache = useRef(new Map<string, Page>());
  useEffect(() => {
    const changed = () => {
      setVisible(!document.hidden);
      if (!document.hidden) {
        setLive(true);
        setQuery({});
      }
    };
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, []);
  useEffect(() => {
    if (!visible) return;
    if (live) cache.current.clear();
    const controller = new AbortController();
    let stream: EventSource | undefined;
    let timer: ReturnType<typeof setInterval> | undefined;
    const pending = new Map<number, AuditSummary>();
    setBusy(true);
    const parameters = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined) parameters.set(key, String(value));
    const key = parameters.toString();
    const cached = cache.current.get(key);
    if (!live && cached) setPage(cached);
    void api<Page>(`/events/page?${key}`, "GET", undefined, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        result.items.sort((a, b) => b.sequence - a.sequence);
        cache.current.delete(key);
        cache.current.set(key, result);
        while (cache.current.size > 3)
          cache.current.delete(cache.current.keys().next().value!);
        setPage(result);
        if (!live) return;
        stream = new EventSource(
          `/api/events/stream?summaries=true&after=${result.watermark}`,
        );
        stream.onopen = () => setStreaming(true);
        stream.onerror = () => setStreaming(false);
        stream.addEventListener("resync", () => {
          stream?.close();
          pending.clear();
          setNotice(
            "Recent events refreshed. Older events remain available in history.",
          );
          setRevision((value) => value + 1);
        });
        stream.addEventListener("journal", (message) => {
          try {
            const event = JSON.parse(
              (message as MessageEvent<string>).data,
            ) as AuditSummary;
            pending.set(event.sequence, event);
            if (pending.size > 2000) {
              stream?.close();
              pending.clear();
              setNotice(
                "Display caught up to recent events; complete history is retained.",
              );
              setRevision((value) => value + 1);
            }
          } catch {
            setNotice(
              "An event could not be displayed. Reload recent events to recover.",
            );
          }
        });
        timer = setInterval(() => {
          if (!pending.size) return;
          const batch = [...pending.values()];
          pending.clear();
          setPage((previous) => {
            if (!previous) return previous;
            const items = mergeSummaries(previous.items, batch);
            return {
              ...previous,
              items,
              next_cursor: items.at(-1)?.sequence ?? null,
              older_cursor: items.at(-1)?.sequence ?? null,
              newer_cursor: null,
            };
          });
        }, 250);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setNotice(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => {
      controller.abort();
      stream?.close();
      clearInterval(timer);
      pending.clear();
      setStreaming(false);
    };
  }, [query, live, revision, visible]);
  useEffect(() => {
    setDetail(null);
    if (selected === null) return;
    const controller = new AbortController();
    void api<Event>(
      `/events/detail/${selected}`,
      "GET",
      undefined,
      controller.signal,
    )
      .then(setDetail)
      .catch((error: Error) => {
        if (!controller.signal.aborted) setNotice(error.message);
      });
    return () => controller.abort();
  }, [selected]);
  function recent() {
    setLive(true);
    setQuery({});
    setRevision((value) => value + 1);
  }
  const older =
    page?.older_cursor === undefined ? page?.next_cursor : page.older_cursor;
  const newer =
    page?.newer_cursor === undefined
      ? page?.items[0]?.sequence
      : page.newer_cursor;
  return (
    <>
      <Panel
        title="Audit history"
        caption="Complete immutable history, loaded in bounded pages. Select a record for details."
        action={
          <Badge tone={streaming ? "success" : "neutral"}>
            {streaming
              ? "Event stream connected"
              : live
                ? "Stream paused or reconnecting"
                : "Browsing history"}
          </Badge>
        }
      >
        <form
          className="ws-inline-actions"
          onSubmit={(event) => {
            event.preventDefault();
            setLive(false);
            setQuery({ q: term.trim() });
            setNotice("");
          }}
        >
          <label>
            Search the complete audit ledger
            <input
              value={term}
              maxLength={200}
              onChange={(event) => setTerm(event.target.value)}
            />
          </label>
          <button disabled={busy}>Search all history</button>
          <button type="button" onClick={recent}>
            Latest events · live
          </button>
        </form>
        {notice && <p role="status">{notice}</p>}
        <Grid<AuditSummary>
          name="activity"
          rows={page?.items ?? emptyRows}
          virtual
          rowId={rowId}
          selected={selected === null ? undefined : String(selected)}
          onSelect={(row) => setSelected(row.sequence)}
          columns={columns}
        />
        <div className="ws-inline-actions">
          <button
            disabled={busy || !older}
            onClick={() => {
              setLive(false);
              setQuery({ q: query.q, before: older! });
            }}
          >
            Older records / continue search
          </button>
          <button
            disabled={busy || live || !newer}
            onClick={() => {
              setQuery({ q: query.q, after: newer! });
            }}
          >
            Newer records
          </button>
          <span>
            {busy
              ? "Loading bounded page…"
              : `Up to 200 records per page · searched through ${page?.scanned_through ?? 0}`}
          </span>
        </div>
      </Panel>
      <Modal
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={
          detail ? titleCase(detail.type.replaceAll(".", " ")) : "Event details"
        }
        description={`Immutable audit event ${selected ?? ""}`}
      >
        {detail ? (
          <pre className="ws-event-payload">
            {JSON.stringify(detail.payload, null, 2)}
          </pre>
        ) : (
          <p>Loading event payload…</p>
        )}
      </Modal>
    </>
  );
}

export const AuditHistory = memo(AuditHistoryView);
