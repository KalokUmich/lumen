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

export type QueryMeta = {
  ms?: number;
  rows?: number;
  cache_hit?: boolean;
  vertical?: string;
  backend?: string;
};

export type AgentSkill = {
  name: string;
  label?: string;
  description?: string;
  prompt: string;
  input?: boolean;
};

export type SchemaBundle = {
  workspace_id: string;
  vertical: string;
  schema_summary: string;
  glossary: string;
  skills?: AgentSkill[];
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

// ── Chat session persistence ──────────────────────────────────────────────────

export type ChatSessionRecord = {
  id: string;
  title: string | null;
  created_at: string | null;
};

export type StoredChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: Record<string, unknown>;
  tier_used: string | null;
  provider_used: string | null;
  tokens_input: number | null;
  tokens_output: number | null;
  created_at: string | null;
};

export async function listChatSessions(workspaceId: string): Promise<ChatSessionRecord[]> {
  const r = await fetch(`/api/v1/chat/sessions?workspace_id=${workspaceId}`, {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`chat sessions: ${r.status}`);
  return r.json();
}

export async function createChatSession(workspaceId: string, title?: string): Promise<{ id: string; title: string | null }> {
  const r = await fetch("/api/v1/chat/sessions", {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify({ workspace_id: workspaceId, title }),
  });
  if (!r.ok) throw new Error(`createChatSession: ${r.status}`);
  return r.json();
}

export async function listChatMessages(sessionId: string): Promise<StoredChatMessage[]> {
  const r = await fetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`chat messages: ${r.status}`);
  return r.json();
}

export async function appendChatMessage(
  sessionId: string,
  msg: { role: "user" | "assistant"; content: Record<string, unknown> | string; tier_used?: string; provider_used?: string; tokens_input?: number; tokens_output?: number },
): Promise<{ id: string }> {
  const r = await fetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify(msg),
  });
  if (!r.ok) throw new Error(`appendChatMessage: ${r.status}`);
  return r.json();
}

// ── Model editor ─────────────────────────────────────────────────────────────

export type ModelFileEntry = {
  path: string;
  size: number;
  vertical: string | null;
};

export type ModelValidationResult = {
  valid: boolean;
  errors: { line: number | null; column: number | null; message: string }[];
  warnings: { line: number | null; column: number | null; message: string }[];
};

export type ModelLocation = {
  path: string;
  line: number;
  cube: string;
  field: string;
};

export async function listModelFiles(): Promise<ModelFileEntry[]> {
  const r = await fetch("/api/v1/model/files", { headers: authHeaders() });
  if (!r.ok) throw new Error(`listModelFiles: ${r.status}`);
  return r.json();
}

export async function getModelFile(path: string): Promise<{ path: string; content: string }> {
  const r = await fetch(`/api/v1/model/files/${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`getModelFile: ${r.status}`);
  return r.json();
}

export async function saveModelFile(path: string, content: string): Promise<{ path: string; size: number }> {
  const r = await fetch(`/api/v1/model/files/${path}`, {
    method: "PUT",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify({ content }),
  });
  if (!r.ok) {
    let detail = "";
    try {
      const body = await r.json();
      detail = body.detail ?? "";
    } catch {
      // ignore
    }
    throw new Error(`saveModelFile: ${r.status}${detail ? ` — ${detail}` : ""}`);
  }
  return r.json();
}

export async function validateModelContent(content: string): Promise<ModelValidationResult> {
  const r = await fetch("/api/v1/model/validate", {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify({ content }),
  });
  if (!r.ok) throw new Error(`validateModelContent: ${r.status}`);
  return r.json();
}

export async function locateMember(member: string): Promise<ModelLocation | null> {
  const r = await fetch(`/api/v1/model/locate?member=${encodeURIComponent(member)}`, {
    headers: authHeaders(),
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`locateMember: ${r.status}`);
  return r.json();
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  const r = await fetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`deleteChatSession: ${r.status}`);
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
): Promise<{
  data: Record<string, unknown>[];
  annotation: Record<string, unknown>;
  sql?: string;
  meta?: QueryMeta;
}> {
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
