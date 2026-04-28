import { describe, expect, it } from "vitest";
import { tokenizeSql, classForToken } from "./sql-highlight";

function typesOf(sql: string): string[] {
  return tokenizeSql(sql)
    .filter((t) => t.type !== "ws")
    .map((t) => `${t.type}:${t.text}`);
}

describe("tokenizeSql", () => {
  it("classifies SELECT/FROM/WHERE as keywords", () => {
    const out = typesOf("SELECT 1 FROM t WHERE x = 1");
    expect(out[0]).toBe("keyword:SELECT");
    expect(out[1]).toBe("number:1");
    expect(out[2]).toBe("keyword:FROM");
    expect(out[3]).toBe("ident:t");
    expect(out[4]).toBe("keyword:WHERE");
  });

  it("recognizes function calls (uppercase ident followed by parenthesis)", () => {
    const out = typesOf("SELECT SUM(x) FROM t");
    expect(out[1]).toBe("function:SUM");
    expect(out[2]).toBe("punct:(");
  });

  it("preserves string literals with single quotes", () => {
    const out = typesOf("WHERE country = 'FRANCE'");
    expect(out.find((s) => s.startsWith("string:"))).toBe("string:'FRANCE'");
  });

  it("handles empty string", () => {
    expect(tokenizeSql("")).toEqual([]);
  });

  it("preserves whitespace tokens (so re-rendering doesn't collapse formatting)", () => {
    const tokens = tokenizeSql("SELECT 1\n  FROM t");
    const ws = tokens.filter((t) => t.type === "ws");
    expect(ws.length).toBeGreaterThan(0);
    // Concatenating all tokens should round-trip the input.
    expect(tokens.map((t) => t.text).join("")).toBe("SELECT 1\n  FROM t");
  });

  it("recognizes double-quoted identifiers (Postgres / Cube style)", () => {
    const out = typesOf(`SELECT "Orders__order_date" FROM t`);
    expect(out[1]).toBe('ident:"Orders__order_date"');
  });

  it("handles a Cube-flavored query end-to-end", () => {
    const sql = `SELECT DATE_TRUNC('month', orders.o_orderdate) AS "Orders__order_date", SUM(lineitem.l_extendedprice * (1 - lineitem.l_discount)) AS "LineItem__revenue" FROM main.lineitem lineitem LEFT JOIN main.orders orders ON lineitem.l_orderkey = orders.o_orderkey GROUP BY DATE_TRUNC('month', orders.o_orderdate)`;
    const tokens = tokenizeSql(sql);
    // Round-trip
    expect(tokens.map((t) => t.text).join("")).toBe(sql);
    // Has at least one of each meaningful type
    const types = new Set(tokens.map((t) => t.type));
    expect(types.has("keyword")).toBe(true);
    expect(types.has("function")).toBe(true);
    expect(types.has("string")).toBe(true);
    expect(types.has("ident")).toBe(true);
    expect(types.has("punct")).toBe(true);
  });
});

describe("classForToken", () => {
  it("maps each token type to a non-empty class (except whitespace)", () => {
    expect(classForToken("keyword")).toMatch(/text-/);
    expect(classForToken("function")).toMatch(/text-/);
    expect(classForToken("string")).toMatch(/text-/);
    expect(classForToken("number")).toMatch(/text-/);
    expect(classForToken("ws")).toBe("");
  });
});
