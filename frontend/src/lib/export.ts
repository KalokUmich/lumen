/**
 * Client-side data export utilities — no server roundtrip needed.
 */

export function rowsToCSV(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return "";
  const cols = Object.keys(rows[0]);
  const escape = (v: unknown): string => {
    if (v == null) return "";
    const s = typeof v === "string" ? v : String(v);
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  };
  const lines = [cols.join(",")];
  for (const r of rows) {
    lines.push(cols.map((c) => escape(r[c])).join(","));
  }
  return lines.join("\n");
}

export function downloadFile(name: string, content: string, mime = "text/plain") {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function downloadCSV(rows: Record<string, unknown>[], filename = "lumen-export.csv") {
  downloadFile(filename, rowsToCSV(rows), "text/csv");
}

/**
 * Convert a pretty SQL string to a single-line for clipboard pastability.
 */
export function flattenSQL(sql: string): string {
  return sql.replace(/\s+/g, " ").trim();
}
