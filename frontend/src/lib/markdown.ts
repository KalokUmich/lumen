/**
 * Tiny dependency-free markdown renderer for dashboard notes.
 * Covers: H1/H2/H3, bold, italic, inline code, unordered lists, links, paragraphs.
 * Escapes everything before applying syntax — the caller can dangerouslySetInnerHTML safely.
 *
 * If we ever need fenced code blocks, tables, GFM, or footnotes, swap to react-markdown + remark-gfm.
 */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function inline(s: string): string {
  let safe = escapeHtml(s);
  safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");
  safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  safe = safe.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, text, url) => {
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  });
  return safe;
}

export function renderMarkdown(source: string): string {
  const lines = source.split(/\r?\n/);
  const out: string[] = [];
  let inList = false;
  for (const line of lines) {
    const liMatch = line.match(/^\s*[-*]\s+(.+)$/);
    if (liMatch) {
      if (!inList) {
        out.push("<ul>");
        inList = true;
      }
      out.push(`<li>${inline(liMatch[1])}</li>`);
      continue;
    }
    if (inList) {
      out.push("</ul>");
      inList = false;
    }
    const h3 = line.match(/^###\s+(.+)$/);
    if (h3) { out.push(`<h3>${inline(h3[1])}</h3>`); continue; }
    const h2 = line.match(/^##\s+(.+)$/);
    if (h2) { out.push(`<h2>${inline(h2[1])}</h2>`); continue; }
    const h1 = line.match(/^#\s+(.+)$/);
    if (h1) { out.push(`<h1>${inline(h1[1])}</h1>`); continue; }
    if (line.trim() === "") { out.push(""); continue; }
    out.push(`<p>${inline(line)}</p>`);
  }
  if (inList) out.push("</ul>");
  return out.join("\n");
}
