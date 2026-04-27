/**
 * Workbench — Omni-class exploratory analysis surface.
 *
 * Layout:
 *   ┌─────────┬─────────────────────────────┬─────────────┐
 *   │ Field   │ Query builder + chart       │ AI assist   │
 *   │ picker  │ (auto chart-type selection) │ + saved     │
 *   │         │ Save / Run buttons          │ workbooks   │
 *   └─────────┴─────────────────────────────┴─────────────┘
 */

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Play, Save, Bot } from "lucide-react";
import {
  runQuery,
  listWorkbooks,
  saveWorkbook,
  getSchemaBundle,
  getActiveWorkspace,
  type CubeQuery,
} from "../../lib/api";
import { parseSchema, SchemaMember } from "../../lib/schema";
import { PlotChart } from "../chart/PlotChart";
import { ChartSpec } from "../chart/ChartSpec";
import { FieldPicker } from "./FieldPicker";

type Granularity = "day" | "week" | "month" | "quarter" | "year";

export function Workbench() {
  const workspaceId = getActiveWorkspace();
  const qc = useQueryClient();

  const [measures, setMeasures] = useState<SchemaMember[]>([]);
  const [dimensions, setDimensions] = useState<SchemaMember[]>([]);
  const [timeDim, setTimeDim] = useState<SchemaMember | null>(null);
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [segments, setSegments] = useState<SchemaMember[]>([]);
  const [limit, setLimit] = useState<number | "">("");
  const [name, setName] = useState("Untitled query");

  const schemaQuery = useQuery({
    queryKey: ["schema", workspaceId],
    queryFn: () => getSchemaBundle(workspaceId),
  });
  const schemas = useMemo(
    () => (schemaQuery.data ? parseSchema(schemaQuery.data.schema_summary) : []),
    [schemaQuery.data]
  );

  const workbooks = useQuery({
    queryKey: ["workbooks", workspaceId],
    queryFn: () => listWorkbooks(workspaceId),
  });

  const cubeQuery: CubeQuery = useMemo(() => {
    const q: CubeQuery = {
      measures: measures.map((m) => m.fullName),
      dimensions: dimensions.map((d) => d.fullName),
    };
    if (timeDim) {
      q.timeDimensions = [{ dimension: timeDim.fullName, granularity }];
    }
    if (segments.length) {
      q.segments = segments.map((s) => s.fullName);
    }
    if (typeof limit === "number" && limit > 0) {
      q.limit = limit;
    }
    if (measures.length > 0 && (dimensions.length > 0 || timeDim)) {
      q.order = { [measures[0].fullName]: "desc" };
    }
    return q;
  }, [measures, dimensions, timeDim, granularity, segments, limit]);

  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (measures.length === 0) {
      setError("Pick at least one measure to run.");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const result = await runQuery(cubeQuery);
      setRows(result.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  // Auto-run when query shape changes meaningfully
  useEffect(() => {
    if (measures.length > 0) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measures.length, dimensions.length, !!timeDim, granularity, segments.length, limit]);

  // Mirror the visualizer subagent's logic on the frontend so the workbench
  // preview shows the SAME chart the AI would have picked. (Server-side
  // visualizer is authoritative for AI-generated charts; this is the
  // workbench manual-build preview.)
  const chartSpec: ChartSpec = useMemo(() => {
    const M = measures.length;
    const D = dimensions.length;
    const T = !!timeDim;
    let type: ChartSpec["type"] = "table";
    if (rows.length === 0) type = "empty";
    else if (M === 1 && D === 0 && !T && rows.length === 1) type = "big-number";
    else if (T && M === 1 && D === 0) type = "line";
    else if (T && M === 1 && D === 1) type = "multi-line";
    else if (M === 1 && D === 1 && !T) type = dimensions[0] && rows.length > 8 ? "horizontal-bar" : "bar";
    else if (M === 1 && D === 2 && !T) type = "heatmap";
    else if (M === 2 && D <= 1 && !T) type = "scatter";
    else type = "table";

    const spec: ChartSpec = { type };
    if (timeDim) {
      spec.x = { field: timeDim.fullName.replace(/\./g, "__"), type: "time", label: timeDim.name };
    } else if (dimensions[0] && type !== "scatter") {
      spec.x = { field: dimensions[0].fullName.replace(/\./g, "__"), type: "ordinal", label: dimensions[0].name };
    }
    if (measures[0]) {
      const fmt: "currency" | "number" | "percent" = measures[0].meta?.includes("currency") ? "currency" : "number";
      spec.y = { field: measures[0].fullName.replace(/\./g, "__"), format: fmt, label: measures[0].name };
    }
    if (dimensions[1] || (T && D === 1)) {
      const dim = T ? dimensions[0] : dimensions[1];
      if (dim) spec.color = { field: dim.fullName.replace(/\./g, "__"), palette: "categorical" };
    }
    return spec;
  }, [rows, measures, dimensions, timeDim]);

  const saveMut = useMutation({
    mutationFn: () =>
      saveWorkbook({
        workspace_id: workspaceId,
        name,
        cube_query: cubeQuery,
        chart_spec: chartSpec,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workbooks", workspaceId] }),
  });

  function loadWorkbook(wb: { name: string; cube_query: CubeQuery }) {
    setName(wb.name);
    // We can't perfectly reverse the schema lookups here without enriching the
    // saved record; for the field picker UX, just reset and apply the raw query.
    const m: SchemaMember[] = [];
    const d: SchemaMember[] = [];
    let td: SchemaMember | null = null;
    const seg: SchemaMember[] = [];

    const lookup = (full: string): SchemaMember | undefined => {
      for (const c of schemas) {
        for (const arr of [c.measures, c.dimensions, c.timeDimensions, c.segments]) {
          const hit = arr.find((x) => x.fullName === full);
          if (hit) return hit;
        }
      }
      return undefined;
    };

    for (const ms of wb.cube_query.measures ?? []) {
      const found = lookup(ms);
      if (found) m.push(found);
    }
    for (const ds of wb.cube_query.dimensions ?? []) {
      const found = lookup(ds);
      if (found) d.push(found);
    }
    for (const td_ of wb.cube_query.timeDimensions ?? []) {
      const found = lookup(td_.dimension);
      if (found) td = found;
      if (td_.granularity) setGranularity(td_.granularity as Granularity);
    }
    for (const sg of wb.cube_query.segments ?? []) {
      const found = lookup(sg);
      if (found) seg.push(found);
    }
    setMeasures(m);
    setDimensions(d);
    setTimeDim(td);
    setSegments(seg);
    setLimit(wb.cube_query.limit ?? "");
  }

  return (
    <div className="grid h-full grid-cols-[14rem_1fr_16rem]">
      <aside className="border-r border-border bg-bg-elevated">
        <FieldPicker
          schemas={schemas}
          onAdd={(kind, member) => {
            if (kind === "measure") setMeasures((prev) => prev.find((p) => p.fullName === member.fullName) ? prev : [...prev, member]);
            if (kind === "dimension") setDimensions((prev) => prev.find((p) => p.fullName === member.fullName) ? prev : [...prev, member]);
            if (kind === "timeDimension") setTimeDim(member);
            if (kind === "segment") setSegments((prev) => prev.find((p) => p.fullName === member.fullName) ? prev : [...prev, member]);
          }}
        />
      </aside>

      <section className="flex flex-col overflow-hidden">
        <header className="flex items-center gap-2 border-b border-border bg-bg-elevated px-4 py-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="input flex-1 max-w-xs"
          />
          <button onClick={run} disabled={running || measures.length === 0} className="btn">
            <Play className="h-3.5 w-3.5" />
            Run
          </button>
          <button
            onClick={() => saveMut.mutate()}
            disabled={saveMut.isPending || measures.length === 0}
            className="btn-primary"
          >
            <Save className="h-3.5 w-3.5" />
            {saveMut.isPending ? "Saving…" : "Save"}
          </button>
        </header>

        <div className="flex flex-wrap gap-2 border-b border-border bg-bg-subtle/40 px-4 py-2">
          {measures.map((m) => (
            <Pill key={m.fullName} kind="measure" label={m.fullName} onRemove={() => setMeasures(s => s.filter(x => x.fullName !== m.fullName))} />
          ))}
          {dimensions.map((d) => (
            <Pill key={d.fullName} kind="dimension" label={d.fullName} onRemove={() => setDimensions(s => s.filter(x => x.fullName !== d.fullName))} />
          ))}
          {timeDim && (
            <Pill
              kind="time"
              label={`${timeDim.fullName} · ${granularity}`}
              onRemove={() => setTimeDim(null)}
            />
          )}
          {segments.map((sg) => (
            <Pill key={sg.fullName} kind="segment" label={sg.fullName} onRemove={() => setSegments(s => s.filter(x => x.fullName !== sg.fullName))} />
          ))}
          {timeDim && (
            <select
              className="input text-xs"
              value={granularity}
              onChange={(e) => setGranularity(e.target.value as Granularity)}
            >
              {["day", "week", "month", "quarter", "year"].map((g) => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>
          )}
          <input
            type="number"
            className="input w-20 text-xs"
            placeholder="limit"
            value={limit}
            onChange={(e) => setLimit(e.target.value === "" ? "" : Number(e.target.value))}
          />
        </div>

        <div className="flex-1 overflow-auto p-4">
          {measures.length === 0 ? (
            <div className="mx-auto mt-12 max-w-md rounded-md border border-dashed border-border p-6 text-center text-sm text-fg-muted">
              Pick a measure from the left to build a query.
            </div>
          ) : (
            <>
              <div className="panel p-4">
                {error ? (
                  <div className="text-danger text-sm">{error}</div>
                ) : running ? (
                  <div className="text-fg-muted text-sm">Running…</div>
                ) : rows.length === 0 ? (
                  <div className="text-fg-muted text-sm">No data yet.</div>
                ) : (
                  <PlotChart spec={chartSpec} rows={rows} height={360} />
                )}
              </div>
              <details className="mt-4 text-xs">
                <summary className="cursor-pointer text-fg-muted">Cube query</summary>
                <pre className="mt-2 overflow-x-auto rounded bg-bg-subtle p-2 font-mono text-fg">
                  {JSON.stringify(cubeQuery, null, 2)}
                </pre>
              </details>
            </>
          )}
        </div>
      </section>

      <aside className="overflow-y-auto border-l border-border bg-bg-elevated p-3">
        <div className="text-xs font-semibold uppercase tracking-wider text-fg-subtle">Saved</div>
        {workbooks.data?.length ? (
          <div className="mt-2 flex flex-col gap-1">
            {workbooks.data.map((wb) => (
              <button
                key={wb.id}
                onClick={() => loadWorkbook(wb)}
                className="rounded-md px-2 py-1.5 text-left text-xs text-fg-muted hover:bg-bg-subtle hover:text-fg"
              >
                {wb.name}
              </button>
            ))}
          </div>
        ) : (
          <div className="mt-2 text-xs text-fg-subtle">No saved workbooks yet.</div>
        )}

        <div className="mt-6 text-xs font-semibold uppercase tracking-wider text-fg-subtle">
          AI assist
        </div>
        <div className="mt-2 rounded-md border border-dashed border-border p-2 text-xs text-fg-muted">
          <Bot className="mb-1 inline h-3 w-3" /> Tip: ask in the chat surface to generate a query for you, then continue here.
        </div>
      </aside>
    </div>
  );
}

const PILL_STYLES: Record<string, string> = {
  measure:   "border-success/40 bg-success/10 text-success",
  dimension: "border-warning/40 bg-warning/10 text-warning",
  time:      "border-accent/40 bg-accent/10 text-accent",
  segment:   "border-border-strong bg-bg-subtle text-fg-muted",
};

function Pill({ kind, label, onRemove }: { kind: string; label: string; onRemove: () => void }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${PILL_STYLES[kind] ?? ""}`}
    >
      {label}
      <button onClick={onRemove} className="opacity-60 hover:opacity-100">
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}
