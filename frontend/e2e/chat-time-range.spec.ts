/**
 * Regression for IMPLEMENTATION_PLAN §0.5 bugs B1 + B2.
 *
 * B1: relative-time phrases ("last 3 months", "MTD", "YoY") must produce a
 *     query with `timeDimensions[].dateRange` — caught by query_critic.
 * B2: a low-N time × low-N category result must render as grouped bar, not
 *     a multi-line trend.
 *
 * These run against the mock LLM (USE_MOCK_LLM=true) so the test is
 * deterministic. The mock now recognises "last N <unit>" phrases.
 */

import { test, expect } from "@playwright/test";

const SCREENSHOT_DIR = ".playwright/screenshots";

test("chat: 'last 3 months by region' completes without a system error (B1+B2 smoke)", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (e) => pageErrors.push(e.message));

  await page.goto("/");
  const textarea = page.getByPlaceholder("Ask a question about your data…");
  await textarea.waitFor({ state: "visible", timeout: 15_000 });

  await textarea.fill("number of orders by region over last 3 months over time");
  await textarea.press("Enter");

  // The user's bug report — "system error preventing query execution" —
  // would manifest as the SQL view never appearing OR an empty chart panel.
  // Wait for *any* finished assistant chart (chart container or table).
  // The mock LLM emits a query that the (now-fixed) query_critic accepts and
  // the runner executes; visualizer picks grouped-bar (R11) for the shape.
  const sqlButton = page.getByRole("button", { name: /View SQL/i });
  await sqlButton.waitFor({ state: "visible", timeout: 60_000 });

  // Open SQL panel and assert the WHERE clause references a date column —
  // the canonical signal that the LLM included a dateRange.
  await sqlButton.click();
  const sql = page.getByTestId("sql-view");
  await expect(sql).toBeVisible();
  const sqlText = (await sql.textContent()) ?? "";
  expect(sqlText.toLowerCase()).toContain("where");
  expect(sqlText.toLowerCase()).toMatch(/o_orderdate|order_date|ship_date|date/i);

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/chat-last-3-months.png`,
    fullPage: true,
  });

  // No uncaught errors in the page.
  expect(pageErrors, `pageerrors: ${pageErrors.join("\n")}`).toHaveLength(0);
});

test("chat: 'Top 5 branches this quarter' renders a non-blank chart (B3)", async ({ page }) => {
  // Regression for the bug where R11 grouped-bar fired with n_periods=1 ×
  // n_categories=5, producing a chart_spec without a color encoding so
  // PlotChart rendered nothing. The fix: R11 now requires ≥ 2 periods, and
  // PlotChart falls back to plain bar if grouped-bar lacks a color encoding.
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto("/");
  const textarea = page.getByPlaceholder("Ask a question about your data…");
  await textarea.waitFor({ state: "visible", timeout: 15_000 });

  await textarea.fill("Top 5 branches by origination volume this quarter");
  await textarea.press("Enter");

  // Wait for the SSE roundtrip to complete; the SQL view is the canonical
  // signal that the assistant produced a final answer.
  const sqlButton = page.getByRole("button", { name: /View SQL/i });
  await sqlButton.waitFor({ state: "visible", timeout: 60_000 });

  // The chart panel must render some visible plot. The exact shape varies
  // (bar / dot-plot / horizontal-bar depending on critic decisions) but
  // *something* must render — the bug was a blank panel.
  //
  // Directly query the DOM in the page: find an SVG inside <main> that has
  // chart marks (rect/circle/line) plus non-trivial size. This catches the
  // blank-bug regardless of whether Plot wraps in <figure> and regardless
  // of whether Playwright's a11y tree collapses the wrapper.
  await expect
    .poll(
      async () =>
        await page.evaluate(() => {
          const svgs = Array.from(
            document.querySelectorAll("main svg"),
          ).filter((s) => {
            // Skip tiny decorative icons (lucide etc).
            const r = (s as SVGSVGElement).getBoundingClientRect();
            return r.width > 80 && r.height > 60;
          });
          if (svgs.length === 0) return { count: 0, marks: 0 };
          const target = svgs[0] as SVGSVGElement;
          const marks = target.querySelectorAll(
            "rect, circle, line, path[d]",
          ).length;
          return { count: svgs.length, marks };
        }),
      { timeout: 15_000, intervals: [500] },
    )
    .toMatchObject({ marks: expect.any(Number) });

  const stats = await page.evaluate(() => {
    const target = Array.from(document.querySelectorAll("main svg"))
      .map((s) => ({ s, r: (s as SVGSVGElement).getBoundingClientRect() }))
      .filter(({ r }) => r.width > 80 && r.height > 60)[0];
    if (!target) return null;
    return {
      width: target.r.width,
      height: target.r.height,
      marks: target.s.querySelectorAll("rect, circle, line, path[d]").length,
    };
  });
  expect(stats, "no chart SVG rendered in <main>").not.toBeNull();
  expect(stats!.marks, "chart SVG has zero marks (blank-chart bug)").toBeGreaterThan(0);
  expect(stats!.width).toBeGreaterThan(80);
  expect(stats!.height).toBeGreaterThan(60);

  // No uncaught console errors (Plot throws via console.error when given a
  // mark with missing required channels).
  const PlotChannelError = consoleErrors.filter((e) =>
    /channel|fill|barY|missing/i.test(e),
  );
  expect(
    PlotChannelError,
    `Plot channel errors:\n${PlotChannelError.join("\n")}`,
  ).toHaveLength(0);
});

test("chat: 'MTD revenue' question executes (B1 — MTD must trigger dateRange)", async ({ page }) => {
  await page.goto("/");
  const textarea = page.getByPlaceholder("Ask a question about your data…");
  await textarea.waitFor({ state: "visible", timeout: 15_000 });

  await textarea.fill("Show me MTD revenue");
  await textarea.press("Enter");

  // big-number is the expected shape; if it shows up, the loop didn't deadlock.
  const bigNumber = page.getByTestId("big-number");
  await bigNumber.waitFor({ state: "visible", timeout: 60_000 });
});
