import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("schema 8 preparation proceeds directly to a live, single-action review with bounded polling", async ({
  page,
}) => {
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const headers = { Origin: "http://127.0.0.1:8013" };
  await page.request.post("/fixture/preparation", { headers });
  const catalog = await (
    await page.request.get("/api/strategies/catalog?schema_version=8")
  ).json();
  const draft = await (
    await page.request.post("/api/strategies", {
      headers,
      data: {
        name: "Minimal META fixture",
        document: catalog.templates.at(-1).document,
        revision: 0,
      },
    })
  ).json();
  await page.request.post(`/api/strategies/${draft.id}/publish`, {
    headers,
    data: { revision: draft.revision },
  });
  let ready = false;
  let failure = false;
  let reads = 0;
  let active = 0;
  let maximum = 0;
  await page.route("**/api/runs/arm-preview", async (route) => {
    reads++;
    maximum = Math.max(maximum, ++active);
    try {
      const response = await route.fetch();
      if (failure) {
        await route.fulfill({
          status: 503,
          json: { detail: "Synthetic readiness unavailable" },
        });
        return;
      }
      const value = await response.json();
      await route.fulfill({
        json: {
          ...value,
          eligible: ready,
          eligible_after_recovery_ack: false,
          recoveries: [],
          checks: [
            {
              code: "trade",
              title: "META execution data",
              passed: ready,
              status: ready ? "ready" : "waiting",
              detail: ready
                ? "Fresh execution evidence"
                : "Waiting for fresh execution trade and bid/ask",
              remediation: null,
            },
          ],
        },
      });
    } finally {
      active--;
    }
  });
  await page
    .getByRole("button", { name: "Prepare a run", exact: true })
    .click();
  await page.getByLabel("Published strategy").selectOption(draft.id);
  await page.getByLabel("Resolved instrument").selectOption("107113386");
  await expect(page.getByLabel("Shares", { exact: true })).toHaveValue("1");
  await expect(page.getByLabel("Entry notional ceiling (USD)")).toHaveValue("");
  await page.getByLabel("Shares", { exact: true }).fill("20");
  await page.getByLabel("Trading session").selectOption("premarket_regular");
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Review paper-session authorization");
  await expect(dialog.getByRole("checkbox")).toHaveCount(0);
  await expect(dialog).toContainText(
    "Waiting for fresh execution trade and bid/ask",
  );
  await expect(dialog.getByText("Resolve", { exact: true })).toHaveCount(0);
  const arm = dialog.getByRole("button", {
    name: "Acknowledge local protection & arm paper run",
  });
  await expect(arm).toBeDisabled();
  ready = true;
  await expect(arm).toBeEnabled();
  failure = true;
  await expect(dialog).toContainText("Current readiness is unavailable");
  await expect(arm).toBeDisabled();
  failure = false;
  await expect(arm).toBeEnabled();
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.waitForTimeout(150);
  const hiddenReads = reads;
  await page.waitForTimeout(2200);
  expect(reads).toBe(hiddenReads);
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => false,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(arm).toBeEnabled();
  let authorizations = 0;
  await page.route("**/api/runs/arm", async (route) => {
    authorizations++;
    const body = route.request().postDataJSON();
    expect(body.local_protection_acknowledged).toBe(true);
    expect(body.review_fingerprint).toBeTruthy();
    expect(body.resume_policy).toBe("same_engine_routine_v1");
    // Exercise the browser contract without authorizing an actual fixture engine.
    await route.fulfill({ json: { armed: body.ids } });
  });
  await page.screenshot({ path: "test-results/minimal-paper-review.png" });
  await arm.click();
  await expect(dialog).toHaveCount(0);
  const finalReads = reads;
  await page.waitForTimeout(2200);
  expect(reads).toBe(finalReads);
  expect(maximum).toBe(1);
  expect(authorizations).toBe(1);
});
