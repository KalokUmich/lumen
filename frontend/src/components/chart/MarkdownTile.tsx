/**
 * Markdown viz primitive — IMPLEMENTATION_PLAN.md §19.1 #1.
 *
 * Renders an HTML/CSS template against the result rows, with:
 *   - Field bindings:   {{row.Region__name}}  {{row.Orders__count|number}}
 *   - Aggregate access: {{result.totalRows}}  {{result.first.Orders__count}}
 *   - Iterators:        {{#each rows}} ... {{/each}}
 *   - Conditional:      {{#if cond}} ... {{/if}}
 *   - Inline components: <Sparkline data="rows.Orders__count" />
 *                        <ChangeArrow value="result.first.Orders__delta" />
 *
 * The template is sandboxed: we render to a string, then mount via
 * `dangerouslySetInnerHTML` AFTER stripping <script> and inline event handlers.
 * Bindings are HTML-escaped by default; use `{{= raw }}` for trusted markup.
 */

import { useMemo } from "react";
import type { ChartSpec } from "./ChartSpec";
import { formatValue } from "../../lib/format";

type Row = Record<string, unknown>;

// ── Public surface ───────────────────────────────────────────────────────────

export function MarkdownTile({
  spec,
  rows,
  height = 320,
}: {
  spec: ChartSpec;
  rows: Row[];
  height?: number;
}) {
  const html = useMemo(
    () => renderMarkdownTemplate(spec.template ?? "", rows),
    [spec.template, rows],
  );
  return (
    <div
      data-testid="markdown-viz"
      className="prose prose-sm max-w-none p-4 text-fg"
      style={{ minHeight: height }}
      // The HTML has been sanitized by sanitizeHtml() inside render*().
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// ── Renderer ─────────────────────────────────────────────────────────────────

/**
 * Tiny Mustache-style renderer. Intentionally NOT a full Mustache impl — this
 * is the v0 of the showcase primitive, scope is fixed to what we need today.
 */
export function renderMarkdownTemplate(template: string, rows: Row[]): string {
  if (!template) return "";

  const ctx: TemplateContext = {
    rows,
    result: {
      totalRows: rows.length,
      first: rows[0] ?? {},
      last: rows[rows.length - 1] ?? {},
    },
  };

  let out = expandSections(template, ctx);
  out = expandComponents(out, ctx);
  out = expandBindings(out, ctx);
  return sanitizeHtml(out);
}

type TemplateContext = {
  rows: Row[];
  result: { totalRows: number; first: Row; last: Row };
};

// ── Sections: {{#each rows}}…{{/each}}, {{#if path}}…{{/if}} ──────────────────

const SECTION_RE = /\{\{#(each|if)\s+([\w.]+)\s*\}\}([\s\S]*?)\{\{\/\1\s*\}\}/g;

function expandSections(template: string, ctx: TemplateContext): string {
  return template.replace(SECTION_RE, (_full, kind, path, body) => {
    if (kind === "each") {
      const list = resolvePath(ctx, path);
      if (!Array.isArray(list)) return "";
      return list
        .map((item) => {
          const inner: TemplateContext = {
            ...ctx,
            // inside each, `row` aliases the current item
            // Cast keeps the row-shaped fields accessible via `row.field`.
            ...(typeof item === "object" && item !== null
              ? { row: item as Row }
              : { row: { value: item } as Row }),
          } as TemplateContext & { row: Row };
          // Expand components first (they reference `row.*`), then bindings.
          let out = expandComponents(body, inner);
          out = expandBindings(out, inner);
          return out;
        })
        .join("");
    }
    // {{#if path}} — truthy renders body, otherwise empty
    const v = resolvePath(ctx, path);
    return v ? body : "";
  });
}

// ── Inline components: <Sparkline data="..."/>, <ChangeArrow value="..." /> ─

const COMPONENT_RE = /<(Sparkline|ChangeArrow)\b([^/>]*)\/>/g;

function expandComponents(html: string, ctx: TemplateContext): string {
  return html.replace(COMPONENT_RE, (_full, name, attrs) => {
    const props = parseAttrs(attrs);
    if (name === "Sparkline") {
      const data = resolvePath(ctx, props.data ?? "");
      if (!Array.isArray(data)) return "";
      const nums = data
        .map((v) => (typeof v === "number" ? v : Number(v)))
        .filter((n) => Number.isFinite(n));
      return inlineSparklineSvg(nums, props);
    }
    if (name === "ChangeArrow") {
      const v = Number(resolvePath(ctx, props.value ?? "") ?? NaN);
      if (!Number.isFinite(v)) return "";
      return inlineChangeArrow(v, props);
    }
    return "";
  });
}

function parseAttrs(input: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /(\w+)=("([^"]*)"|'([^']*)')/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(input)) !== null) {
    out[m[1]] = m[3] ?? m[4] ?? "";
  }
  return out;
}

// ── Plain bindings: {{result.totalRows}} or {{row.field|format}} ─────────────

const BINDING_RE = /\{\{=?\s*([\w.]+)(?:\|(\w+))?\s*\}\}/g;

function expandBindings(template: string, ctx: TemplateContext): string {
  return template.replace(BINDING_RE, (full, path, fmt) => {
    const v = resolvePath(ctx, path);
    if (v === undefined || v === null) return "";
    let out: string;
    if (fmt === "raw") return String(v);
    if (fmt && (fmt === "currency" || fmt === "percent" || fmt === "number")) {
      const n = Number(v);
      out = Number.isFinite(n) ? formatValue(n, fmt) : String(v);
    } else if (typeof v === "number") {
      out = formatValue(v, "number");
    } else {
      out = String(v);
    }
    // {{= path}} returns raw (already returned above); plain {{path}} escapes.
    return full.includes("{{=") ? out : escapeHtml(out);
  });
}

// ── Path resolution ──────────────────────────────────────────────────────────

function resolvePath(ctx: TemplateContext, path: string): unknown {
  if (!path) return undefined;
  const parts = path.split(".");
  let cur: unknown = ctx as unknown;
  for (const p of parts) {
    if (cur === null || cur === undefined) return undefined;
    // shorthand: "rows.<field>" → array of values for that field across all rows
    if (Array.isArray(cur) && p !== "length") {
      cur = (cur as Row[]).map((r) => r?.[p]);
      continue;
    }
    cur = (cur as Record<string, unknown>)[p];
  }
  return cur;
}

// ── Helper components ────────────────────────────────────────────────────────

function inlineSparklineSvg(values: number[], props: Record<string, string>): string {
  if (values.length < 2) return "";
  const w = Number(props.width ?? 100);
  const h = Number(props.height ?? 28);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = w / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * stepX).toFixed(2)},${(h - ((v - min) / range) * h).toFixed(2)}`)
    .join(" ");
  const stroke = props.color ?? "currentColor";
  return (
    `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" ` +
    `class="inline-block align-middle text-accent" aria-hidden="true">` +
    `<polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="1.5" />` +
    `</svg>`
  );
}

function inlineChangeArrow(value: number, props: Record<string, string>): string {
  const positive = value >= 0;
  const goodWhen = (props.goodWhen ?? "up").toLowerCase();
  const isGood = goodWhen === "down" ? !positive : positive;
  const arrow = positive ? "▲" : "▼";
  const cls = isGood ? "text-success" : "text-danger";
  const fmt = (props.format ?? "percent") as "percent" | "currency" | "number";
  const formatted = formatValue(Math.abs(value), fmt);
  return (
    `<span class="inline-flex items-baseline gap-0.5 ${cls} font-medium">` +
    `<span aria-hidden="true">${arrow}</span><span>${escapeHtml(formatted)}</span>` +
    `</span>`
  );
}

// ── Sanitization ─────────────────────────────────────────────────────────────

const SCRIPT_RE = /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi;
const HANDLER_RE = /\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi;
const JS_HREF_RE = /\b(href|src)\s*=\s*("javascript:[^"]*"|'javascript:[^']*')/gi;

function sanitizeHtml(html: string): string {
  return html
    .replace(SCRIPT_RE, "")
    .replace(HANDLER_RE, "")
    .replace(JS_HREF_RE, "$1=\"#\"");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
