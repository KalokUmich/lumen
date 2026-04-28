import { describe, it, expect } from "vitest";
import { renderMarkdownTemplate } from "./MarkdownTile";

const rows = [
  { Region__name: "ASIA", Orders__count: 1234 },
  { Region__name: "EUROPE", Orders__count: 987 },
  { Region__name: "AFRICA", Orders__count: 200 },
];

describe("renderMarkdownTemplate — bindings", () => {
  it("substitutes {{result.totalRows}}", () => {
    const html = renderMarkdownTemplate("Total: {{result.totalRows}}", rows);
    expect(html).toBe("Total: 3");
  });

  it("substitutes {{result.first.field}}", () => {
    const html = renderMarkdownTemplate(
      "Top region: {{result.first.Region__name}}",
      rows,
    );
    expect(html).toContain("Top region: ASIA");
  });

  it("formats numbers with the |format pipe", () => {
    const html = renderMarkdownTemplate(
      "{{result.first.Orders__count|number}}",
      rows,
    );
    // formatValue truncates large numbers; just check the digit shows up.
    expect(html).toMatch(/1\.?2/);
  });

  it("escapes HTML by default", () => {
    const evil = [{ x: "<img src=x onerror=alert(1)>" }];
    const html = renderMarkdownTemplate("{{result.first.x}}", evil);
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("returns raw HTML with the {{= path}} form", () => {
    const data = [{ x: "<b>bold</b>" }];
    const html = renderMarkdownTemplate("{{= result.first.x}}", data);
    expect(html).toContain("<b>bold</b>");
  });
});

describe("renderMarkdownTemplate — sections", () => {
  it("iterates rows with {{#each rows}}", () => {
    const tpl =
      '<ul>{{#each rows}}<li>{{row.Region__name}}: {{row.Orders__count|number}}</li>{{/each}}</ul>';
    const html = renderMarkdownTemplate(tpl, rows);
    expect(html).toContain("<li>ASIA");
    expect(html).toContain("<li>EUROPE");
    expect(html).toContain("<li>AFRICA");
  });

  it("conditionally renders with {{#if path}}", () => {
    const tpl = "{{#if result.totalRows}}has rows{{/if}}";
    expect(renderMarkdownTemplate(tpl, rows)).toBe("has rows");
    expect(renderMarkdownTemplate(tpl, [])).toBe("");
  });
});

describe("renderMarkdownTemplate — components", () => {
  it("renders <Sparkline> as inline SVG", () => {
    const tpl = '<Sparkline data="rows.Orders__count" width="80" height="20" />';
    const html = renderMarkdownTemplate(tpl, rows);
    expect(html).toContain("<svg");
    expect(html).toContain("polyline");
  });

  it("<Sparkline> with <2 data points renders nothing", () => {
    const tpl = '<Sparkline data="rows.Orders__count" />';
    expect(renderMarkdownTemplate(tpl, rows.slice(0, 1))).not.toContain("<svg");
  });

  it("renders <ChangeArrow> with up arrow for positive value", () => {
    const tpl = '<ChangeArrow value="result.first.delta" format="percent" />';
    const html = renderMarkdownTemplate(tpl, [{ delta: 0.12 }]);
    expect(html).toContain("▲");
    expect(html).toContain("text-success");
  });

  it("<ChangeArrow goodWhen=down> turns green for negative", () => {
    const tpl =
      '<ChangeArrow value="result.first.delta" format="percent" goodWhen="down" />';
    const html = renderMarkdownTemplate(tpl, [{ delta: -0.05 }]);
    expect(html).toContain("▼");
    expect(html).toContain("text-success");
  });
});

describe("renderMarkdownTemplate — sanitization", () => {
  it("strips <script> tags", () => {
    const tpl = "<div>{{= result.first.x}}</div>";
    const html = renderMarkdownTemplate(tpl, [
      { x: '<script>alert(1)</script>safe' },
    ]);
    expect(html).not.toContain("<script");
    expect(html).toContain("safe");
  });

  it("strips inline event handlers", () => {
    const tpl = '<button onclick="alert(1)">click</button>';
    const html = renderMarkdownTemplate(tpl, []);
    expect(html).not.toContain("onclick");
  });

  it("neutralizes javascript: URLs", () => {
    const tpl = '<a href="javascript:alert(1)">x</a>';
    const html = renderMarkdownTemplate(tpl, []);
    expect(html).not.toContain("javascript:");
  });
});
