/**
 * Right-click context menu for charts (Omni-style drill).
 *
 * Wraps any chart-rendering content. On contextmenu it positions a menu at
 * the cursor with actions:
 *   - Open in Workbook (loads cubeQuery into workbench, no filter)
 *   - Filter by [first categorical dim] = <value> (submenu over current rows)
 *   - Copy SQL (when sql provided)
 *   - Download CSV
 *
 * We deliberately do NOT try to map the cursor to an individual mark inside
 * the Plot SVG — Plot doesn't expose stable mark↔row mapping post-render and
 * any DOM-diving solution would break across chart types. A chart-scoped menu
 * keeps the UX consistent and the implementation honest.
 */

import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Code, Copy, Download, Filter, Check } from "lucide-react";
import { useApp } from "../../lib/store";
import type { CubeQuery } from "../../lib/api";
import { downloadCSV, flattenSQL } from "../../lib/export";

type Props = {
  rows: Record<string, unknown>[];
  cubeQuery?: CubeQuery;
  sql?: string | null;
  /** Dashboard id when this chart is on a dashboard; enables cross-filter actions. */
  dashboardId?: string;
  filenameStem?: string;
  children: React.ReactNode;
};

type Position = { x: number; y: number };

export function ChartContextMenu({
  rows,
  cubeQuery,
  sql,
  dashboardId,
  filenameStem = "lumen-export",
  children,
}: Props) {
  const [pos, setPos] = useState<Position | null>(null);
  const setPendingDrill = useApp((s) => s.setPendingDrill);
  const addCrossFilter = useApp((s) => s.addCrossFilter);

  const close = () => setPos(null);

  // Pick the first non-time dimension as the drill axis.
  const drillDim = (cubeQuery?.dimensions ?? [])[0];
  const drillKey = drillDim?.replace(/\./g, "__");

  // Collect distinct values from current rows; cap at 20 so the submenu doesn't explode.
  const drillValues: string[] = (() => {
    if (!drillKey) return [];
    const seen = new Set<string>();
    for (const r of rows) {
      const v = r[drillKey];
      if (v == null) continue;
      seen.add(String(v));
      if (seen.size >= 20) break;
    }
    return Array.from(seen);
  })();

  function openInWorkbook() {
    if (!cubeQuery) return;
    setPendingDrill({ cubeQuery, source: "chart-context" });
    close();
  }

  function filterBy(value: string) {
    if (!drillDim) return;
    if (dashboardId) {
      addCrossFilter(dashboardId, {
        member: drillDim,
        operator: "equals",
        values: [value],
      });
    } else if (cubeQuery) {
      // Outside a dashboard: drill into Workbook with the filter applied.
      setPendingDrill({
        cubeQuery,
        filter: { member: drillDim, operator: "equals", values: [value] },
        source: "chart-context",
      });
    }
    close();
  }

  function copySQL() {
    if (sql) navigator.clipboard.writeText(flattenSQL(sql)).catch(() => {});
    close();
  }

  function exportCSV() {
    downloadCSV(rows, `${filenameStem}.csv`);
    close();
  }

  return (
    <>
      <div
        onContextMenu={(e) => {
          // Only intercept when there's at least one action to offer.
          if (!cubeQuery && !sql && rows.length === 0) return;
          e.preventDefault();
          setPos({ x: e.clientX, y: e.clientY });
        }}
      >
        {children}
      </div>
      {pos && (
        <ContextMenu
          pos={pos}
          onClose={close}
          openInWorkbook={cubeQuery ? openInWorkbook : undefined}
          drillDim={drillDim}
          drillValues={drillValues}
          onFilterBy={drillValues.length ? filterBy : undefined}
          onCopySQL={sql ? copySQL : undefined}
          onExportCSV={rows.length ? exportCSV : undefined}
          dashboardScope={Boolean(dashboardId)}
        />
      )}
    </>
  );
}

function ContextMenu({
  pos,
  onClose,
  openInWorkbook,
  drillDim,
  drillValues,
  onFilterBy,
  onCopySQL,
  onExportCSV,
  dashboardScope,
}: {
  pos: Position;
  onClose: () => void;
  openInWorkbook?: () => void;
  drillDim?: string;
  drillValues: string[];
  onFilterBy?: (v: string) => void;
  onCopySQL?: () => void;
  onExportCSV?: () => void;
  dashboardScope: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [submenu, setSubmenu] = useState(false);

  // Close on outside click + Escape.
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    // Defer a tick so the click that opened the menu doesn't immediately close it.
    const t = setTimeout(() => {
      document.addEventListener("mousedown", onDoc);
      document.addEventListener("keydown", onKey);
    }, 0);
    return () => {
      clearTimeout(t);
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  // Clamp to viewport so the menu doesn't render off-screen.
  const left = Math.min(pos.x, window.innerWidth - 240);
  const top = Math.min(pos.y, window.innerHeight - 220);

  return (
    <div
      ref={ref}
      role="menu"
      data-testid="chart-context-menu"
      className="fixed z-50 min-w-[220px] overflow-hidden rounded-md border border-border bg-bg-elevated text-sm text-fg shadow-lg"
      style={{ left, top }}
    >
      {openInWorkbook && (
        <MenuItem icon={<ArrowUpRight className="h-3.5 w-3.5" />} onClick={openInWorkbook}>
          Open in Workbook
        </MenuItem>
      )}
      {onFilterBy && drillDim && drillValues.length > 0 && (
        <div
          className="relative"
          onMouseEnter={() => setSubmenu(true)}
          onMouseLeave={() => setSubmenu(false)}
        >
          <MenuItem icon={<Filter className="h-3.5 w-3.5" />} chevron>
            {dashboardScope ? "Filter all tiles by" : "Drill by"} {labelOf(drillDim)}
          </MenuItem>
          {submenu && (
            <div className="absolute left-full top-0 ml-px max-h-64 overflow-y-auto rounded-md border border-border bg-bg-elevated shadow-lg">
              {drillValues.map((v) => (
                <button
                  key={v}
                  onClick={() => onFilterBy(v)}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-bg-subtle"
                  role="menuitem"
                >
                  <Check className="h-3 w-3 opacity-0" />
                  <span className="truncate">{v}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {(onCopySQL || onExportCSV) && <Divider />}
      {onCopySQL && (
        <MenuItem icon={<Copy className="h-3.5 w-3.5" />} onClick={onCopySQL}>
          Copy SQL
        </MenuItem>
      )}
      {onExportCSV && (
        <MenuItem icon={<Download className="h-3.5 w-3.5" />} onClick={onExportCSV}>
          Download CSV
        </MenuItem>
      )}
      {!openInWorkbook && !onFilterBy && !onCopySQL && !onExportCSV && (
        <div className="px-3 py-2 text-xs text-fg-subtle">No actions available.</div>
      )}
    </div>
  );
}

function MenuItem({
  icon,
  onClick,
  chevron,
  children,
}: {
  icon?: React.ReactNode;
  onClick?: () => void;
  chevron?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      role="menuitem"
      className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left hover:bg-bg-subtle"
    >
      <span className="flex items-center gap-2">
        <Code className="h-3.5 w-3.5 opacity-0" style={{ display: icon ? "none" : undefined }} />
        {icon}
        <span className="text-xs">{children}</span>
      </span>
      {chevron && <span className="text-fg-subtle">›</span>}
    </button>
  );
}

function Divider() {
  return <div className="my-1 border-t border-border" />;
}

function labelOf(dim: string): string {
  // "Orders.country" → "country"
  return dim.split(".").pop() ?? dim;
}
