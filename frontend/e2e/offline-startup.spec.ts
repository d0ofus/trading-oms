import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("opens before Gateway login and retains navigation after a migration connection failure", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(
    "http://127.0.0.1:8015/desk#pair=synthetic-offline-browser-pairing-only",
  );
  await expect(
    page.getByRole("heading", { name: "Trading Desk" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByText("Workspace migration pending", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/You can browse the app and edit strategies/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Verify paper context" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Connect paper Gateway" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Workspace migration pending" }),
  ).toContainText("Gateway code 502");
  await expect(
    page.getByRole("button", { name: "Connect paper Gateway" }),
  ).toBeEnabled();
  await page
    .getByRole("link", { name: "Strategy Studio", exact: true })
    .click();
  await expect(page.locator(".ws-library-templates")).toBeVisible();
  await page.getByRole("link", { name: "Activity", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Activity", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Workspace migration pending" }),
  ).toContainText("Gateway code 502");
  expect(errors).toEqual([]);
});
