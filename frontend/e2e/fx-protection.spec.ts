import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("FX stop status follows current evidence with specific waiting and failure reasons", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  // Presentation-only fixture: do not add persisted runs to the shared test server.
  const run = {
    id: "f".repeat(32),
    strategy_id: "d".repeat(32),
    version: 1,
    name: "FX protection fixture",
    symbol: "AUD",
    conid: 14433401,
    risk: "0",
    protection_type: "broker_held",
    binding: {
      hash: "fx-protection-presentation",
      sizing: { quantity: "1000", notional: null, risk: null },
      contract: {
        conid: 14433401,
        symbol: "AUD",
        currency: "USD",
        sec_type: "CASH",
        exchange: "IDEALPRO",
      },
      execution_plan: {
        family: "spot_fx",
        policy: "idealpro_broker_candles_v2",
        funding_policy: "paper_buying_power_v1",
        currency: "USD",
      },
    },
  };
  let state = "active";
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    const value = await response.json();
    value.runs = [
      {
        ...run,
        position: "1000",
        state: "position_open",
        protected: state === "active",
        armed: false,
        protection_type: "broker_held",
        protection_verification: {
          state,
          evaluated_at: new Date().toISOString(),
          evidence_revision: 1,
          broker_status: "PreSubmitted",
          stop: "0.69440",
          reasons:
            state === "checking"
              ? ["Waiting for current paper-account and order evidence."]
              : state === "mismatch"
                ? [
                    "Broker stop price or remaining quantity does not match owned exposure.",
                  ]
                : [],
        },
      },
    ];
    value.positions = [
      {
        run_id: run.id,
        symbol: "AUD",
        quantity: "1000",
        cash: "-701.40",
        conid: run.conid,
      },
    ];
    await route.fulfill({ json: value });
  });
  await page.reload();
  await expect(
    page.getByText("Broker stop active", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("SELL 1000 AUD · Stop 0.69440 · PreSubmitted", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Protection requires review", { exact: true }),
  ).toHaveCount(0);
  await page.screenshot({ path: "test-results/fx-protection-active.png" });
  state = "checking";
  await expect(
    page
      .locator(".ws-position")
      .getByText("Checking broker protection", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Waiting for current paper-account and order evidence."),
  ).toBeVisible();
  state = "mismatch";
  await expect(
    page.getByText("Protection requires attention", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Broker stop price or remaining quantity does not match owned exposure.",
    ),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
