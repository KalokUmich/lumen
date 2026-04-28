/**
 * Renders a Cube-generated SQL string with syntax highlighting.
 * Tokenizer lives in `lib/sql-highlight` so it's testable and swappable.
 */

import { useMemo } from "react";
import { tokenizeSql, classForToken } from "../../lib/sql-highlight";

export function SqlView({ sql }: { sql: string }) {
  const tokens = useMemo(() => tokenizeSql(sql), [sql]);
  return (
    <pre
      data-testid="sql-view"
      className="overflow-x-auto whitespace-pre-wrap break-words p-2 font-mono text-[11px] leading-relaxed"
    >
      {tokens.map((t, i) => (
        <span key={i} className={classForToken(t.type)}>
          {t.text}
        </span>
      ))}
    </pre>
  );
}
