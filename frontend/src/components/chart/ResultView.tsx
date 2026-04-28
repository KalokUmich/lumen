/**
 * Wraps a chart + data table + actions bar into one switchable view.
 *
 * Mirrors Omni's "Visualize / Results" toggle: every query result has both a
 * chart-form and a tabular-form, and the user can flip between them with one
 * click. Replaces the prior `<PlotChart /> + <ChartActions />` pair.
 */

import { useState } from "react";
import { BarChart3, Table as TableIcon } from "lucide-react";
import { PlotChart } from "./PlotChart";
import { DataTable } from "./DataTable";
import { ChartActions } from "./ChartActions";
import { ChartContextMenu } from "./ChartContextMenu";
import { ChartSpec } from "./ChartSpec";
import type { CubeQuery, QueryMeta } from "../../lib/api";

type Mode = "chart" | "table";

type Props = {
  spec: ChartSpec;
  rows: Record<string, unknown>[];
  sql?: string | null;
  height?: number;
  filenameStem?: string;
  /** Default to "chart"; pass "table" to start in tabular mode (e.g. for raw exports). */
  initialMode?: Mode;
  /** When provided, enables right-click → "Open in Workbook" / "Drill by …". */
  cubeQuery?: CubeQuery;
  /** When provided, right-click drill adds a cross-filter to that dashboard. */
  dashboardId?: string;
  /** Compact mode hides the inline chart title (when host already shows one). */
  compact?: boolean;
  /** Per-query execution metadata for the Inspect button. */
  meta?: QueryMeta;
};

export function ResultView({
  spec,
  rows,
  sql,
  height,
  filenameStem,
  initialMode = "chart",
  cubeQuery,
  dashboardId,
  compact = false,
  meta,
}: Props) {
  const [mode, setMode] = useState<Mode>(initialMode);

  return (
    <div>
      <div className="mb-2 flex items-center justify-end">
        <ModeToggle mode={mode} onChange={setMode} />
      </div>
      <ChartContextMenu
        rows={rows}
        cubeQuery={cubeQuery}
        sql={sql ?? null}
        dashboardId={dashboardId}
        filenameStem={filenameStem}
      >
        {mode === "chart" ? (
          <PlotChart spec={spec} rows={rows} height={height} compact={compact} />
        ) : (
          <DataTable rows={rows} />
        )}
      </ChartContextMenu>
      <ChartActions
        rows={rows}
        sql={sql}
        spec={spec}
        filenameStem={filenameStem}
        meta={meta}
      />
    </div>
  );
}

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div className="inline-flex rounded-md border border-border bg-bg-elevated text-xs">
      <button
        onClick={() => onChange("chart")}
        aria-pressed={mode === "chart"}
        className={`flex items-center gap-1 rounded-l-md px-2 py-1 ${
          mode === "chart" ? "bg-bg-subtle text-fg" : "text-fg-muted hover:text-fg"
        }`}
        title="Chart view"
      >
        <BarChart3 className="h-3 w-3" />
        Chart
      </button>
      <button
        onClick={() => onChange("table")}
        aria-pressed={mode === "table"}
        className={`flex items-center gap-1 rounded-r-md border-l border-border px-2 py-1 ${
          mode === "table" ? "bg-bg-subtle text-fg" : "text-fg-muted hover:text-fg"
        }`}
        title="Table view"
      >
        <TableIcon className="h-3 w-3" />
        Table
      </button>
    </div>
  );
}
