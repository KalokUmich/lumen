/**
 * Typed API client. Talks to /api/* (proxied by Vite to api_gateway in dev).
 *
 * Phase 0 auth: a `dev:user:workspace:role:preset` bearer token. The workspace
 * portion is dynamic (selected via UI) so the same client can switch workspaces.
 */

let activeWorkspaceId = "ws-demo";
let activePreset = "balanced";

export function setActiveWorkspace(workspaceId: string, preset = "balanced"): void {
  activeWorkspaceId = workspaceId;
  activePreset = preset;
}

export function getActiveWorkspace(): string {
  return activeWorkspaceId;
}

function authHeaders(): HeadersInit {
  return {
    Authorization: `Bearer dev:user-1:${activeWorkspaceId}:admin:${activePreset}`,
  };
}

export type Workspace = {
  id: string;
  slug: string;
  name: string;
  vertical: string;
  llm_preset: string;
};

export type SchemaBundle = {
  workspace_id: string;
  vertical: string;
  schema_summary: string;
  glossary: string;
};

export async function listWorkspaces(): Promise<Workspace[]> {
  const r = await fetch("/api/v1/workspaces", { headers: authHeaders() });
  if (!r.ok) throw new Error(`workspaces: ${r.status}`);
  return r.json();
}

export async function getSchemaBundle(workspaceId: string): Promise<SchemaBundle> {
  const r = await fetch(`/api/v1/workspaces/${workspaceId}/schema-bundle`, {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`schema-bundle: ${r.status}`);
  return r.json();
}

export type WorkbookRecord = {
  id: string;
  name: string;
  cube_query: CubeQuery;
  chart_spec: unknown;
  updated_at?: string;
};

export async function listWorkbooks(workspaceId: string): Promise<WorkbookRecord[]> {
  const r = await fetch(`/api/v1/workbooks?workspace_id=${workspaceId}`, {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`workbooks: ${r.status}`);
  return r.json();
}

export async function saveWorkbook(input: {
  workspace_id: string;
  name: string;
  cube_query: CubeQuery;
  chart_spec: unknown;
}): Promise<{ id: string; name: string }> {
  const r = await fetch("/api/v1/workbooks", {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`saveWorkbook: ${r.status}`);
  return r.json();
}

export async function getProvidersHealth(): Promise<unknown> {
  const r = await fetch("/api/v1/providers", { headers: authHeaders() });
  if (!r.ok) throw new Error(`providers: ${r.status}`);
  return r.json();
}

export type CubeQuery = {
  measures?: string[];
  dimensions?: string[];
  timeDimensions?: Array<{
    dimension: string;
    granularity?: string;
    dateRange?: string | string[];
  }>;
  filters?: Array<{ member: string; operator: string; values?: unknown[] }>;
  segments?: string[];
  order?: Record<string, "asc" | "desc">;
  limit?: number;
};

export async function runQuery(
  cubeQuery: CubeQuery
): Promise<{ data: Record<string, unknown>[]; annotation: Record<string, unknown> }> {
  const r = await fetch("/api/v1/queries/run", {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify({ cube_query: cubeQuery }),
  });
  if (!r.ok) throw new Error(`Query failed: ${r.status}`);
  return r.json();
}

/**
 * Stream a chat response. Yields parsed SSE events.
 */
export async function* streamChat(
  question: string,
  history: unknown[] = []
): AsyncGenerator<{ event: string; data: unknown }> {
  const r = await fetch("/api/v1/chat/respond", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "text/event-stream",
      ...authHeaders(),
    },
    body: JSON.stringify({ question, history }),
  });
  if (!r.ok || !r.body) throw new Error(`Chat failed: ${r.status}`);

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      const ev = parseSSEBlock(block);
      if (ev) yield ev;
    }
  }
}

function parseSSEBlock(block: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { event, data: dataLines.join("\n") };
  }
}
