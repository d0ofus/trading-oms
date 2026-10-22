import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("armed FX shows the detected signal outcome and approved protection plan", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  const headers = { Origin: "http://127.0.0.1:8013" };
  const setup = await page.request.post("/fixture/fx-policy", { headers });
  const { run } = await setup.json();
  const changed = await page.request.post("/api/runs/policy-replacement", {
    headers,
    data: {
      ids: [run.id],
      expected_binding_hashes: { [run.id]: run.binding.hash },
      target_policy_revision: "paper_buying_power_v1",
      mutation_id: "ea".repeat(16),
    },
  });
  expect(changed.ok(), await changed.text()).toBeTruthy();
  const { review_ids: ids } = await changed.json();
  let blocked = false;
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    const value = await response.json();
    const at = new Date().toISOString();
    // Presentation fixture only; no authorization or broker submission is made.
    value.runs = value.runs
      .filter((r: { id: string }) => ids.includes(r.id))
      .map((r: object) => ({
        ...r,
        armed: true,
        blocking_reason: blocked ? "Insufficient broker buying power." : null,
        state: "armed",
        position: "0",
        display_state: blocked
          ? "Entry blocked: Insufficient broker buying power."
          : "Signal detected — checking account",
        required_inputs: {
          ready: true,
          detail: "Fresh MIDPOINT and bid/ask.",
          evaluated_at: at,
        },
        signal_progress: {
          source: "MIDPOINT",
          price: "0.702595",
          reference_high: "0.702585",
          reference_candle: at,
          observed_at: at,
          comparison: "gt",
          above_high: true,
        },
        signal_outcome: {
          state: blocked ? "blocked" : "checking",
          updated_at: at,
          detail: blocked
            ? "Insufficient broker buying power."
            : "Waiting for current account evidence.",
          trigger: { price: "0.702595", high: "0.702585", triggered_at: at },
        },
      }));
    await route.fulfill({ json: value });
  });
  await page.evaluate((selected) => {
    localStorage.setItem(
      "oms.workspace.desk.selected",
      JSON.stringify(selected),
    );
  }, ids);
  await page.reload();
  await expect(page.getByText("1 armed run", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Run inputs current", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Entries eligible for authorization"),
  ).toHaveCount(0);
  await page
    .getByRole("row")
    .filter({ hasText: "Legacy FX policy fixture" })
    .click();
  const drawer = page.getByRole("complementary", { name: "Run details" });
  await expect(drawer).toContainText(
    "Protection plan approved; stop submitted for confirmed fills.",
  );
  await expect(drawer).toContainText("0.702585");
  await expect(drawer).toContainText("0.702595");
  await expect(drawer).toContainText("Waiting for current account evidence.");
  blocked = true;
  await expect(drawer).toContainText("Insufficient broker buying power.");
  await page.screenshot({ path: "test-results/fx-signal-outcome.png" });
  expect(errors).toEqual([]);
});
