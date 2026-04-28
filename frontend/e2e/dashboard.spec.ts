/**
 * Dashboard E2E — date-range picker, auto-refresh, markdown tile.
 */

import { test, expect } from "@playwright/test";

const SCREENSHOTS = ".playwright/screenshots";

test("dashboard: time-range and auto-refresh controls render", async ({ page }) => {
  await page.goto("/");
  // Switch to dashboard surface (left rail icon order is: chat, workbook, dashboard, model)
  await page.getByRole("button", { name: /dashboard/i }).click().catch(() => {});
  // Fallback: click 3rd icon if accessible name not present
  if (await page.getByLabel(/Dashboard date range/i).count() === 0) {
    const railButtons = page.locator("aside button, nav button");
    const count = await railButtons.count();
    for (let i = 0; i < count; i++) {
      const t = await railButtons.nth(i).getAttribute("title") ?? "";
      if (/dashboard/i.test(t)) {
        await railButtons.nth(i).click();
        break;
      }
    }
  }

  const timeRange = page.getByLabel("Dashboard date range");
  await expect(timeRange).toBeVisible();

  const autoRefresh = page.getByLabel("Dashboard auto-refresh");
  await expect(autoRefresh).toBeVisible();

  // Open the tile picker — markdown CTA should appear
  await page.getByRole("button", { name: /add tile/i }).click();
  const mdButton = page.getByRole("button", { name: /\+ Markdown note/i });
  await expect(mdButton).toBeVisible();

  // Add a markdown tile and edit it
  await mdButton.click();
  const note = page.getByTestId("markdown-tile").first();
  await expect(note).toBeVisible();

  // Pencil → edit; type; Save (Check icon)
  await note.getByLabel("Edit note").click();
  const ta = note.locator("textarea");
  await ta.fill("# Hello\n\n- one\n- **two**");
  await note.getByLabel("Save note").click();

  // Rendered: should contain "Hello" as h1 and a list item with bold
  await expect(note.getByRole("heading", { level: 1, name: "Hello" })).toBeVisible();
  await expect(note.getByText("one")).toBeVisible();

  await page.screenshot({ path: `${SCREENSHOTS}/dashboard-md-tile.png`, fullPage: true });
});

test("dashboard: changing time range updates the URL/select state", async ({ page }) => {
  await page.goto("/");
  // Navigate to dashboard via the same fallback
  const railButtons = page.locator("aside button, nav button");
  const count = await railButtons.count();
  for (let i = 0; i < count; i++) {
    const t = await railButtons.nth(i).getAttribute("title") ?? "";
    if (/dashboard/i.test(t)) {
      await railButtons.nth(i).click();
      break;
    }
  }
  const timeRange = page.getByLabel("Dashboard date range");
  await timeRange.selectOption("last month");
  await expect(timeRange).toHaveValue("last month");
});
