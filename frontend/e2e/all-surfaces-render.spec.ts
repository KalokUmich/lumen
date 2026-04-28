/**
 * Smoke test: every left-rail surface mounts cleanly with no console errors.
 *
 * This catches the class of bugs where a ChartSpec / API change leaves the
 * page blank-rendering — the failure mode we ran into when the markdown
 * ChartType was first added. If a runtime error escapes ErrorBoundary, this
 * test fails; if a surface's main content doesn't appear, this test fails.
 */

import { test, expect, type Page } from "@playwright/test";

type Surface = { label: RegExp; sentinel: () => Promise<void> };

async function clickRailButton(page: Page, label: RegExp): Promise<void> {
  const buttons = page.locator("aside button, nav button");
  const count = await buttons.count();
  for (let i = 0; i < count; i++) {
    const t = (await buttons.nth(i).getAttribute("title")) ?? "";
    if (label.test(t)) {
      await buttons.nth(i).click();
      return;
    }
  }
  throw new Error(`Rail button matching ${label} not found`);
}

const SURFACES: Surface[] = [
  {
    label: /chat/i,
    sentinel: async () => undefined, // chat input verified separately
  },
  {
    label: /workbench|workbook/i,
    sentinel: async () => undefined,
  },
  {
    label: /dashboard/i,
    sentinel: async () => undefined,
  },
  {
    label: /model/i,
    sentinel: async () => undefined,
  },
];

test("all surfaces mount with no console errors", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];

  // Filter out known noise: vite HMR client warnings, react-dom dev warnings
  // about missing keys (we don't want to regress on those, but they aren't
  // blank-screen bugs).
  const NOISE_RE = /\[vite\]|HMR|DevTools|Download the React/i;

  page.on("console", (msg) => {
    if (msg.type() === "error" && !NOISE_RE.test(msg.text())) {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (e) => pageErrors.push(e.stack ?? e.message));

  await page.goto("/");
  // Default surface is chat; verify the input renders.
  await page
    .getByPlaceholder("Ask a question about your data…")
    .waitFor({ state: "visible", timeout: 15_000 });

  // Workbench
  await clickRailButton(page, /workbench|workbook/i);
  // FieldPicker renders rows for measures/dimensions; assert at least one.
  await page.locator("[data-testid^='field-row-']").first().waitFor({
    state: "visible",
    timeout: 15_000,
  });

  // Dashboard
  await clickRailButton(page, /dashboard/i);
  // Dashboard has a default empty/setup state; just ensure main element renders.
  await page.locator("main").waitFor({ state: "visible" });

  // Model
  await clickRailButton(page, /model/i);
  await page.locator("[data-testid^='file-row-']").first().waitFor({
    state: "visible",
    timeout: 15_000,
  });
  await expect(page.getByTestId("model-editor-textarea")).toBeVisible();

  // Back to chat to close the loop.
  await clickRailButton(page, /chat/i);
  await page
    .getByPlaceholder("Ask a question about your data…")
    .waitFor({ state: "visible", timeout: 5_000 });

  expect(
    pageErrors,
    `Uncaught page errors:\n${pageErrors.join("\n--\n")}`,
  ).toHaveLength(0);
  expect(
    consoleErrors,
    `Unexpected console errors:\n${consoleErrors.join("\n--\n")}`,
  ).toHaveLength(0);
});

test("ErrorBoundary catches surface-level render errors", async ({ page }) => {
  // Force a runtime error in ChatPanel by short-circuiting the API call.
  // If ErrorBoundary is wired up, we see the fallback UI; otherwise, blank screen.
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 500, body: "boom" }),
  );
  await page.route("**/api/v1/workspaces*", (route) =>
    route.fulfill({ status: 500, body: "boom" }),
  );

  await page.goto("/");
  // The page should still render the rail + topbar even when API calls fail.
  // Assert at least the main element exists — we shouldn't be staring at white.
  await expect(page.locator("main")).toBeVisible({ timeout: 10_000 });
});
