import { expect } from "@playwright/test";
import { test } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";

test("configure, recover, publish, replay and inspect blocked arming", async ({
  page,
}) => {
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
  await page.getByRole("button", { name: "Prepare paper run" }).click();
  await expect(
    page.getByRole("heading", { name: "Trading Desk", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("checkbox", { name: "Select Morning crossover AAPL" })
    .check();
  await page.getByRole("button", { name: /Review & arm/ }).click();
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
      page.locator(".ws-topbar").getByText("Paper", { exact: true }),
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
  await page.route("**/api/paper/session", (route) => route.abort());
  await expect(page.getByText(/Last known values are retained/)).toBeVisible();
  await expect(
    page.getByText("Morning crossover", { exact: true }).first(),
  ).toBeVisible();
  await page.unroute("**/api/paper/session");
  expect(errors).toEqual([]);
});
