/**
 * Number formatting per `data-viz-standards` SKILL §6.
 *
 * - K/M/B/T suffixes with 3 significant digits
 * - Currency: $1.2M, €450K — symbol prefix + suffix abbreviation
 * - Percent: precision adjusts by magnitude
 * - Tabular numerals everywhere (the .num CSS class handles font-feature-settings)
 *
 * Use formatValue for general number display. For axis ticks and chart cell
 * labels prefer formatCompact (always abbreviates).
 */

export type ValueFormat = "number" | "currency" | "percent" | undefined;

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CNY: "¥",
};

function compactNumber(n: number): string {
  const abs = Math.abs(n);
  if (!Number.isFinite(n)) return "—";
  if (abs < 1000) return Number.isInteger(n) ? n.toString() : n.toFixed(2);
  const units = [
    { v: 1e12, s: "T" },
    { v: 1e9, s: "B" },
    { v: 1e6, s: "M" },
    { v: 1e3, s: "K" },
  ];
  for (const u of units) {
    if (abs >= u.v) {
      const x = n / u.v;
      // 3 significant digits
      const fixed = Math.abs(x) >= 100 ? 0 : Math.abs(x) >= 10 ? 1 : 2;
      return `${x.toFixed(fixed)}${u.s}`;
    }
  }
  return n.toLocaleString();
}

export function formatValue(
  value: unknown,
  fmt?: ValueFormat,
  currency: string = "USD"
): string {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);

  if (fmt === "currency") {
    const sym = CURRENCY_SYMBOLS[currency] ?? "$";
    return `${sym}${compactNumber(n)}`;
  }
  if (fmt === "percent") {
    const v = n * 100;
    const abs = Math.abs(v);
    if (abs >= 10) return `${v.toFixed(0)}%`;
    if (abs >= 1) return `${v.toFixed(1)}%`;
    return `${v.toFixed(2)}%`;
  }
  return compactNumber(n);
}

export function formatExact(value: unknown, fmt?: ValueFormat, currency: string = "USD"): string {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (fmt === "currency") {
    return n.toLocaleString("en-US", { style: "currency", currency });
  }
  if (fmt === "percent") {
    return `${(n * 100).toFixed(2)}%`;
  }
  return n.toLocaleString();
}

/**
 * Parse a value into a Date, handling the common "YYYY-MM-DD" wire format
 * locally (not as UTC midnight) so the date doesn't shift by a day when the
 * user's timezone is west of UTC.
 */
export function parseDate(value: unknown): Date | null {
  if (value == null) return null;
  if (value instanceof Date) return value;
  if (typeof value === "number") return new Date(value);
  if (typeof value === "string") {
    // "YYYY-MM-DD" — treat as LOCAL date, not UTC, to avoid TZ off-by-one.
    const m = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) return new Date(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10));
    // ISO with time — let Date parse, but strip any trailing "T00:00:00" first
    // for the (rare) case where backend didn't strip it.
    const stripped = value.replace(/T00:00:00(?:\.0+)?(?:Z)?$/, "");
    const cleanMatch = stripped.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (cleanMatch) {
      return new Date(parseInt(cleanMatch[1], 10), parseInt(cleanMatch[2], 10) - 1, parseInt(cleanMatch[3], 10));
    }
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  return null;
}

export function formatDate(value: unknown, granularity?: string): string {
  if (value == null || value === "") return "—";
  const d = parseDate(value);
  if (!d) return String(value);

  if (granularity === "year") {
    return String(d.getFullYear());
  }
  if (granularity === "quarter") {
    return `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`;
  }
  if (granularity === "week" || granularity === "day") {
    return new Intl.DateTimeFormat("en-US", {
      year: "numeric", month: "short", day: "numeric",
    }).format(d);
  }
  // Default (month / unknown granularity) → "Jan 1998"
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric", month: "short",
  }).format(d);
}
