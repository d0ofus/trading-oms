// Isolated browser probe: all HTTP and event traffic is synthetic; no broker access.
const { chromium } = require("../frontend/node_modules/@playwright/test");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const duration = Number(process.argv[2] || 0);
const root = path.resolve(__dirname, "..");
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const events = Array.from({ length: 200 }, (_, i) => ({
      sequence: 1000000 - i, timestamp: "2026-09-21T00:00:00+00:00",
      type: "connection.lost", summary: "Synthetic historical event",
    }));
    await page.route("**/*", async (route) => {
      const u = new URL(route.request().url());
      if (u.pathname === "/healthz") return route.fulfill({ json: { mode: "paper" } });
      if (u.pathname === "/api/workspace/overview") return route.fulfill({ json: {
        mode: "paper", environment: "paper", connection: "connected", checks: [],
        runs: [], orders: [], positions: [], data: [], contracts: [], incidents: [
          { id: "1".repeat(32), code: "watchdog", severity: "critical", resolved: false, restriction: "ready_for_release", condition: "recovered", investigation: "open", revision: 2, review_policy: "arming", scope: { type: "workspace", key: "*" }, detail: "Synthetic recovered watchdog incident", recovery_detail: "Recovery verified; operator acknowledgment required.", timestamp: "2026-09-21T00:00:00Z" },
          { id: "2".repeat(32), code: "engine_fault", severity: "critical", resolved: false, restriction: "held", condition: "unknown", investigation: "open", revision: 1, review_policy: "dedicated", scope: { type: "workspace", key: "*" }, detail: "Synthetic fault", recovery_detail: "Complete reconciliation and inspect diagnostic evidence.", timestamp: "2026-09-21T00:00:00Z" },
        ], incident_counts: { held: 1, ready_for_release: 1, released: 1000000 },
        watchdog: { ready: true, state: "monitoring", detail: "Synthetic current-owner heartbeat", age_seconds: 1 },
        account_facts: {}, timestamp: new Date().toISOString(), emergency: false, entry_permission: false,
      } });
      if (u.pathname === "/api/events/page") return route.fulfill({ json: {
        items: events, watermark: 1000000, next_cursor: 999801, scanned_through: 999801,
      } });
      if (u.pathname.startsWith("/api/")) return route.fulfill({ json: [] });
      const file = path.join(root, "frontend", "dist", u.pathname.startsWith("/assets/") ? u.pathname.slice(1) : "index.html");
      if (!fs.existsSync(file)) return route.abort();
      return route.fulfill({ body: fs.readFileSync(file), contentType: file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html" });
    });
    await page.addInitScript(() => {
      window.__auditCount = 1000000;
      window.__openStreams = 0;
      window.EventSource = class {
        constructor() { this.listeners = {}; this.closed = false; window.__openStreams++; setTimeout(() => this.onopen?.({}), 0); window.__auditStream = this; }
        addEventListener(type, fn) { this.listeners[type] = fn; }
        close() { if (!this.closed) window.__openStreams--; this.closed = true; this.listeners = {}; }
        send(count) { for (let i = 0; i < count; i++) this.listeners.journal?.({ data: JSON.stringify({ sequence: ++window.__auditCount, timestamp: "2026-09-21T00:00:00+00:00", type: "fixture", summary: "Synthetic continuous event" }) }); }
      };
    });
    await page.goto("http://127.0.0.1:8049/activity");
    await page.getByText("Event stream connected", { exact: true }).waitFor();
    const cdp = await page.context().newCDPSession(page);
    const browserCdp = await browser.newBrowserCDPSession();
    let previousCpu = null;
    async function measure(label) {
      await cdp.send("HeapProfiler.collectGarbage");
      const heap = await cdp.send("Runtime.getHeapUsage");
      const dom = await cdp.send("Memory.getDOMCounters");
      const rows = await page.locator('tbody tr[data-row-id]').count();
      const { processInfo } = await browserCdp.send("SystemInfo.getProcessInfo");
      const cpuSeconds = processInfo.reduce((sum, item) => sum + item.cpuTime, 0);
      const stamp = Date.now();
      const cpuCoresSinceLast = previousCpu ? Math.max(0, (cpuSeconds - previousCpu.cpu) / ((stamp - previousCpu.stamp) / 1000)) : null;
      previousCpu = { cpu: cpuSeconds, stamp };
      let processMemory = {};
      if (process.platform === "win32") {
        const ids = processInfo.map((item) => item.id).filter((id) => Number.isSafeInteger(id) && id > 0);
        const readings = JSON.parse(execFileSync("powershell.exe", ["-NoProfile", "-Command", `Get-Process -Id ${ids.join(",")} -ErrorAction SilentlyContinue | Select-Object WorkingSet64,PrivateMemorySize64 | ConvertTo-Json -Compress`], { encoding: "utf8", windowsHide: true }));
        const processes = Array.isArray(readings) ? readings : [readings];
        processMemory = {
          processWorkingSetMiB: Number((processes.reduce((sum, item) => sum + item.WorkingSet64, 0) / 1048576).toFixed(2)),
          processPrivateMiB: Number((processes.reduce((sum, item) => sum + item.PrivateMemorySize64, 0) / 1048576).toFixed(2)),
        };
      }
      const result = { label, heapMiB: Number((heap.usedSize / 1048576).toFixed(2)), dom, rows, cpuSeconds, cpuCoresSinceLast, ...processMemory };
      console.log(JSON.stringify(result));
      assert(rows <= 60, "Audit DOM must be bounded");
      assert(result.heapMiB < 25, "Retained JS heap must stay under 25 MiB");
      return result;
    }
    await measure("recent_200");
    for (let i = 0; i < 25; i++) { await page.evaluate(() => window.__auditStream.send(200)); await page.waitForTimeout(100); }
    await page.waitForTimeout(500);
    await measure("after_5000_events");
    for (let i = 0; i < 5; i++) {
      await page.getByRole("link", { name: "Trading Desk", exact: true }).click();
      assert.equal(await page.evaluate(() => window.__openStreams), 0);
      await page.getByRole("link", { name: "Activity", exact: true }).click();
      await page.getByText("Event stream connected", { exact: true }).waitFor();
    }
    await measure("after_five_navigations");
    const started = Date.now();
    let milestone = 60;
    while (Date.now() - started < duration * 1000) {
      await page.evaluate(() => window.__auditStream.send(200));
      await page.waitForTimeout(1000);
      if ((Date.now() - started) / 1000 >= milestone) { await measure(`soak_${milestone}s`); milestone += 60; }
    }
    await measure("final");
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, durationSeconds: duration, events: await page.evaluate(() => window.__auditCount - 1000000) }));
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
