import { useEffect, useState } from "react";
import { api, type Order, type Run } from "./api";
import { Grid, Panel } from "./components";

export function RecordHistory({
  selectOrder,
  selectRun,
}: {
  selectOrder: (id: string) => void;
  selectRun: (run: Run) => void;
}) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState("orders");
  const [cursor, setCursor] = useState<number | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [rows, setRows] = useState<(Run | Order)[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    setRows([]);
    if (!open) return;
    const controller = new AbortController();
    void api<{ items: (Run | Order)[]; next_cursor: number | null }>(
      `/workspace/records/${kind}${cursor ? `?before=${cursor}` : ""}`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((page) => {
        setRows(page.items);
        setNext(page.next_cursor);
        setError("");
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) setError(failure.message);
      });
    return () => controller.abort();
  }, [open, kind, cursor]);
  return (
    <Panel
      title="Run & order history"
      caption="Browse saved runs and all broker order outcomes without loading the entire ledger."
    >
      <details onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary>Browse records</summary>
        <label>
          Record type
          <select
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setCursor(null);
            }}
          >
            <option value="orders">Orders & executions</option>
            <option value="runs">Saved runs</option>
          </select>
        </label>
        {error && <p role="alert">{error}</p>}
        <Grid<Run | Order>
          name="record-history"
          rows={rows}
          virtual
          rowId={(row) => row.id}
          onSelect={(row) => {
            if ("payload" in row) selectOrder(row.id);
            else selectRun(row);
          }}
          columns={[
            {
              id: "name",
              header: "Run / instrument",
              accessorFn: (row) =>
                "payload" in row
                  ? row.payload.symbol
                  : `${row.name} · ${row.symbol}`,
            },
            {
              id: "state",
              header: "State",
              accessorFn: (row) =>
                !("payload" in row) && row.archived ? "Archived" : row.state,
            },
            { accessorKey: "id", header: "Identity", size: 320 },
          ]}
        />
        <button disabled={!next} onClick={() => setCursor(next)}>
          Older records
        </button>
        <button onClick={() => setCursor(null)}>Latest records</button>
        <p>
          Select a saved run to inspect and review it on the desk. Selection
          never arms it.
        </p>
      </details>
    </Panel>
  );
}
