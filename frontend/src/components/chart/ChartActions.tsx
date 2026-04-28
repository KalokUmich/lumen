/**
 * The bar of actions that lives below every rendered chart:
 *   - Show generated SQL (collapsible code panel)
 *   - Copy SQL to clipboard
 *   - Download data as CSV
 *   - "Why this chart?" rationale tooltip
 */

import { useState } from "react";
import { Code, Copy, Download, Info, Check, Activity } from "lucide-react";
import { downloadCSV, flattenSQL } from "../../lib/export";
import { ChartSpec } from "./ChartSpec";
import { SqlView } from "./SqlView";
import type { QueryMeta } from "../../lib/api";

type Props = {
  rows: Record<string, unknown>[];
  sql?: string | null;
  spec?: ChartSpec;
  filenameStem?: string;
  /** Query execution metadata: ms, rows, cache_hit. Surfaces a tile-inspect popover. */
  meta?: QueryMeta;
};

export function ChartActions({ rows, sql, spec, filenameStem = "lumen-export", meta }: Props) {
  const [showInspect, setShowInspect] = useState(false);
  const [showSQL, setShowSQL] = useState(false);
  const [copiedSQL, setCopiedSQL] = useState(false);
  const [showRationale, setShowRationale] = useState(false);

  async function copySQL() {
    if (!sql) return;
    try {
      await navigator.clipboard.writeText(flattenSQL(sql));
      setCopiedSQL(true);
      setTimeout(() => setCopiedSQL(false), 1200);
    } catch {
      // ignore
    }
  }

  function exportCSV() {
    downloadCSV(rows, `${filenameStem}.csv`);
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
      {sql && (
        <button
          onClick={() => setShowSQL((v) => !v)}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-fg-subtle transition-colors hover:bg-bg-subtle hover:text-fg"
          title="View generated SQL"
        >
          <Code className="h-3.5 w-3.5" />
          {showSQL ? "Hide SQL" : "View SQL"}
        </button>
      )}
      <button
        onClick={exportCSV}
        disabled={rows.length === 0}
        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-fg-subtle transition-colors hover:bg-bg-subtle hover:text-fg disabled:opacity-40"
        title="Download data as CSV"
      >
        <Download className="h-3.5 w-3.5" />
        CSV
      </button>
      {spec?.rationale && (
        <button
          onClick={() => setShowRationale((v) => !v)}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-fg-subtle transition-colors hover:bg-bg-subtle hover:text-fg"
          title="Why this chart?"
        >
          <Info className="h-3.5 w-3.5" />
          Why this chart?
        </button>
      )}
      {meta && (meta.ms !== undefined || meta.rows !== undefined) && (
        <button
          onClick={() => setShowInspect((v) => !v)}
          data-testid="inspect-button"
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-fg-subtle transition-colors hover:bg-bg-subtle hover:text-fg"
          title="Inspect query timing, row count, and cache status"
        >
          <Activity className="h-3.5 w-3.5" />
          Inspect
        </button>
      )}
      {showInspect && meta && (
        <div
          data-testid="inspect-panel"
          className="mt-2 w-full rounded-md border border-border bg-bg-subtle px-3 py-2 text-[12px] text-fg-muted"
        >
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
            <Stat label="Time" value={meta.ms !== undefined ? `${meta.ms} ms` : "—"} />
            <Stat label="Rows" value={meta.rows !== undefined ? meta.rows.toLocaleString() : "—"} />
            <Stat
              label="Cache"
              value={meta.cache_hit ? "hit" : "miss"}
              tone={meta.cache_hit ? "success" : "muted"}
            />
            <Stat label="Backend" value={meta.backend ?? "—"} />
          </div>
        </div>
      )}

      {showRationale && spec?.rationale && (
        <div className="mt-1 w-full rounded border border-border bg-bg-subtle p-2 text-fg-muted">
          {spec.rationale}
          {typeof spec.confidence === "number" && (
            <span className="ml-2 text-fg-subtle">
              · confidence {(spec.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}

      {showSQL && sql && (
        <div className="mt-1 w-full rounded border border-border bg-bg-subtle">
          <div className="flex items-center justify-between border-b border-border px-2 py-1">
            <span className="text-[10px] uppercase tracking-wider text-fg-subtle">Generated SQL</span>
            <button
              onClick={copySQL}
              className="flex items-center gap-1 rounded px-1.5 py-0.5 text-fg-muted hover:text-fg"
            >
              {copiedSQL ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
              {copiedSQL ? "Copied" : "Copy"}
            </button>
          </div>
          <SqlView sql={sql} />
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string | number;
  tone?: "muted" | "success";
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-fg-subtle">{label}</div>
      <div
        className={`mt-0.5 font-medium tabular-nums ${
          tone === "success" ? "text-success" : "text-fg"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
