import { describe, expect, it } from "vitest";
import { mergeSummaries, type AuditSummary } from "./AuditHistory";

const event = (sequence: number): AuditSummary => ({
  sequence,
  timestamp: "2026-09-21T00:00:00Z",
  type: "fixture",
  summary: String(sequence),
});
describe("bounded audit display", () => {
  it("deduplicates and retains exactly the latest page through repeated bursts", () => {
    let rows: AuditSummary[] = [];
    for (let i = 0; i < 5000; i += 200)
      rows = mergeSummaries(
        rows,
        Array.from({ length: 200 }, (_, j) => event(i + j)),
      );
    expect(rows).toHaveLength(200);
    expect(rows[0].sequence).toBe(4999);
    expect(rows.at(-1)?.sequence).toBe(4800);
    expect(mergeSummaries(rows, [event(4999), event(4800)])).toEqual(rows);
  });
  it("accepts corrected display summaries without duplicate rows", () => {
    expect(
      mergeSummaries([event(1)], [{ ...event(1), summary: "changed" }]),
    ).toEqual([{ ...event(1), summary: "changed" }]);
  });
});
