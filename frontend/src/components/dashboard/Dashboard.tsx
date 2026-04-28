/**
 * Dashboard — multi-tile grid of saved workbook queries with cross-filter.
 *
 * Cross-filter:
 *   When the user clicks a categorical mark in any tile, we read the
 *   underlying dimension value and broadcast a CubeFilter to the global
 *   store. Every tile re-fetches with the merged filter set.
 *   Per the data-viz-standards skill §4.2, this is the standard Omni-class
 *   interaction.
 */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, RefreshCw, X, FileText, Pencil, Check } from "lucide-react";
import {
  listWorkbooks,
  runQuery,
  getActiveWorkspace,
  type WorkbookRecord,
  type CubeQuery,
} from "../../lib/api";
import {
  applyCrossFilters,
  applyDashboardTimeRange,
  useApp,
  type DashboardFilter,
} from "../../lib/store";
import { ResultView } from "../chart/ResultView";
import { ChartSpec } from "../chart/ChartSpec";
import { MarkdownView } from "../MarkdownView";

// Stable sentinel — `?? []` would return a NEW empty array every selector call,
// causing Zustand to think the value changed every render → infinite loop
// ("Maximum update depth exceeded").
const EMPTY_FILTERS: DashboardFilter[] = [];

type MarkdownTile = { id: string; content: string };

/**
 * Patch a stored chart_spec with encodings derived from the cube_query when
 * fields are missing. Fixes pre-fix-saved workbooks (where chart_spec might
 * be just `{ type: "bar" }`) and never lets the chart render with mismatched
 * field names.
 */
function reconcileSpec(
  stored: ChartSpec | null | undefined,
  cubeQuery: CubeQuery,
  rows: Record<string, unknown>[],
): ChartSpec {
  const measures = cubeQuery.measures ?? [];
  const dimensions = cubeQuery.dimensions ?? [];
  const timeDims = cubeQuery.timeDimensions ?? [];
  const T = timeDims.length > 0;
  const M = measures.length;
  const D = dimensions.length;
  const N = rows.length;

  // Pick a chart type if not provided or if it doesn't fit the data shape.
  let type: ChartSpec["type"] = stored?.type ?? "table";
  if (!stored?.type || (stored.type === "bar" && N === 1) || stored.type === "table") {
    if (N === 0) type = "empty";
    else if (M === 1 && D === 0 && N === 1) type = "big-number";
    else if (M >= 2 && D === 0 && N === 1) type = "kpi-strip";
    else if (T && M === 1 && D === 0) type = "line";
    else if (T && M === 1 && D === 1) type = "multi-line";
    else if (M === 1 && D === 1 && !T) type = N > 8 ? "horizontal-bar" : "bar";
    else if (M === 1 && D === 2 && !T) type = "heatmap";
    else if (M === 2 && !T) type = "scatter";
    else type = stored?.type ?? "table";
  }

  const spec: ChartSpec = { ...(stored ?? {}), type };

  // Derive encodings if missing.
  if (T && !spec.x) {
    spec.x = { field: timeDims[0].dimension.replace(/\./g, "__"), type: "time", label: "Date" };
  } else if (!T && dimensions[0] && !spec.x) {
    spec.x = { field: dimensions[0].replace(/\./g, "__"), type: "ordinal", label: dimensions[0].split(".").pop() };
  }
  if (measures[0] && !spec.y) {
    const fmt: "currency" | "number" | "percent" =
      /revenue|price|cost|amount|value|balance|aov/i.test(measures[0]) ? "currency"
      : /rate|ratio|pct|percent/i.test(measures[0]) ? "percent"
      : "number";
    spec.y = { field: measures[0].replace(/\./g, "__"), format: fmt, label: measures[0].split(".").pop() };
  }
  // Scatter overrides — both axes are measures
  if (type === "scatter" && M >= 2) {
    spec.x = { field: measures[0].replace(/\./g, "__"), label: measures[0].split(".").pop() };
    spec.y = { field: measures[1].replace(/\./g, "__"), label: measures[1].split(".").pop() };
  }
  // Categorical color for low-cardinality bars
  if (["bar", "horizontal-bar", "dot-plot"].includes(type) && D === 1 && N <= 10 && !spec.color) {
    spec.color = { field: dimensions[0].replace(/\./g, "__"), palette: "categorical" };
  }
  return spec;
}

const DASHBOARD_ID = "default";

export function Dashboard() {
  const workspaceId = getActiveWorkspace();
  const workbooks = useQuery({
    queryKey: ["workbooks", workspaceId],
    queryFn: () => listWorkbooks(workspaceId),
  });

  const [tiles, setTiles] = useState<WorkbookRecord[]>([]);
  const [mdTiles, setMdTiles] = useState<MarkdownTile[]>([]);
  const [picker, setPicker] = useState(false);

  const filters = useApp((s) => s.crossFilters[DASHBOARD_ID] ?? EMPTY_FILTERS);
  const removeFilter = useApp((s) => s.removeCrossFilter);
  const clearFilters = useApp((s) => s.clearCrossFilters);
  const dashboardTimeRange = useApp((s) => s.dashboardTimeRange[DASHBOARD_ID] ?? null);
  const setDashboardTimeRange = useApp((s) => s.setDashboardTimeRange);
  const [autoRefreshSec, setAutoRefreshSec] = useState<number | null>(null);

  useEffect(() => {
    if (!workbooks.data) return;
    const stored = localStorage.getItem(`lumen.dashboard.${workspaceId}`);
    let ids: string[] = [];
    try {
      if (stored) ids = JSON.parse(stored);
    } catch {
      ids = [];
    }
    const fromStored = workbooks.data.filter((w) => ids.includes(w.id));
    if (fromStored.length > 0) {
      setTiles(fromStored);
    } else if (workbooks.data.length > 0) {
      // Empty / stale stored state but we have workbooks → auto-populate so the
      // user sees something meaningful on first visit.
      setTiles(workbooks.data.slice(0, Math.min(4, workbooks.data.length)));
    } else {
      setTiles([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workbooks.data, workspaceId]);

  useEffect(() => {
    localStorage.setItem(
      `lumen.dashboard.${workspaceId}`,
      JSON.stringify(tiles.map((t) => t.id))
    );
  }, [tiles, workspaceId]);

  // Load + persist markdown tiles in localStorage (no backend yet).
  useEffect(() => {
    try {
      const raw = localStorage.getItem(`lumen.dashboard.md.${workspaceId}`);
      if (raw) setMdTiles(JSON.parse(raw));
    } catch {
      // ignore
    }
  }, [workspaceId]);

  useEffect(() => {
    localStorage.setItem(`lumen.dashboard.md.${workspaceId}`, JSON.stringify(mdTiles));
  }, [mdTiles, workspaceId]);

  function addMarkdownTile() {
    setMdTiles((prev) => [
      ...prev,
      {
        id: `md-${Date.now()}`,
        content: "## New note\n\nClick the pencil icon to edit. Supports basic markdown.",
      },
    ]);
    setPicker(false);
  }
  function updateMdTile(id: string, content: string) {
    setMdTiles((prev) => prev.map((t) => (t.id === id ? { ...t, content } : t)));
  }
  function removeMdTile(id: string) {
    setMdTiles((prev) => prev.filter((t) => t.id !== id));
  }

  function addTile(wb: WorkbookRecord) {
    if (!tiles.find((t) => t.id === wb.id)) setTiles((prev) => [...prev, wb]);
    setPicker(false);
  }

  function removeTile(id: string) {
    setTiles((prev) => prev.filter((t) => t.id !== id));
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border bg-bg-elevated px-4 py-2">
        <div className="text-sm font-semibold text-fg">My Dashboard</div>
        <div className="flex items-center gap-2">
          <TimeRangePicker
            value={dashboardTimeRange}
            onChange={(v) => setDashboardTimeRange(DASHBOARD_ID, v)}
          />
          <AutoRefreshPicker value={autoRefreshSec} onChange={setAutoRefreshSec} />
          <button onClick={() => workbooks.refetch()} className="btn">
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          <button onClick={() => setPicker((v) => !v)} className="btn-primary">
            <Plus className="h-3.5 w-3.5" />
            Add tile
          </button>
        </div>
      </header>

      {filters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-accent/5 px-4 py-2">
          <span className="text-xs uppercase tracking-wider text-fg-subtle">Cross-filters</span>
          {filters.map((f) => (
            <span
              key={f.member}
              className="inline-flex items-center gap-1 rounded-md border border-accent/40 bg-accent/15 px-2 py-0.5 text-xs text-accent"
            >
              {f.member} = {f.values.map(String).join(", ")}
              <button
                onClick={() => removeFilter(DASHBOARD_ID, f.member)}
                className="opacity-70 hover:opacity-100"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          <button
            onClick={() => clearFilters(DASHBOARD_ID)}
            className="ml-2 text-xs text-fg-muted underline hover:text-fg"
          >
            clear all
          </button>
        </div>
      )}

      {picker && (
        <div className="border-b border-border bg-bg-subtle/40 p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-xs uppercase tracking-wider text-fg-subtle">
              Pick a saved workbook
            </div>
            <button
              onClick={addMarkdownTile}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-bg-elevated px-2 py-1 text-xs text-fg-muted hover:border-accent hover:text-fg"
            >
              <FileText className="h-3 w-3" />
              + Markdown note
            </button>
          </div>
          {!workbooks.data?.length ? (
            <div className="text-sm text-fg-muted">
              No saved workbooks yet — go to Workbook, build a query, hit Save, then come back.
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {workbooks.data.map((wb) => (
                <button
                  key={wb.id}
                  onClick={() => addTile(wb)}
                  className="rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs hover:border-accent"
                >
                  + {wb.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex-1 overflow-auto p-6">
        {tiles.length === 0 && mdTiles.length === 0 ? (
          <div className="mx-auto mt-12 max-w-md rounded-md border border-dashed border-border p-6 text-center text-sm text-fg-muted">
            {workbooks.isLoading ? (
              <span>Loading saved workbooks…</span>
            ) : !workbooks.data || workbooks.data.length === 0 ? (
              <>
                <div className="mb-2 font-medium text-fg">No saved workbooks yet</div>
                <div>Go to the Workbook surface (left rail), build a query, hit Save.<br />Then come back here and add it as a tile.</div>
              </>
            ) : (
              <>
                <div className="mb-2 font-medium text-fg">Dashboard is empty</div>
                <div>You have {workbooks.data.length} saved workbook{workbooks.data.length === 1 ? "" : "s"}.</div>
                <button
                  onClick={() => setPicker(true)}
                  className="btn-primary mt-3"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add tile
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {tiles.map((tile) => (
              <Tile
                key={tile.id}
                tile={tile}
                onRemove={() => removeTile(tile.id)}
                autoRefreshSec={autoRefreshSec}
              />
            ))}
            {mdTiles.map((mt) => (
              <MarkdownTileView
                key={mt.id}
                tile={mt}
                onChange={(content) => updateMdTile(mt.id, content)}
                onRemove={() => removeMdTile(mt.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Tile({
  tile,
  onRemove,
  autoRefreshSec,
}: {
  tile: WorkbookRecord;
  onRemove: () => void;
  autoRefreshSec: number | null;
}) {
  const filters = useApp((s) => s.crossFilters[DASHBOARD_ID] ?? EMPTY_FILTERS);
  const addFilter = useApp((s) => s.addCrossFilter);
  const dashboardTimeRange = useApp((s) => s.dashboardTimeRange[DASHBOARD_ID] ?? null);
  const queryWithTime = applyDashboardTimeRange(
    tile.cube_query as CubeQuery,
    dashboardTimeRange,
  );
  const filteredQuery = applyCrossFilters(queryWithTime, filters);

  const q = useQuery({
    queryKey: ["tile-data", tile.id, JSON.stringify(filteredQuery)],
    queryFn: () => runQuery(filteredQuery as CubeQuery),
    refetchOnWindowFocus: false,
    refetchInterval: autoRefreshSec ? autoRefreshSec * 1000 : false,
  });

  // Pick a categorical dimension for cross-filter clicks (first non-time dim).
  const cfDimension = (tile.cube_query.dimensions ?? [])[0];

  function handleRowClick(row: Record<string, unknown>) {
    if (!cfDimension) return;
    const fieldKey = cfDimension.replace(/\./g, "__");
    const value = row[fieldKey];
    if (value == null) return;
    addFilter(DASHBOARD_ID, {
      member: cfDimension,
      operator: "equals",
      values: [String(value)],
    });
  }

  return (
    <div className="panel flex flex-col p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[14px] font-medium leading-snug text-fg">{tile.name}</div>
        <button onClick={onRemove} className="text-fg-subtle transition-colors hover:text-fg">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="min-h-[260px]">
        {q.isLoading ? (
          <div className="text-fg-muted text-sm">Loading…</div>
        ) : q.isError ? (
          <div className="text-danger text-xs">{String(q.error)}</div>
        ) : !q.data?.data?.length ? (
          <div className="text-fg-muted text-sm">No data.</div>
        ) : (
          <>
            <ResultView
              spec={reconcileSpec(tile.chart_spec as ChartSpec | null, tile.cube_query, q.data.data)}
              rows={q.data.data}
              sql={q.data.sql ?? null}
              height={260}
              filenameStem={tile.name}
              cubeQuery={tile.cube_query as CubeQuery}
              dashboardId={DASHBOARD_ID}
              compact
              meta={q.data.meta}
            />
            {cfDimension && q.data.data.length > 0 && (
              <ClickToFilterRows rows={q.data.data} dimension={cfDimension} onPick={handleRowClick} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

/**
 * A small row-list shown below each chart that lets users click categorical
 * values to add them as cross-filters. Plot's click events are awkward to wire
 * generically; a clickable legend below the chart keeps the UX consistent
 * across all chart types.
 */
function ClickToFilterRows({
  rows,
  dimension,
  onPick,
}: {
  rows: Record<string, unknown>[];
  dimension: string;
  onPick: (row: Record<string, unknown>) => void;
}) {
  const fieldKey = dimension.replace(/\./g, "__");
  const values = Array.from(new Set(rows.map((r) => r[fieldKey]))).filter((v) => v != null);
  if (values.length === 0 || values.length > 12) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-fg-subtle">
        Click to cross-filter:
      </span>
      {values.slice(0, 12).map((v) => (
        <button
          key={String(v)}
          onClick={() => onPick({ [fieldKey]: v })}
          className="rounded border border-border bg-bg-elevated px-2 py-0.5 text-[11px] text-fg-muted transition-colors hover:border-accent hover:bg-accent/10 hover:text-accent"
          title={`Filter all tiles by ${dimension} = ${String(v)}`}
        >
          {String(v)}
        </button>
      ))}
    </div>
  );
}

const TIME_RANGES: { label: string; value: string | null }[] = [
  { label: "All time", value: null },
  { label: "Today", value: "today" },
  { label: "This week", value: "this week" },
  { label: "This month", value: "this month" },
  { label: "Last month", value: "last month" },
  { label: "This quarter", value: "this quarter" },
  { label: "Last quarter", value: "last quarter" },
  { label: "This year", value: "this year" },
  { label: "Last year", value: "last year" },
  { label: "Last 30 days", value: "last 30 days" },
  { label: "Last 90 days", value: "last 90 days" },
];

function TimeRangePicker({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  const current = TIME_RANGES.find((r) => r.value === value)?.label ?? "All time";
  return (
    <label className="flex items-center gap-1 text-xs text-fg-muted">
      <span className="hidden md:inline">Date:</span>
      <select
        aria-label="Dashboard date range"
        className="rounded-md border border-border bg-bg-elevated px-2 py-1 text-xs text-fg"
        value={value ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === "" ? null : v);
        }}
        title={`Current: ${current}`}
      >
        {TIME_RANGES.map((r) => (
          <option key={r.label} value={r.value ?? ""}>
            {r.label}
          </option>
        ))}
      </select>
    </label>
  );
}

const REFRESH_OPTIONS: { label: string; value: number | null }[] = [
  { label: "Off", value: null },
  { label: "30s", value: 30 },
  { label: "1m", value: 60 },
  { label: "5m", value: 300 },
  { label: "15m", value: 900 },
  { label: "1h", value: 3600 },
];

function AutoRefreshPicker({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-xs text-fg-muted">
      <span className="hidden md:inline">Auto-refresh:</span>
      <select
        aria-label="Dashboard auto-refresh"
        className="rounded-md border border-border bg-bg-elevated px-2 py-1 text-xs text-fg"
        value={value === null ? "" : String(value)}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === "" ? null : Number(v));
        }}
      >
        {REFRESH_OPTIONS.map((o) => (
          <option key={o.label} value={o.value === null ? "" : String(o.value)}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function MarkdownTileView({
  tile,
  onChange,
  onRemove,
}: {
  tile: MarkdownTile;
  onChange: (content: string) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(tile.content);

  function save() {
    onChange(draft);
    setEditing(false);
  }

  return (
    <div className="panel flex flex-col p-4" data-testid="markdown-tile">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-sm font-semibold text-fg">
          <FileText className="h-3.5 w-3.5 text-fg-subtle" />
          Note
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => {
              if (editing) save();
              else {
                setDraft(tile.content);
                setEditing(true);
              }
            }}
            aria-label={editing ? "Save note" : "Edit note"}
            className="text-fg-subtle hover:text-fg"
          >
            {editing ? <Check className="h-3.5 w-3.5" /> : <Pencil className="h-3.5 w-3.5" />}
          </button>
          <button onClick={onRemove} aria-label="Remove note" className="text-fg-subtle hover:text-fg">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <div className="min-h-[120px]">
        {editing ? (
          <textarea
            className="input h-full min-h-[120px] w-full resize-y font-mono text-sm"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoFocus
          />
        ) : (
          <MarkdownView source={tile.content} />
        )}
      </div>
    </div>
  );
}

