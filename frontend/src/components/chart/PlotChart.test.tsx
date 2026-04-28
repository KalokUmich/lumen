/**
 * Component tests for the chart dispatch — specifically the failure modes
 * that have actually bitten us in the wild:
 *   - "What was revenue last month?" → big-number rendered with 0 height
 *     because the parent had auto height and we used h-full → blank panel.
 *   - Field-name mismatch between cube_query keys and spec.y.field collapsed
 *     the value to "—".
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PlotChart } from "./PlotChart";
import type { ChartSpec } from "./ChartSpec";

// PlotChart.tsx imports runQuery for CompareDelta. Stub it so the
// useEffect in CompareDelta doesn't try to actually fetch.
vi.mock("../../lib/api", () => ({
  runQuery: vi.fn(async () => ({ data: [], annotation: {} })),
}));

describe("PlotChart big-number", () => {
  it("renders the formatted value when row keys match spec.y.field", () => {
    const spec: ChartSpec = {
      type: "big-number",
      y: { field: "LineItem__revenue", format: "currency", label: "Revenue" },
    };
    const rows = [{ LineItem__revenue: 2_820_000_000 }];
    render(<PlotChart spec={spec} rows={rows} />);
    // Currency formatter prefixes $ and uses B for billions
    expect(screen.getByText(/\$2\.82B/)).toBeInTheDocument();
    expect(screen.getByText("Revenue")).toBeInTheDocument();
  });

  it("falls back to first numeric column when spec.y.field doesn't match the row keys", () => {
    // Common bug: visualizer set y.field to "LineItem.revenue" (dotted) but the
    // row came back with underscored keys. Fallback ensures we still render.
    const spec: ChartSpec = {
      type: "big-number",
      y: { field: "LineItem.revenue", format: "currency", label: "Revenue" },
    };
    const rows = [{ LineItem__revenue: 1500 }];
    render(<PlotChart spec={spec} rows={rows} />);
    expect(screen.queryByText("—")).not.toBeInTheDocument();
    expect(screen.getByText(/\$1\.50K|\$1500|\$1\.5K/)).toBeInTheDocument();
  });

  it("does not collapse to zero height (uses min-h, not h-full)", () => {
    const spec: ChartSpec = {
      type: "big-number",
      y: { field: "x", label: "X" },
    };
    const rows = [{ x: 100 }];
    render(<PlotChart spec={spec} rows={rows} />);
    const el = screen.getByTestId("big-number");
    // Tailwind class assertion — the regression is using h-full again.
    // 160px is the current Tufte breathing-room target; older 140px is also OK.
    expect(el.className).toMatch(/min-h-\[1[46]0px\]/);
    expect(el.className).not.toContain("h-full");
  });

  it("renders an em-dash placeholder when there is no resolvable numeric value", () => {
    const spec: ChartSpec = {
      type: "big-number",
      y: { field: "x", label: "X" },
    };
    const rows: Record<string, unknown>[] = [{ name: "asia" }]; // no number anywhere
    render(<PlotChart spec={spec} rows={rows} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
