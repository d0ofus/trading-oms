import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("stock templates keep the current canvas and prepare/review workflow", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  expect(
    (
      await page.request.post("/fixture/stocks", {
        headers: { Origin: "http://127.0.0.1:8013" },
      })
    ).ok(),
  ).toBeTruthy();
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  const created = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" && r.url().endsWith("/api/strategies"),
  );
  await page
    .locator(".ws-library-templates")
    .getByRole("button", { name: /Previous-minute long-only breakout/ })
    .click();
  expect((await created).ok()).toBeTruthy();
  await expect(page.getByLabel("Strategy name")).toHaveValue(
    "Previous-minute long-only breakout",
  );
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  const saved = page.waitForResponse(
    (r) =>
      r.request().method() === "PUT" &&
      r.url().includes("/api/strategies/") &&
      r.request().postDataJSON()?.name === "Reusable stock browser fixture",
  );
  await page.getByLabel("Strategy name").fill("Reusable stock browser fixture");
  expect((await saved).ok()).toBeTruthy();
  await page.getByRole("button", { name: "Review & publish" }).click();
  await expect(page.getByRole("dialog")).toContainText("share-based");
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page.getByRole("button", { name: "Prepare published v1" }).click();
  await page.getByLabel("Resolved instrument").selectOption("456");
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeDisabled();
  await expect(page.getByRole("dialog")).toContainText(
    "other asset families are outside",
  );
  await page.getByLabel("Resolved instrument").selectOption("323608988");
  await expect(page.getByRole("dialog")).toContainText("Minimum 200 shares");
  await expect(page.getByLabel("Entry notional ceiling (USD)")).toHaveValue("");
  await expect(page.getByLabel("Shares", { exact: true })).toHaveValue("200");
  await expect(page.getByLabel("Protection method")).toHaveValue("broker_held");
  await page.getByLabel("Protection method").selectOption("locally_monitored");
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  await expect(page.getByRole("dialog")).toContainText("HKD");
  await page.getByText("Advanced execution policy", { exact: true }).click();
  await expect(page.getByLabel("Risk profile")).toHaveValue("stock_selected:2");
  await expect(page.getByRole("dialog")).toContainText("No ceiling");
  await expect(page.getByRole("dialog")).toContainText(
    "Locally monitored protection",
  );
  await expect(page.getByRole("dialog").getByRole("checkbox")).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: "Acknowledge local protection & arm paper run",
    }),
  ).toBeDisabled();
  await page.screenshot({ path: "test-results/stock-review.png" });
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Activity", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Activity", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("Xiaomi automatically shows the 200-share rule and USD 25 conflict without technical forms", async ({
  page,
}) => {
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await expect(
    page.getByRole("button", { name: "Prepare a run", exact: true }),
  ).toBeVisible();
  const headers = { Origin: "http://127.0.0.1:8013" };
  const catalog = await (
    await page.request.get("/api/strategies/catalog?schema_version=7")
  ).json();
  const draft = await (
    await page.request.post("/api/strategies", {
      headers,
      data: {
        name: "Xiaomi automatic rules (stock copy)",
        document: catalog.templates.at(-1).document,
        revision: 0,
      },
    })
  ).json();
  await page.request.post(`/api/strategies/${draft.id}/publish`, {
    headers,
    data: { revision: draft.revision },
  });
  await page.request.post("/fixture/stocks-valued", { headers });
  await page
    .getByRole("button", { name: "Prepare a run", exact: true })
    .click();
  await page.getByLabel("Published strategy").selectOption(draft.id);
  await page.getByLabel("Resolved instrument").selectOption("323608988");
  await expect(page.getByRole("dialog")).toContainText(
    "Reusable stock strategy",
  );
  await expect(page.getByRole("dialog")).toContainText("Minimum 200 shares");
  await expect(page.getByRole("dialog")).toContainText(
    "Budget/funding requirement",
  );
  await expect(page.getByRole("dialog")).toContainText("6000");
  await expect(page.getByRole("dialog")).toContainText(
    "Indicative stop risk: USD 7.69",
  );
  await expect(page.getByLabel("Entry notional ceiling (USD)")).toHaveValue(
    "25",
  );
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Record verified rules" }),
  ).toHaveCount(0);
  await expect(
    page.getByLabel("Minimum entry quantity", { exact: true }),
  ).toHaveCount(0);
  await page.getByText("Automatic contract rules", { exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "No manual verification form is required",
  );
  await page.screenshot({
    path: "test-results/xiaomi-automatic-rules-budget.png",
  });
});
