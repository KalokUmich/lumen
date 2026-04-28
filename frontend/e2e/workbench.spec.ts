/**
 * Workbench — field picker click-to-add and drag-to-add.
 */

import { test, expect, type Page } from "@playwright/test";

async function gotoWorkbench(page: Page) {
  await page.goto("/");
  const railButtons = page.locator("aside button, nav button");
  const count = await railButtons.count();
  for (let i = 0; i < count; i++) {
    const t = (await railButtons.nth(i).getAttribute("title")) ?? "";
    if (/workbook|workbench/i.test(t)) {
      await railButtons.nth(i).click();
      break;
    }
  }
  await page.getByPlaceholder(/Filter fields/i).waitFor({ state: "visible", timeout: 15_000 });
}

test("field picker: click-to-add appends a measure pill", async ({ page }) => {
  await gotoWorkbench(page);
  // Pick the first available measure row.
  const firstMeasure = page.locator("[data-testid^='field-row-measure-']").first();
  const id = await firstMeasure.getAttribute("data-testid");
  expect(id).toBeTruthy();
  const measureFullName = id!.replace("field-row-measure-", "");

  await firstMeasure.click();

  const pillRow = page.getByTestId("pill-row");
  await expect(pillRow).toContainText(measureFullName);
});

test("field picker: drag a dimension into the pill row adds it", async ({ page }) => {
  await gotoWorkbench(page);
  // First we need a measure (workbench rejects queries without one), click any.
  await page.locator("[data-testid^='field-row-measure-']").first().click();

  const dimRow = page.locator("[data-testid^='field-row-dimension-']").first();
  const dimId = await dimRow.getAttribute("data-testid");
  expect(dimId).toBeTruthy();
  const dimFullName = dimId!.replace("field-row-dimension-", "");

  // Simulate drag-and-drop in-page since Playwright's dispatchEvent for
  // dragstart/dragover/drop doesn't share a DataTransfer between actions.
  const target = page.getByTestId("pill-row");
  await page.evaluate(
    ({ srcSel, dstSel }) => {
      const src = document.querySelector(srcSel) as HTMLElement;
      const dst = document.querySelector(dstSel) as HTMLElement;
      if (!src || !dst) throw new Error("missing elements");
      const dt = new DataTransfer();
      const FIELD_DND_MIME = "application/x-lumen-field";
      // Read the kind from the testid prefix.
      const tid = src.getAttribute("data-testid")!;
      const kind = tid.split("-")[2];
      const fullName = tid.replace(`field-row-${kind}-`, "");
      dt.setData(FIELD_DND_MIME, JSON.stringify({ kind, fullName }));
      const fire = (el: Element, type: string) => {
        const ev = new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt });
        el.dispatchEvent(ev);
      };
      fire(src, "dragstart");
      fire(dst, "dragover");
      fire(dst, "drop");
      fire(src, "dragend");
    },
    { srcSel: `[data-testid="${dimId}"]`, dstSel: `[data-testid="pill-row"]` },
  );

  await expect(target).toContainText(dimFullName);
});
