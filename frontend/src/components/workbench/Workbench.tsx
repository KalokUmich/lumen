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
import { parseSchema, SchemaMember, lookupSchemaMember } from "../../lib/schema";
import { useApp } from "../../lib/store";
import { ResultView } from "../chart/ResultView";
import { ChartSpec } from "../chart/ChartSpec";
import { FieldPicker, FIELD_DND_MIME, type FieldDragPayload } from "./FieldPicker";

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
  const [drillFilter, setDrillFilter] = useState<{ member: string; values: unknown[] } | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Pick up drill-down handoff from chat / dashboard.
  const pendingDrill = useApp((s) => s.pendingDrill);
  const setPendingDrill = useApp((s) => s.setPendingDrill);

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
    if (drillFilter) {
      q.filters = [
        ...(q.filters ?? []),
        {
          member: drillFilter.member,
          operator: "equals",
          values: drillFilter.values as (string | number)[],
        },
      ];
    }
    return q;
  }, [measures, dimensions, timeDim, granularity, segments, limit, drillFilter]);

  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [sql, setSql] = useState<string | null>(null);
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
      setSql(result.sql ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  // Auto-run when query shape changes meaningfully. Use the SERIALIZED query
  // shape as the dep so we re-run whenever any of (measures / dims / segments /
  // timeDim / limit / drillFilter) change identity.
  const queryShapeKey = useMemo(
    () =>
      JSON.stringify({
        m: measures.map((x) => x.fullName),
        d: dimensions.map((x) => x.fullName),
        t: timeDim?.fullName,
        g: granularity,
        s: segments.map((x) => x.fullName),
        l: limit,
        df: drillFilter,
      }),
    [measures, dimensions, timeDim, granularity, segments, limit, drillFilter]
  );

  useEffect(() => {
    setRows([]);
    if (measures.length > 0) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryShapeKey]);

  // Handle drill-down handoff: load the originating query + drill filter into
  // the workbench, then clear the pending state so we don't re-run on every
  // mount.
  useEffect(() => {
    if (!pendingDrill || schemas.length === 0) return;
    const lookup = (full: string): SchemaMember | undefined => {
      for (const c of schemas) {
        for (const arr of [c.measures, c.dimensions, c.timeDimensions, c.segments]) {
          const hit = arr.find((x) => x.fullName === full);
          if (hit) return hit;
        }
      }
      return undefined;
    };
    const m: SchemaMember[] = [];
    for (const ms of pendingDrill.cubeQuery.measures ?? []) {
      const found = lookup(ms);
      if (found) m.push(found);
    }
    const d: SchemaMember[] = [];
    for (const ds of pendingDrill.cubeQuery.dimensions ?? []) {
      const found = lookup(ds);
      if (found) d.push(found);
    }
    let td: SchemaMember | null = null;
    for (const td_ of pendingDrill.cubeQuery.timeDimensions ?? []) {
      const found = lookup(td_.dimension);
      if (found) td = found;
      if (td_.granularity) setGranularity(td_.granularity as Granularity);
    }
    setMeasures(m);
    setDimensions(d);
    setTimeDim(td);
    if (pendingDrill.filter) {
      setDrillFilter({
        member: pendingDrill.filter.member,
        values: pendingDrill.filter.values,
      });
      setName(
        `Drill-down: ${pendingDrill.filter.member} = ${pendingDrill.filter.values.join(", ")}`,
      );
    } else {
      // "Continue in Workbook" — no filter, just hand off the query.
      setDrillFilter(null);
      setName(pendingDrill.source === "chat" ? "From chat" : "Loaded query");
    }
    setPendingDrill(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingDrill, schemas.length]);

  // Mirror the visualizer subagent's logic on the frontend so the workbench
  // preview shows the SAME chart the AI would have picked. (Server-side
  // visualizer is authoritative for AI-generated charts; this is the
  // workbench manual-build preview.)
  //
  // TODO(phase-1): replace this with a /api/v1/visualize endpoint call so
  // we have ONE chart-pick implementation, not two.
  const chartSpec: ChartSpec = useMemo(() => {
    const M = measures.length;
    const D = dimensions.length;
    const T = !!timeDim;
    const N = rows.length;
    const fmtFor = (m: SchemaMember | undefined): "currency" | "number" | "percent" => {
      if (!m) return "number";
      if (m.meta?.includes("currency")) return "currency";
      if (m.meta?.includes("percent")) return "percent";
      return "number";
    };

    let type: ChartSpec["type"] = "table";
    if (N === 0) type = "empty";
    else if (M === 1 && D === 0 && N === 1) type = "big-number";    // ignore time, single value
    else if (M >= 2 && D === 0 && N === 1) type = "kpi-strip";       // multiple measures, one row → KPI tiles
    else if (T && M === 1 && D === 0) type = N < 5 ? "bar" : "line";
    else if (T && M === 1 && D === 1) type = "multi-line";
    else if (M === 1 && D === 1 && !T) type = dimensions[0] && N > 8 ? "horizontal-bar" : "bar";
    else if (M === 1 && D === 2 && !T) type = "heatmap";
    else if (M === 2 && D === 0 && N >= 2) type = "scatter";
    else if (M === 2 && D === 1 && !T) type = "scatter";
    else type = "table";

    const spec: ChartSpec = { type };

    // Scatter: x AND y both come from the two measures (not from a dim).
    if (type === "scatter") {
      if (measures[0]) {
        spec.x = {
          field: measures[0].fullName.replace(/\./g, "__"),
          format: fmtFor(measures[0]),
          label: measures[0].name,
        };
      }
      if (measures[1]) {
        spec.y = {
          field: measures[1].fullName.replace(/\./g, "__"),
          format: fmtFor(measures[1]),
          label: measures[1].name,
        };
      }
      if (dimensions[0]) {
        spec.color = { field: dimensions[0].fullName.replace(/\./g, "__"), palette: "categorical" };
      }
      return spec;
    }

    // All other chart types: x from time / first dim, y from first measure.
    if (timeDim) {
      spec.x = { field: timeDim.fullName.replace(/\./g, "__"), type: "time", label: timeDim.name };
    } else if (dimensions[0]) {
      spec.x = { field: dimensions[0].fullName.replace(/\./g, "__"), type: "ordinal", label: dimensions[0].name };
    }
    if (measures[0]) {
      spec.y = {
        field: measures[0].fullName.replace(/\./g, "__"),
        format: fmtFor(measures[0]),
        label: measures[0].name,
      };
    }
    // Color: secondary dim (multi-line: time-series + dim, grouped: 2 dims)
    if (T && D === 1) {
      spec.color = { field: dimensions[0].fullName.replace(/\./g, "__"), palette: "categorical" };
    } else if (!T && D === 1 && (type === "bar" || type === "horizontal-bar") && dimensions[0].fullName) {
      // §4.2.2: low-cardinality categorical bar gets categorical color.
      // (For accurate cardinality we'd need server-side rows — approximate via N.)
      if (N <= 10) {
        spec.color = { field: dimensions[0].fullName.replace(/\./g, "__"), palette: "categorical" };
      }
    } else if (dimensions[1]) {
      spec.color = { field: dimensions[1].fullName.replace(/\./g, "__"), palette: "categorical" };
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

        <div
          data-testid="pill-row"
          className="flex flex-wrap gap-2 border-b border-border bg-bg-subtle/40 px-5 py-3"
          onDragOver={(e) => {
            if (e.dataTransfer.types.includes(FIELD_DND_MIME)) {
              e.preventDefault();
              e.dataTransfer.dropEffect = "copy";
              setIsDragOver(true);
            }
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={(e) => {
            const raw = e.dataTransfer.getData(FIELD_DND_MIME);
            setIsDragOver(false);
            if (!raw) return;
            try {
              const payload = JSON.parse(raw) as FieldDragPayload;
              const member = lookupSchemaMember(schemas, payload.fullName);
              if (!member) return;
              if (payload.kind === "measure") {
                setMeasures((prev) =>
                  prev.find((p) => p.fullName === member.fullName) ? prev : [...prev, member],
                );
              } else if (payload.kind === "dimension") {
                setDimensions((prev) =>
                  prev.find((p) => p.fullName === member.fullName) ? prev : [...prev, member],
                );
              } else if (payload.kind === "timeDimension") {
                setTimeDim(member);
              } else if (payload.kind === "segment") {
                setSegments((prev) =>
                  prev.find((p) => p.fullName === member.fullName) ? prev : [...prev, member],
                );
              }
            } catch {
              // ignore malformed drag payloads
            }
          }}
          style={isDragOver ? { outline: "1px dashed var(--tw-color-accent, #7C5CFF)", outlineOffset: -1 } : undefined}
        >
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
          {drillFilter && (
            <span className="inline-flex items-center gap-1 rounded-md border border-accent/40 bg-accent/15 px-2 py-0.5 text-xs text-accent">
              ⌖ {drillFilter.member} = {drillFilter.values.map(String).join(", ")}
              <button onClick={() => setDrillFilter(null)} className="opacity-70 hover:opacity-100">
                <X className="h-3 w-3" />
              </button>
            </span>
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
            <WorkbenchEmptyState
              schemas={schemas}
              onTryExample={(measure, dim) => {
                setMeasures([measure]);
                if (dim) setDimensions([dim]);
              }}
            />
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
                  <ResultView
                    spec={chartSpec}
                    rows={rows}
                    sql={sql}
                    height={360}
                    filenameStem="workbench-export"
                    cubeQuery={cubeQuery}
                  />
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

function WorkbenchEmptyState({
  schemas,
  onTryExample,
}: {
  schemas: ReturnType<typeof parseSchema>;
  onTryExample: (measure: SchemaMember, dim?: SchemaMember) => void;
}) {
  // Pick a sensible "starter" example: first revenue/count measure × first dim
  const allMeasures = schemas.flatMap((c) => c.measures);
  const allDims = schemas.flatMap((c) => c.dimensions);
  const starter =
    allMeasures.find((m) => /revenue|sales|count/i.test(m.name)) ?? allMeasures[0];
  const starterDim = allDims.find((d) => /name|region|segment|priority/i.test(d.name)) ?? allDims[0];

  return (
    <div className="mx-auto mt-8 max-w-2xl">
      <div className="mb-4 text-lg font-semibold text-fg">Build a query</div>

      <ol className="space-y-3 text-sm">
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/20 text-xs font-semibold text-accent">1</span>
          <div>
            <div className="font-medium text-fg">Pick a measure</div>
            <div className="text-fg-muted">
              From the left rail, click a green ▮ measure (the number you want to compute, like Revenue or Customer Count).
            </div>
          </div>
        </li>
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/20 text-xs font-semibold text-accent">2</span>
          <div>
            <div className="font-medium text-fg">Add a dimension <span className="text-fg-subtle font-normal">(optional)</span></div>
            <div className="text-fg-muted">
              Click a yellow # dimension to break the measure down by category — e.g. Region, Brand, Customer Segment. Click a blue 🗓 time dimension for a trend over time.
            </div>
          </div>
        </li>
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/20 text-xs font-semibold text-accent">3</span>
          <div>
            <div className="font-medium text-fg">Save</div>
            <div className="text-fg-muted">
              The chart auto-runs. When you like it, click <span className="rounded bg-bg-subtle px-1 py-0.5 text-xs">Save</span> at the top to add it to a dashboard later.
            </div>
          </div>
        </li>
      </ol>

      {starter && (
        <div className="mt-6 rounded-md border border-border bg-bg-subtle/40 p-4">
          <div className="text-xs uppercase tracking-wider text-fg-subtle">Or try this</div>
          <div className="mt-1 mb-3 text-sm text-fg-muted">
            Click below to load a starter query — see how it works, then adjust.
          </div>
          <button
            onClick={() => onTryExample(starter, starterDim)}
            className="btn-primary"
          >
            {starter.name} {starterDim ? `by ${starterDim.name}` : ""}
          </button>
        </div>
      )}

      <div className="mt-4 text-xs text-fg-subtle">
        💡 Tip: hover any field in the left rail to see its description, synonyms, and example questions the AI can answer with it.
      </div>
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
