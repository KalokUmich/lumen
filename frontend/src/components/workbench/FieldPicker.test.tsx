/**
 * FieldPicker — tree rendering, click-to-add, drag start payload.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { FieldPicker, FIELD_DND_MIME } from "./FieldPicker";
import type { CubeSchema } from "../../lib/schema";

const SCHEMAS: CubeSchema[] = [
  {
    name: "Orders",
    description: "Order facts",
    measures: [
      { cube: "Orders", name: "count", fullName: "Orders.count", type: "count" },
      { cube: "Orders", name: "revenue", fullName: "Orders.revenue", type: "sum", description: "Revenue ($)" },
    ],
    dimensions: [
      { cube: "Orders", name: "country", fullName: "Orders.country", type: "string" },
    ],
    timeDimensions: [
      { cube: "Orders", name: "order_date", fullName: "Orders.order_date", type: "time" },
    ],
    segments: [
      { cube: "Orders", name: "paid_only", fullName: "Orders.paid_only", type: "segment" },
    ],
    joins: [],
  },
];

describe("FieldPicker", () => {
  it("renders one row per measure / dimension / time / segment", () => {
    render(<FieldPicker schemas={SCHEMAS} onAdd={() => {}} />);
    expect(screen.getByTestId("field-row-measure-Orders.count")).toBeInTheDocument();
    expect(screen.getByTestId("field-row-measure-Orders.revenue")).toBeInTheDocument();
    expect(screen.getByTestId("field-row-dimension-Orders.country")).toBeInTheDocument();
    expect(screen.getByTestId("field-row-timeDimension-Orders.order_date")).toBeInTheDocument();
    expect(screen.getByTestId("field-row-segment-Orders.paid_only")).toBeInTheDocument();
  });

  it("calls onAdd with the right kind on click", () => {
    const onAdd = vi.fn();
    render(<FieldPicker schemas={SCHEMAS} onAdd={onAdd} />);
    fireEvent.click(screen.getByTestId("field-row-measure-Orders.revenue"));
    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd.mock.calls[0][0]).toBe("measure");
    expect(onAdd.mock.calls[0][1].fullName).toBe("Orders.revenue");
  });

  it("filters by name across measures and dimensions", () => {
    render(<FieldPicker schemas={SCHEMAS} onAdd={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText("Filter fields…"), { target: { value: "country" } });
    expect(screen.queryByTestId("field-row-measure-Orders.revenue")).not.toBeInTheDocument();
    expect(screen.getByTestId("field-row-dimension-Orders.country")).toBeInTheDocument();
  });

  it("populates the drag payload on dragStart", () => {
    render(<FieldPicker schemas={SCHEMAS} onAdd={() => {}} />);
    const row = screen.getByTestId("field-row-measure-Orders.revenue");

    const stored: Record<string, string> = {};
    const dataTransfer = {
      setData: (k: string, v: string) => { stored[k] = v; },
      effectAllowed: "" as DataTransfer["effectAllowed"],
    } as unknown as DataTransfer;

    fireEvent.dragStart(row, { dataTransfer });
    expect(stored[FIELD_DND_MIME]).toBeDefined();
    const payload = JSON.parse(stored[FIELD_DND_MIME]);
    expect(payload).toEqual({ kind: "measure", fullName: "Orders.revenue" });
  });
});
