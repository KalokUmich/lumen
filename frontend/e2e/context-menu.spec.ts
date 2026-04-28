/**
 * Right-click context menu — exercises the menu in real Chromium.
 */

import { test, expect, type Page } from "@playwright/test";

const SCREENSHOTS = ".playwright/screenshots";

async function gotoDashboard(page: Page) {
  await page.goto("/");
  const railButtons = page.locator("aside button, nav button");
  const count = await railButtons.count();
  for (let i = 0; i < count; i++) {
    const t = (await railButtons.nth(i).getAttribute("title")) ?? "";
    if (/dashboard/i.test(t)) {
      await railButtons.nth(i).click();
      break;
    }
  }
  // Wait for an actual chart SVG (≥5000 px²) — `.panel svg` matches lucide
  // icons too, which render way before the chart.
  await page.waitForFunction(
    () => {
      const svgs = Array.from(document.querySelectorAll(".panel svg"));
      return svgs.some((s) => {
        const r = (s as SVGElement).getBoundingClientRect();
        return r.width * r.height > 5000;
      });
    },
    null,
    { timeout: 30_000 },
  );
}

/**
 * Right-click on the centre of the largest SVG in the first chart panel.
 * We dispatch the contextmenu event from inside the page so that React's
 * delegated synthetic-event listener at the document root reliably catches
 * it. Playwright's `mouse.click({button:'right'})` doesn't always trigger
 * `contextmenu` through CDP in headless mode.
 */
async function rightClickChart(page: Page) {
  const panel = page.locator(".panel").filter({ has: page.locator("svg") }).first();
  await expect(panel).toBeVisible();
  await panel.evaluate((panelEl) => {
    const svgs = Array.from(panelEl.querySelectorAll("svg"));
    if (svgs.length === 0) throw new Error("no svg in panel");
    let target = svgs[0];
    let bestArea = 0;
    for (const s of svgs) {
      const r = (s as SVGElement).getBoundingClientRect();
      const area = r.width * r.height;
      if (area > bestArea) { bestArea = area; target = s; }
    }
    const r = target.getBoundingClientRect();
    const ev = new MouseEvent("contextmenu", {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: r.left + r.width / 2,
      clientY: r.top + r.height / 2,
      button: 2,
    });
    target.dispatchEvent(ev);
  });
}

test("right-click on a dashboard chart opens a context menu with drill actions", async ({ page }) => {
  await gotoDashboard(page);
  await rightClickChart(page);

  const menu = page.getByTestId("chart-context-menu");
  await expect(menu).toBeVisible();
  await expect(menu).toContainText("Open in Workbook");
  await expect(menu).toContainText(/Filter all tiles by/i);

  await page.screenshot({ path: `${SCREENSHOTS}/context-menu-open.png`, fullPage: true });
});

test("right-click menu closes on Escape", async ({ page }) => {
  await gotoDashboard(page);
  await rightClickChart(page);
  await expect(page.getByTestId("chart-context-menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("chart-context-menu")).not.toBeVisible();
});
