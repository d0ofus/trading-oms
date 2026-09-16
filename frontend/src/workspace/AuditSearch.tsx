import { useState } from "react";
import { api, localTime, type Event } from "./api";
import { Grid } from "./components";

export function AuditSearch({ select }: { select: (event: Event) => void }) {
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState("");
  const [rows, setRows] = useState<Event[]>([]);
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");
  async function search(append = false) {
    setBusy(true);
    setError("");
    try {
      const term = append ? searched : query;
      const result = await api<Event[]>(
        `/events?q=${encodeURIComponent(term)}&after=${append ? (rows.at(-1)?.sequence ?? 0) : 0}`,
      );
      setSearched(term);
      setRows(append ? [...rows, ...result] : result);
      setMore(result.length === 200);
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="ws-diagnostics">
      <summary>Search the complete audit ledger</summary>
      <form
        className="ws-inline-actions"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <label>
          Event or detail
          <input
            value={query}
            maxLength={200}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button disabled={busy || !query.trim()}>Search all history</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {searched && (
        <>
          <p>
            {rows.length} records loaded for “{searched}”.
          </p>
          <Grid<Event>
            name="audit-search"
            rows={rows}
            rowId={(row) => String(row.sequence)}
            onSelect={select}
            columns={[
              {
                accessorKey: "timestamp",
                header: "Time",
                size: 240,
                cell: ({ row }) => localTime(row.original.timestamp),
              },
              { accessorKey: "type", header: "Event", size: 300 },
            ]}
          />
          {more && (
            <button disabled={busy} onClick={() => void search(true)}>
              Load next matches
            </button>
          )}
        </>
      )}
    </details>
  );
}
