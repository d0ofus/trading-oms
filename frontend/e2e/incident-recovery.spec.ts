import { expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { test } from "./fixtures";

const watchdog = {
  id: "a".repeat(32),
  code: "watchdog",
  detail: "Synthetic watchdog interruption",
  timestamp: "2026-09-21T00:00:00Z",
  first_at: "2026-09-21T00:00:00Z",
  last_at: "2026-09-21T00:00:00Z",
  resolved: false,
  severity: "critical",
  revision: 2,
  condition: "recovered",
  restriction: "ready_for_release",
  investigation: "open",
  scope: { type: "workspace", key: "*" },
  review_policy: "arming",
  recovery_detail:
    "Current engine, fresh watchdog and post-incident reconciliation verified.",
  evidence: { engine_instance: "synthetic", healthy_seconds: 30 },
  recovery: {
    can_release: true,
    checked_at: "2026-09-21T00:00:30Z",
    remaining_seconds: 0,
    checks: [
      {
        code: "reconciliation",
        title: "Reconciliation after failure",
        passed: true,
        detail: "Verified",
      },
    ],
  },
};

test("Current attention clears verified recovery automatically without an acknowledgment workflow", async ({
  page,
}) => {
  let recovered = false;
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: {
        ...(await response.json()),
        incidents: recovered
          ? []
          : [
              {
                ...watchdog,
                release_policy: "automatic",
                category: "operational",
                severity: "warning",
                actionable: true,
              },
            ],
        incident_counts: {
          held: recovered ? 0 : 1,
          ready_for_release: 0,
          released: recovered ? 1 : 0,
        },
      },
    });
  });
  await page.goto("/activity#pair=synthetic-browser-pairing-for-tests-only");
  await expect(
    page.getByRole("heading", { name: "Current attention" }),
  ).toBeVisible();
  await expect(page.locator(`tr[data-row-id="${watchdog.id}"]`)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Routine recovery status" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Acknowledge recovery/ }),
  ).toHaveCount(0);
  recovered = true;
  await expect(
    page.getByText("No current concerns require attention.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByLabel("Activity view")).toHaveValue("current");
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
});

test("Activity retains history and legacy rollback recovery controls", async ({
  page,
}) => {
  const fault = {
    ...watchdog,
    id: "b".repeat(32),
    code: "engine_fault",
    automatic_release_enabled: false,
    revision: 3,
    review_policy: "dedicated",
  };
  const history = {
    ...watchdog,
    id: "d".repeat(32),
    resolved: true,
    restriction: "released",
  };
  let released = false;
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: {
        ...(await response.json()),
        incidents: released ? [watchdog] : [watchdog, fault],
        incident_counts: {
          held: 0,
          ready_for_release: released ? 1 : 2,
          released: 1000000,
        },
        build: {
          backend: "fixture-backend",
          frontend: "older-build.js",
          started_at: "2026-09-21T00:00:00Z",
        },
      },
    });
  });
  await page.route("**/api/incidents?*", (route) =>
    route.fulfill({ json: { items: [history], next_cursor: null } }),
  );
  await page.route("**/api/incidents/*", (route) =>
    route.fulfill({
      json: route.request().url().endsWith(fault.id) ? fault : history,
    }),
  );
  await page.route(
    `**/api/operations/incidents/${fault.id}/review`,
    async (route) => {
      expect(route.request().postDataJSON()).toEqual({
        revision: 3,
        rationale: "",
      });
      released = true;
      await route.fulfill({
        json: { ...fault, restriction: "released", resolved: true },
      });
    },
  );
  await page.goto("/activity#pair=synthetic-browser-pairing-for-tests-only");
  await expect(
    page.getByText("Recovery evidence verified").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reload application" }),
  ).toBeVisible();
  expect(requests.some((url) => url.includes(`/incidents/${fault.id}`))).toBe(
    false,
  );
  await page.screenshot({
    path: "test-results/incident-current.png",
    fullPage: true,
  });
  await page.locator(`tr[data-row-id="${fault.id}"]`).click();
  const dialog = page.getByRole("dialog");
  const release = dialog.getByRole("button", {
    name: "Acknowledge recovery and release restriction",
  });
  await expect(release).toBeEnabled();
  await expect(dialog.getByLabel(/Recovery notes/)).not.toBeVisible();
  await dialog.screenshot({ path: "test-results/incident-review.png" });
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  await release.click();
  await expect(dialog).toHaveCount(0);
  await page.getByLabel("Activity view").selectOption("history");
  await expect(
    page.getByText("Historical — restriction released"),
  ).toBeVisible();
  await page.locator(`tr[data-row-id="${history.id}"]`).click();
  await expect(page.getByRole("dialog")).toContainText("Investigation: open");
  await expect(
    page.getByRole("button", { name: "Close investigation" }),
  ).toBeDisabled();
  await page.keyboard.press("Escape");
  await page.getByLabel("Activity view").selectOption("current");
  await expect(page.locator(`tr[data-row-id="${fault.id}"]`)).toHaveCount(0);
  await page.unrouteAll({ behavior: "wait" });
});

test("Review and arm requires explicit recovery consent and sends episode revisions", async ({
  page,
}) => {
  const run = {
    id: "f".repeat(32),
    name: "Recovery consent fixture",
    strategy_id: "e".repeat(32),
    version: 1,
    symbol: "AAPL",
    conid: 100,
    state: "paused",
    armed: false,
    position: "0",
    protected: false,
    risk: "10",
  };
  let submitted = false;
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: { ...(await response.json()), runs: [run], incidents: [watchdog] },
    });
  });
  await page.route("**/api/runs/arm-preview", (route) =>
    route.fulfill({
      json: {
        eligible: false,
        eligible_after_recovery_ack: true,
        recoveries: [watchdog],
        review_instance: "c".repeat(32),
        checks: [
          {
            code: "incidents",
            title: "Applicable restrictions",
            passed: false,
            detail: "Acknowledge verified recovery",
            remediation: "/activity",
          },
        ],
        runs: [run],
        summaries: [],
        expires_at: "2026-09-22T00:00:00Z",
        entry_cutoff: "2026-09-21T23:45:00Z",
        limits: {
          id: "smoke",
          version: 1,
          planned_stop_risk: "10",
          notional: "1000",
          shares: 1,
        },
        authorization: "supervised_paper_session",
        environment: "paper",
        session_policy: "xnys",
      },
    }),
  );
  await page.route("**/api/runs/arm", async (route) => {
    const body = route.request().postDataJSON();
    expect(body.recovery_acknowledgments).toEqual([
      { id: watchdog.id, revision: 2 },
    ]);
    expect(body.review_instance).toBe("c".repeat(32));
    submitted = true;
    await route.fulfill({ json: { armed: [run.id] } });
  });
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await page
    .getByRole("checkbox", { name: "Select Recovery consent fixture AAPL" })
    .check();
  await page.getByRole("button", { name: /Review & arm/ }).click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", {
    name: "Acknowledge verified recoveries & arm paper run",
  });
  await expect(dialog.getByRole("checkbox")).toHaveCount(0);
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(dialog).toHaveCount(0);
  expect(submitted).toBe(true);
  await expect(
    page.getByText("Reviewed paper session armed.", { exact: true }),
  ).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
});

test("open recovery review polls, fails closed, pauses while hidden and stops on close", async ({
  page,
}) => {
  let ready = false;
  let unavailable = false;
  let reads = 0;
  const episode = {
    ...watchdog,
    code: "order_uncertain",
    automatic_release_enabled: false,
    review_policy: "dedicated",
  };
  await page.addInitScript(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () =>
        Boolean(
          (window as unknown as { recoveryHidden?: boolean }).recoveryHidden,
        ),
    });
  });
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: { ...(await response.json()), incidents: [episode] },
    });
  });
  await page.route(`**/api/incidents/${episode.id}`, async (route) => {
    reads++;
    if (unavailable)
      return route.fulfill({
        status: 503,
        json: { detail: "Synthetic connection interrupted" },
      });
    return route.fulfill({
      json: {
        ...episode,
        revision: ready ? 3 : 2,
        restriction: ready ? "ready_for_release" : "held",
        recovery: {
          ...watchdog.recovery,
          can_release: ready,
          remaining_seconds: ready ? 0 : 15,
          checks: [
            {
              code: "stability",
              title: "Continuous healthy observation",
              passed: ready,
              detail: "15 seconds remaining",
            },
          ],
        },
      },
    });
  });
  await page.goto("/activity#pair=synthetic-browser-pairing-for-tests-only");
  await page.locator(`tr[data-row-id="${episode.id}"]`).click();
  const dialog = page.getByRole("dialog");
  const acknowledge = dialog.getByRole("button", {
    name: "Acknowledge recovery and release restriction",
  });
  await expect(acknowledge).toBeDisabled();
  await expect(dialog).toContainText("15 seconds remaining");
  await dialog.getByText("Optional notes", { exact: true }).click();
  await dialog
    .getByLabel(/Recovery notes/)
    .fill("Optional note survives refresh");
  ready = true;
  await expect(acknowledge).toBeEnabled();
  await expect(dialog.getByLabel(/Recovery notes/)).toHaveValue(
    "Optional note survives refresh",
  );
  unavailable = true;
  await expect(dialog.getByRole("alert")).toContainText(
    "Condition status unavailable",
  );
  await expect(acknowledge).toBeDisabled();
  unavailable = false;
  await dialog.getByRole("button", { name: "Recheck recovery" }).click();
  await expect(acknowledge).toBeEnabled();
  await page.evaluate(() => {
    (window as unknown as { recoveryHidden: boolean }).recoveryHidden = true;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const hiddenReads = reads;
  await page.waitForTimeout(2300);
  expect(reads).toBe(hiddenReads);
  await expect(acknowledge).toBeDisabled();
  await page.evaluate(() => {
    (window as unknown as { recoveryHidden: boolean }).recoveryHidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(acknowledge).toBeEnabled();
  expect(reads).toBeGreaterThan(hiddenReads);
  await page.keyboard.press("Escape");
  const closedReads = reads;
  await page.waitForTimeout(2300);
  expect(reads).toBe(closedReads);
  expect(
    await page.locator("tbody tr[data-row-id]").count(),
  ).toBeLessThanOrEqual(60);
});

test("market data distinguishes sampled prices from execution trades and retries only failed feeds", async ({
  page,
}) => {
  const components = {
    quote: { status: "healthy", retry_available: false },
    trade: {
      status: "failed",
      retry_available: true,
      diagnostic: {
        code: 10189,
        reason: "session_conflict",
        detail: "Resolve the conflicting login before retrying.",
      },
    },
    history: {
      status: "failed",
      retry_available: true,
      diagnostic: {
        code: 162,
        reason: "unknown",
        detail: "Inspect broker diagnostics before retrying.",
      },
      progress: { completed: 7, failed: 1, queued: 5 },
    },
  };
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: {
        ...(await response.json()),
        data: [
          {
            conid: 456,
            symbol: "BTC",
            live: true,
            warm: false,
            ready: false,
            history_status: "failed",
            feed_status: "trade_feed_rejected",
            candle_source: "AGGTRADES",
            quotes: {
              last: { price: "84000", received_at: "2026-09-21T00:00:00Z" },
            },
            components,
          },
        ],
      },
    });
  });
  let retried = false;
  await page.route("**/api/market-data/456/retry", async (route) => {
    expect(route.request().postDataJSON().components).toEqual([
      "trade",
      "history",
    ]);
    retried = true;
    await route.fulfill({ json: { queued: ["trade", "history"] } });
  });
  await page.goto("/desk#pair=synthetic-browser-pairing-for-tests-only");
  await expect(page.getByText("Sampled Last", { exact: true })).toBeVisible();
  await expect(
    page.getByText("No execution trade received", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Execution trades: IBKR 10189/)).toBeVisible();
  await expect(page.getByText(/Historical data: IBKR 162/)).toBeVisible();
  await expect(
    page.getByText("7 completed · 1 failed · 5 queued requests"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Retry failed feeds" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Failed feeds queued" }),
  ).toBeVisible();
  expect(retried).toBe(true);
  await page.screenshot({
    path: "test-results/independent-feeds.png",
    fullPage: true,
  });
});

test("slow incident reads never overlap and closing aborts the pending request", async ({
  page,
}) => {
  await page.addInitScript((identity) => {
    const probe = { active: 0, peak: 0, aborted: 0 };
    Object.defineProperty(window, "recoveryRequests", { value: probe });
    const original = window.fetch.bind(window);
    window.fetch = (input, options) => {
      if (String(input).endsWith(`/incidents/${identity}`)) {
        probe.active++;
        probe.peak = Math.max(probe.peak, probe.active);
        return new Promise<Response>((_, reject) => {
          options?.signal?.addEventListener(
            "abort",
            () => {
              probe.active--;
              probe.aborted++;
              reject(new DOMException("Aborted", "AbortError"));
            },
            { once: true },
          );
        });
      }
      return original(input, options);
    };
  }, watchdog.id);
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: { ...(await response.json()), incidents: [watchdog] },
    });
  });
  await page.goto("/activity#pair=synthetic-browser-pairing-for-tests-only");
  await page.locator(`tr[data-row-id="${watchdog.id}"]`).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Loading current incident evidence",
  );
  await page.waitForTimeout(4300);
  const counters = () =>
    page.evaluate(
      () =>
        (
          window as unknown as {
            recoveryRequests: { active: number; peak: number; aborted: number };
          }
        ).recoveryRequests,
    );
  expect(await counters()).toEqual({ active: 1, peak: 1, aborted: 0 });
  await page.keyboard.press("Escape");
  await expect.poll(counters).toEqual({ active: 0, peak: 1, aborted: 1 });
});

test("Subscription removal names a real dependency and permits unused data removal", async ({
  page,
}) => {
  let removed = false;
  let blocked = true;
  await page.route("**/api/workspace/overview", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: {
        ...(await response.json()),
        data: removed
          ? []
          : [
              {
                conid: 14433401,
                symbol: "AUD.USD",
                live: true,
                warm: false,
                history_loaded: true,
              },
            ],
      },
    });
  });
  await page.route("**/api/market-data/unsubscribe", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ conid: 14433401 });
    if (blocked) {
      await route.fulfill({
        status: 409,
        json: {
          detail: "AUDUSD test: an exit operation is outstanding.",
          dependencies: [
            {
              code: "exit_request",
              run_id: "fixture-run",
              run_name: "AUDUSD test",
              detail: "An exit operation is outstanding.",
              action: "desk",
            },
          ],
        },
      });
    } else {
      removed = true;
      await route.fulfill({ json: { removed: true } });
    }
  });
  await page.goto("/settings#pair=synthetic-browser-pairing-for-tests-only");
  const remove = page.getByRole("button", { name: "Remove subscription" });
  await remove.click();
  await expect(
    page.getByText("This subscription is currently needed:"),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Inspect AUDUSD test" }),
  ).toHaveAttribute("href", "/desk");
  blocked = false;
  await remove.click();
  await expect(remove).toHaveCount(0);
  await expect(
    page.getByText("This subscription is currently needed:"),
  ).toHaveCount(0);
});
