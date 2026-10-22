import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("Desk prepares the selected immutable stock version and archives an inactive Xiaomi run", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const headers = { Origin: "http://127.0.0.1:8013" };
  await page.request.post("/fixture/unified/ready", { headers });
  await page.request.post("/fixture/stocks", { headers });
  const catalog = await (
    await page.request.get("/api/strategies/catalog?schema_version=7")
  ).json();
  const draft = await (
    await page.request.post("/api/strategies", {
      headers,
      data: {
        name: "Desk Xiaomi archive fixture",
        document: catalog.templates.at(-1).document,
        revision: 0,
      },
    })
  ).json();
  const published = await page.request.post(
    `/api/strategies/${draft.id}/publish`,
    { headers, data: { revision: draft.revision } },
  );
  expect(published.ok(), await published.text()).toBeTruthy();
  await page
    .getByRole("button", { name: "Prepare a run", exact: true })
    .click();
  await page.getByLabel("Published strategy").selectOption(draft.id);
  await expect(page.getByLabel("Resolved instrument")).toBeVisible();
  await page.getByLabel("Resolved instrument").selectOption("323608988");
  await expect(page.getByLabel("Shares", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Entry notional ceiling (USD)")).toHaveValue(
    "25",
  );
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeEnabled();
  const created = page.waitForResponse(
    (r) => r.request().method() === "POST" && r.url().endsWith("/api/runs"),
  );
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  const run = await (await created).json();
  expect(run.conid).toBe(323608988);
  expect(run.armed).toBe(false);
  await expect(page.getByRole("dialog")).toContainText(
    "Review paper-session authorization",
  );
  await page.keyboard.press("Escape");
  // Selection preferences are shared with earlier tests; this action uses only this run.
  const selectedNames = await page
    .locator('input[aria-label^="Select "]:checked')
    .evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("aria-label")!),
    );
  for (const name of selectedNames)
    await page.getByRole("checkbox", { name, exact: true }).uncheck();
  await page
    .getByRole("checkbox", { name: "Select Desk Xiaomi archive fixture 1810" })
    .check();
  await page
    .getByRole("button", { name: "Archive selected", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Eligible");
  await page
    .getByRole("button", { name: "Confirm archive", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("checkbox", {
      name: "Select Desk Xiaomi archive fixture 1810",
    }),
  ).toHaveCount(0);
  await page.getByText("Browse records", { exact: true }).click();
  await page.getByLabel("Record type").selectOption("runs");
  await expect(
    page.getByText("Desk Xiaomi archive fixture · 1810", { exact: true }),
  ).toBeVisible();
  const records = await (
    await page.request.get("/api/workspace/records/runs")
  ).json();
  expect(
    records.items.find((i: { id: string }) => i.id === run.id).archived,
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("contract search displays SMART failure and SEHK results without changing the route", async ({
  page,
}) => {
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const headers = { Origin: "http://127.0.0.1:8013" };
  await page.request.post("/fixture/unified/ready", { headers });
  await page.request.post("/fixture/stocks", { headers });
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel("Symbol or name", { exact: true }).fill("1810");
  await page
    .getByRole("combobox", { name: "Security type", exact: true })
    .selectOption("STK");
  await page.getByLabel("Currency", { exact: true }).fill("HKD");
  await page
    .getByLabel("Direct contract ID", { exact: true })
    .fill("323608988");
  await page.getByLabel("Routing exchange", { exact: true }).fill("SMART");
  await page.getByRole("button", { name: "Find contracts" }).click();
  const search = page.getByRole("region", { name: "Current contract search" });
  await expect(search).toContainText("IBKR code 200");
  await expect(
    page.getByLabel("Routing exchange", { exact: true }),
  ).toHaveValue("SMART");
  await page.getByLabel("Routing exchange", { exact: true }).fill("SEHK");
  await page.getByRole("button", { name: "Find contracts" }).click();
  await expect(search).toContainText("1 contract results");
  await expect(search).toContainText("323608988");
  await expect(
    page.getByLabel("Routing exchange", { exact: true }),
  ).toHaveValue("SEHK");
});

test("explicit stock conversion selects the new draft; Testing uses the shared bound preparation", async ({
  page,
}) => {
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const headers = { Origin: "http://127.0.0.1:8013" };
  await page.request.post("/fixture/stocks", { headers });
  const catalog = await (
    await page.request.get("/api/strategies/catalog?schema_version=6")
  ).json();
  const document = catalog.templates.find(
    (t: { document: { nodes: { kind: string }[] } }) =>
      t.document.nodes.some((n) => n.kind === "long_breakout"),
  ).document;
  const draft = await (
    await page.request.post("/api/strategies", {
      headers,
      data: { name: "Legacy conversion fixture", document, revision: 0 },
    })
  ).json();
  const original = await (
    await page.request.post(`/api/strategies/${draft.id}/publish`, {
      headers,
      data: { revision: draft.revision },
    })
  ).json();
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page
    .locator(".ws-library-items")
    .getByRole("button", { name: /Legacy conversion fixture/ })
    .click();
  await page.getByRole("button", { name: "Review & publish" }).click();
  const conversion = page.waitForResponse((r) =>
    r.url().endsWith("/api/strategies/convert-stock"),
  );
  await page.getByRole("button", { name: "Create reusable copy" }).click();
  const copy = await (await conversion).json();
  await expect(page.getByLabel("Strategy name")).toHaveValue(
    "Legacy conversion fixture (stock copy)",
  );
  expect(copy.document.schema_version).toBe(7);
  expect(copy.document.settings.notional).toBe(document.settings.notional);
  const unchanged = await (
    await page.request.get(`/api/strategies/${draft.id}/versions/1`)
  ).json();
  expect(unchanged.hash).toBe(original.hash);
  expect(unchanged.document.schema_version).toBe(6);
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await page.route("**/api/testing/results", (route) =>
    route.fulfill({
      json: [
        {
          id: "synthetic-result",
          strategy_id: copy.id,
          strategy_name: copy.name,
          version: 1,
          dataset: "synthetic",
          dataset_source: "synthetic_fixture",
          timestamp: "2026-09-22T00:00:00Z",
          ticks: 0,
          realized_pnl: "0",
          signals: [],
          trades: [],
          open_position: null,
          working_entry: false,
          limitations: [],
        },
      ],
    }),
  );
  await page.getByRole("link", { name: "Testing", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Published strategy", exact: true })
    .selectOption(copy.id);
  await expect(
    page.getByRole("combobox", { name: "Version", exact: true }),
  ).toHaveValue("1");
  await page
    .getByRole("button", { name: "Prepare a run", exact: true })
    .click();
  await page.getByLabel("Resolved instrument").selectOption("323608988");
  await expect(page.getByLabel("Shares", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toContainText(
    "Review paper-session authorization",
  );
});
