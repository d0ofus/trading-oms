import { useState } from "react";
import { money, type Replay } from "./api";

export function ReplayCompare({ results }: { results: Replay[] }) {
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  if (results.length < 2)
    return (
      <p className="ws-muted">
        Run a second replay to compare results side by side.
      </p>
    );
  const a = results.find((r) => r.id === left),
    b = results.find((r) => r.id === right);
  return (
    <details className="ws-diagnostics">
      <summary>Compare two replays</summary>
      <div className="ws-form-grid">
        {[
          ["Baseline", left, setLeft],
          ["Comparison", right, setRight],
        ].map(([label, value, change]) => (
          <label key={String(label)}>
            {String(label)}
            <select
              value={String(value)}
              onChange={(event) =>
                (change as (value: string) => void)(event.target.value)
              }
            >
              <option value="">Choose a replay</option>
              {results.map((r) => (
                <option value={r.id} key={r.id}>
                  {r.strategy_name} v{r.version} · {r.dataset} ·{" "}
                  {new Date(r.timestamp).toLocaleTimeString()}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      {a &&
        b &&
        (a.id === b.id ? (
          <p role="status">Choose two different results.</p>
        ) : (
          <>
            {(a.dataset !== b.dataset ||
              a.dataset_source !== b.dataset_source) && (
              <p className="ws-banner warning">
                These runs use different datasets or evidence sources.
                Differences cannot be attributed only to the strategy.
              </p>
            )}
            <table className="ws-compare-table">
              <thead>
                <tr>
                  <th>Measure</th>
                  <th>Baseline</th>
                  <th>Comparison</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["Version", a.version, b.version],
                  ["Observations", a.ticks, b.ticks],
                  ["Signals", a.signals.length, b.signals.length],
                  ["Completed trades", a.trades.length, b.trades.length],
                  [
                    "Simulated P/L",
                    money(a.realized_pnl),
                    money(b.realized_pnl),
                  ],
                  [
                    "Open shares at end",
                    a.open_position?.quantity ?? 0,
                    b.open_position?.quantity ?? 0,
                  ],
                  [
                    "Working entry at end",
                    String(a.working_entry),
                    String(b.working_entry),
                  ],
                ].map(([label, av, bv]) => (
                  <tr key={label}>
                    <th>{label}</th>
                    <td>{av}</td>
                    <td>{bv}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ))}
    </details>
  );
}
