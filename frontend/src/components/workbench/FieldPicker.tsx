/**
 * Schema-aware field picker — left rail of the Workbench.
 * Reads the workspace's schema_summary, parses it, and shows cubes →
 * measures / dimensions / segments as click-to-add tokens.
 */

import { useMemo, useState } from "react";
import * as React from "react";
import clsx from "clsx";
import { ChevronDown, ChevronRight, Hash, Calendar, Tag, Layers, BarChart2 } from "lucide-react";
import { CubeSchema, SchemaMember } from "../../lib/schema";

type Props = {
  schemas: CubeSchema[];
  onAdd: (kind: "measure" | "dimension" | "timeDimension" | "segment", member: SchemaMember) => void;
};

export function FieldPicker({ schemas, onAdd }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(schemas.slice(0, 2).map((c) => c.name))
  );
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    if (!filter.trim()) return schemas;
    const f = filter.toLowerCase();
    return schemas
      .map((c) => ({
        ...c,
        measures: c.measures.filter((m) => m.fullName.toLowerCase().includes(f) || m.description?.toLowerCase().includes(f)),
        dimensions: c.dimensions.filter((m) => m.fullName.toLowerCase().includes(f) || m.description?.toLowerCase().includes(f)),
        timeDimensions: c.timeDimensions.filter((m) => m.fullName.toLowerCase().includes(f)),
        segments: c.segments.filter((m) => m.fullName.toLowerCase().includes(f)),
      }))
      .filter((c) => c.measures.length || c.dimensions.length || c.timeDimensions.length || c.segments.length);
  }, [schemas, filter]);

  function toggle(cube: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(cube)) next.delete(cube);
      else next.add(cube);
      return next;
    });
  }

  return (
    <div className="flex h-full w-full flex-col">
      <div className="border-b border-border p-2">
        <input
          className="input w-full text-xs"
          placeholder="Filter fields…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className="flex-1 overflow-y-auto">
        {filtered.map((cube) => {
          const isOpen = expanded.has(cube.name) || filter.trim() !== "";
          return (
            <div key={cube.name} className="border-b border-border/50">
              <button
                onClick={() => toggle(cube.name)}
                className="flex w-full items-center gap-1 px-2 py-1.5 text-xs font-semibold text-fg hover:bg-bg-subtle"
              >
                {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                <Layers className="h-3 w-3 text-fg-subtle" />
                <span>{cube.name}</span>
                <span className="ml-auto text-fg-subtle">
                  {cube.measures.length}m · {cube.dimensions.length + cube.timeDimensions.length}d
                </span>
              </button>
              {isOpen && (
                <div className="pb-2">
                  {cube.measures.length > 0 && (
                    <Section title="Measures">
                      {cube.measures.map((m) => (
                        <FieldRow
                          key={m.fullName}
                          member={m}
                          icon={<BarChart2 className="h-3 w-3 text-success" />}
                          onClick={() => onAdd("measure", m)}
                        />
                      ))}
                    </Section>
                  )}
                  {cube.timeDimensions.length > 0 && (
                    <Section title="Time">
                      {cube.timeDimensions.map((m) => (
                        <FieldRow
                          key={m.fullName}
                          member={m}
                          icon={<Calendar className="h-3 w-3 text-accent" />}
                          onClick={() => onAdd("timeDimension", m)}
                        />
                      ))}
                    </Section>
                  )}
                  {cube.dimensions.length > 0 && (
                    <Section title="Dimensions">
                      {cube.dimensions.map((m) => (
                        <FieldRow
                          key={m.fullName}
                          member={m}
                          icon={<Hash className="h-3 w-3 text-warning" />}
                          onClick={() => onAdd("dimension", m)}
                        />
                      ))}
                    </Section>
                  )}
                  {cube.segments.length > 0 && (
                    <Section title="Segments">
                      {cube.segments.map((m) => (
                        <FieldRow
                          key={m.fullName}
                          member={m}
                          icon={<Tag className="h-3 w-3 text-fg-muted" />}
                          onClick={() => onAdd("segment", m)}
                        />
                      ))}
                    </Section>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="px-2 pt-1 text-[10px] uppercase tracking-wider text-fg-subtle">{title}</div>
      {children}
    </div>
  );
}

function FieldRow({
  member,
  icon,
  onClick,
}: {
  member: SchemaMember;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        onClick={onClick}
        className={clsx(
          "flex w-full items-center gap-2 px-2 py-1 text-left text-xs",
          "text-fg-muted hover:bg-bg-subtle hover:text-fg"
        )}
      >
        {icon}
        <span className="truncate">{member.name}</span>
      </button>
      {hovered && (member.description || member.synonyms?.length || member.aiHint) && (
        <FieldTooltip member={member} />
      )}
    </div>
  );
}

function FieldTooltip({ member }: { member: SchemaMember }) {
  return (
    <div
      className="absolute left-full top-0 z-50 ml-1 w-72 rounded-md border border-border bg-bg-elevated p-3 shadow-xl"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="mb-1 font-mono text-[11px] text-fg">{member.fullName}</div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-fg-subtle">{member.type}</div>
      {member.description && (
        <div className="mb-2 text-xs leading-snug text-fg-muted">{member.description}</div>
      )}
      {member.synonyms && member.synonyms.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] uppercase tracking-wider text-fg-subtle">Synonyms</div>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {member.synonyms.map((s) => (
              <span key={s} className="rounded border border-border px-1.5 py-0.5 text-[10px] text-fg-muted">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
      {member.enumValues && member.enumValues.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] uppercase tracking-wider text-fg-subtle">Values</div>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {member.enumValues.map((v) => (
              <span key={v} className="rounded bg-bg-subtle px-1.5 py-0.5 font-mono text-[10px] text-fg">
                {v}
              </span>
            ))}
          </div>
        </div>
      )}
      {member.aiHint && (
        <div className="mb-1 rounded border border-accent/30 bg-accent/5 p-1.5">
          <div className="text-[10px] uppercase tracking-wider text-accent/80">AI hint</div>
          <div className="text-[11px] leading-snug text-fg-muted">{member.aiHint}</div>
        </div>
      )}
      {member.exampleQuestions && member.exampleQuestions.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-fg-subtle">Example questions</div>
          <ul className="mt-0.5 list-inside list-disc text-[11px] leading-snug text-fg-muted">
            {member.exampleQuestions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
