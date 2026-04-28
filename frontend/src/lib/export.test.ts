import { describe, it, expect } from "vitest";
import { rowsToCSV, flattenSQL } from "./export";

describe("rowsToCSV", () => {
  it("returns empty string for empty rows", () => {
    expect(rowsToCSV([])).toBe("");
  });

  it("emits a header line + data lines", () => {
    const rows = [
      { country: "US", revenue: 1234 },
      { country: "GB", revenue: 567 },
    ];
    expect(rowsToCSV(rows)).toBe(
      "country,revenue\nUS,1234\nGB,567"
    );
  });

  it("escapes commas, quotes, newlines", () => {
    const rows = [{ name: 'Acme, "Inc"', note: "line1\nline2" }];
    const csv = rowsToCSV(rows);
    expect(csv).toContain('"Acme, ""Inc"""');
    expect(csv).toContain('"line1\nline2"');
  });

  it("handles null and undefined as empty cells", () => {
    const rows = [{ a: null, b: undefined, c: "x" }];
    expect(rowsToCSV(rows)).toBe("a,b,c\n,,x");
  });
});

describe("flattenSQL", () => {
  it("collapses whitespace", () => {
    const sql = `SELECT *
       FROM   table
   WHERE x = 1`;
    expect(flattenSQL(sql)).toBe("SELECT * FROM table WHERE x = 1");
  });

  it("trims surrounding whitespace", () => {
    expect(flattenSQL("   SELECT 1   ")).toBe("SELECT 1");
  });
});
