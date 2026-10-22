import { expect } from "@playwright/test";
import { test } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";

test("crypto workspace identifies local fills, fractional settings and history separately", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:8014/desk");
  await expect(
    page.getByText(".\\scripts\\start-crypto-sim.ps1", { exact: true }),
  ).toBeVisible();
  await page.goto("about:blank");
  await page.goto(
    "http://127.0.0.1:8014/desk#pair=synthetic-crypto-browser-pairing-only",
  );
  await expect(
    page.getByText("Simulation — live Paxos data — local fills", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("$59,999.75", { exact: true })).toBeVisible();
  await expect(page.getByText("$60,000.25", { exact: true })).toBeVisible();
  await expect(
    page.getByText("History downloaded", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/10\/10 complete reference sessions/),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/crypto-desk.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page.getByRole("button", { name: /Moving average crossover/ }).click();
  await expect(
    page.getByRole("combobox", { name: "Crypto symbol", exact: true }),
  ).toHaveValue("BTC");
  await page.getByLabel("Fixed-quantity ceiling").fill("0.0001");
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByText("Daily loss stop", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByText("Daily P/L is informational and never blocks entries."),
  ).toBeVisible();
  await expect(
    page.getByText("No broker orders", { exact: true }),
  ).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  expect(errors).toEqual([]);
  const fixture = async (step: string) => {
    const response = await page.request.post(
      `http://127.0.0.1:8014/fixture/oca/${step}`,
      { headers: { Origin: "http://127.0.0.1:8014" } },
    );
    expect(response.ok(), await response.text()).toBeTruthy();
  };
  await fixture("ready");
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page.getByRole("button", { name: /Previous 1-minute candle/ }).click();
  await expect(page.getByLabel("Strategy name")).toHaveValue(
    "Previous 1-minute candle — OCA breakout",
  );
  await page.getByLabel("Strategy name").fill("Weekend OCA test");
  await expect(page.getByLabel("Candle interval")).toBeDisabled();
  await expect(
    page.getByText(/Shorts are hypothetical local positions/),
  ).toBeVisible();
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByRole("button", { name: "Review & publish" }).click();
  await expect(page.getByRole("dialog")).toContainText("Fixed 1% protection");
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page.getByRole("button", { name: "Prepare published v1" }).click();
  await page.getByLabel("Resolved instrument").selectOption("1");
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  await expect(page.getByRole("dialog")).toContainText("authorization");
  await fixture("warm");
  await expect(page.getByLabel("Paired entry review")).toContainText(
    "Combined pending reservation",
  );
  await expect(page.getByLabel("Paired entry review")).toContainText(
    "Short sell stop-market",
  );
  const armResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/runs/arm") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Arm selected simulation session" })
    .click();
  expect((await armResponse).ok()).toBeTruthy();
  await page.getByRole("link", { name: "Trading Desk", exact: true }).click();
  await fixture("minute");
  await expect(page.getByLabel("OCA group status")).toContainText(
    "Awaiting direction",
  );
  await fixture("short");
  await expect(
    page.getByRole("button", { name: "Buy to cover", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Protection verified", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/oca-short-protected.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Buy to cover", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Buy to cover an owned short position",
  );
  const closeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/close") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Request close of owned position" })
    .click();
  expect((await closeResponse).ok()).toBeTruthy();
  await fixture("exit");
  await expect(
    page.getByText("No owned positions", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("OCA group status")).toContainText("Complete");
  await expect(page.getByText(/One OCA trade completed/)).toBeVisible();
  await fixture("warm");
  await page
    .getByRole("checkbox", { name: "Select Weekend OCA test BTC" })
    .check();
  await page.getByRole("button", { name: /Review & arm/ }).click();
  const secondArm = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/runs/arm") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Arm selected simulation session" })
    .click();
  expect((await secondArm).ok()).toBeTruthy();
  await fixture("minute");
  await fixture("long");
  await expect(
    page.getByRole("button", { name: "Close owned position", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Protection verified", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Close owned position", exact: true })
    .click();
  const longClose = page.waitForResponse(
    (response) =>
      response.url().endsWith("/close") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Request close of owned position" })
    .click();
  expect((await longClose).ok()).toBeTruthy();
  await fixture("exit");
  await expect(
    page.getByText("No owned positions", { exact: true }),
  ).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  expect(errors).toEqual([]);
});

test("configure, recover, publish, replay and inspect blocked arming", async ({
  page,
}) => {
  // Exercise the existing schema-6 workflow and visual baselines. The schema-7
  // catalog/binding is covered separately by zzz-stock-strategies.spec.ts.
  await page.route(
    "**/api/strategies/catalog?schema_version=8",
    async (route) => {
      const response = await route.fetch({
        url: route
          .request()
          .url()
          .replace("schema_version=8", "schema_version=6"),
      });
      await route.fulfill({ response });
    },
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  async function visual(name: string) {
    if (await page.evaluate(() => navigator.platform === "Win32")) {
      const options = {
        animations: "disabled" as const,
        style: ".ws-toast { visibility: hidden !important; }",
        maxDiffPixelRatio: 0.015,
        mask: [
          page.locator(".ws-footer"),
          page.locator(".ws-save-state"),
          page.locator(".ws-arm-summary > div:nth-child(2)"),
          page.locator(".ws-arm-summary > div:nth-child(3)"),
        ],
      };
      if (name === "arming-blocked.png") {
        // The modal has its own scroll area. Exclude the background document,
        // whose full-page height changes when Radix locks its scrollbar.
        await expect(page.getByRole("dialog")).toHaveScreenshot(name, options);
      } else {
        await expect(page).toHaveScreenshot(name, {
          ...options,
          // Compare the supported desktop viewport. Full-page inspection
          // artifacts below retain scrollable content without coupling the
          // baseline dimensions to native table scrollbar heights.
          fullPage: false,
        });
      }
    }
  }
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await expect(
    page.getByRole("heading", { name: "Your desk is ready for a strategy" }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/desk-dark.png", fullPage: true });
  await visual("desk-dark.png");
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page.getByRole("button", { name: /Moving average crossover/ }).click();
  await expect(page.getByLabel("Strategy name")).toHaveValue(
    "Moving average crossover",
  );
  await page.getByLabel("Strategy name").fill("Morning crossover");
  await expect(page.getByText(/^Saved ·/)).toHaveCount(0);
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  const before = await page.evaluate(
    async () => (await (await fetch("/api/strategies")).json())[0].document,
  );
  await page.getByRole("tab", { name: "Canvas", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(
    before.nodes.length,
  );
  await page.screenshot({
    path: "test-results/studio-canvas.png",
    fullPage: true,
  });
  await visual("studio-canvas.png");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("tab", { name: "Guided configuration" }).click();
  const after = await page.evaluate(
    async () => (await (await fetch("/api/strategies")).json())[0].document,
  );
  expect(after).toEqual(before);
  await page.reload();
  await expect(page.getByLabel("Strategy name")).toHaveValue(
    "Morning crossover",
  );
  await expect(
    page.getByRole("button", { name: "Review & publish" }),
  ).toBeEnabled();
  await expect(
    page.getByText("Entry conditions & shared calculations", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/studio-guided.png",
    fullPage: true,
  });
  await visual("studio-guided.png");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Review & publish" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Review executable version",
  );
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".ws-save-state")).toContainText(
    "Running versions stay pinned",
  );
  await page.getByRole("link", { name: "Testing", exact: true }).click();
  await page
    .getByRole("button", { name: "Add synthetic practice data" })
    .click();
  await expect(
    page.getByRole("button", { name: "Run replay", exact: true }),
  ).toBeEnabled();
  const replayResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/testing/replay") &&
      response.request().method() === "POST",
    { timeout: 60000 },
  );
  await page.getByRole("button", { name: "Run replay", exact: true }).click();
  expect((await replayResponse).status()).toBe(200);
  await expect(
    page.getByRole("heading", { name: "Replay trade ledger" }),
  ).toBeVisible();
  await expect(
    page.getByText("Synthetic exercise", { exact: false }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Prepare a run" }).click();
  await page.getByLabel("Resolved instrument").selectOption("100");
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Review paper-session authorization",
  );
  await expect(
    page.getByRole("button", { name: "Arm selected paper session" }),
  ).toBeDisabled();
  await expect(page.getByRole("dialog")).toContainText("Gateway handshake");
  await page.screenshot({
    path: "test-results/arming-blocked.png",
    fullPage: true,
  });
  await visual("arming-blocked.png");
  // Session-dependent clock cells are masked in the dialog visual baseline.
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Back to desk" }).click();
  await page.getByRole("link", { name: "Trading Desk", exact: true }).click();
  await page
    .getByRole("button", { name: "Emergency stop", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Emergency stop active" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Emergency stop active" }),
  ).toBeVisible();
  await visual("desk-recovery.png");
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Prepare your paper environment" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/setup-dark.png",
    fullPage: true,
  });
  await visual("setup-dark.png");
  const darkAudit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(darkAudit.violations).toEqual([]);
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await page.screenshot({
    path: "test-results/setup-light.png",
    fullPage: true,
  });
  await visual("setup-light.png");
  const lightAudit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(lightAudit.violations).toEqual([]);
  for (const viewport of [
    { width: 1280, height: 720 },
    { width: 1920, height: 1080 },
    { width: 960, height: 540 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(
      page.locator(".ws-topbar").getByText("IBKR Paper", { exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Strategy Studio" }).click();
    await expect(
      page.getByRole("button", { name: "Review & publish" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `test-results/studio-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.goBack();
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe(
    "BODY",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page.evaluate(async () => {
    const draft = (await (await fetch("/api/strategies")).json())[0];
    const response = await fetch(`/api/strategies/${draft.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Concurrent edit",
        document: draft.document,
        revision: draft.revision,
      }),
    });
    if (!response.ok) throw new Error("Concurrent edit fixture failed");
  });
  await page.getByLabel("Strategy name").fill("My retained edits");
  await expect(
    page.getByText("This draft changed in another session."),
  ).toBeVisible();
  expect(
    await page.evaluate(async () => {
      const draft = (await (await fetch("/api/strategies")).json())[0];
      return (
        await (await fetch(`/api/strategies/${draft.id}/versions/1`)).json()
      ).name;
    }),
  ).toBe("Morning crossover");
  await page.getByRole("button", { name: "Save my copy" }).click();
  await expect(page.getByLabel("Strategy name")).toHaveValue(
    "My retained edits recovered",
  );
  await page.getByRole("link", { name: "Trading Desk", exact: true }).click();
  await page.route("**/api/workspace/overview", (route) => route.abort());
  await expect(page.getByText(/Last known values are retained/)).toBeVisible();
  await expect(
    page.getByText("Morning crossover", { exact: true }).first(),
  ).toBeVisible();
  await page.unroute("**/api/workspace/overview");
  expect(errors).toEqual([]);
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page.getByRole("button", { name: /Previous 1-minute candle/ }).click();
  await expect(page.getByLabel("Stock or ETF symbol")).toHaveCount(0);
  await expect(page.getByLabel("Candle interval")).toBeDisabled();
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByRole("button", { name: "Review & publish" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "short sell stop-market",
  );
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(errors).toEqual([]);
});
