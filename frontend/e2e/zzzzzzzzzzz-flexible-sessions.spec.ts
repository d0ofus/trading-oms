import AxeBuilder from "@axe-core/playwright";
import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("legacy stock session editing and blocked paper diagnostics retain explicit review", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route(
    "**/api/strategies/catalog?schema_version=8",
    async (route) => {
      const response = await route.fetch();
      const catalog = await response.json();
      // Represent legacy drafts that were already saved before reusable stock graphs.
      catalog.templates = catalog.templates.slice(0, 2).map(
        (item: {
          document: {
            schema_version: number;
            settings: Record<string, unknown>;
          };
        }) => ({
          ...item,
          document: {
            ...item.document,
            schema_version: 3,
            settings: {
              ...item.document.settings,
              symbol: "AAPL",
              shares: 1,
              risk: "10",
              notional: "1000",
              sizing: "fixed",
            },
          },
        }),
      );
      await route.fulfill({ json: catalog });
    },
  );
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  await page
    .locator(".ws-library-templates")
    .getByRole("button", { name: /Moving average crossover/ })
    .click();
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page
    .getByRole("button", { name: "Enable session settings in this draft" })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Execution hours", exact: true }),
  ).toHaveValue("regular");
  await page
    .getByRole("combobox", { name: "Execution hours", exact: true })
    .selectOption("extended");
  await expect(page.getByText(/triggered stop-limit can remain/)).toBeVisible();
  await expect(page.locator(".ws-save-state")).toContainText("Saved");
  await page.getByRole("button", { name: "Review & publish" }).click();
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("link", { name: "Testing", exact: true }).click();
  await page
    .getByRole("button", { name: "Paper connection test", exact: true })
    .click();
  await page.getByRole("button", { name: "Check connection & data" }).click();
  await expect(
    page.getByText("Connection and data results", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Review paper order test" }),
  ).toBeDisabled();
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  expect(errors).toEqual([]);
});
