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

type AppState = {
  density: "comfortable" | "dense";
  setDensity: (d: AppState["density"]) => void;

  // Cross-filter state, scoped per dashboard.
  // Map<dashboardId, filters[]>
  crossFilters: Record<string, DashboardFilter[]>;
  addCrossFilter: (dashboardId: string, f: DashboardFilter) => void;
  removeCrossFilter: (dashboardId: string, member: string) => void;
  clearCrossFilters: (dashboardId: string) => void;
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
}));

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
