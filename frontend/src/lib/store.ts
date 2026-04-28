/**
 * Zustand client-side store for cross-cutting UI state.
 * Server state lives in TanStack Query.
 */

import { create } from "zustand";

export type DashboardFilter = {
  member: string;          // Cube member name (e.g. "Orders.country")
  operator: "equals" | "notEquals";
  values: (string | number)[];
};

/**
 * Drill-down handoff state: when the user clicks a chart mark in chat or
 * dashboard, we route them to the Workbench with the originating query +
 * a filter for the clicked categorical. The workbench reads this on mount,
 * applies it, then clears it.
 */
export type DrillDownPayload = {
  cubeQuery: {
    measures?: string[];
    dimensions?: string[];
    timeDimensions?: { dimension: string; granularity?: string; dateRange?: string | string[] }[];
    segments?: string[];
    filters?: { member: string; operator: string; values?: unknown[] }[];
    order?: Record<string, "asc" | "desc">;
    limit?: number;
  };
  /** Optional — when omitted, the workbench loads the query verbatim ("Continue in Workbook"). */
  filter?: DashboardFilter;
  source: string; // "chat" | "dashboard:<id>"
};

type AppState = {
  density: "comfortable" | "dense";
  setDensity: (d: AppState["density"]) => void;

  // Cross-filter state, scoped per dashboard.
  // Map<dashboardId, filters[]>
  crossFilters: Record<string, DashboardFilter[]>;
  addCrossFilter: (dashboardId: string, f: DashboardFilter) => void;
  removeCrossFilter: (dashboardId: string, member: string) => void;
  clearCrossFilters: (dashboardId: string) => void;

  // Per-dashboard global time range (Cube relative-date string) that overrides
  // the dateRange on each tile's first timeDimension. `null` = use each tile's
  // own dateRange unchanged.
  dashboardTimeRange: Record<string, string | null>;
  setDashboardTimeRange: (dashboardId: string, value: string | null) => void;

  // Drill-down handoff state (single-shot)
  pendingDrill: DrillDownPayload | null;
  setPendingDrill: (p: DrillDownPayload | null) => void;

  // Pending model-editor jump from chat citation (single-shot).
  pendingModelJump: { path: string; line: number } | null;
  setPendingModelJump: (p: { path: string; line: number } | null) => void;
};

export const useApp = create<AppState>((set) => ({
  density: "comfortable",
  setDensity: (d) => set({ density: d }),

  crossFilters: {},
  addCrossFilter: (dashboardId, f) =>
    set((s) => {
      const existing = s.crossFilters[dashboardId] ?? [];
      // Replace any prior filter on the same member; otherwise append.
      const others = existing.filter((x) => x.member !== f.member);
      return {
        crossFilters: { ...s.crossFilters, [dashboardId]: [...others, f] },
      };
    }),
  removeCrossFilter: (dashboardId, member) =>
    set((s) => ({
      crossFilters: {
        ...s.crossFilters,
        [dashboardId]: (s.crossFilters[dashboardId] ?? []).filter((x) => x.member !== member),
      },
    })),
  clearCrossFilters: (dashboardId) =>
    set((s) => ({
      crossFilters: { ...s.crossFilters, [dashboardId]: [] },
    })),

  dashboardTimeRange: {},
  setDashboardTimeRange: (dashboardId, value) =>
    set((s) => ({
      dashboardTimeRange: { ...s.dashboardTimeRange, [dashboardId]: value },
    })),

  pendingDrill: null,
  setPendingDrill: (p) => set({ pendingDrill: p }),

  pendingModelJump: null,
  setPendingModelJump: (p) => set({ pendingModelJump: p }),
}));

/**
 * Override the dateRange on the first timeDimension of a query.
 * Tiles without a timeDimension are returned unchanged (we don't fabricate one).
 */
export function applyDashboardTimeRange<
  T extends { timeDimensions?: { dimension: string; granularity?: string; dateRange?: string | string[] }[] },
>(query: T, dateRange: string | null): T {
  if (!dateRange) return query;
  const tds = query.timeDimensions ?? [];
  if (tds.length === 0) return query;
  const [first, ...rest] = tds;
  return { ...query, timeDimensions: [{ ...first, dateRange }, ...rest] };
}

/**
 * Merge a base CubeQuery with the active cross-filters for a dashboard.
 * Returns a new query — does not mutate.
 */
export function applyCrossFilters<T extends { filters?: unknown[] }>(
  query: T,
  filters: DashboardFilter[],
): T {
  if (filters.length === 0) return query;
  const merged = [...((query.filters as unknown[]) ?? []), ...filters];
  return { ...query, filters: merged };
}
