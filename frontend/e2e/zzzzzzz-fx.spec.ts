import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("FX copy preserves the canvas and exposes price source, currency units and one final review", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const headers = { Origin: "http://127.0.0.1:8013" };
  expect(
    (await page.request.post("/fixture/fx", { headers })).ok(),
  ).toBeTruthy();
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page
    .locator(".ws-library-templates")
    .getByRole("button", { name: /Previous-minute long-only breakout/ })
    .click();
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  const initialNodes = await page.locator(".react-flow__node").count();
  await page.getByRole("button", { name: "Review & publish" }).click();
  const copied = page.waitForResponse((r) =>
    r.url().endsWith("/api/strategies/convert-fx"),
  );
  await page
    .getByRole("button", { name: "Create FX copy", exact: true })
    .click();
  const draft = await (await copied).json();
  expect(draft.document.schema_version).toBe(9);
  await expect(page.getByLabel("Strategy name")).toHaveValue(/\(FX copy\)$/);
  await expect(page.locator(".react-flow__node")).toHaveCount(initialNodes);
  await expect(page.getByLabel("Signal price source")).toHaveValue("MIDPOINT");
  await page.getByLabel("Signal price source").selectOption("BID");
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByLabel("Signal price source").selectOption("ASK");
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByLabel("Signal price source").selectOption("MIDPOINT");
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByRole("button", { name: "Review & publish" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Equality does not trigger",
  );
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page.getByRole("button", { name: "Prepare published v1" }).click();
  await page.getByLabel("Resolved instrument").selectOption("14433401");
  await expect(page.getByLabel("Quantity (AUD)")).toHaveValue("1");
  await expect(page.getByLabel("Entry notional ceiling (USD)")).toHaveValue("");
  await expect(page.getByRole("dialog")).toContainText("USD per AUD");
  await expect(page.getByLabel("Trading session")).toHaveValue("fx");
  await expect(
    page.getByLabel("Minimum entry quantity", { exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Quantity (AUD)").fill("25000");
  await page.getByLabel("Protection method").selectOption("locally_monitored");
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeEnabled();
  await page.screenshot({ path: "test-results/fx-preparation.png" });
  let fresh = false;
  let reviewReads = 0;
  await page.route("**/api/runs/arm-preview", async (route) => {
    reviewReads++;
    const response = await route.fetch();
    const value = await response.json();
    await route.fulfill({
      json: {
        ...value,
        eligible: true,
        eligible_after_recovery_ack: false,
        recoveries: [],
        checks: [
          {
            code: "fx_data",
            title: "FX feed and history",
            feed_health: "healthy",
            signal_source: "MIDPOINT",
            execution_state: fresh ? "waiting_live_minute" : "waiting_quotes",
            execution_detail: fresh
              ? "Waiting for a complete live minute after authorization."
              : "Waiting for fresh MIDPOINT and bid/ask.",
            passed: fresh,
            stable: true,
            authorization_ready: true,
            status: fresh ? "ready" : "waiting",
            detail: fresh
              ? "Synthetic fresh FX observations"
              : "Healthy quiet feed; waiting for fresh MIDPOINT and bid/ask",
            remediation: null,
          },
          {
            code: "fx_funding",
            title: "Broker buying power and quantity",
            passed: fresh,
            stable: true,
            authorization_ready: true,
            status: fresh ? "ready" : "waiting",
            detail: fresh
              ? "Broker credit ready"
              : "Waiting for quote evidence",
            remediation: null,
          },
        ],
      },
    });
  });
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Review paper-session authorization");
  await expect(dialog).toContainText("25000 AUD");
  await expect(dialog).toContainText("MKT/IOC");
  await expect(dialog).toContainText(
    "immediately preceding completed IBKR candle",
  );
  await expect(dialog).toContainText(
    "available immediately after authorization",
  );
  await expect(dialog.getByRole("checkbox")).toHaveCount(0);
  await expect(dialog).toContainText("Financing costs may apply");
  const dataRow = dialog
    .locator(".ws-check")
    .filter({ hasText: "FX feed and history" });
  const fundingRow = dialog
    .locator(".ws-check")
    .filter({ hasText: "Broker buying power and quantity" });
  await expect(dataRow).toBeVisible();
  await expect(fundingRow).toBeVisible();
  await expect(dataRow).toHaveClass("ws-check passed");
  await expect(fundingRow).toHaveClass("ws-check waiting");
  await expect(dialog.getByText("Resolve", { exact: true })).toHaveCount(0);
  await expect(
    dialog.getByRole("button", {
      name: "Acknowledge local protection & arm paper run",
    }),
  ).toBeEnabled();
  await dataRow.evaluate((element) =>
    element.setAttribute("data-stable-row", "original"),
  );
  fresh = true;
  await expect(dataRow).toContainText("Waiting for a complete live minute");
  await expect(dataRow).toHaveAttribute("data-stable-row", "original");
  fresh = false;
  await expect(dataRow).toContainText("Waiting for fresh MIDPOINT and bid/ask");
  await expect(dataRow).toHaveClass("ws-check passed");
  await expect(dataRow).toHaveAttribute("data-stable-row", "original");
  await expect(fundingRow).toBeVisible();
  let authorization = 0;
  await page.route("**/api/runs/arm", async (route) => {
    const body = route.request().postDataJSON();
    expect(body.fx_policy_revision).toEqual(["idealpro_broker_candles_v2"]);
    expect(body.funding_policy_acknowledged).toBe("paper_buying_power_v1");
    expect(body.local_protection_acknowledged).toBe(true);
    expect(body.execution_plan_revisions).toBeTruthy();
    authorization++;
    await route.fulfill({ json: { armed: body.ids } });
  });
  await page.screenshot({ path: "test-results/fx-authorization.png" });
  await dialog
    .getByRole("button", {
      name: "Acknowledge local protection & arm paper run",
    })
    .click();
  await expect(dialog).toHaveCount(0);
  expect(authorization).toBe(1);
  const stoppedReads = reviewReads;
  await page.waitForTimeout(2200);
  expect(reviewReads).toBe(stoppedReads);
  expect(errors).toEqual([]);
});
