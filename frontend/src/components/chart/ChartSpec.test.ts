import { describe, it, expect } from "vitest";
import { ChartSpec, PALETTES } from "./ChartSpec";

describe("ChartSpec schema", () => {
  it("validates a minimal spec", () => {
    const result = ChartSpec.safeParse({ type: "bar" });
    expect(result.success).toBe(true);
  });

  it("validates a complete spec", () => {
    const result = ChartSpec.safeParse({
      type: "line",
      x: { field: "Orders__order_date", type: "time", label: "Date" },
      y: { field: "LineItem__revenue", format: "currency", label: "Revenue" },
      caption: "Note: y-axis is zoomed",
    });
    expect(result.success).toBe(true);
  });

  it("rejects an unknown chart type", () => {
    const result = ChartSpec.safeParse({ type: "wormhole" });
    expect(result.success).toBe(false);
  });

  it("rejects an invalid format", () => {
    const result = ChartSpec.safeParse({
      type: "bar",
      y: { field: "x", format: "wattage" },
    });
    expect(result.success).toBe(false);
  });
});

describe("PALETTES", () => {
  it("provides at least 10 categorical colors", () => {
    expect(PALETTES.categorical.length).toBeGreaterThanOrEqual(10);
  });

  it("sequential and diverging palettes are non-empty", () => {
    expect(PALETTES.sequential.length).toBeGreaterThan(0);
    expect(PALETTES.diverging.length).toBeGreaterThan(0);
  });

  it("colors are valid hex codes", () => {
    for (const palette of Object.values(PALETTES)) {
      for (const c of palette) {
        expect(c).toMatch(/^#[0-9A-F]{6}$/i);
      }
    }
  });
});
