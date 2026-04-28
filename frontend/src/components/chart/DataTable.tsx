/**
 * Sortable data table — the "Results" view paired with every chart.
 *
 * Click a column header to sort. Numeric columns sort numerically, everything
 * else lexically. Limited to first 500 rows in the DOM with a footer hint —
 * users who want the full set should use CSV export.
 */

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { formatValue, formatDate } from "../../lib/format";

type CellKind = "number" | "date" | "string";
type Direction = "asc" | "desc";
const VISIBLE_LIMIT = 500;

function inferKind(values: unknown[]): CellKind {
  for (const v of values) {
    if (v == null) continue;
    if (typeof v === "number") return "number";
    if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v)) return "date";
    return "string";
  }
  return "string";
}

function renderCell(v: unknown, kind: CellKind): string {
  if (v == null || v === "") return "—";
  if (kind === "number") return formatValue(v, "number");
  if (kind === "date") return formatDate(v);
  return String(v);
}

function prettyHeader(key: string): string {
  // "LineItem__revenue" → "LineItem · revenue"
  // "Orders.country" → "Orders · country"
  return key.replace(/__/g, " · ").replace(/\./g, " · ").replace(/_/g, " ");
}

export function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = useMemo(() => {
    if (rows.length === 0) return [] as { key: string; kind: CellKind }[];
    const keys = Object.keys(rows[0]);
    return keys.map((k) => ({
      key: k,
      kind: inferKind(rows.slice(0, 50).map((r) => r[k])),
    }));
  }, [rows]);

  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<Direction>("asc");

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return (av - bv) * dir;
      }
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [rows, sortKey, sortDir]);

  function toggleSort(k: string) {
    if (sortKey !== k) {
      setSortKey(k);
      setSortDir("asc");
    } else if (sortDir === "asc") {
      setSortDir("desc");
    } else {
      setSortKey(null);
    }
  }

  if (rows.length === 0) {
    return <div className="px-2 py-4 text-sm text-fg-muted">No rows.</div>;
  }

  const visible = sorted.slice(0, VISIBLE_LIMIT);

  return (
    <div className="overflow-x-auto rounded border border-border bg-bg-elevated">
      <table className="w-full text-xs">
        <thead className="bg-bg-subtle">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                onClick={() => toggleSort(c.key)}
                className="cursor-pointer select-none whitespace-nowrap px-2 py-1.5 text-left font-medium text-fg-muted hover:text-fg"
                title="Click to sort"
              >
                <span className="inline-flex items-center gap-1">
                  {prettyHeader(c.key)}
                  {sortKey === c.key &&
                    (sortDir === "asc" ? (
                      <ArrowUp className="h-3 w-3" />
                    ) : (
                      <ArrowDown className="h-3 w-3" />
                    ))}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((r, i) => (
            <tr key={i} className="border-t border-border/50 hover:bg-bg-subtle/50">
              {columns.map((c) => {
                const numeric = c.kind === "number";
                return (
                  <td
                    key={c.key}
                    className={`whitespace-nowrap px-2 py-1 text-fg ${numeric ? "text-right tabular-nums" : ""}`}
                  >
                    {renderCell(r[c.key], c.kind)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length > VISIBLE_LIMIT && (
        <div className="border-t border-border bg-bg-subtle px-2 py-1 text-[10px] text-fg-subtle">
          Showing first {VISIBLE_LIMIT.toLocaleString()} of {sorted.length.toLocaleString()} rows.
          Download CSV for the full set.
        </div>
      )}
    </div>
  );
}
