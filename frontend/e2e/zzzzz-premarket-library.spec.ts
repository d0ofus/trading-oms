import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("META preparation derives whole shares, explains the budget, and pins pre-market policy", async ({
  page,
}) => {
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await expect(
    page.getByRole("button", { name: "Prepare a run", exact: true }),
  ).toBeVisible();
  const headers = { Origin: "http://127.0.0.1:8013" };
  expect(
    (await page.request.post("/fixture/preparation", { headers })).ok(),
  ).toBeTruthy();
  const catalog = await (
    await page.request.get("/api/strategies/catalog?schema_version=7")
  ).json();
  const document = catalog.templates.at(-1).document;
  document.settings.sizing = "fixed";
  const draft = await (
    await page.request.post("/api/strategies", {
      headers,
      data: { name: "META pre-market fixture", document, revision: 0 },
    })
  ).json();
  await page.request.post(`/api/strategies/${draft.id}/publish`, {
    headers,
    data: { revision: draft.revision },
  });
  await page
    .getByRole("button", { name: "Prepare a run", exact: true })
    .click();
  await page.getByLabel("Published strategy").selectOption(draft.id);
  await page.getByLabel("Resolved instrument").selectOption("107113386");
  await expect(page.getByLabel("Shares", { exact: true })).toHaveValue("1");
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeDisabled();
  await expect(
    page.getByLabel(/Reusable fee allowance per branch/),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Record verified rules" }),
  ).toHaveCount(0);
  await expect(page.getByRole("dialog")).toContainText(
    "Minimum 1 shares requires approximately 600.00 USD",
  );
  await expect(page.getByLabel("Entry notional ceiling (USD)")).toHaveValue(
    "25",
  );
  await page.getByLabel("Trading session").selectOption("premarket_regular");
  await expect(page.getByLabel("Protection method")).toHaveValue(
    "locally_monitored",
  );
  await expect(page.getByLabel(/Native protected OCA/)).toHaveCount(0);
  await page.keyboard.press("Escape");

  // A higher ceiling is an explicit new published revision, never a preparation default.
  document.settings.notional = "1000";
  const saved = await (
    await page.request.put(`/api/strategies/${draft.id}`, {
      headers,
      data: { name: draft.name, document, revision: draft.revision + 1 },
    })
  ).json();
  await page.request.post(`/api/strategies/${draft.id}/publish`, {
    headers,
    data: { revision: saved.revision },
  });
  await page.request.post("/fixture/preparation", { headers });
  await page
    .getByRole("button", { name: "Prepare a run", exact: true })
    .click();
  await page.getByLabel("Published strategy").selectOption(draft.id);
  await page.getByLabel("Resolved instrument").selectOption("107113386");
  await page.getByLabel("Trading session").selectOption("premarket_regular");
  await expect(page.getByRole("dialog")).toContainText(
    "Ready for supervised qualification",
  );
  await expect(
    page.getByRole("button", { name: "Prepare bound run" }),
  ).toBeEnabled();
  await page.screenshot({ path: "test-results/premarket-preparation.png" });
  const created = page.waitForResponse(
    (r) => r.request().method() === "POST" && r.url().endsWith("/api/runs"),
  );
  await page.getByRole("button", { name: "Prepare bound run" }).click();
  const run = await (await created).json();
  expect(run.armed).toBe(false);
  expect(run.binding.execution_plan.entry_type).toBe("LMT");
  expect(run.binding.execution_plan.session_mode).toBe("premarket_regular");
  expect(run.binding.sizing.shares).toBe("1");
});

test("library removal deletes unused drafts, archives referenced versions, and restores without changing history", async ({
  page,
}) => {
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await expect(
    page.getByRole("button", { name: "Prepare a run", exact: true }),
  ).toBeVisible();
  const headers = { Origin: "http://127.0.0.1:8013" };
  const catalog = await (
    await page.request.get("/api/strategies/catalog?schema_version=7")
  ).json();
  const document = catalog.templates.at(-1).document;
  const drafts = [];
  for (const name of ["Unused removal fixture", "Published removal fixture"]) {
    drafts.push(
      await (
        await page.request.post("/api/strategies", {
          headers,
          data: { name, document, revision: 0 },
        })
      ).json(),
    );
  }
  const original = await (
    await page.request.post(`/api/strategies/${drafts[1].id}/publish`, {
      headers,
      data: { revision: drafts[1].revision },
    })
  ).json();
  await page.getByRole("link", { name: "Strategy Studio" }).click();
  for (const d of drafts)
    await page
      .getByRole("checkbox", { name: `Select strategy ${d.name}` })
      .check();
  await page
    .getByRole("button", { name: "Remove selected", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Delete unused draft");
  await expect(page.getByRole("dialog")).toContainText("Archive");
  await page.screenshot({ path: "test-results/strategy-library-removal.png" });
  await page.getByRole("button", { name: "Confirm removal" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  for (const d of drafts)
    await expect(
      page.getByRole("checkbox", { name: `Select strategy ${d.name}` }),
    ).toHaveCount(0);
  const late = await page.request.put(`/api/strategies/${drafts[0].id}`, {
    headers,
    data: { name: drafts[0].name, document, revision: drafts[0].revision },
  });
  expect(late.status()).toBe(409);
  const unchanged = await (
    await page.request.get(`/api/strategies/${drafts[1].id}/versions/1`)
  ).json();
  expect(unchanged.hash).toBe(original.hash);
  await page.getByRole("button", { name: "Archived", exact: true }).click();
  await page.getByRole("button", { name: `Restore ${drafts[1].name}` }).click();
  await page
    .getByRole("button", { name: "Active library", exact: true })
    .click();
  await expect(
    page.getByRole("checkbox", { name: `Select strategy ${drafts[1].name}` }),
  ).toBeVisible();
  await expect(
    page
      .locator(".ws-library-templates")
      .getByRole("button", { name: /Previous-minute long-only breakout/ }),
  ).toBeVisible();
});
