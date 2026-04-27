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
import { Plus, RefreshCw, X } from "lucide-react";
import {
  listWorkbooks,
  runQuery,
  getActiveWorkspace,
  type WorkbookRecord,
  type CubeQuery,
} from "../../lib/api";
import { applyCrossFilters, useApp } from "../../lib/store";
import { PlotChart } from "../chart/PlotChart";
import { ChartSpec } from "../chart/ChartSpec";

const DASHBOARD_ID = "default";

export function Dashboard() {
  const workspaceId = getActiveWorkspace();
  const workbooks = useQuery({
    queryKey: ["workbooks", workspaceId],
    queryFn: () => listWorkbooks(workspaceId),
  });

  const [tiles, setTiles] = useState<WorkbookRecord[]>([]);
  const [picker, setPicker] = useState(false);

  const filters = useApp((s) => s.crossFilters[DASHBOARD_ID] ?? []);
  const removeFilter = useApp((s) => s.removeCrossFilter);
  const clearFilters = useApp((s) => s.clearCrossFilters);

  useEffect(() => {
    const stored = localStorage.getItem(`lumen.dashboard.${workspaceId}`);
    if (stored && workbooks.data) {
      const ids: string[] = JSON.parse(stored);
      setTiles(workbooks.data.filter((w) => ids.includes(w.id)));
    } else if (workbooks.data && workbooks.data.length > 0 && tiles.length === 0) {
      setTiles(workbooks.data.slice(0, Math.min(4, workbooks.data.length)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workbooks.data, workspaceId]);

  useEffect(() => {
    localStorage.setItem(
      `lumen.dashboard.${workspaceId}`,
      JSON.stringify(tiles.map((t) => t.id))
    );
  }, [tiles, workspaceId]);

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
          <div className="mb-2 text-xs uppercase tracking-wider text-fg-subtle">
            Pick a saved workbook
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

      <div className="flex-1 overflow-auto p-4">
        {tiles.length === 0 ? (
          <div className="mx-auto mt-12 max-w-md rounded-md border border-dashed border-border p-6 text-center text-sm text-fg-muted">
            Add your first tile to start building this dashboard.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {tiles.map((tile) => (
              <Tile key={tile.id} tile={tile} onRemove={() => removeTile(tile.id)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Tile({ tile, onRemove }: { tile: WorkbookRecord; onRemove: () => void }) {
  const filters = useApp((s) => s.crossFilters[DASHBOARD_ID] ?? []);
  const addFilter = useApp((s) => s.addCrossFilter);
  const filteredQuery = applyCrossFilters(tile.cube_query, filters);

  const q = useQuery({
    queryKey: ["tile-data", tile.id, JSON.stringify(filteredQuery)],
    queryFn: () => runQuery(filteredQuery as CubeQuery),
    refetchOnWindowFocus: false,
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
    <div className="panel flex flex-col p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-semibold text-fg">{tile.name}</div>
        <button onClick={onRemove} className="text-fg-subtle hover:text-fg">
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
            <PlotChart spec={(tile.chart_spec ?? { type: "table" }) as ChartSpec} rows={q.data.data} height={260} />
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
    <div className="mt-2 flex flex-wrap gap-1">
      {values.slice(0, 12).map((v) => (
        <button
          key={String(v)}
          onClick={() => onPick({ [fieldKey]: v })}
          className="rounded border border-border px-1.5 py-0.5 text-[10px] text-fg-muted hover:border-accent hover:text-accent"
          title={`Filter all tiles by ${dimension} = ${String(v)}`}
        >
          {String(v)}
        </button>
      ))}
    </div>
  );
}
