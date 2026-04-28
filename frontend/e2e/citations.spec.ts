/**
 * Citations — chat answer renders measure/dimension chips that navigate to
 * the model editor at the source location.
 *
 * Requires /api/v1/model/locate to be live in api_gateway + workspace_service.
 */

import { test, expect } from "@playwright/test";

const SCREENSHOTS = ".playwright/screenshots";

test("chat citation: clicking a source chip jumps to the model editor", async ({ page }) => {
  await page.goto("/");

  // Ask a question that produces a chart with measures + time dimension.
  const textarea = page.getByPlaceholder("Ask a question about your data…");
  await textarea.waitFor({ state: "visible", timeout: 15_000 });
  await textarea.fill("What was our total revenue last month?");
  await textarea.press("Enter");

  // Wait for at least one citation chip to appear (the measure used).
  const chip = page.locator("[data-testid^='citation-']").first();
  await chip.waitFor({ state: "visible", timeout: 45_000 });

  await page.screenshot({ path: `${SCREENSHOTS}/citations.png`, fullPage: true });

  // Click the first citation — should switch to the Model Editor surface and
  // open the file containing that measure.
  await chip.click();

  // The Model Editor's textarea is the unique testid that proves we navigated.
  await expect(page.getByTestId("model-editor-textarea")).toBeVisible({ timeout: 10_000 });
});
