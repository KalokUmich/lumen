import { describe, it, expect } from "vitest";
import { formatValue, formatExact, formatDate, parseDate } from "./format";

describe("formatValue", () => {
  it("renders K/M/B/T suffixes", () => {
    expect(formatValue(0)).toBe("0");
    expect(formatValue(999)).toBe("999");
    expect(formatValue(1234)).toBe("1.23K");
    expect(formatValue(1234567)).toBe("1.23M");
    expect(formatValue(1.234e9)).toBe("1.23B");
    expect(formatValue(1.234e12)).toBe("1.23T");
  });

  it("formats currency with prefix", () => {
    expect(formatValue(1234567, "currency")).toBe("$1.23M");
    expect(formatValue(1234567, "currency", "EUR")).toBe("€1.23M");
  });

  it("formats percent precision by magnitude", () => {
    expect(formatValue(0.246, "percent")).toBe("25%");      // ≥10% → integer
    expect(formatValue(0.075, "percent")).toBe("7.5%");     // 1–10% → 1 decimal
    expect(formatValue(0.0034, "percent")).toBe("0.34%");   // <1% → 2 decimals
  });

  it("returns '—' for null/undefined/non-finite", () => {
    expect(formatValue(null)).toBe("—");
    expect(formatValue(undefined)).toBe("—");
    expect(formatValue("")).toBe("—");
    expect(formatValue(NaN)).toBe("NaN");
  });
});

describe("formatExact", () => {
  it("preserves full precision for currency", () => {
    expect(formatExact(1234.56, "currency")).toBe("$1,234.56");
  });

  it("returns full percent precision", () => {
    expect(formatExact(0.123456, "percent")).toBe("12.35%");
  });
});

describe("parseDate", () => {
  it("parses YYYY-MM-DD as local date (no TZ shift)", () => {
    const d = parseDate("1998-01-15");
    expect(d?.getFullYear()).toBe(1998);
    expect(d?.getMonth()).toBe(0);  // January
    expect(d?.getDate()).toBe(15);
  });

  it("strips T00:00:00 trailing time and parses local", () => {
    const d = parseDate("1998-01-15T00:00:00");
    expect(d?.getFullYear()).toBe(1998);
    expect(d?.getMonth()).toBe(0);
    expect(d?.getDate()).toBe(15);
  });

  it("returns null for unparseable input", () => {
    expect(parseDate("not a date")).toBe(null);
    expect(parseDate(null)).toBe(null);
    expect(parseDate(undefined)).toBe(null);
  });
});

describe("formatDate", () => {
  it("renders 'Jan 1998' for default month granularity", () => {
    expect(formatDate("1998-01-15")).toBe("Jan 1998");
  });

  it("renders just year for year granularity", () => {
    expect(formatDate("1998-01-01", "year")).toBe("1998");
  });

  it("renders Q1 1998 for quarter granularity", () => {
    expect(formatDate("1998-01-01", "quarter")).toBe("Q1 1998");
    expect(formatDate("1998-04-01", "quarter")).toBe("Q2 1998");
    expect(formatDate("1998-10-01", "quarter")).toBe("Q4 1998");
  });

  it("includes day for day/week granularity", () => {
    const out = formatDate("1998-01-15", "day");
    expect(out).toContain("15");
    expect(out).toContain("Jan");
    expect(out).toContain("1998");
  });
});
