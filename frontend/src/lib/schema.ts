/**
 * Lightweight parser for the workspace's schema_summary text.
 *
 * The schema_summary is markdown emitted by `shared.schema_bundle.get_bundle`,
 * structured by H2 sections like "## Cube: Foo" with bullet lists for
 * Dimensions / Measures / Segments / Joins. We parse it into a navigable tree
 * so the frontend can render a field picker.
 */

export type SchemaMember = {
  cube: string;
  name: string;        // member name without cube prefix
  fullName: string;    // "Cube.member"
  type: string;
  description?: string;
  meta?: string;       // raw [...] meta string
  // Parsed from `meta`:
  synonyms?: string[];
  enumValues?: string[];
  aiHint?: string;
  exampleQuestions?: string[];
};

function parseMetaString(meta: string | undefined): {
  synonyms?: string[];
  enumValues?: string[];
  aiHint?: string;
  exampleQuestions?: string[];
} {
  if (!meta) return {};
  // The meta string looks like:
  //   synonyms: ['sales', 'gmv', ...]; enum_values: [...]; ai_hint: "..."
  const out: Record<string, unknown> = {};

  const synMatch = meta.match(/synonyms:\s*\[([^\]]*)\]/);
  if (synMatch) {
    out.synonyms = synMatch[1].split(",").map((s) => s.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean);
  }
  const enumMatch = meta.match(/enum_values:\s*\[([^\]]*)\]/);
  if (enumMatch) {
    out.enumValues = enumMatch[1].split(",").map((s) => s.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean);
  }
  const hintMatch = meta.match(/ai_hint:\s*"([^"]*)"/);
  if (hintMatch) {
    out.aiHint = hintMatch[1];
  }
  const exMatch = meta.match(/examples:\s*\[([^\]]*)\]/);
  if (exMatch) {
    out.exampleQuestions = exMatch[1]
      .split(",")
      .map((s) => s.trim().replace(/^['"]|['"]$/g, ""))
      .filter(Boolean);
  }
  return out;
}

export type CubeSchema = {
  name: string;
  description?: string;
  dimensions: SchemaMember[];
  measures: SchemaMember[];
  timeDimensions: SchemaMember[];
  segments: SchemaMember[];
  joins: string[];
};

const CUBE_HEADER_RE = /^##\s+Cube:\s+([A-Z][A-Za-z0-9_]*)\s*$/;
const SECTION_RE = /^###\s+(.+)$/;
const MEMBER_RE = /^-\s+([A-Z][A-Za-z0-9_]*)\.([a-z][a-z0-9_]*)\s*\(([^)]*)\)\s*(.*)$/;
const JOIN_RE = /^-\s+→\s+([A-Z][A-Za-z0-9_]*)/;

export function parseSchema(text: string): CubeSchema[] {
  const cubes: CubeSchema[] = [];
  let current: CubeSchema | null = null;
  let section: "Dimensions" | "Measures" | "Segments" | "Joins" | null = null;
  let descriptionPending = false;

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trimEnd();

    const cubeMatch = line.match(CUBE_HEADER_RE);
    if (cubeMatch) {
      if (current) cubes.push(current);
      current = {
        name: cubeMatch[1],
        dimensions: [],
        measures: [],
        timeDimensions: [],
        segments: [],
        joins: [],
      };
      section = null;
      descriptionPending = true;
      continue;
    }

    if (!current) continue;

    if (descriptionPending && line.startsWith("Description:")) {
      current.description = line.replace(/^Description:\s*/, "").trim();
      descriptionPending = false;
      continue;
    }

    const sec = line.match(SECTION_RE);
    if (sec) {
      const s = sec[1].trim();
      section = (s as "Dimensions" | "Measures" | "Segments" | "Joins") ?? null;
      descriptionPending = false;
      continue;
    }

    if (section === "Joins") {
      const j = line.match(JOIN_RE);
      if (j) current.joins.push(j[1]);
      continue;
    }

    const m = line.match(MEMBER_RE);
    if (m) {
      const cube = m[1];
      const name = m[2];
      const type = m[3].trim();
      const rest = m[4] ?? "";
      const metaStr = rest.match(/\[([^\]]+)\]/)?.[1];
      const parsedMeta = parseMetaString(metaStr);
      const member: SchemaMember = {
        cube,
        name,
        fullName: `${cube}.${name}`,
        type,
        description: rest.split("[")[0].replace(/^—\s*/, "").trim() || undefined,
        meta: metaStr,
        ...parsedMeta,
      };
      if (section === "Measures") current.measures.push(member);
      else if (section === "Segments") current.segments.push(member);
      else if (type.includes("time")) current.timeDimensions.push(member);
      else if (section === "Dimensions") current.dimensions.push(member);
    }

    // Lines starting with bullets that don't match — likely segment plain text
    if (section === "Segments" && line.startsWith("- ")) {
      const seg = line.match(/^-\s+([A-Z][A-Za-z0-9_]*)\.([a-z][a-z0-9_]*)/);
      if (seg && !current.segments.find((s) => s.fullName === `${seg[1]}.${seg[2]}`)) {
        current.segments.push({
          cube: seg[1],
          name: seg[2],
          fullName: `${seg[1]}.${seg[2]}`,
          type: "segment",
        });
      }
    }
  }

  if (current) cubes.push(current);
  return cubes;
}
