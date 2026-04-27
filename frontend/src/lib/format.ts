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

export function formatDate(value: unknown, granularity?: string): string {
  if (!value) return "—";
  let d: Date;
  if (value instanceof Date) d = value;
  else if (typeof value === "string") d = new Date(value);
  else if (typeof value === "number") d = new Date(value);
  else return String(value);
  if (Number.isNaN(d.getTime())) return String(value);

  const opts: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "short",
  };
  if (granularity === "day" || granularity === "week") {
    opts.day = "numeric";
  } else if (granularity === "year") {
    delete opts.month;
  } else if (granularity === "quarter") {
    const q = Math.floor(d.getMonth() / 3) + 1;
    return `Q${q} ${d.getFullYear()}`;
  }
  return new Intl.DateTimeFormat("en-US", opts).format(d);
}
