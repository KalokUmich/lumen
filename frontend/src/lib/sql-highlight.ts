/**
 * Tiny SQL syntax highlighter — emits an array of styled tokens.
 *
 * Why not Prism / highlight.js: those add 30-100KB for a single panel that
 * shows ~1KB of SQL. A regex tokenizer + 6 token classes is enough for the
 * Cube-generated SQL we display (SELECT/FROM/WHERE/JOIN/GROUP BY etc).
 *
 * Pipeline: tokens come back as `{type, text}[]`. The renderer maps the type
 * to a Tailwind class so the colors stay theme-aware (light/dark).
 *
 * Coverage:
 *   - keywords  — SELECT, FROM, WHERE, JOIN, GROUP BY, ORDER BY, AS, IS, NOT,
 *                 NULL, AND, OR, ON, INNER, LEFT, RIGHT, OUTER, BY, DESC, ASC,
 *                 BETWEEN, IN, LIKE, ILIKE, CASE, WHEN, THEN, ELSE, END,
 *                 LIMIT, OFFSET, DISTINCT, UNION, ALL, WITH, HAVING
 *   - functions — uppercase identifiers immediately followed by `(`
 *   - strings   — single-quoted, with `''` escape
 *   - numbers   — int or float
 *   - punct     — parens, commas, semicolons, operators
 *   - identifier — anything else
 *
 * Multi-word keywords like "GROUP BY" are matched as two tokens with separate
 * highlighting; that's both simpler and what most editors do.
 */

export type SqlTokenType =
  | "keyword"
  | "function"
  | "string"
  | "number"
  | "punct"
  | "ident"
  | "ws";

export type SqlToken = { type: SqlTokenType; text: string };

const KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER", "FULL",
  "ON", "AS", "AND", "OR", "NOT", "IS", "NULL", "BY", "GROUP", "ORDER", "ASC",
  "DESC", "LIMIT", "OFFSET", "DISTINCT", "UNION", "ALL", "WITH", "HAVING",
  "BETWEEN", "IN", "LIKE", "ILIKE", "CASE", "WHEN", "THEN", "ELSE", "END",
  "INTERVAL", "CAST", "OVER", "PARTITION", "ROWS", "RANGE", "PRECEDING",
  "FOLLOWING", "UNBOUNDED", "CURRENT", "ROW", "EXISTS", "UPDATE", "INSERT",
  "DELETE", "VALUES", "SET", "INTO", "RETURNING", "TRUE", "FALSE",
]);

export function tokenizeSql(sql: string): SqlToken[] {
  const tokens: SqlToken[] = [];
  let i = 0;
  const n = sql.length;
  while (i < n) {
    const ch = sql[i];

    // whitespace (preserved verbatim)
    if (/\s/.test(ch)) {
      let j = i + 1;
      while (j < n && /\s/.test(sql[j])) j++;
      tokens.push({ type: "ws", text: sql.slice(i, j) });
      i = j;
      continue;
    }

    // single-line comment -- ...
    if (ch === "-" && sql[i + 1] === "-") {
      let j = i + 2;
      while (j < n && sql[j] !== "\n") j++;
      tokens.push({ type: "ws", text: sql.slice(i, j) });
      i = j;
      continue;
    }

    // single-quoted string
    if (ch === "'") {
      let j = i + 1;
      while (j < n) {
        if (sql[j] === "'" && sql[j + 1] === "'") { j += 2; continue; }
        if (sql[j] === "'") { j++; break; }
        j++;
      }
      tokens.push({ type: "string", text: sql.slice(i, j) });
      i = j;
      continue;
    }

    // double-quoted identifier (Postgres/Cube style "Orders.order_date")
    if (ch === '"') {
      let j = i + 1;
      while (j < n && sql[j] !== '"') j++;
      if (j < n) j++; // closing quote
      tokens.push({ type: "ident", text: sql.slice(i, j) });
      i = j;
      continue;
    }

    // number
    if (/[0-9]/.test(ch) || (ch === "." && /[0-9]/.test(sql[i + 1] ?? ""))) {
      let j = i + 1;
      while (j < n && /[0-9.]/.test(sql[j])) j++;
      tokens.push({ type: "number", text: sql.slice(i, j) });
      i = j;
      continue;
    }

    // identifier or keyword
    if (/[A-Za-z_]/.test(ch)) {
      let j = i + 1;
      while (j < n && /[A-Za-z0-9_]/.test(sql[j])) j++;
      const word = sql.slice(i, j);
      const upper = word.toUpperCase();
      if (KEYWORDS.has(upper)) {
        tokens.push({ type: "keyword", text: word });
      } else if (sql[j] === "(") {
        tokens.push({ type: "function", text: word });
      } else {
        tokens.push({ type: "ident", text: word });
      }
      i = j;
      continue;
    }

    // everything else → punct (operators, parens, commas, …)
    tokens.push({ type: "punct", text: ch });
    i++;
  }
  return tokens;
}

export function classForToken(type: SqlTokenType): string {
  switch (type) {
    case "keyword":  return "text-accent font-semibold";
    case "function": return "text-info";
    case "string":   return "text-success";
    case "number":   return "text-warning";
    case "punct":    return "text-fg-muted";
    case "ws":       return "";
    case "ident":    return "text-fg";
  }
}
