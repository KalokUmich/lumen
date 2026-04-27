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

import { useEffect, useRef } from "react";
import * as Plot from "@observablehq/plot";
import { ChartSpec, PALETTES } from "./ChartSpec";
import { formatValue, formatExact } from "../../lib/format";

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
  // Chart types that have their own custom (non-Plot) renderers.
  if (spec.type === "empty") return <EmptyState />;
  if (spec.type === "big-number") return <BigNumber spec={spec} rows={rows} />;
  if (spec.type === "kpi-strip") return <KPIStrip spec={spec} rows={rows} />;
  if (spec.type === "table") return <SimpleTable rows={rows} height={height} />;
  if (spec.type === "donut") return <Donut spec={spec} rows={rows} height={height} />;
  if (spec.type === "treemap") return <Treemap spec={spec} rows={rows} height={height} />;
  if (spec.type === "small-multiples-line")
    return <SmallMultiples spec={spec} rows={rows} height={height} />;

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
    const el = renderPlot(spec, rows, height, width, compact);
    ref.current.replaceChildren(el);
    return () => el.remove();
  }, [spec, rows, height, width, compact]);

  return <div ref={ref} className="w-full" />;
}

function tickFormatter(format?: "number" | "currency" | "percent") {
  return (d: unknown) => formatValue(d, format);
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
          marks.push(Plot.dot(rows, { x: xField, y: yField, fill: palette[0], r: 2.5 }));
        }
      }
      break;

    case "multi-line":
      if (xField && yField && colorField) {
        marks.push(
          Plot.line(rows, { x: xField, y: yField, stroke: colorField, strokeWidth: 1.5 })
        );
        if (rows.length <= 30) {
          marks.push(Plot.dot(rows, { x: xField, y: yField, fill: colorField, r: 2 }));
        }
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
            fill: palette[0],
            sort: { x: "y", reverse: true, limit: 30 },
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
            fill: palette[0],
            sort: { y: "x", reverse: true, limit: 30 },
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
            r: 3,
            fillOpacity: rows.length > 500 ? 0.3 : 0.8,
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
            fillOpacity: 0.6,
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
      if (xField && yField) {
        marks.push(
          Plot.dot(rows, {
            x: yField,
            y: xField,
            fill: palette[0],
            r: 4,
            sort: { y: "x", reverse: true },
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
  return Plot.plot({
    height,
    width,
    marginLeft: isHorizontal ? 100 : 56,
    marginBottom: 36,
    style: {
      background: "transparent",
      color: "var(--plot-text)",
      fontFamily: PLOT_FONT,
      fontSize: compact ? "10px" : "12px",
    },
    x: {
      label: spec.x?.label ?? null,
      grid: spec.type === "heatmap" ? false : (spec.type === "line" || spec.type === "area"),
      tickFormat: isHorizontal ? tickFormatter(spec.y?.format) : undefined,
    },
    y: {
      label: spec.y?.label ?? null,
      grid: true,
      tickFormat: isHorizontal ? undefined : tickFormatter(spec.y?.format),
      // Bar charts MUST start at zero per the skill §7.1
      ...(["bar", "horizontal-bar", "grouped-bar", "stacked-bar", "stacked-bar-100", "area", "stacked-area"].includes(spec.type)
        ? { zero: true }
        : {}),
    },
    color: spec.color
      ? { range: palette, legend: spec.type !== "heatmap" }
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
  const yField = spec.y?.field;
  const value = rows.length && yField ? Number(rows[0][yField]) : NaN;
  const label = spec.y?.label ?? yField ?? "";
  return (
    <div className="flex h-full flex-col items-start justify-center px-6 py-4">
      <div className="text-xs uppercase tracking-wider text-fg-muted">{label}</div>
      <div className="mt-1 text-4xl font-semibold tabular-nums text-fg" title={formatExact(value, spec.y?.format)}>
        {Number.isFinite(value) ? formatValue(value, spec.y?.format) : "—"}
      </div>
      {spec.subtitle && <div className="mt-1 text-xs text-fg-subtle">{spec.subtitle}</div>}
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

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
      {entries.map(([key, gRows]) => (
        <div key={key} className="rounded-md border border-border p-2">
          <div className="mb-1 truncate text-xs font-medium text-fg" title={key}>
            {key}
          </div>
          <PlotMount
            spec={{ ...spec, type: "line", color: undefined, facet: undefined }}
            rows={gRows}
            height={120}
            compact
          />
        </div>
      ))}
    </div>
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
