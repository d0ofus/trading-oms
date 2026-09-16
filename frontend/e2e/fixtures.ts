import { test as base } from "@playwright/test";

// The isolated Python test service owns the browser process. Connecting via CDP
// keeps the runner independent of Windows child-process pipe shutdown behavior.
// This endpoint and profile exist only during offline browser verification.
export const test = base.extend({
  browser: [
    async ({ playwright }, use) => {
      const response = await fetch("http://127.0.0.1:8013/browser-endpoint");
      const { endpoint } = await response.json();
      const browser = await playwright.chromium.connectOverCDP(endpoint, {
        timeout: 15000,
      });
      await use(browser);
      await browser.close();
    },
    { scope: "worker" },
  ],
});
