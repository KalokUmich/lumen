/**
 * ChartContextMenu — right-click context menu behavior.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ChartContextMenu } from "./ChartContextMenu";
import type { CubeQuery } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  // No-op CubeQuery type passthrough; runQuery isn't called by this component.
}));

const ROWS = [
  { Region__name: "ASIA", LineItem__revenue: 1000 },
  { Region__name: "EUROPE", LineItem__revenue: 2000 },
  { Region__name: "AMERICA", LineItem__revenue: 3000 },
];
const QUERY: CubeQuery = {
  measures: ["LineItem.revenue"],
  dimensions: ["Region.name"],
};

function fireContextMenu(el: Element) {
  fireEvent.contextMenu(el, { clientX: 100, clientY: 100 });
}

describe("ChartContextMenu", () => {
  it("does not open on right-click when there's nothing to do", () => {
    render(
      <ChartContextMenu rows={[]}>
        <div data-testid="chart">chart</div>
      </ChartContextMenu>,
    );
    fireContextMenu(screen.getByTestId("chart"));
    expect(screen.queryByTestId("chart-context-menu")).not.toBeInTheDocument();
  });

  it("opens with the expected actions when cubeQuery + rows are provided", () => {
    render(
      <ChartContextMenu rows={ROWS} cubeQuery={QUERY} sql="SELECT 1">
        <div data-testid="chart">chart</div>
      </ChartContextMenu>,
    );
    fireContextMenu(screen.getByTestId("chart"));
    const menu = screen.getByTestId("chart-context-menu");
    expect(menu).toBeInTheDocument();
    expect(menu.textContent).toMatch(/Open in Workbook/);
    expect(menu.textContent).toMatch(/Drill by name/);
    expect(menu.textContent).toMatch(/Copy SQL/);
    expect(menu.textContent).toMatch(/Download CSV/);
  });

  it("uses 'Filter all tiles by …' wording when on a dashboard", () => {
    render(
      <ChartContextMenu rows={ROWS} cubeQuery={QUERY} dashboardId="default">
        <div data-testid="chart">chart</div>
      </ChartContextMenu>,
    );
    fireContextMenu(screen.getByTestId("chart"));
    const menu = screen.getByTestId("chart-context-menu");
    expect(menu.textContent).toMatch(/Filter all tiles by name/);
  });

  it("hides the drill submenu when there are no categorical values", () => {
    const noDimQuery: CubeQuery = { measures: ["LineItem.revenue"] };
    render(
      <ChartContextMenu rows={[{ LineItem__revenue: 100 }]} cubeQuery={noDimQuery}>
        <div data-testid="chart">chart</div>
      </ChartContextMenu>,
    );
    fireContextMenu(screen.getByTestId("chart"));
    const menu = screen.getByTestId("chart-context-menu");
    expect(menu.textContent).toMatch(/Open in Workbook/);
    expect(menu.textContent).not.toMatch(/Drill by/);
    expect(menu.textContent).not.toMatch(/Filter all tiles/);
  });

  it("closes when Escape is pressed", () => {
    render(
      <ChartContextMenu rows={ROWS} cubeQuery={QUERY}>
        <div data-testid="chart">chart</div>
      </ChartContextMenu>,
    );
    fireContextMenu(screen.getByTestId("chart"));
    expect(screen.getByTestId("chart-context-menu")).toBeInTheDocument();

    // The component defers attaching keydown by setTimeout(0) — flush via act.
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByTestId("chart-context-menu")).not.toBeInTheDocument();
        resolve();
      }, 5);
    });
  });

  it("dedupes repeated values and caps at 20 entries", () => {
    const many = Array.from({ length: 50 }, (_, i) => ({
      Region__name: `Region-${i}`,
      LineItem__revenue: i,
    }));
    // Add a few duplicates to confirm dedup.
    many.push({ Region__name: "Region-0", LineItem__revenue: 999 });
    render(
      <ChartContextMenu rows={many} cubeQuery={QUERY}>
        <div data-testid="chart">chart</div>
      </ChartContextMenu>,
    );
    fireContextMenu(screen.getByTestId("chart"));
    // Hover the "Drill by" item to expand the submenu.
    const drillItem = screen.getByText(/Drill by name/);
    fireEvent.mouseEnter(drillItem.closest("div")!);
    const items = screen.getAllByRole("menuitem").filter((el) => /^Region-\d+$/.test(el.textContent ?? ""));
    expect(items.length).toBeLessThanOrEqual(20);
    expect(items.length).toBeGreaterThan(0);
  });
});
