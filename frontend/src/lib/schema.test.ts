import { describe, it, expect } from "vitest";
import { parseSchema } from "./schema";

const SAMPLE_SCHEMA = `# Cube Semantic Model — sample (parser test fixture)

## Cube: Orders
Description: One row per customer order.

### Dimensions
- Orders.id (string)
- Orders.status (string) — Order lifecycle status  [enum_values: ['F', 'O', 'P']; ai_hint: "F=Finished, O=Open, P=Partial"]
- Orders.order_date (time) — When the order was placed

### Measures
- Orders.count (count_distinct) — Number of unique orders  [synonyms: ['orders', 'order_count']]
- Orders.total_price (sum, currency) — Sum of order totals

### Joins
- → Customer (many_to_one)

## Cube: LineItem
Description: One row per line item.

### Measures
- LineItem.revenue (sum, currency) — Canonical revenue  [synonyms: ['sales', 'gmv']; examples: ['Revenue last month', 'Top 10 by sales']]
`;

describe("parseSchema", () => {
  it("extracts cubes by name", () => {
    const cubes = parseSchema(SAMPLE_SCHEMA);
    expect(cubes.map((c) => c.name)).toEqual(["Orders", "LineItem"]);
  });

  it("captures dimensions and measures", () => {
    const [orders] = parseSchema(SAMPLE_SCHEMA);
    expect(orders.dimensions.map((d) => d.name)).toContain("id");
    expect(orders.dimensions.map((d) => d.name)).toContain("status");
    expect(orders.measures.map((m) => m.name)).toContain("count");
    expect(orders.measures.map((m) => m.name)).toContain("total_price");
  });

  it("identifies time dimensions", () => {
    const [orders] = parseSchema(SAMPLE_SCHEMA);
    expect(orders.timeDimensions.map((t) => t.name)).toContain("order_date");
  });

  it("parses synonyms from meta", () => {
    const [orders] = parseSchema(SAMPLE_SCHEMA);
    const count = orders.measures.find((m) => m.name === "count");
    expect(count?.synonyms).toEqual(["orders", "order_count"]);
  });

  it("parses enum_values + ai_hint from meta", () => {
    const [orders] = parseSchema(SAMPLE_SCHEMA);
    const status = orders.dimensions.find((d) => d.name === "status");
    expect(status?.enumValues).toEqual(["F", "O", "P"]);
    expect(status?.aiHint).toBe("F=Finished, O=Open, P=Partial");
  });

  it("parses example_questions", () => {
    const cubes = parseSchema(SAMPLE_SCHEMA);
    const lineItem = cubes.find((c) => c.name === "LineItem")!;
    const revenue = lineItem.measures.find((m) => m.name === "revenue")!;
    expect(revenue.exampleQuestions).toEqual([
      "Revenue last month",
      "Top 10 by sales",
    ]);
  });

  it("captures cube descriptions", () => {
    const [orders] = parseSchema(SAMPLE_SCHEMA);
    expect(orders.description).toBe("One row per customer order.");
  });

  it("captures joins", () => {
    const [orders] = parseSchema(SAMPLE_SCHEMA);
    expect(orders.joins).toEqual(["Customer"]);
  });
});
