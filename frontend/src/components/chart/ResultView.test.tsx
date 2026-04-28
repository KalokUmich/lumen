/**
 * ResultView — chart ↔ table toggle behavior.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ResultView } from "./ResultView";
import type { ChartSpec } from "./ChartSpec";

vi.mock("../../lib/api", () => ({
  runQuery: vi.fn(async () => ({ data: [], annotation: {} })),
}));

const SPEC: ChartSpec = {
  type: "big-number",
  y: { field: "Orders__count", format: "number", label: "Orders" },
};
const ROWS = [{ Orders__count: 9999 }];

describe("ResultView", () => {
  it("renders the chart by default", () => {
    render(<ResultView spec={SPEC} rows={ROWS} />);
    expect(screen.getByTestId("big-number")).toBeInTheDocument();
    // Table should not be in the document
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("switches to the table when the user clicks Table", () => {
    render(<ResultView spec={SPEC} rows={ROWS} />);
    const tableButton = screen.getByRole("button", { name: /table/i });
    fireEvent.click(tableButton);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByTestId("big-number")).not.toBeInTheDocument();
  });

  it("switches back to the chart", () => {
    render(<ResultView spec={SPEC} rows={ROWS} />);
    fireEvent.click(screen.getByRole("button", { name: /table/i }));
    fireEvent.click(screen.getByRole("button", { name: /chart/i }));
    expect(screen.getByTestId("big-number")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows aria-pressed=true on the active mode toggle", () => {
    render(<ResultView spec={SPEC} rows={ROWS} initialMode="table" />);
    const tableBtn = screen.getByRole("button", { name: /table/i });
    expect(tableBtn).toHaveAttribute("aria-pressed", "true");
  });

  it("renders the data table with the row data when in table mode", () => {
    render(
      <ResultView
        spec={SPEC}
        rows={[
          { Region__name: "ASIA", LineItem__revenue: 1000 },
          { Region__name: "EUROPE", LineItem__revenue: 2000 },
        ]}
        initialMode="table"
      />,
    );
    // Headers should be the prettified column names
    expect(screen.getByText(/Region · name/i)).toBeInTheDocument();
    expect(screen.getByText(/LineItem · revenue/i)).toBeInTheDocument();
    // Cell values
    expect(screen.getByText("ASIA")).toBeInTheDocument();
    expect(screen.getByText("EUROPE")).toBeInTheDocument();
  });
});
