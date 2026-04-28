/**
 * Wrapper around Observable Plot with the chart vocabulary defined in
 * `.claude/skills/data-viz-standards/SKILL.md`.
 *
 * Each chart type is rendered following that skill's rules: bars start at zero
 * and sort descending; lines start near data range; donuts cap at 6 slices;
 * heatmaps use sequential palettes; etc.
 *
 * The component is intentionally a switch on spec.type — each branch is small
 * and easy to audit for compliance with the standards.
 */

import { useEffect, useRef, useState } from "react";
import * as Plot from "@observablehq/plot";
import { ChartSpec, PALETTES } from "./ChartSpec";
import { MarkdownTile } from "./MarkdownTile";
import { formatValue, formatExact, formatDate, parseDate } from "../../lib/format";
import { runQuery, type CubeQuery } from "../../lib/api";

type Row = Record<string, unknown>;

type Props = {
  spec: ChartSpec;
  rows: Row[];
  height?: number;
  width?: number;
  compact?: boolean;
};

const PLOT_FONT = "Inter Variable, Inter, system-ui, sans-serif";

export function PlotChart({ spec, rows, height = 320, width, compact = false }: Props) {
  // Tufte breathing room: title-block sits above the plot with clear vertical
  // rhythm; caption (axis explanations) sits below in muted italic.
  const showTitleBlock = !compact && (spec.title || spec.subtitle);
  return (
    <div className="flex flex-col">
      {showTitleBlock && (
        <div className="mb-4 px-1">
          {spec.title && (
            <div className="text-[16px] font-medium leading-snug text-fg">
              {spec.title}
            </div>
          )}
          {spec.subtitle && (
            <div className="mt-1 text-[13px] leading-snug text-fg-muted">
              {spec.subtitle}
            </div>
          )}
        </div>
      )}
      <PlotChartInner spec={spec} rows={rows} height={height} width={width} compact={compact} />
      {spec.caption && (
        <div className="mt-3 text-[12px] leading-relaxed text-fg-subtle italic">
          {spec.caption}
        </div>
      )}
    </div>
  );
}

function PlotChartInner({ spec, rows, height = 320, width, compact = false }: Props) {
  // Chart types that have their own custom (non-Plot) renderers.
  if (spec.type === "empty") return <EmptyState />;
  if (spec.type === "big-number") return <BigNumber spec={spec} rows={rows} />;
  if (spec.type === "kpi-strip") return <KPIStrip spec={spec} rows={rows} />;
  if (spec.type === "table") return <SimpleTable rows={rows} height={height} />;
  if (spec.type === "donut") return <Donut spec={spec} rows={rows} height={height} />;
  if (spec.type === "treemap") return <Treemap spec={spec} rows={rows} height={height} />;
  if (spec.type === "markdown")
    return <MarkdownTile spec={spec} rows={rows} height={height} />;
  if (spec.type === "small-multiples-line")
    return <SmallMultiples spec={spec} rows={rows} height={height} />;

  // Defensive fallback: if a Plot-rendered chart is missing required
  // encodings (e.g. saved workbook with `{type:"bar"}` but no x/y), Plot
  // would throw on render. Fall back to a table so we never crash.
  const needsXY = [
    "bar", "horizontal-bar", "grouped-bar", "stacked-bar", "stacked-bar-100",
    "line", "multi-line", "area", "stacked-area", "sparkline", "bullet",
    "scatter", "bubble", "heatmap", "dot-plot",
  ].includes(spec.type);
  if (needsXY && (!spec.x?.field || !spec.y?.field)) {
    return <SimpleTable rows={rows} height={height} />;
  }

  return <PlotMount spec={spec} rows={rows} height={height} width={width} compact={compact} />;
}

// ── Plot-rendered charts ──────────────────────────────────────────────────────

function PlotMount({
  spec,
  rows,
  height,
  width,
  compact = false,
}: {
  spec: ChartSpec;
  rows: Row[];
  height: number;
  width?: number;
  compact?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    // 1. Coerce time-x string values to Date objects → Plot uses time scale + nice ticks
    // 2. Sort rows so line/area marks draw in the right order
    const coerced = coerceTimes(spec, rows);
    const sortedRows = sortForChart(spec, coerced);
    const el = renderPlot(spec, sortedRows, height, width, compact);
    ref.current.replaceChildren(el);
    return () => el.remove();
  }, [spec, rows, height, width, compact]);

  return <div ref={ref} className="w-full" />;
}

/**
 * Sort rows for chart rendering.
 *
 * Cleveland-McGill canonical rules:
 *   - Time → ASC chronological
 *   - Ordinal with detected natural order (months, quarters, "1-URGENT" prefixes,
 *     loyalty tiers) → that natural order
 *   - Nominal (no order) → defer to server's default (which is by first measure
 *     DESC for non-time queries)
 *
 * This function ONLY overrides server order when we detect a known ordinal
 * pattern. Otherwise rows pass through unchanged.
 */
/**
 * Convert string time values into Date objects so Plot uses its time scale
 * (with nice tick labels) rather than treating them as ordinal strings.
 * Avoids TZ off-by-one by going through `parseDate` (local-time parser).
 */
function coerceTimes(spec: ChartSpec, rows: Row[]): Row[] {
  if (spec.x?.type !== "time" || !spec.x.field) return rows;
  const xField = spec.x.field;
  return rows.map((r) => {
    const v = r[xField];
    if (v instanceof Date) return r;
    const d = parseDate(v);
    return d ? { ...r, [xField]: d } : r;
  });
}

function sortForChart(spec: ChartSpec, rows: Row[]): Row[] {
  // Time-axis charts must be chronologically sorted regardless of server order.
  if (spec.x?.type === "time" && spec.x.field) {
    const xField = spec.x.field;
    return [...rows].sort((a, b) => {
      const av = a[xField];
      const bv = b[xField];
      const at = av instanceof Date ? av.getTime() : new Date(String(av)).getTime();
      const bt = bv instanceof Date ? bv.getTime() : new Date(String(bv)).getTime();
      return at - bt;
    });
  }

  // For categorical x: detect ordinal patterns and apply natural sort.
  if (spec.x?.type === "ordinal" && spec.x.field) {
    const xField = spec.x.field;
    const values = rows.map((r) => r[xField]).filter((v) => v != null);
    const ordinalSort = detectOrdinalSort(values);
    if (ordinalSort) {
      return [...rows].sort((a, b) => ordinalSort(a[xField], b[xField]));
    }
  }

  return rows;
}

/**
 * Detect whether a categorical column has a known ordinal pattern and return
 * a comparator that respects that order. Returns null if nominal (no detected
 * order) — the caller should keep server order.
 */
function detectOrdinalSort(values: unknown[]): ((a: unknown, b: unknown) => number) | null {
  const sample = Array.from(new Set(values.map((v) => String(v))));
  if (sample.length === 0) return null;

  // Pattern 1: numeric-prefix labels like "1-URGENT", "2-HIGH"
  const numericPrefixRe = /^(\d+)\s*[-_.\s]/;
  if (sample.every((s) => numericPrefixRe.test(s))) {
    return (a, b) => {
      const an = parseInt(String(a).match(numericPrefixRe)?.[1] ?? "0", 10);
      const bn = parseInt(String(b).match(numericPrefixRe)?.[1] ?? "0", 10);
      return an - bn;
    };
  }

  // Pattern 2: month names (Jan, Feb, January, February — case-insensitive)
  const months = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];
  const monthIdx = (s: unknown): number => {
    const lower = String(s).toLowerCase().slice(0, 3);
    return months.indexOf(lower);
  };
  if (sample.every((s) => monthIdx(s) >= 0)) {
    return (a, b) => monthIdx(a) - monthIdx(b);
  }

  // Pattern 3: day-of-week (Mon, Tue, Mon..., Sunday)
  const days = ["mon","tue","wed","thu","fri","sat","sun"];
  const dayIdx = (s: unknown): number => days.indexOf(String(s).toLowerCase().slice(0, 3));
  if (sample.every((s) => dayIdx(s) >= 0)) {
    return (a, b) => dayIdx(a) - dayIdx(b);
  }

  // Pattern 4: quarter labels Q1, Q2, Q3, Q4 (with optional year)
  const quarterRe = /^Q([1-4])(?:[\s\-_](\d{2,4}))?$/i;
  if (sample.every((s) => quarterRe.test(s))) {
    return (a, b) => {
      const am = String(a).match(quarterRe);
      const bm = String(b).match(quarterRe);
      // Sort by year first if present, then quarter
      const ay = am ? parseInt(am[2] ?? "0", 10) : 0;
      const by = bm ? parseInt(bm[2] ?? "0", 10) : 0;
      if (ay !== by) return ay - by;
      return parseInt(am?.[1] ?? "0", 10) - parseInt(bm?.[1] ?? "0", 10);
    };
  }

  // Pattern 5: known SaaS / loyalty tier labels (lower → higher)
  const tiers: Record<string, number> = {
    free: 0, basic: 1, starter: 2, growth: 3, pro: 4, business: 5,
    plus: 4, premium: 5, enterprise: 6, ultimate: 7,
    bronze: 0, silver: 1, gold: 2, platinum: 3, diamond: 4,
    low: 0, medium: 1, high: 2, critical: 3,
    none: 0, small: 1, large: 3, xl: 4, xxl: 5,
  };
  const tierIdx = (s: unknown): number | null => {
    const k = String(s).toLowerCase();
    return k in tiers ? tiers[k] : null;
  };
  if (sample.every((s) => tierIdx(s) !== null)) {
    return (a, b) => (tierIdx(a) ?? 0) - (tierIdx(b) ?? 0);
  }

  // Pattern 6: TPC-H order status (F, O, P) — known business meaning
  if (sample.every((s) => ["F","O","P"].includes(String(s)))) {
    const order: Record<string, number> = { F: 0, O: 1, P: 2 };
    return (a, b) => (order[String(a)] ?? 99) - (order[String(b)] ?? 99);
  }

  // Nominal — no detected order. Keep server-side sort.
  return null;
}

function tickFormatter(format?: "number" | "currency" | "percent") {
  return (d: unknown) => formatValue(d, format);
}

function timeTickFormatter(granularity?: string) {
  return (d: unknown) => formatDate(d, granularity);
}

function formatX(value: unknown, spec: ChartSpec): string {
  if (spec.x?.type === "time") return formatDate(value);
  return String(value ?? "");
}

function tooltipTitle(spec: ChartSpec) {
  const xField = spec.x?.field;
  const yField = spec.y?.field;
  const colorField = spec.color?.field;
  const yFormat = spec.y?.format;
  return (d: Row) => {
    const lines: string[] = [];
    if (colorField && d[colorField] != null) {
      lines.push(String(d[colorField]));
    } else if (xField && d[xField] != null) {
      lines.push(formatX(d[xField], spec));
    }
    if (yField && d[yField] != null) {
      lines.push(`${spec.y?.label ?? yField}: ${formatValue(d[yField], yFormat)}`);
    }
    if (xField && yField && d[xField] != null && colorField !== xField && colorField != null) {
      // For time series with a color category, also include the time label
      if (spec.x?.type === "time") {
        lines.push(`${spec.x.label ?? "Date"}: ${formatDate(d[xField])}`);
      }
    }
    return lines.join("\n");
  };
}

function renderPlot(
  spec: ChartSpec,
  rows: Row[],
  height: number,
  width: number | undefined,
  compact: boolean,
) {
  const palette = PALETTES[spec.color?.palette ?? "categorical"];
  const xField = spec.x?.field;
  const yField = spec.y?.field;
  const colorField = spec.color?.field;
  const isHorizontal = spec.type === "horizontal-bar";

  const marks: Plot.Markish[] = [];

  switch (spec.type) {
    case "line":
      if (xField && yField) {
        marks.push(Plot.line(rows, { x: xField, y: yField, stroke: palette[0], strokeWidth: 2 }));
        if (rows.length <= 30) {
          marks.push(Plot.dot(rows, { x: xField, y: yField, fill: palette[0], r: 3, className: "plot-mark-hover" }));
        }
        marks.push(Plot.tip(rows, Plot.pointerX({ x: xField, y: yField, title: tooltipTitle(spec) })));
      }
      break;

    case "multi-line":
      if (xField && yField && colorField) {
        marks.push(
          Plot.line(rows, { x: xField, y: yField, stroke: colorField, strokeWidth: 1.5 })
        );
        if (rows.length <= 30) {
          marks.push(Plot.dot(rows, { x: xField, y: yField, fill: colorField, r: 2.5, className: "plot-mark-hover" }));
        }
        marks.push(Plot.tip(rows, Plot.pointer({ x: xField, y: yField, title: tooltipTitle(spec) })));
      }
      break;

    case "area":
      if (xField && yField) {
        marks.push(Plot.areaY(rows, { x: xField, y: yField, fill: palette[0], fillOpacity: 0.4 }));
        marks.push(Plot.line(rows, { x: xField, y: yField, stroke: palette[0], strokeWidth: 2 }));
      }
      break;

    case "stacked-area":
      if (xField && yField && colorField) {
        marks.push(
          Plot.areaY(rows, { x: xField, y: yField, fill: colorField, fillOpacity: 0.7 })
        );
      }
      break;

    case "sparkline":
      if (xField && yField) {
        marks.push(
          Plot.line(rows, {
            x: xField,
            y: yField,
            stroke: palette[0],
            strokeWidth: 1.5,
          })
        );
      }
      return Plot.plot({
        height: 30,
        width: width ?? 100,
        marginLeft: 0,
        marginRight: 0,
        marginTop: 2,
        marginBottom: 2,
        x: { axis: null },
        y: { axis: null, grid: false },
        style: { background: "transparent" },
        marks,
      });

    case "bar":
      if (xField && yField) {
        marks.push(
          Plot.barY(rows, {
            x: xField,
            y: yField,
            fill: colorField ?? palette[0],
            sort: { x: "y", reverse: true, limit: 30 },
            inset: 2,                      // small gap between bars
            className: "plot-mark-hover",
            tip: { format: { y: tickFormatter(spec.y?.format) } },
          })
        );
      }
      break;

    case "horizontal-bar":
      if (xField && yField) {
        marks.push(
          Plot.barX(rows, {
            x: yField, // value
            y: xField, // category
            fill: colorField ?? palette[0],
            sort: { y: "x", reverse: true, limit: 30 },
            inset: 2,
            className: "plot-mark-hover",
            tip: { format: { x: tickFormatter(spec.y?.format) } },
          })
        );
      }
      break;

    case "grouped-bar":
      if (xField && yField && colorField) {
        marks.push(
          Plot.barY(rows, {
            x: xField,
            y: yField,
            fill: colorField,
            fx: xField,
            sort: { x: "y", reverse: true },
          })
        );
      } else if (xField && yField) {
        // Defence in depth: a grouped-bar without color is just a bar. The
        // visualizer should not emit this shape (see backend visualizer.py),
        // but if it does, render as plain bar instead of blank.
        marks.push(
          Plot.barY(rows, {
            x: xField,
            y: yField,
            sort: { x: "y", reverse: true },
          })
        );
      }
      break;

    case "stacked-bar":
      if (xField && yField && colorField) {
        marks.push(
          Plot.barY(rows, {
            x: xField,
            y: yField,
            fill: colorField,
            sort: { x: "y", reverse: true },
          })
        );
      }
      break;

    case "stacked-bar-100":
      if (xField && yField && colorField) {
        marks.push(
          Plot.barY(rows, {
            x: xField,
            y: yField,
            fill: colorField,
            offset: "normalize",
          })
        );
      }
      break;

    case "scatter": {
      const m1 = spec.x?.field;
      const m2 = spec.y?.field;
      if (m1 && m2) {
        marks.push(
          Plot.dot(rows, {
            x: m1,
            y: m2,
            fill: colorField ?? palette[0],
            r: 3.5,
            fillOpacity: rows.length > 500 ? 0.3 : 0.8,
            className: "plot-mark-hover",
            tip: true,
          })
        );
      }
      break;
    }

    case "bubble":
      if (spec.x?.field && spec.y?.field) {
        marks.push(
          Plot.dot(rows, {
            x: spec.x.field,
            y: spec.y.field,
            r: spec.size?.field ?? 4,
            fill: colorField ?? palette[0],
            fillOpacity: 0.7,
            className: "plot-mark-hover",
            tip: true,
          })
        );
      }
      break;

    case "heatmap":
      if (xField && yField && colorField) {
        marks.push(
          Plot.cell(rows, {
            x: xField,
            y: yField,
            fill: colorField,
            inset: 0.5,
          })
        );
        marks.push(
          Plot.text(rows, {
            x: xField,
            y: yField,
            text: (d: Row) =>
              typeof d[colorField] === "number" ? formatValue(d[colorField], "number") : "",
            fontSize: 10,
            fill: "white",
            stroke: "black",
            strokeOpacity: 0.4,
            strokeWidth: 2,
          })
        );
      }
      break;

    case "dot-plot":
      // Dot-plot — used when bar's length encoding is wasteful (clustered values).
      // Renders as a horizontal lollipop: thin connecting line + bold dot.
      // Y-axis is NOT zero-based (skill §4.10) — position encodes value, no lie factor.
      if (xField && yField) {
        marks.push(
          Plot.ruleY(rows, {
            x: yField,
            y: xField,
            stroke: colorField ?? "#3A3F49",
            strokeOpacity: 0.4,
            strokeWidth: 1,
          })
        );
        marks.push(
          Plot.dot(rows, {
            x: yField,
            y: xField,
            fill: colorField ?? palette[0],
            r: 7,
            stroke: "white",
            strokeWidth: 2,
            sort: { y: "x", reverse: true },
            className: "plot-mark-hover",
            tip: { format: { x: tickFormatter(spec.y?.format) } },
          })
        );
      }
      break;

    case "bullet": {
      // Simple bullet: actual bar + target rule. spec.y = actual; annotations[0].target = target value
      if (yField && rows.length > 0) {
        const value = Number(rows[0][yField]) || 0;
        const target = Number(spec.annotations?.[0]?.target ?? 0);
        marks.push(Plot.barX([{ value }], { x: "value", fill: palette[0], y: () => "" }));
        if (target > 0) {
          marks.push(
            Plot.tickX([{ target }], {
              x: "target",
              y: () => "",
              stroke: "white",
              strokeWidth: 3,
            })
          );
        }
      }
      return Plot.plot({
        height: 40,
        width: width ?? 200,
        marginLeft: 0,
        marginRight: 8,
        marginTop: 4,
        marginBottom: 16,
        x: { tickFormat: tickFormatter(spec.y?.format) },
        y: { axis: null },
        style: { background: "transparent", color: "var(--plot-text)", fontFamily: PLOT_FONT },
        marks,
      });
    }
  }

  // Default Plot config (line/bar/area/scatter/heatmap/etc).
  // Dot-plot intentionally uses a non-zero baseline (skill §4.10).
  const isDotPlot = spec.type === "dot-plot";
  const isHorizontalLayout = isHorizontal || isDotPlot;

  // Compute padded value range for dot-plot (5% padding on each side)
  let valueDomain: [number, number] | undefined;
  if (isDotPlot && yField) {
    const vals = rows.map((r) => Number(r[yField])).filter(Number.isFinite);
    if (vals.length) {
      const lo = Math.min(...vals);
      const hi = Math.max(...vals);
      const pad = (hi - lo) * 0.08 || hi * 0.05;
      valueDomain = [lo - pad, hi + pad];
    }
  }

  // Detect long x-axis labels — if labels are long enough to overlap on a
  // vertical bar, rotate them. Use horizontal layout if rotation alone isn't
  // enough.
  const xValuesForLabels = xField && spec.x?.type !== "time"
    ? rows.map((r) => String(r[xField] ?? ""))
    : [];
  const maxXLabelLen = xValuesForLabels.reduce((m, v) => Math.max(m, v.length), 0);
  const xLabelOverflow = maxXLabelLen > 8 && xValuesForLabels.length > 4;
  const tickRotate = xLabelOverflow && !isHorizontalLayout ? -30 : 0;
  const dynamicMarginBottom = tickRotate ? Math.min(80, 36 + maxXLabelLen * 4) : 36;

  // Tufte breathing-room defaults (skill §23). Generous margins are not
  // wasted ink — they're separator space that lets the data sit cleanly.
  // Compact mode (chat-embedded) pulls tighter; default tile uses full rhythm.
  const baseTop = compact ? 24 : 32;
  const baseRight = compact ? 16 : 24;
  const baseLeft = isHorizontalLayout
    ? Math.min(180, 72 + maxXLabelLen * 5)
    : (compact ? 48 : 56);
  const baseBottom = Math.max(compact ? 32 : 40, dynamicMarginBottom);

  return Plot.plot({
    height,
    width,
    marginTop: baseTop,
    marginLeft: baseLeft,
    marginBottom: baseBottom,
    marginRight: isHorizontalLayout ? (compact ? 24 : 32) : baseRight,
    style: {
      background: "transparent",
      color: "var(--plot-text)",
      fontFamily: PLOT_FONT,
      fontSize: compact ? "11px" : "12px",
    },
    x: {
      label: isDotPlot ? (spec.y?.label ?? null) : (spec.x?.label ?? null),
      grid: isDotPlot ? true : (spec.type === "heatmap" ? false : (spec.type === "line" || spec.type === "area")),
      tickFormat: isHorizontalLayout
        ? tickFormatter(spec.y?.format)
        : (spec.x?.type === "time" ? timeTickFormatter() : undefined),
      tickRotate,
      ...(valueDomain ? { domain: valueDomain } : {}),
    },
    y: {
      label: isDotPlot ? (spec.x?.label ?? null) : (spec.y?.label ?? null),
      grid: !isDotPlot,
      tickFormat: isHorizontalLayout ? undefined : tickFormatter(spec.y?.format),
      // Bar charts MUST start at zero per the skill §7.1.
      // Dot-plot deliberately does NOT — the whole point is to zoom in on tight values.
      ...(["bar", "horizontal-bar", "grouped-bar", "stacked-bar", "stacked-bar-100", "area", "stacked-area"].includes(spec.type)
        ? { zero: true }
        : {}),
    },
    color: spec.color
      ? {
          range: palette,
          // Tufte R5 (erase redundant ink): suppress legend when color
          // encodes the same field as X — the X-axis labels already name the
          // categories. Heatmaps & dot-plots skip the standard legend
          // anyway.
          legend:
            spec.type !== "heatmap" &&
            spec.type !== "dot-plot" &&
            spec.color.field !== spec.x?.field,
        }
      : undefined,
    marks,
  });
}

// ── Custom (non-Plot) renderers ──────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-border text-sm text-fg-muted">
      No data for this query.
    </div>
  );
}

function BigNumber({ spec, rows }: { spec: ChartSpec; rows: Row[] }) {
  const empty = rows.length === 0;
  // The row keys come back from Cube with underscores (e.g. "LineItem__revenue").
  // If we can't find the explicit yField, fall back to the first numeric key
  // so a missing/stale spec doesn't blank-out the panel.
  const explicitField = spec.y?.field;
  let value = NaN;
  let resolvedKey: string | undefined;
  if (rows.length) {
    if (explicitField && rows[0][explicitField] != null) {
      value = Number(rows[0][explicitField]);
      resolvedKey = explicitField;
    } else {
      // fallback: first numeric column
      for (const k of Object.keys(rows[0])) {
        const v = rows[0][k];
        if (typeof v === "number" && Number.isFinite(v)) {
          value = v;
          resolvedKey = k;
          break;
        }
      }
    }
  }
  const label = spec.y?.label ?? resolvedKey ?? "";
  if (empty) {
    return (
      <div
        data-testid="big-number"
        className="flex min-h-[160px] flex-col items-start justify-center px-6 py-6"
      >
        <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-fg-muted">{label}</div>
        <div className="mt-3 text-2xl font-medium text-fg-muted tabular-nums">No data for this period</div>
        {spec.subtitle && <div className="mt-2 text-xs text-fg-subtle">{spec.subtitle}</div>}
      </div>
    );
  }
  // min-h ensures we render with a visible footprint even when parent has
  // no explicit height (e.g. chat bubbles use content-based sizing). Earlier
  // we used `h-full` which collapsed to 0 in flex/auto-height contexts.
  return (
    <div
      data-testid="big-number"
      className="flex min-h-[160px] flex-col items-start justify-center px-6 py-6"
    >
      <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-fg-muted">{label}</div>
      <div className="mt-3 flex items-baseline gap-3">
        <div
          className="text-[32px] font-semibold leading-tight tabular-nums text-fg"
          title={formatExact(value, spec.y?.format)}
        >
          {Number.isFinite(value) ? formatValue(value, spec.y?.format) : "—"}
        </div>
        {spec.compare && Number.isFinite(value) && (
          <CompareDelta spec={spec} currentValue={value} />
        )}
      </div>
      {spec.subtitle && <div className="mt-2 text-xs text-fg-subtle">{spec.subtitle}</div>}
    </div>
  );
}

/** Period-over-period: re-runs the query with the prior date range, shows ↑/↓ delta. */
function CompareDelta({ spec, currentValue }: { spec: ChartSpec; currentValue: number }) {
  const compare = spec.compare!;
  const yField = spec.y?.field;
  const [prior, setPrior] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!yField) return;
    setLoading(true);
    const measure = yField.replace("__", ".");
    const query: CubeQuery = {
      measures: [measure],
      timeDimensions: [{ dimension: compare.time_dimension, dateRange: compare.prior_date_range }],
    };
    runQuery(query)
      .then((r) => {
        const v = r.data[0]?.[yField];
        setPrior(typeof v === "number" ? v : v != null ? Number(v) : null);
      })
      .catch(() => setPrior(null))
      .finally(() => setLoading(false));
  }, [yField, compare.prior_date_range, compare.time_dimension]);

  if (loading) return <span className="text-xs text-fg-subtle">…</span>;
  if (prior == null || !Number.isFinite(prior) || prior === 0) {
    return <span className="text-xs text-fg-subtle">{compare.label}</span>;
  }
  const delta = (currentValue - prior) / Math.abs(prior);
  const arrow = delta >= 0 ? "↑" : "↓";
  const color = delta >= 0 ? "text-success" : "text-danger";
  return (
    <div className={`flex items-baseline gap-1 text-sm font-medium ${color}`}>
      <span>{arrow}</span>
      <span>{Math.abs(delta * 100).toFixed(1)}%</span>
      <span className="text-xs font-normal text-fg-subtle">{compare.label}</span>
    </div>
  );
}

function KPIStrip({ spec, rows }: { spec: ChartSpec; rows: Row[] }) {
  if (!rows[0]) return <EmptyState />;
  const cols = Object.keys(rows[0]).filter((k) => typeof rows[0][k] === "number");
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4 p-2">
      {cols.map((key) => (
        <div key={key} className="rounded-md border border-border bg-bg-elevated p-3">
          <div className="text-[10px] uppercase tracking-wider text-fg-muted">{key.replace(/__/g, " ")}</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums text-fg" title={String(rows[0][key])}>
            {formatValue(rows[0][key], spec.y?.format)}
          </div>
        </div>
      ))}
    </div>
  );
}

function Donut({ spec, rows, height }: { spec: ChartSpec; rows: Row[]; height: number }) {
  if (rows.length === 0) return <EmptyState />;
  const yField = spec.y?.field;
  const colorField = spec.color?.field;
  if (!yField || !colorField) return <EmptyState />;

  // Cap at 6 slices per skill §4.13
  const sorted = [...rows].sort((a, b) => Number(b[yField]) - Number(a[yField]));
  const top = sorted.slice(0, 6);
  const rest = sorted.slice(6);
  const sliced = rest.length
    ? [
        ...top,
        { [colorField]: "Other", [yField]: rest.reduce((s, r) => s + Number(r[yField] ?? 0), 0) },
      ]
    : top;

  const total = sliced.reduce((s, r) => s + Number(r[yField] ?? 0), 0);
  const palette = PALETTES.categorical;

  // SVG donut: simple geometry, no extra dep.
  const cx = height / 2;
  const cy = height / 2;
  const r = height / 2 - 10;
  const innerR = r * 0.6;

  let cumulative = 0;
  const arcs = sliced.map((row, i) => {
    const value = Number(row[yField] ?? 0);
    const startAngle = (cumulative / total) * 2 * Math.PI;
    cumulative += value;
    const endAngle = (cumulative / total) * 2 * Math.PI;
    return {
      label: String(row[colorField]),
      value,
      pct: (value / total) * 100,
      d: arcPath(cx, cy, r, innerR, startAngle, endAngle),
      color: palette[i % palette.length],
    };
  });

  return (
    <div className="flex items-center gap-6">
      <svg width={height} height={height} viewBox={`0 0 ${height} ${height}`}>
        {arcs.map((a, i) => (
          <path key={i} d={a.d} fill={a.color}>
            <title>{`${a.label}: ${formatValue(a.value, spec.y?.format)} (${a.pct.toFixed(1)}%)`}</title>
          </path>
        ))}
        <text x={cx} y={cy - 4} textAnchor="middle" className="fill-fg" fontSize="14" fontWeight="600">
          {formatValue(total, spec.y?.format)}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" className="fill-fg-muted" fontSize="10">
          total
        </text>
      </svg>
      <div className="flex flex-col gap-1 text-xs">
        {arcs.map((a, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: a.color }} />
            <span className="text-fg">{a.label}</span>
            <span className="text-fg-muted">{a.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function arcPath(
  cx: number,
  cy: number,
  outer: number,
  inner: number,
  startAngle: number,
  endAngle: number,
) {
  const start = polar(cx, cy, outer, startAngle);
  const end = polar(cx, cy, outer, endAngle);
  const innerStart = polar(cx, cy, inner, endAngle);
  const innerEnd = polar(cx, cy, inner, startAngle);
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
  return [
    `M ${start.x} ${start.y}`,
    `A ${outer} ${outer} 0 ${largeArc} 1 ${end.x} ${end.y}`,
    `L ${innerStart.x} ${innerStart.y}`,
    `A ${inner} ${inner} 0 ${largeArc} 0 ${innerEnd.x} ${innerEnd.y}`,
    "Z",
  ].join(" ");
}

function polar(cx: number, cy: number, r: number, angle: number) {
  return { x: cx + r * Math.sin(angle), y: cy - r * Math.cos(angle) };
}

function Treemap({ spec, rows, height }: { spec: ChartSpec; rows: Row[]; height: number }) {
  // Squarified treemap layout — basic implementation.
  if (rows.length === 0) return <EmptyState />;
  const yField = spec.y?.field;
  const colorField = spec.color?.field;
  if (!yField || !colorField) return <EmptyState />;

  const items = rows
    .map((r) => ({ label: String(r[colorField]), value: Math.max(0, Number(r[yField] ?? 0)) }))
    .filter((d) => d.value > 0)
    .sort((a, b) => b.value - a.value);

  const total = items.reduce((s, d) => s + d.value, 0);
  if (total === 0) return <EmptyState />;

  // Simple slice-and-dice — sufficient for v1
  const W = 800;
  const H = height;
  let x = 0;
  const cells = items.map((d, i) => {
    const w = (d.value / total) * W;
    const cell = { ...d, x, y: 0, w, h: H, color: PALETTES.categorical[i % PALETTES.categorical.length] };
    x += w;
    return cell;
  });

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={H}>
        {cells.map((c, i) => (
          <g key={i}>
            <rect x={c.x} y={c.y} width={c.w} height={c.h} fill={c.color} stroke="#0B0D10" strokeWidth={2}>
              <title>{`${c.label}: ${formatValue(c.value, spec.y?.format)}`}</title>
            </rect>
            {c.w > 60 && (
              <text x={c.x + 8} y={c.y + 18} fill="white" fontSize="11" fontWeight="600">
                {c.label}
              </text>
            )}
            {c.w > 60 && (
              <text x={c.x + 8} y={c.y + 32} fill="rgba(255,255,255,0.85)" fontSize="10">
                {formatValue(c.value, spec.y?.format)}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

function SmallMultiples({
  spec,
  rows,
  height,
}: {
  spec: ChartSpec;
  rows: Row[];
  height: number;
}) {
  const groupField = spec.facet?.column ?? spec.color?.field;
  if (!groupField) return <PlotMount spec={{ ...spec, type: "line" }} rows={rows} height={height} />;

  // Group rows by group field
  const groups = new Map<string, Row[]>();
  for (const r of rows) {
    const k = String(r[groupField]);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(r);
  }
  const entries = Array.from(groups.entries()).slice(0, 12);

  // Density: 2 panels per row by default (Tufte: each panel needs to be
  // *legible*, not just *visible*). User can switch to 3 if data is tall &
  // shallow. 4-col is gone — it always made panels too small to read.
  const [cols, setCols] = useState<2 | 3>(2);
  const colsClass =
    cols === 2 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3";
  // Per-panel height grows when the grid is sparser.
  const panelHeight = cols === 2 ? 200 : 150;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-fg-subtle">
          {entries.length} panels — click any one to expand
        </div>
        <DensityToggle cols={cols} onChange={setCols} />
      </div>
      <div className={`grid gap-4 ${colsClass}`}>
        {entries.map(([key, gRows]) => (
          <SmallMultiplePanel
            key={key}
            title={key}
            spec={spec}
            rows={gRows}
            height={panelHeight}
          />
        ))}
      </div>
    </div>
  );
}

function DensityToggle({
  cols,
  onChange,
}: {
  cols: 2 | 3;
  onChange: (n: 2 | 3) => void;
}) {
  const Btn = ({ n, label }: { n: 2 | 3; label: string }) => (
    <button
      onClick={() => onChange(n)}
      aria-pressed={cols === n}
      className={`px-2 py-0.5 text-[11px] font-medium transition-colors ${
        cols === n
          ? "bg-accent/15 text-accent"
          : "text-fg-subtle hover:text-fg"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-border bg-bg-elevated">
      <Btn n={2} label="2-up" />
      <span className="w-px bg-border" />
      <Btn n={3} label="3-up" />
    </div>
  );
}

function SmallMultiplePanel({
  title,
  spec,
  rows,
  height,
}: {
  title: string;
  spec: ChartSpec;
  rows: Row[];
  height: number;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  // The inline panel uses the slim "no chrome" treatment. The expanded
  // version drops `compact` to render the full title block + Plot at full
  // size — same single-source-of-truth ChartSpec, two layouts.
  const inlineSpec: ChartSpec = {
    ...spec,
    type: "line",
    color: undefined,
    facet: undefined,
    title: undefined,
    subtitle: undefined,
  };
  const expandedSpec: ChartSpec = {
    ...spec,
    type: "line",
    color: undefined,
    facet: undefined,
    title: title,
    subtitle: spec.subtitle,
  };

  function open() {
    dialogRef.current?.showModal();
  }
  function close() {
    dialogRef.current?.close();
  }

  return (
    <>
      <button
        type="button"
        onClick={open}
        title={`Click to expand · ${title}`}
        data-testid={`sm-panel-${title}`}
        className="group relative block w-full rounded-md border border-border bg-bg-elevated p-3 text-left transition-colors hover:border-accent/60 hover:bg-bg-subtle/40"
      >
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="truncate text-[13px] font-medium text-fg">{title}</span>
          <span
            className="flex h-5 w-5 items-center justify-center rounded text-fg-subtle opacity-0 transition-opacity group-hover:opacity-100"
            aria-hidden="true"
          >
            <ExpandIcon />
          </span>
        </div>
        <PlotMount spec={inlineSpec} rows={rows} height={height} compact />
      </button>

      {/* Native <dialog> — backdrop + Esc-to-close + a11y for free. */}
      <dialog
        ref={dialogRef}
        data-testid={`sm-dialog-${title}`}
        onClick={(e) => {
          // Click outside the modal body closes it.
          if (e.target === dialogRef.current) close();
        }}
        className="m-0 w-full max-w-4xl rounded-md border border-border bg-bg-elevated p-0 backdrop:bg-black/60 backdrop:backdrop-blur-sm sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="text-[15px] font-medium text-fg">{title}</div>
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            className="flex h-7 w-7 items-center justify-center rounded text-fg-subtle hover:bg-bg-subtle hover:text-fg"
          >
            ✕
          </button>
        </div>
        <div className="px-5 py-5">
          <PlotMount spec={expandedSpec} rows={rows} height={420} />
        </div>
      </dialog>
    </>
  );
}

function ExpandIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="15 3 21 3 21 9" />
      <polyline points="9 21 3 21 3 15" />
      <line x1="21" y1="3" x2="14" y2="10" />
      <line x1="3" y1="21" x2="10" y2="14" />
    </svg>
  );
}

function SimpleTable({ rows, height }: { rows: Row[]; height: number }) {
  if (rows.length === 0) return <EmptyState />;
  const cols = Object.keys(rows[0]);
  return (
    <div className="overflow-auto" style={{ maxHeight: height }}>
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-bg-elevated">
          <tr>
            {cols.map((c) => (
              <th
                key={c}
                className="border-b border-border px-3 py-2 text-left font-medium text-fg-muted"
              >
                {c.replace(/__/g, " · ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 1000).map((r, i) => (
            <tr key={i} className="hover:bg-bg-subtle">
              {cols.map((c) => (
                <td key={c} className="border-b border-border px-3 py-1.5 num">
                  {typeof r[c] === "number" ? formatValue(r[c]) : String(r[c] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
