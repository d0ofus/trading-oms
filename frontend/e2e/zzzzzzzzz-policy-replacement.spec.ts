import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("legacy FX review adopts current policies inline and preserves exact settings and history", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const headers = { Origin: "http://127.0.0.1:8013" };
  const setup = await page.request.post("/fixture/fx-policy", { headers });
  expect(setup.ok()).toBeTruthy();
  const { run: original } = await setup.json();
  let incompatible = false;
  let reviewReads = 0;
  let replacements = 0;
  let authorizations = 0;
  await page.route("**/api/runs/arm-preview", async (route) => {
    reviewReads++;
    try {
      const response = await route.fetch();
      const value = await response.json();
      if (
        incompatible &&
        value.policy_replacement.items.some(
          (item: { needs_replacement: boolean }) => item.needs_replacement,
        )
      ) {
        value.policy_replacement.eligible = false;
        value.policy_replacement.items[0].blockers = [
          "Synthetic changed quantity rules. Review preparation.",
        ];
      }
      await route.fulfill({ json: value });
    } catch (error) {
      // Closing/reloading intentionally aborts a readiness request in flight.
      if (!/disposed|Target page.*closed|aborted/.test(String(error)))
        throw error;
    }
  });
  await page.route("**/api/runs/policy-replacement", async (route) => {
    replacements++;
    const body = route.request().postDataJSON();
    expect(body.expected_binding_hashes[original.id]).toBe(
      original.binding.hash,
    );
    expect(body.target_policy_revision).toBe("paper_buying_power_v1");
    await route.continue();
  });
  await page.route("**/api/runs/arm", async (route) => {
    authorizations++;
    await route.abort();
  });
  await page.reload();
  for (const checkbox of await page
    .locator('input[aria-label^="Select "]:checked')
    .all())
    await checkbox.uncheck();
  await page
    .getByRole("checkbox", { name: "Select Legacy FX policy fixture AUD" })
    .check();
  await expect(
    page.getByRole("button", { name: /Review & arm/ }),
  ).toBeVisible();
  if (await page.getByRole("button", { name: "Close run details" }).isVisible())
    await page.getByRole("button", { name: "Close run details" }).click();
  await page.getByRole("button", { name: /Review & arm/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("earlier cash-only execution policy");
  await expect(dialog).toContainText("0.01 AUD");
  await expect(dialog).toContainText("no intentional borrowing");
  incompatible = true;
  await expect(
    dialog.getByRole("button", { name: "Use current execution policy" }),
  ).toBeDisabled();
  await dialog.getByRole("button", { name: "Review preparation" }).click();
  await expect(dialog).toContainText("Prepare strategy run");
  await expect(dialog.getByLabel("Resolved instrument")).toHaveValue(
    "14433401",
  );
  await expect(dialog.getByLabel("Quantity (AUD)")).toHaveValue("0.01");
  await expect(dialog.getByLabel("Protection method")).toHaveValue(
    "broker_held",
  );
  await expect(dialog.getByLabel("Entry notional ceiling (USD)")).toHaveValue(
    "",
  );
  await expect(dialog).toContainText("Broker-permitted borrowing");
  await expect(dialog).not.toContainText("No top-ups, borrowing");
  await page.keyboard.press("Escape");
  incompatible = false;
  await expect(
    page.getByRole("button", { name: /Review & arm/ }),
  ).toBeVisible();
  if (await page.getByRole("button", { name: "Close run details" }).isVisible())
    await page.getByRole("button", { name: "Close run details" }).click();
  await page.getByRole("button", { name: /Review & arm/ }).click();
  const replacementResponse = page.waitForResponse((r) =>
    r.url().endsWith("/api/runs/policy-replacement"),
  );
  await expect(
    dialog.getByRole("button", { name: "Use current execution policy" }),
  ).toBeEnabled();
  await dialog
    .getByRole("button", { name: "Use current execution policy" })
    .click();
  const response = await replacementResponse;
  expect(response.ok(), await response.text()).toBeTruthy();
  const result = await response.json();
  expect(result.review_ids).not.toContain(original.id);
  await expect(dialog).toContainText("Broker buying power and quantity");
  await expect(dialog).toContainText("0.01 AUD");
  await expect(dialog).toContainText("Financing costs may apply");
  await expect(dialog).not.toContainText("no intentional borrowing");
  await expect(
    dialog.getByRole("button", { name: "Use current execution policy" }),
  ).toHaveCount(0);
  const records = await (
    await page.request.get("/api/workspace/records/runs")
  ).json();
  const source = records.items.find(
    (r: { id: string }) => r.id === original.id,
  );
  const target = records.items.find(
    (r: { id: string }) => r.id === result.review_ids[0],
  );
  expect(source.binding).toEqual(original.binding);
  expect(target.binding.sizing).toEqual(original.binding.sizing);
  expect(target.binding.strategy_hash).toBe(original.binding.strategy_hash);
  expect(target.binding.execution_plan.funding_policy).toBe(
    "paper_buying_power_v1",
  );
  expect(target.binding.execution_plan.authorization_policy).toBe(
    "quiet_fx_v1",
  );
  expect(source.armed).toBe(false);
  expect(target.armed).toBe(false);
  await page.screenshot({ path: "test-results/policy-replacement.png" });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  const stopped = reviewReads;
  await page.waitForTimeout(2200);
  expect(reviewReads).toBe(stopped);
  // Adoption must survive leaving the review, navigation and a full reload.
  await page
    .getByRole("link", { name: /Strategy Studio/ })
    .first()
    .click();
  await page
    .getByRole("link", { name: /Trading Desk/ })
    .first()
    .click();
  await page.reload();
  await expect(
    page.getByRole("button", { name: /Review & arm/ }),
  ).toBeVisible();
  if (await page.getByRole("button", { name: "Close run details" }).isVisible())
    await page.getByRole("button", { name: "Close run details" }).click();
  await page.getByRole("button", { name: /Review & arm/ }).click();
  await expect(dialog).toContainText("Broker buying power and quantity");
  await expect(dialog).not.toContainText("no intentional borrowing");
  await page.keyboard.press("Escape");
  const archivePreview = await (
    await page.request.post("/api/runs/archive-preview", {
      headers,
      data: { ids: result.review_ids },
    })
  ).json();
  const archive = await page.request.post("/api/runs/archive-confirm", {
    headers,
    data: {
      preview_id: archivePreview.preview_id,
      mutation_id: "a8".repeat(16),
    },
  });
  expect(archive.ok(), await archive.text()).toBeTruthy();
  await page.reload();
  // Explicitly review the old run again to offer restoration of its linked target.
  await page
    .getByRole("checkbox", {
      name: "Select Legacy FX policy fixture AUD",
      exact: true,
    })
    .check();
  // Remove the archived selection through the fixture's normal saved selection shape.
  await page.evaluate((id) => {
    localStorage.setItem("oms.workspace.desk.selected", JSON.stringify([id]));
  }, original.id);
  await page.reload();
  await expect(
    page.getByRole("button", { name: /Review & arm/ }),
  ).toBeVisible();
  if (await page.getByRole("button", { name: "Close run details" }).isVisible())
    await page.getByRole("button", { name: "Close run details" }).click();
  await page.getByRole("button", { name: /Review & arm/ }).click();
  await expect(
    dialog.getByRole("button", { name: "Restore current-policy run" }),
  ).toBeEnabled();
  await dialog
    .getByRole("button", { name: "Restore current-policy run" })
    .click();
  await expect(dialog).toContainText("Broker buying power and quantity");
  await expect(dialog).not.toContainText("no intentional borrowing");
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(
    page.getByRole("button", { name: /Review & arm/ }),
  ).toBeVisible();
  if (await page.getByRole("button", { name: "Close run details" }).isVisible())
    await page.getByRole("button", { name: "Close run details" }).click();
  await page.getByRole("button", { name: /Review & arm/ }).click();
  await expect(dialog).toContainText("Broker buying power and quantity");
  await page.keyboard.press("Escape");
  expect(replacements).toBe(2);
  expect(authorizations).toBe(0);
  expect(errors).toEqual([]);
});
