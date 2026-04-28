import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("renders H1/H2/H3 headings", () => {
    const out = renderMarkdown("# Big\n## Med\n### Small");
    expect(out).toContain("<h1>Big</h1>");
    expect(out).toContain("<h2>Med</h2>");
    expect(out).toContain("<h3>Small</h3>");
  });

  it("renders unordered lists", () => {
    const out = renderMarkdown("- one\n- two\n- three");
    expect(out).toContain("<ul>");
    expect(out).toMatch(/<li>one<\/li>[\s\S]*<li>two<\/li>/);
    expect(out).toContain("</ul>");
  });

  it("renders inline bold/italic/code", () => {
    const out = renderMarkdown("**bold** *em* `code`");
    expect(out).toContain("<strong>bold</strong>");
    expect(out).toContain("<em>em</em>");
    expect(out).toContain("<code>code</code>");
  });

  it("renders links with target=_blank", () => {
    const out = renderMarkdown("[docs](https://example.com)");
    expect(out).toContain('<a href="https://example.com"');
    expect(out).toContain("target=\"_blank\"");
    expect(out).toContain("rel=\"noopener noreferrer\"");
  });

  it("escapes raw HTML", () => {
    const out = renderMarkdown("<script>alert(1)</script>");
    expect(out).toContain("&lt;script&gt;");
    expect(out).not.toContain("<script>");
  });

  it("treats blank lines as paragraph separators", () => {
    const out = renderMarkdown("first\n\nsecond");
    expect(out).toContain("<p>first</p>");
    expect(out).toContain("<p>second</p>");
  });
});
