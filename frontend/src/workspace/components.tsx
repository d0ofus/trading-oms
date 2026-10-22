import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnSizingState,
  type SortingState,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Search,
  X,
} from "lucide-react";
import { preference, readPreference, type Check } from "./api";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <span className={`ws-badge ${tone}`}>
      <span aria-hidden="true" className="ws-dot" />
      {children}
    </span>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="ws-empty">
      <div className="ws-empty-icon" aria-hidden="true">
        ◇
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Panel({
  title,
  caption,
  action,
  children,
  className = "",
}: {
  title: string;
  caption?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`ws-panel ${className}`}>
      <div className="ws-panel-heading">
        <div>
          <h2>{title}</h2>
          {caption && <p>{caption}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="ws-modal-shade" />
        <Dialog.Content className={`ws-modal ${wide ? "wide" : ""}`}>
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description>{description}</Dialog.Description>
          <Dialog.Close
            className="ws-icon ws-modal-close"
            aria-label="Close dialog"
          >
            <X size={18} />
          </Dialog.Close>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function Readiness({
  checks,
  navigate,
}: {
  checks: Check[];
  navigate?: (path: string) => void;
}) {
  return (
    <div className="ws-readiness">
      {checks.map((item) => {
        const tone = item.feed_health
          ? item.feed_health === "healthy"
            ? "passed"
            : item.feed_health === "checking"
              ? "waiting"
              : "blocked"
          : item.passed
            ? "passed"
            : ["waiting", "checking"].includes(item.status ?? "")
              ? "waiting"
              : "blocked";
        return (
          <div key={item.code} className={`ws-check ${tone}`}>
            {tone === "passed" ? (
              <CheckCircle2
                size={17}
                aria-label={item.feed_health ? "Feed healthy" : "Passed"}
              />
            ) : tone === "waiting" ? (
              <Clock3 size={17} aria-label="Waiting" />
            ) : (
              <CircleAlert size={17} aria-label="Blocked" />
            )}
            <div>
              <strong>{item.title}</strong>
              <p>
                {item.feed_health === "healthy"
                  ? `Timestamped ${item.signal_source ?? "signal"} and bid/ask feeds established. Required history complete.`
                  : item.detail}
              </p>
              {item.feed_health === "healthy" && item.execution_detail && (
                <p className="ws-execution-status">{item.execution_detail}</p>
              )}
            </div>
            {!item.passed &&
              navigate &&
              item.remediation &&
              !["waiting", "checking"].includes(item.status ?? "") && (
                <button
                  className="ws-link"
                  onClick={() => navigate(item.remediation!)}
                >
                  Resolve <span aria-hidden="true">↗</span>
                </button>
              )}
          </div>
        );
      })}
    </div>
  );
}

export function Grid<T>({
  name,
  rows,
  columns,
  rowId,
  onSelect,
  selected,
  virtual = false,
}: {
  name: string;
  virtual?: boolean;
  rows: T[];
  columns: ColumnDef<T>[];
  rowId: (row: T) => string;
  onSelect?: (row: T) => void;
  selected?: string;
}) {
  const [sizing, setSizing] = useState<ColumnSizingState>(() =>
    readPreference(`table.${name}.sizes`, {}),
  );
  const [sorting, setSorting] = useState<SortingState>(() =>
    readPreference(`table.${name}.sorting`, []),
  );
  const [visibility, setVisibility] = useState<Record<string, boolean>>(() =>
    readPreference(`table.${name}.columns`, {}),
  );
  const [height, setHeight] = useState(() =>
    readPreference(`table.${name}.height`, 420),
  );
  const [filter, setFilter] = useState(() =>
    readPreference(`table.${name}.filter`, ""),
  );
  const [order, setOrder] = useState<string[]>(() =>
    readPreference(`table.${name}.order`, rows.map(rowId)),
  );
  useEffect(() => {
    preference(`table.${name}.order`, order);
    preference(`table.${name}.sorting`, sorting);
  }, [name, order, sorting]);
  useEffect(() => {
    setOrder((previous) => {
      const ids = rows.map(rowId);
      const present = new Set(ids);
      const kept = previous.filter((id) => present.has(id));
      const known = new Set(kept);
      const next = [...kept, ...ids.filter((id) => !known.has(id))];
      return next.length === previous.length &&
        next.every((id, index) => id === previous[index])
        ? previous
        : next;
    });
  }, [rows, rowId]);
  const [density, setDensity] = useState(() =>
    readPreference(`table.${name}.density`, "comfortable"),
  );
  const data = useMemo(() => {
    const filtered = rows.filter(
      (row) =>
        !filter ||
        JSON.stringify(row).toLowerCase().includes(filter.toLowerCase()),
    );
    if (virtual) {
      const current = sorting[0];
      if (!current) return filtered;
      const column = columns.find(
        (item) =>
          item.id === current.id ||
          ("accessorKey" in item && item.accessorKey === current.id),
      );
      const value = (row: T) =>
        column && "accessorFn" in column && column.accessorFn
          ? column.accessorFn(row, 0)
          : (row as Record<string, unknown>)[
              column && "accessorKey" in column
                ? String(column.accessorKey)
                : current.id
            ];
      return filtered.sort(
        (a, b) => compareValues(value(a), value(b)) * (current.desc ? -1 : 1),
      );
    }
    const ranks = new Map(order.map((id, i) => [id, i]));
    return filtered.sort(
      (a, b) => (ranks.get(rowId(a)) ?? 1e9) - (ranks.get(rowId(b)) ?? 1e9),
    );
  }, [rows, order, filter, rowId, virtual, sorting, columns]);
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: rowId,
    state: { columnSizing: sizing, sorting, columnVisibility: visibility },
    onColumnVisibilityChange: setVisibility,
    onColumnSizingChange: setSizing,
    columnResizeMode: "onChange",
    defaultColumn: { minSize: 80, size: 140, maxSize: 500 },
    manualSorting: true,
  });
  useEffect(() => {
    preference(`table.${name}.sizes`, sizing);
  }, [name, sizing]);
  useEffect(() => {
    preference(`table.${name}.columns`, visibility);
    preference(`table.${name}.height`, height);
  }, [name, visibility, height]);
  useEffect(() => {
    preference(`table.${name}.filter`, filter);
    preference(`table.${name}.density`, density);
  }, [name, filter, density]);
  const scroll = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const rowHeight = density === "compact" ? 32 : 44;
  const allRows = table.getRowModel().rows;
  const first = virtual
    ? Math.max(
        0,
        Math.min(allRows.length - 1, Math.floor(scrollTop / rowHeight) - 5),
      )
    : 0;
  const last = virtual
    ? Math.min(allRows.length, first + Math.ceil(height / rowHeight) + 10)
    : allRows.length;
  useEffect(() => {
    if (virtual && scroll.current && scrollTop > allRows.length * rowHeight) {
      scroll.current.scrollTop = 0;
      setScrollTop(0);
    }
  }, [virtual, allRows.length, rowHeight, scrollTop]);
  function sortColumn(id: string) {
    const desc = sorting[0]?.id === id && !sorting[0].desc;
    const ordered = [...table.getCoreRowModel().rows].sort(
      (a, b) => compareValues(a.getValue(id), b.getValue(id)) * (desc ? -1 : 1),
    );
    setOrder(ordered.map((row) => row.id));
    setSorting([{ id, desc }]);
  }
  return (
    <div className={`ws-grid ${density}`}>
      <div className="ws-table-tools">
        <label className="ws-search">
          <Search size={15} />
          <input
            aria-label={`Filter ${name}`}
            value={filter}
            placeholder="Filter records…"
            onChange={(event) => setFilter(event.target.value)}
          />
        </label>
        <span className="ws-muted">{data.length} records</span>
        <details className="ws-table-preferences">
          <summary>Table options</summary>
          <div>
            <label>
              Panel height
              <input
                aria-label={`${name} panel height`}
                type="range"
                min={180}
                max={800}
                step={20}
                value={height}
                onChange={(event) => setHeight(Number(event.target.value))}
              />
            </label>
            {table.getAllLeafColumns().map((column) => (
              <label className="ws-checkbox" key={column.id}>
                <input
                  type="checkbox"
                  checked={column.getIsVisible()}
                  disabled={
                    column.getIsVisible() &&
                    table.getVisibleLeafColumns().length === 1
                  }
                  onChange={column.getToggleVisibilityHandler()}
                />
                {String(column.columnDef.header ?? column.id)}
              </label>
            ))}
          </div>
        </details>
        <select
          aria-label={`${name} density`}
          value={density}
          onChange={(event) => setDensity(event.target.value)}
        >
          <option value="comfortable">Comfortable</option>
          <option value="compact">Compact</option>
        </select>
      </div>
      <div
        ref={scroll}
        className={`ws-table-scroll ${virtual ? "ws-virtual" : ""}`}
        style={{ maxHeight: height }}
        onScroll={(event) => {
          if (virtual) setScrollTop(event.currentTarget.scrollTop);
        }}
      >
        <table style={{ minWidth: table.getTotalSize() }}>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => (
                  <th
                    key={header.id}
                    style={{ width: header.getSize() }}
                    aria-sort={
                      sorting[0]?.id === header.column.id
                        ? sorting[0].desc
                          ? "descending"
                          : "ascending"
                        : "none"
                    }
                  >
                    <button onClick={() => sortColumn(header.column.id)}>
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
                      {sorting[0]?.id === header.column.id &&
                        (sorting[0].desc ? (
                          <ArrowDown size={12} />
                        ) : (
                          <ArrowUp size={12} />
                        ))}
                    </button>
                    <button
                      className="ws-column-resizer"
                      aria-label={`Resize ${String(header.column.columnDef.header)} column`}
                      onMouseDown={header.getResizeHandler()}
                      onTouchStart={header.getResizeHandler()}
                      onKeyDown={(event) => {
                        if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
                          event.preventDefault();
                          setSizing((previous) => ({
                            ...previous,
                            [header.column.id]: Math.max(
                              80,
                              header.getSize() +
                                (event.key === "ArrowRight" ? 20 : -20),
                            ),
                          }));
                        }
                      }}
                    />
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {virtual && first > 0 && (
              <tr aria-hidden="true" className="ws-spacer">
                <td
                  colSpan={table.getVisibleLeafColumns().length}
                  style={{ height: first * rowHeight, padding: 0 }}
                />
              </tr>
            )}
            {allRows.slice(first, last).map((row) => (
              <tr
                key={row.id}
                style={virtual ? { height: rowHeight } : undefined}
                className={selected === row.id ? "selected" : ""}
                tabIndex={onSelect ? 0 : undefined}
                aria-selected={onSelect ? selected === row.id : undefined}
                onClick={() => onSelect?.(row.original)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && onSelect) {
                    event.preventDefault();
                    onSelect(row.original);
                  }
                  if (virtual && ["ArrowDown", "ArrowUp"].includes(event.key)) {
                    event.preventDefault();
                    const index =
                      allRows.findIndex((item) => item.id === row.id) +
                      (event.key === "ArrowDown" ? 1 : -1);
                    if (
                      index >= 0 &&
                      index < allRows.length &&
                      scroll.current
                    ) {
                      scroll.current.scrollTop = Math.max(
                        0,
                        (index - 2) * rowHeight,
                      );
                      requestAnimationFrame(() => {
                        const target =
                          scroll.current?.querySelector<HTMLElement>(
                            `tr[data-row-id="${CSS.escape(allRows[index].id)}"]`,
                          );
                        target?.focus();
                      });
                    }
                  }
                }}
                data-row-id={row.id}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {virtual && last < allRows.length && (
              <tr aria-hidden="true" className="ws-spacer">
                <td
                  colSpan={table.getVisibleLeafColumns().length}
                  style={{
                    height: (allRows.length - last) * rowHeight,
                    padding: 0,
                  }}
                />
              </tr>
            )}
          </tbody>
        </table>
        {data.length === 0 && (
          <p className="ws-table-empty">No matching records.</p>
        )}
      </div>
    </div>
  );
}

function compareValues(a: unknown, b: unknown) {
  const left = String(a ?? ""),
    right = String(b ?? "");
  return left.trim() &&
    right.trim() &&
    Number.isFinite(Number(left)) &&
    Number.isFinite(Number(right))
    ? Number(left) - Number(right)
    : left.localeCompare(right, undefined, { numeric: true });
}
