/**
 * Citations — clickable chips for the measures + dimensions used in an
 * assistant message. Click a chip → look up the source location via
 * `/api/v1/model/locate` and navigate to the Model Editor at that line.
 *
 * Renders nothing if the cube_query has no fields.
 */

import { Link2 } from "lucide-react";
import { useApp } from "../../lib/store";
import { locateMember, type CubeQuery } from "../../lib/api";

export function Citations({ cubeQuery }: { cubeQuery: CubeQuery }) {
  const setPendingModelJump = useApp((s) => s.setPendingModelJump);

  const fields: { kind: "measure" | "dimension"; name: string }[] = [
    ...(cubeQuery.measures ?? []).map((n) => ({ kind: "measure" as const, name: n })),
    ...(cubeQuery.dimensions ?? []).map((n) => ({ kind: "dimension" as const, name: n })),
    ...(cubeQuery.timeDimensions ?? []).map((td) => ({
      kind: "dimension" as const,
      name: td.dimension,
    })),
  ];
  if (fields.length === 0) return null;

  async function jump(member: string) {
    try {
      const loc = await locateMember(member);
      if (loc) {
        setPendingModelJump({ path: loc.path, line: loc.line });
      }
    } catch (e) {
      console.warn("locate failed", e);
    }
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-fg-subtle">Sources:</span>
      {fields.map((f) => (
        <button
          key={`${f.kind}:${f.name}`}
          data-testid={`citation-${f.name}`}
          onClick={() => jump(f.name)}
          className="inline-flex items-center gap-1 rounded-md border border-border bg-bg-elevated px-2 py-0.5 font-mono text-[10px] text-fg-muted hover:border-accent hover:text-fg"
          title={`Open ${f.name} in Model Editor`}
        >
          <Link2 className="h-2.5 w-2.5" />
          {f.name}
        </button>
      ))}
    </div>
  );
}
