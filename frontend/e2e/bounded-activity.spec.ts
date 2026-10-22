import { expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { test } from "./fixtures";

test("audit pages mount bounded rows, search complete history and load payloads on selection", async ({
  page,
}) => {
  const reads: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) reads.push(request.url());
  });
  await page.route("**/api/events/page**", async (route) => {
    const url = new URL(route.request().url());
    const start = url.searchParams.has("before") ? 999800 : 1000000;
    const search = url.searchParams.get("q");
    await route.fulfill({
      json: {
        watermark: 1000000,
        next_cursor: start - 199,
        scanned_through: start - 199,
        items: Array.from({ length: 200 }, (_, i) => ({
          sequence: start - i,
          timestamp: "2026-09-21T00:00:00Z",
          type: "fixture.audit",
          summary: search ? `Search match ${search}` : `Summary ${start - i}`,
        })),
      },
    });
  });
  await page.route("**/api/events/stream**", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: ": keepalive\n\n",
    }),
  );
  await page.route("**/api/events/detail/*", (route) =>
    route.fulfill({
      json: {
        sequence: 1000000,
        timestamp: "2026-09-21T00:00:00Z",
        type: "fixture.audit",
        payload: { detail: "Lazy immutable payload" },
      },
    }),
  );
  await page.goto("/activity#pair=synthetic-browser-pairing-for-tests-only");
  await expect(
    page.getByText("Summary 1000000", { exact: true }),
  ).toBeVisible();
  expect(
    await page.locator("tbody tr[data-row-id]").count(),
  ).toBeLessThanOrEqual(60);
  expect(reads.some((url) => url.includes("/events/detail/"))).toBe(false);
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({
    path: "test-results/activity-bounded.png",
    fullPage: true,
  });
  await page.locator('tr[data-row-id="1000000"]').focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.locator('tr[data-row-id="999999"]')).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toContainText(
    "Lazy immutable payload",
  );
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Older records / continue search" })
    .click();
  await expect(page.getByText("Summary 999800", { exact: true })).toBeVisible();
  await page.getByLabel("Search the complete audit ledger").fill("needle");
  await page
    .getByRole("button", { name: "Search all history", exact: true })
    .click();
  await expect(page.getByText("Search match needle").first()).toBeVisible();
  expect(reads.some((url) => url.includes("q=needle"))).toBe(true);
  expect(
    reads.some(
      (url) => url.includes("/workspace/session") || url.includes("/candles"),
    ),
  ).toBe(false);
});

test("audit stream pauses while hidden, refreshes bounded catch-up and closes on navigation", async ({
  page,
}) => {
  let reads = 0;
  await page.route("**/api/events/page**", (route) => {
    reads++;
    return route.fulfill({
      json: {
        items: [
          {
            sequence: 42,
            timestamp: "2026-09-21T00:00:00Z",
            type: "fixture",
            summary: "Recent audit evidence",
          },
        ],
        watermark: 42,
        next_cursor: null,
        scanned_through: 42,
      },
    });
  });
  await page.addInitScript(() => {
    const probe = { active: 0, hidden: false, resync: () => {} };
    Object.defineProperty(window, "auditProbe", { value: probe });
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => probe.hidden,
    });
    class Stream {
      onopen?: () => void;
      closed = false;
      constructor() {
        probe.active++;
        setTimeout(() => this.onopen?.(), 0);
      }
      addEventListener(type: string, listener: () => void) {
        if (type === "resync") probe.resync = listener;
      }
      close() {
        if (!this.closed) probe.active--;
        this.closed = true;
      }
    }
    Object.defineProperty(window, "EventSource", { value: Stream });
  });
  await page.goto("/activity#pair=synthetic-browser-pairing-for-tests-only");
  await expect(
    page.getByText("Recent audit evidence", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Event stream connected", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => {
    const probe = (window as unknown as { auditProbe: { hidden: boolean } })
      .auditProbe;
    probe.hidden = true;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { auditProbe: { active: number } }).auditProbe
            .active,
      ),
    )
    .toBe(0);
  const before = reads;
  await page.evaluate(() => {
    (
      window as unknown as { auditProbe: { hidden: boolean } }
    ).auditProbe.hidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect.poll(() => reads).toBeGreaterThan(before);
  await expect(
    page.getByText("Event stream connected", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() =>
    (
      window as unknown as { auditProbe: { resync: () => void } }
    ).auditProbe.resync(),
  );
  await expect(
    page.getByText(
      "Recent events refreshed. Older events remain available in history.",
    ),
  ).toBeVisible();
  await expect.poll(() => reads).toBeGreaterThan(before + 1);
  await page.getByRole("link", { name: "Trading Desk", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { auditProbe: { active: number } }).auditProbe
            .active,
      ),
    )
    .toBe(0);
});
