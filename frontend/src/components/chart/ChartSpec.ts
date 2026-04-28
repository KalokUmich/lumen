import { z } from "zod";

export const FieldRef = z.object({
  field: z.string(),
  type: z.enum(["time", "ordinal", "quantitative"]).optional(),
  agg: z.enum(["sum", "avg", "count"]).optional(),
  format: z.enum(["number", "currency", "percent"]).optional(),
  label: z.string().optional(),
});
export type FieldRef = z.infer<typeof FieldRef>;

export const ColorRef = z.object({
  field: z.string(),
  palette: z.enum(["categorical", "sequential", "diverging"]).default("categorical"),
});
export type ColorRef = z.infer<typeof ColorRef>;

export const FacetRef = z.object({
  row: z.string().optional(),
  column: z.string().optional(),
});
export type FacetRef = z.infer<typeof FacetRef>;

export const ChartType = z.enum([
  "big-number",
  "kpi-strip",
  "bar",
  "horizontal-bar",
  "grouped-bar",
  "stacked-bar",
  "stacked-bar-100",
  "line",
  "multi-line",
  "small-multiples-line",
  "area",
  "stacked-area",
  "sparkline",
  "bullet",
  "dot-plot",
  "scatter",
  "bubble",
  "heatmap",
  "donut",
  "treemap",
  "table",
  "markdown",
  "empty",
]);
export type ChartType = z.infer<typeof ChartType>;

export const ChartSpec = z.object({
  type: ChartType,
  x: FieldRef.optional(),
  y: FieldRef.optional(),
  color: ColorRef.optional(),
  size: FieldRef.optional(),
  facet: FacetRef.optional(),
  title: z.string().optional(),
  subtitle: z.string().optional(),
  caption: z.string().optional(),  // shown below the plot, decodes abbreviations
  compare: z
    .object({
      prior_date_range: z.string(),
      label: z.string(),
      time_dimension: z.string(),
    })
    .optional(),
  annotations: z.array(z.record(z.unknown())).optional(),
  rationale: z.string().optional(),
  confidence: z.number().optional(),
  alt_text: z.string().optional(),
  // Markdown viz primitive (§19.1 #1). When type === "markdown", `template`
  // holds Mustache-bound HTML the renderer fills against the result rows.
  template: z.string().optional(),
});
export type ChartSpec = z.infer<typeof ChartSpec>;

export const PALETTES = {
  categorical: [
    "#5B8FF9",
    "#5AD8A6",
    "#5D7092",
    "#F6BD16",
    "#E8684A",
    "#6DC8EC",
    "#9270CA",
    "#FF9D4D",
    "#269A99",
    "#FF99C3",
  ],
  sequential: ["#EAF1FF", "#C5D9FF", "#8BB1FF", "#5B8FF9", "#2E5CD8", "#1A3A9C"],
  diverging: ["#D63E3E", "#F09494", "#F2F2F2", "#9DBFE3", "#1F5BB5"],
};
