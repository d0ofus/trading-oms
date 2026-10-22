import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("paper order inspector distinguishes pending acknowledgment and known local cancellation", async ({
  page,
}) => {
  let cancelled = false;
  const order = () => ({
    id: "synthetic-pending-order",
    run_id: "synthetic-pending-run",
    broker_id: 600,
    state: cancelled ? "cancelled" : "dispatching",
    created_at: "2026-09-21T11:50:03Z",
    payload: {
      symbol: "BTC",
      purpose: "entry",
      execution: "crypto_breakout",
      quantity: "0",
      cash_quantity: "25.00",
      stop: "99.00",
    },
    diagnostics: {
      broker_status: cancelled ? "ApiCancelled" : "ApiPending",
      acknowledgment_pending: !cancelled,
      identity_status: cancelled ? "verified" : "pending",
      status_label: cancelled ? "Cancelled" : "Awaiting broker acknowledgment",
      status_conflict: false,
      cancellation_reason: cancelled ? "incident_restriction" : null,
      cancellation_detail: cancelled
        ? "Cancelled by the application because an incident restricted entries"
        : null,
    },
  });
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    const value = await response.json();
    await route.fulfill({
      json: {
        ...value,
        orders: [order()],
        runs: [],
        crypto_triggers: [],
        local_protection: [],
        oca_groups: [],
      },
    });
  });
  await page.route(
    "**/api/operations/orders/synthetic-pending-order",
    async (route) => {
      await route.fulfill({
        json: {
          order: order(),
          run: null,
          executions: [],
          broker_observations: [],
          timeline: [],
        },
      });
    },
  );
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await page
    .getByText("Awaiting broker acknowledgment", { exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: /BTC/ });
  await expect(dialog).toContainText("ApiPending");
  await expect(dialog).toContainText("Awaiting complete broker order details");
  await expect(dialog).toContainText("$25.00");
  await expect(dialog).toContainText(
    "Pending acknowledgment does not confirm acceptance or a fill",
  );
  cancelled = true;
  await expect(dialog).toContainText("ApiCancelled");
  await expect(dialog).toContainText(
    "Cancelled by the application because an incident restricted entries",
  );
  await expect(dialog).toContainText("Verified against durable intent");
  await expect(dialog).not.toContainText("permissions and minimum");
  await expect(
    dialog.getByText("Awaiting broker acknowledgment", { exact: true }),
  ).toHaveCount(0);
});
