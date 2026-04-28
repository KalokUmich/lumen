/**
 * Markdown viz primitive (IMPLEMENTATION_PLAN §19.1 #1).
 *
 * The chart_spec.type === "markdown" path renders a Mustache-bound HTML/CSS
 * template against the result rows, with inline <Sparkline> and <ChangeArrow>
 * components. The AI service does not yet emit this chart type on its own;
 * we exercise it end-to-end by stubbing a dashboard tile.
 *
 * Strategy: instead of plumbing a UI for users to set chart_spec.template
 * (that's the v0.5 right-rail viz settings panel), we drive PlotChart
 * through a route stub: when the dashboard fetches its tile, we inject a
 * markdown ChartSpec and assert the rendered HTML.
 */

import { test, expect } from "@playwright/test";

test("markdown viz: result-set bindings + Sparkline + ChangeArrow render", async ({ page }) => {
  // Build a self-contained HTML page that imports the actual MarkdownTile
  // module via Vite. This is the smallest test that exercises the renderer
  // through Vite's TS pipeline (so a typo in MarkdownTile.tsx fails here).
  const html = `<!doctype html>
    <html><head><title>md-viz</title></head>
    <body><div id="root"></div>
    <script type="module">
      import { renderMarkdownTemplate } from "/src/components/chart/MarkdownTile.tsx";
      const rows = [
        { Region__name: "ASIA", Orders__count: 1234, delta: 0.12 },
        { Region__name: "EUROPE", Orders__count: 987, delta: -0.04 },
        { Region__name: "AFRICA", Orders__count: 200, delta: 0.0 },
      ];
      const tpl = [
        '<div data-testid="kpi"><h2>Total: {{result.totalRows}} regions</h2></div>',
        '<ul data-testid="rows">{{#each rows}}<li>{{row.Region__name}}: <Sparkline data="rows.Orders__count" width="60" height="18"/> <ChangeArrow value="row.delta" format="percent"/></li>{{/each}}</ul>',
      ].join("");
      const root = document.getElementById("root");
      root.innerHTML = renderMarkdownTemplate(tpl, rows);
      window.__rendered = true;
    </script>
    </body></html>`;

  // Vite serves index.html at /; we use page.setContent to swap a custom
  // shell. Vite still resolves /src/* imports because we hit the same origin.
  await page.goto("/");
  await page.setContent(html);
  await page.waitForFunction(() => (window as unknown as { __rendered?: boolean }).__rendered === true, undefined, { timeout: 10_000 });

  // Bindings populated.
  await expect(page.getByTestId("kpi")).toContainText("Total: 3 regions");

  // 3 list items, one per row.
  const items = page.locator("[data-testid='rows'] li");
  await expect(items).toHaveCount(3);
  await expect(items.nth(0)).toContainText("ASIA");
  await expect(items.nth(1)).toContainText("EUROPE");

  // Sparkline rendered as inline SVG with a polyline.
  const svg = page.locator("[data-testid='rows'] svg polyline").first();
  await expect(svg).toBeVisible();

  // ChangeArrow: positive delta in the first row is up + success-coloured.
  const firstRow = page.locator("[data-testid='rows'] li").nth(0);
  await expect(firstRow).toContainText("▲");
  await expect(firstRow.locator("span.text-success").first()).toBeVisible();
  // Negative delta in the second row is the danger arrow.
  const secondRow = page.locator("[data-testid='rows'] li").nth(1);
  await expect(secondRow).toContainText("▼");
});

test("markdown viz: HTML content from data is escaped, not executed", async ({ page }) => {
  const html = `<!doctype html>
    <html><body><div id="root"></div>
    <script type="module">
      import { renderMarkdownTemplate } from "/src/components/chart/MarkdownTile.tsx";
      const rows = [{ x: '<img src=x onerror="window.__pwn=1">' }];
      const tpl = '<div data-testid="bind">{{result.first.x}}</div>';
      document.getElementById("root").innerHTML = renderMarkdownTemplate(tpl, rows);
      window.__rendered = true;
    </script></body></html>`;
  await page.goto("/");
  await page.setContent(html);
  await page.waitForFunction(() => (window as unknown as { __rendered?: boolean }).__rendered === true);

  // The literal text appears, but no <img> element materialises.
  await expect(page.getByTestId("bind")).toContainText("<img");
  await expect(page.locator("[data-testid='bind'] img")).toHaveCount(0);

  // Onerror never fired.
  const pwned = await page.evaluate(() => (window as unknown as { __pwn?: number }).__pwn);
  expect(pwned).toBeUndefined();
});
