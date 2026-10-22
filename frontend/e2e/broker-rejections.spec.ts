import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("rejected entry retains its cause while conclusive recovery clears automatically", async ({
  page,
}) => {
  const rejection = {
    code: 201,
    category: "permissions",
    detail:
      "Broker reports missing trading permissions. Check the rejected order in TWS.",
    available: true,
    advanced_codes: [],
  };
  const label =
    "Broker rejected entry — no fill; final broker status: Cancelled";
  const order = {
    id: "synthetic-rejected-order",
    run_id: "synthetic-rejected-run",
    broker_id: 600,
    state: "cancelled",
    created_at: "2026-09-22T00:26:05Z",
    payload: {
      symbol: "BTC",
      purpose: "entry",
      execution: "crypto_breakout",
      quantity: "0",
      cash_quantity: "25.00",
    },
    diagnostics: {
      broker_status: "Cancelled",
      acknowledgment_pending: false,
      identity_status: "verified",
      status_label: label,
      status_conflict: false,
      cancellation_reason: null,
      cancellation_detail: null,
      rejection,
    },
  };
  let ready = false;
  const incident = () => ({
    id: "e".repeat(32),
    code: "order_uncertain",
    detail: "Broker rejected an order.",
    severity: "critical",
    timestamp: "2026-09-22T00:26:06Z",
    resolved: false,
    revision: ready ? 3 : 2,
    restriction: ready ? "released" : "held",
    automatic_release_enabled: true,
    release_policy: "automatic",
    condition: ready ? "recovered" : "active",
    scope: { type: "workspace", key: "*" },
    investigation: "open",
    occurrences: 1,
    order_context: {
      order_id: order.id,
      run_id: order.run_id,
      broker_id: order.broker_id,
    },
    rejection,
    recovery: {
      can_release: ready,
      checked_at: "2026-09-22T00:26:24Z",
      remaining_seconds: 0,
      checks: [
        {
          code: "terminal_outcome",
          title: "Confirmed terminal outcome and executions",
          passed: ready,
          detail: "Waiting for the terminal order and execution evidence.",
        },
      ],
    },
  });
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: {
        ...(await response.json()),
        orders: [order],
        runs: [],
        incidents: ready ? [] : [incident()],
        crypto_triggers: [],
        local_protection: [],
        oca_groups: [],
      },
    });
  });
  await page.route(`**/api/operations/orders/${order.id}`, (route) =>
    route.fulfill({
      json: {
        order,
        run: null,
        executions: [],
        broker_observations: [],
        timeline: [],
      },
    }),
  );
  await page.route(`**/api/incidents/${incident().id}`, (route) =>
    route.fulfill({ json: incident() }),
  );
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await page.getByText("Broker rejected", { exact: true }).click();
  let dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(label);
  await expect(
    dialog.getByRole("region", { name: "Broker rejection" }),
  ).toContainText("Broker rejection 201");
  await expect(dialog).toContainText(rejection.detail);
  await expect(dialog).toContainText(
    "Recovery acknowledgment does not establish",
  );
  await expect(dialog).toContainText("$25.00");
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Activity", exact: true }).click();
  await page.locator(`tr[data-row-id="${incident().id}"]`).click();
  dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(
    "Originating order: synthetic-rejected-order",
  );
  await expect(dialog).toContainText(rejection.detail);
  await expect(dialog).toContainText(
    "Waiting for the terminal order and execution evidence.",
  );
  const acknowledge = dialog.getByRole("button", {
    name: "Acknowledge recovery and release restriction",
  });
  await expect(acknowledge).toHaveCount(0);
  ready = true;
  await expect(acknowledge).toHaveCount(0);
  await expect(dialog).toContainText("Current recovery evidence verified");
  await expect(dialog.getByLabel(/Recovery notes/)).not.toBeVisible();
});
