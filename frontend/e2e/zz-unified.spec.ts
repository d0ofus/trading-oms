import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("one paper workspace searches contracts, binds reusable templates and recovers local protection", async ({
  page,
}) => {
  // Retain the legacy schema-6 crypto creation and execution regression.
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
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const fixture = async (step: string) => {
    const response = await page.request.post(`/fixture/unified/${step}`, {
      headers: { Origin: "http://127.0.0.1:8013" },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
  };
  await fixture("ready");
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel("Symbol or name", { exact: true }).fill("BTC");
  await page
    .getByRole("combobox", { name: "Security type", exact: true })
    .selectOption("CRYPTO");
  await page.getByLabel("Routing exchange", { exact: true }).fill("PAXOS");
  await page.getByRole("button", { name: "Find contracts" }).click();
  await expect(
    page.getByText(/BTC · CRYPTO · USD · PAXOS · ID 456/),
  ).toBeVisible();
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page
    .locator(".ws-library-templates")
    .getByRole("button", { name: /Previous 1-minute candle/ })
    .click();
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page.getByRole("button", { name: "Prepare published v1" }).click();
  await page.getByLabel("Resolved instrument").selectOption("456");
  await expect(page.getByRole("alert")).toContainText("PAXOS does not support");
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeDisabled();
  await page.getByLabel("Resolved instrument").selectOption("100");
  await expect(page.getByRole("dialog")).toContainText(
    "Broker-held protection",
  );
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: /Previous-minute long-only breakout/ })
    .click();
  await expect(page.getByLabel("Strategy name")).toHaveValue(
    "Previous-minute long-only breakout",
  );
  const savedName = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response.url().includes("/api/strategies/") &&
      response.request().postDataJSON()?.name === "Unified crypto paper test",
  );
  await page.getByLabel("Strategy name").fill("Unified crypto paper test");
  expect((await savedName).ok()).toBeTruthy();
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page.getByRole("button", { name: "Prepare published v1" }).click();
  await page.getByLabel("Resolved instrument").selectOption("456");
  await expect(page.getByRole("dialog")).toContainText(
    "Locally monitored protection",
  );
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  await expect(page.getByRole("dialog")).toContainText("authorization");
  await fixture("warm");
  await expect(page.getByRole("dialog")).toContainText("$25");
  await page
    .getByRole("button", { name: "Arm selected paper session" })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("link", { name: "Trading Desk", exact: true }).click();
  await fixture("entry");
  await expect(page.getByLabel("Local protection status")).toContainText(
    "Active",
  );
  await expect(page.getByLabel("Local protection status")).toContainText(
    "99.00",
  );
  await fixture("outage");
  await expect(page.getByLabel("Local protection status")).toContainText(
    "Suspended",
  );
  await fixture("recovery");
  await expect(page.getByLabel("Local protection status")).toContainText(
    "Active",
  );
  await page
    .getByRole("button", { name: "Close owned position", exact: true })
    .click();
  const closeRequested = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/operations/positions/") &&
      response.url().endsWith("/close"),
  );
  await page
    .getByRole("button", { name: "Request close of owned position" })
    .click();
  expect((await closeRequested).ok()).toBeTruthy();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await fixture("exit");
  await expect(page.getByLabel("Local protection status")).toContainText(
    "Closed",
  );
  await expect(
    page.getByText(/Trade completed; manually review and arm again/),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
