import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("paused unsubscribed stock runs cannot block FX candles or mislabel the initial queue", async ({
  page,
}) => {
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const headers = { Origin: "http://127.0.0.1:8013" };
  const queued = await page.request.post("/fixture/fx-scheduling/queued", {
    headers,
  });
  expect(queued.ok()).toBeTruthy();
  let fixture = await queued.json();
  expect(fixture.incidents).toEqual([]);
  expect(fixture.orders).toEqual([]);
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: { ...(await response.json()), data: [fixture.data] },
    });
  });
  let candleReads = 0;
  await page.route("**/api/market-data/14433401/candles?*", async (route) => {
    candleReads++;
    await route.fulfill({ json: fixture.candles });
  });
  await page.reload();
  const panel = page
    .locator(".ws-market-detail")
    .filter({ hasText: "AUD.USD" });
  await expect(panel).toContainText("MIDPOINT history: Queued");
  await expect(panel).not.toContainText("Retry queued");
  await expect(panel).not.toContainText("null USD");
  await expect(panel).not.toContainText("session ?");
  await expect(
    panel.locator(".ws-quote-grid").locator("div").first(),
  ).toContainText("Unavailable");
  await panel.getByText("View candles", { exact: true }).click();
  await expect(panel).toContainText("No supported candles received");
  const progressed = await page.request.post("/fixture/fx-scheduling/ready", {
    headers,
  });
  expect(progressed.ok()).toBeTruthy();
  fixture = await progressed.json();
  expect(fixture.incidents).toEqual([]);
  expect(fixture.orders).toEqual([]);
  expect(fixture.data.history_ready).toBe(true);
  expect(fixture.data.execution_fresh).toBe(true);
  await expect(panel).toContainText("MIDPOINT history: History complete");
  await expect(panel).toContainText("MIDPOINT history / complete");
  await expect(panel).toContainText("0.65005 USD per AUD");
  await expect(panel).not.toContainText("No supported candles received");
  await expect(panel).not.toContainText("Waiting for fresh trades");
  await expect(panel.getByText("Feed live", { exact: true })).toBeVisible();
  fixture.data = {
    ...fixture.data,
    ready: false,
    execution_fresh: false,
    execution_detail:
      "Waiting for clock alignment of timestamped observations.",
    ages: { "signal source": -0.25, "signal receipt": 0.1 },
  };
  await expect(panel).toContainText("Waiting for clock alignment");
  await expect(panel).toContainText("0.3s ahead of clock");
  await expect(panel.getByText("Feed live", { exact: true })).toBeVisible();
  fixture.data = {
    ...fixture.data,
    execution_detail: "Waiting for fresh timestamped observations.",
    ages: { "signal source": 17, "signal receipt": 17 },
  };
  await expect(panel).toContainText(
    "Waiting for fresh timestamped observations",
  );
  await expect(panel.getByText("Feed live", { exact: true })).toBeVisible();
  fixture.data = {
    ...fixture.data,
    stream_health: "blocked",
    feed_health: "blocked",
    execution_detail: "Required FX stream was rejected by the broker.",
  };
  await expect(panel).toContainText("Feed needs attention");
  await expect(panel).toContainText("rejected by the broker");
  await page.screenshot({ path: "test-results/fx-data-recovered.png" });
  await panel.getByText("View candles", { exact: true }).click();
  await page.waitForTimeout(300);
  const closedReads = candleReads;
  await page.waitForTimeout(2400);
  expect(candleReads).toBe(closedReads);
});
