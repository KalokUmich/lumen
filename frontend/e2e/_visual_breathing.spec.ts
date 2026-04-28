/**
 * Visual snapshots of the Tufte breathing-room pass for human inspection.
 * Not a regression test — just dumps PNGs under .playwright/screenshots/.
 */

import { test, type Page } from "@playwright/test";

const SCREENSHOTS = ".playwright/screenshots";

async function clickRail(page: Page, label: RegExp) {
  const buttons = page.locator("aside button, nav button");
  const n = await buttons.count();
  for (let i = 0; i < n; i++) {
    const t = (await buttons.nth(i).getAttribute("title")) ?? "";
    if (label.test(t)) {
      await buttons.nth(i).click();
      return;
    }
  }
}

test("visual: chat empty state", async ({ page }) => {
  await page.goto("/");
  await page
    .getByPlaceholder("Ask a question about your data…")
    .waitFor({ state: "visible", timeout: 15_000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${SCREENSHOTS}/_visual_chat_empty.png`, fullPage: false });
});

test("visual: dashboard with seeded tiles", async ({ page }) => {
  await page.goto("/");
  await clickRail(page, /dashboard/i);
  // Wait until a chart SVG actually rendered.
  await page.waitForFunction(
    () => {
      const svgs = Array.from(document.querySelectorAll("main svg"));
      return svgs.some((s) => {
        const r = (s as SVGSVGElement).getBoundingClientRect();
        return r.width * r.height > 5000;
      });
    },
    null,
    { timeout: 20_000 },
  );
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/_visual_dashboard.png`, fullPage: true });
});

test("visual: model editor", async ({ page }) => {
  await page.goto("/");
  await clickRail(page, /model/i);
  await page
    .getByTestId("model-editor-textarea")
    .waitFor({ state: "visible", timeout: 15_000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${SCREENSHOTS}/_visual_model.png`, fullPage: false });
});

test("visual: small multiples — 2-up density + expand", async ({ page }) => {
  await page.goto("/");
  const ta = page.getByPlaceholder("Ask a question about your data…");
  await ta.waitFor({ state: "visible", timeout: 15_000 });
  // A query that yields multi-line, which the visualizer should fall back to
  // small-multiples once cardinality > 5 dimensions.
  await ta.fill(
    "Loan count by month last 12 months by branch region",
  );
  await ta.press("Enter");
  // Wait for SQL panel as a "loop completed" signal.
  await page.getByRole("button", { name: /View SQL/i }).waitFor({
    state: "visible",
    timeout: 60_000,
  });
  await page.waitForTimeout(800);
  await page.screenshot({
    path: `${SCREENSHOTS}/_visual_small_multiples_inline.png`,
    fullPage: true,
  });

  // Try to click an expand panel if present.
  const panel = page.locator("[data-testid^='sm-panel-']").first();
  if (await panel.count()) {
    await panel.click();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: `${SCREENSHOTS}/_visual_small_multiples_expanded.png`,
      fullPage: false,
    });
  }
});

test("visual: chat after answering a question", async ({ page }) => {
  await page.goto("/");
  const ta = page.getByPlaceholder("Ask a question about your data…");
  await ta.waitFor({ state: "visible", timeout: 15_000 });
  await ta.fill("Default rate by grade");
  await ta.press("Enter");
  // Wait for a chart to render.
  await page.waitForFunction(
    () => {
      const svgs = Array.from(document.querySelectorAll("main svg"));
      return svgs.some((s) => {
        const r = (s as SVGSVGElement).getBoundingClientRect();
        return r.width * r.height > 5000;
      });
    },
    null,
    { timeout: 30_000 },
  );
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/_visual_chat_answer.png`, fullPage: true });
});
