/**
 * End-to-end smoke tests through real Chromium.
 *
 * These hit the running vite dev server + backend (api_gateway on :8000).
 * If the user reports "the page shows nothing", this is the level of test
 * that catches it.
 */

import { test, expect } from "@playwright/test";

const SCREENSHOT_DIR = ".playwright/screenshots";

test("chat: 'total revenue last month' renders a big number", async ({ page }) => {
  // Capture browser console + page errors so we can diagnose blank-render bugs.
  const consoleMessages: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => consoleMessages.push(`[${msg.type()}] ${msg.text()}`));
  page.on("pageerror", (e) => pageErrors.push(e.stack ?? e.message));

  await page.goto("/");
  // The chat input is a textarea with the placeholder we ship.
  const textarea = page.getByPlaceholder("Ask a question about your data…");
  await textarea.waitFor({ state: "visible", timeout: 15_000 });

  await textarea.fill("What was our total revenue last month?");
  await textarea.press("Enter");

  // The response includes either a big-number testid or fallback text.
  // Wait for the assistant bubble to finish — pending spinner goes away.
  // The big number should appear within ~30s end-to-end.
  const bigNumber = page.getByTestId("big-number");
  await bigNumber.waitFor({ state: "visible", timeout: 45_000 });

  // Open the SQL panel and confirm the highlighter rendered tokens.
  await page.getByRole("button", { name: /View SQL/i }).click();
  await expect(page.getByTestId("sql-view")).toBeVisible();

  // Snapshot for human inspection regardless of pass/fail.
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/chat-revenue-last-month.png`,
    fullPage: true,
  });

  // The rendered value must actually be visible, not collapsed to 0 height,
  // and must show something non-empty (either a formatted number or the
  // graceful "No data for this period" fallback).
  const box = await bigNumber.boundingBox();
  expect(box, "big-number must have a layout box").not.toBeNull();
  expect(box!.height).toBeGreaterThan(80);

  // The shown text should be either a currency value or the empty-state copy.
  const shown = (await bigNumber.innerText()).toLowerCase();
  const hasValue = /\$[\d.,]+[kmbt]?/.test(shown);
  const isEmpty = shown.includes("no data");
  expect(hasValue || isEmpty, `unexpected big-number content: ${shown}`).toBe(true);

  // Surface diagnostics if the test failed downstream.
  if (pageErrors.length) {
    console.log("PAGE ERRORS:\n" + pageErrors.join("\n"));
  }
  if (consoleMessages.some((m) => m.startsWith("[error]"))) {
    console.log("CONSOLE ERRORS:\n" + consoleMessages.filter((m) => m.startsWith("[error]")).join("\n"));
  }
});
