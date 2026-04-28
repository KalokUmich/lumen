/**
 * AI Chat — the centerpiece surface in Phase 0.
 *
 * Sends a question to /api/v1/chat/respond, parses SSE events, and renders
 * tokens, tool calls, and a final chart all in one message.
 */

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, Bot, User, Loader2, Plus, MessageSquare, Trash2, ArrowUpRight } from "lucide-react";
import { useApp } from "../../lib/store";
import {
  streamChat,
  runQuery,
  getActiveWorkspace,
  getSchemaBundle,
  listChatSessions,
  createChatSession,
  listChatMessages,
  appendChatMessage,
  deleteChatSession,
  type AgentSkill,
  type CubeQuery,
  type StoredChatMessage,
} from "../../lib/api";
import { ResultView } from "../chart/ResultView";
import { ChartSpec } from "../chart/ChartSpec";
import { MarkdownView } from "../MarkdownView";
import { Citations } from "./Citations";

type AssistantMessage = {
  role: "assistant";
  text: string;
  tier?: string;
  cubeQuery?: CubeQuery;
  chartSpec?: ChartSpec;
  rows?: Record<string, unknown>[];
  sql?: string | null;
  pending: boolean;
  toolCalls: Array<{ tool: string; input: unknown }>;
};

type UserMessage = { role: "user"; text: string };

type Message = UserMessage | AssistantMessage;

export function ChatPanel() {
  const workspaceId = getActiveWorkspace();
  const qc = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const sessionsQuery = useQuery({
    queryKey: ["chat-sessions", workspaceId],
    queryFn: () => listChatSessions(workspaceId),
  });

  // Agent Skills (§22 Sprint A) — render in EmptyState when no messages yet.
  const skillsQuery = useQuery({
    queryKey: ["schema-bundle", workspaceId],
    queryFn: () => getSchemaBundle(workspaceId),
    staleTime: 5 * 60 * 1000,
  });

  // We deliberately do NOT auto-hydrate on currentSessionId change.
  // The earlier version raced: send() set currentSessionId after creating a
  // brand-new session, the effect fired and called listChatMessages() which
  // returned [], we did setMessages([]), and the in-flight SSE stream's
  // updateLast then crashed reading `.role` off an empty array.
  // Hydration happens only when the user explicitly picks a sidebar entry.

  function newSession() {
    setCurrentSessionId(null);
    setMessages([]);
    setInput("");
  }

  async function pickSession(id: string) {
    if (busy) return;
    if (id === currentSessionId) return;
    try {
      const stored = await listChatMessages(id);
      setCurrentSessionId(id);
      setMessages(storedToUiMessages(stored));
      setInput("");
    } catch (e) {
      console.warn("load messages failed", e);
    }
  }

  async function removeSession(id: string) {
    try {
      await deleteChatSession(id);
      if (currentSessionId === id) newSession();
      qc.invalidateQueries({ queryKey: ["chat-sessions", workspaceId] });
    } catch (e) {
      console.warn("delete session failed", e);
    }
  }

  async function send() {
    const q = input.trim();
    if (!q || busy) return;

    const userMsg: UserMessage = { role: "user", text: q };
    const assistantStub: AssistantMessage = {
      role: "assistant",
      text: "",
      pending: true,
      toolCalls: [],
    };

    // Build conversation history for the backend BEFORE we add the new
    // user message — so the AI sees the prior turns and remembers context
    // (the prior user request, the prior chart it built, etc.). Without this
    // each turn was a cold start and follow-ups like "by region" had no anchor.
    const history = messages.flatMap((m): { role: "user" | "assistant"; content: string }[] => {
      if (m.role === "user") {
        return [{ role: "user", content: m.text }];
      }
      // For assistant messages, include the natural-language answer + a
      // compact summary of any cube_query that was run, so the AI has full
      // context for follow-up questions like "what about by region?"
      const parts: string[] = [];
      if (m.text && !m.text.startsWith("[mock]")) parts.push(m.text);
      if (m.cubeQuery) parts.push(`(Previously ran cube_query: ${JSON.stringify(m.cubeQuery)})`);
      const content = parts.join("\n").trim();
      return content ? [{ role: "assistant", content }] : [];
    });

    setMessages((prev) => [...prev, userMsg, assistantStub]);
    setInput("");
    setBusy(true);

    // Ensure a session exists for persistence. First message creates it
    // (the backend derives the title from this message), subsequent messages
    // append to the same session.
    let sessionId = currentSessionId;
    if (!sessionId) {
      try {
        const created = await createChatSession(workspaceId);
        sessionId = created.id;
        setCurrentSessionId(sessionId);
        qc.invalidateQueries({ queryKey: ["chat-sessions", workspaceId] });
      } catch (e) {
        console.warn("createChatSession failed — continuing without persistence", e);
      }
    }
    if (sessionId) {
      appendChatMessage(sessionId, { role: "user", content: { text: q } })
        .then(() => {
          // First user message sets the session title server-side; refresh
          // the sidebar so "Untitled chat" updates.
          qc.invalidateQueries({ queryKey: ["chat-sessions", workspaceId] });
        })
        .catch((e) => console.warn("append user message failed", e));
    }

    const updateLast = (patch: Partial<AssistantMessage>) => {
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const arr = [...prev];
        const last = arr[arr.length - 1];
        if (last && last.role === "assistant") {
          arr[arr.length - 1] = { ...last, ...patch };
        }
        return arr;
      });
    };

    try {
      let textBuf = "";
      let cubeQuery: CubeQuery | undefined;
      let chartSpec: ChartSpec | undefined;

      for await (const ev of streamChat(q, history)) {
        if (ev.event === "thinking") {
          const d = ev.data as { tier: string };
          updateLast({ tier: d.tier });
        } else if (ev.event === "token") {
          const d = ev.data as { text: string };
          textBuf += d.text;
          updateLast({ text: textBuf });
        } else if (ev.event === "tool_use") {
          const d = ev.data as { tool: string; input: unknown };
          setMessages((prev) => {
            if (prev.length === 0) return prev;
            const arr = [...prev];
            const last = arr[arr.length - 1];
            if (last && last.role === "assistant") {
              arr[arr.length - 1] = {
                ...last,
                toolCalls: [...last.toolCalls, d],
              };
            }
            return arr;
          });
        } else if (ev.event === "final") {
          const d = ev.data as {
            text?: string;
            cube_query?: CubeQuery;
            chart_spec?: ChartSpec;
          };
          if (d.text) updateLast({ text: d.text });
          if (d.cube_query) cubeQuery = d.cube_query;
          if (d.chart_spec) chartSpec = d.chart_spec;
        } else if (ev.event === "clarification") {
          const d = ev.data as { question: string };
          updateLast({ text: `❓ ${d.question}` });
        }
      }

      // After streaming completes, fetch the actual rows for rendering.
      let rows: Record<string, unknown>[] | undefined;
      let sql: string | null = null;
      if (cubeQuery) {
        try {
          const result = await runQuery(cubeQuery);
          rows = result.data;
          sql = result.sql ?? null;
        } catch (e) {
          console.warn("Final query fetch failed", e);
        }
      }

      updateLast({
        cubeQuery,
        chartSpec,
        rows,
        sql,
        pending: false,
      });

      // Persist the assistant message. Don't block on it.
      if (sessionId) {
        appendChatMessage(sessionId, {
          role: "assistant",
          content: {
            text: textBuf,
            cube_query: cubeQuery ?? null,
            chart_spec: chartSpec ?? null,
            sql: sql ?? null,
          },
        }).catch((e) => console.warn("append assistant message failed", e));
      }
    } catch (e) {
      updateLast({
        text: `Error: ${e instanceof Error ? e.message : String(e)}`,
        pending: false,
      });
    } finally {
      setBusy(false);
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: "smooth",
        });
      });
    }
  }

  const sessions = sessionsQuery.data ?? [];

  return (
    <div className="flex h-full">
      <SessionSidebar
        sessions={sessions}
        currentId={currentSessionId}
        onPick={pickSession}
        onNew={newSession}
        onDelete={removeSession}
      />
      <div className="flex h-full flex-1 flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
          {messages.length === 0 && (
            <EmptyState
              onPick={(q) => setInput(q)}
              skills={skillsQuery.data?.skills ?? []}
            />
          )}
          <div className="mx-auto max-w-3xl space-y-8">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <UserBubble key={i} text={m.text} />
              ) : (
                <AssistantBubble key={i} msg={m} />
              )
            )}
          </div>
        </div>
        <div className="border-t border-border bg-bg-elevated px-6 py-4">
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <textarea
              className="input flex-1 resize-none"
              rows={1}
              placeholder="Ask a question about your data…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button className="btn-primary" onClick={send} disabled={busy}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SessionSidebar({
  sessions,
  currentId,
  onPick,
  onNew,
  onDelete,
}: {
  sessions: { id: string; title: string | null; created_at: string | null }[];
  currentId: string | null;
  onPick: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-border bg-bg-subtle">
      <button
        onClick={onNew}
        className="m-3 flex items-center justify-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-fg hover:bg-bg-subtle"
      >
        <Plus className="h-4 w-4" />
        New chat
      </button>
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {sessions.length === 0 ? (
          <div className="px-3 py-4 text-xs text-fg-subtle">No saved chats yet.</div>
        ) : (
          <ul className="space-y-1">
            {sessions.map((s) => {
              const active = s.id === currentId;
              return (
                <li key={s.id} className="group relative">
                  <button
                    onClick={() => onPick(s.id)}
                    className={`flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm ${
                      active ? "bg-bg-elevated text-fg" : "text-fg-muted hover:bg-bg-elevated"
                    }`}
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{s.title ?? "Untitled chat"}</span>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(s.id);
                    }}
                    aria-label="Delete chat"
                    className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded p-1 text-fg-subtle hover:bg-bg-subtle hover:text-fg group-hover:block"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}

function storedToUiMessages(stored: StoredChatMessage[]): Message[] {
  return stored.map((m): Message => {
    const c = m.content as Record<string, unknown>;
    const text = typeof c.text === "string" ? c.text : "";
    if (m.role === "user") {
      return { role: "user", text };
    }
    return {
      role: "assistant",
      text,
      tier: m.tier_used ?? undefined,
      cubeQuery: (c.cube_query as CubeQuery | null) ?? undefined,
      chartSpec: (c.chart_spec as ChartSpec | null) ?? undefined,
      sql: (c.sql as string | null) ?? null,
      pending: false,
      toolCalls: [],
    };
  });
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-4">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-bg-elevated">
        <User className="h-4 w-4" />
      </div>
      <div className="max-w-[65ch] text-[15px] leading-relaxed text-fg">{text}</div>
    </div>
  );
}

function AssistantBubble({ msg }: { msg: AssistantMessage }) {
  return (
    <div className="flex items-start gap-4">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/20">
        <Bot className="h-4 w-4 text-accent" />
      </div>
      <div className="flex-1 space-y-4">
        {msg.tier && (
          <div className="text-xs text-fg-subtle">tier: {msg.tier}</div>
        )}
        {msg.text && <MarkdownView source={msg.text} />}

        {msg.toolCalls.length > 0 && (
          <details className="text-xs text-fg-muted">
            <summary className="cursor-pointer">
              {msg.toolCalls.length} tool call{msg.toolCalls.length > 1 ? "s" : ""}
            </summary>
            <pre className="mt-2 overflow-x-auto rounded bg-bg-subtle p-2 font-mono">
              {JSON.stringify(msg.toolCalls, null, 2)}
            </pre>
          </details>
        )}

        {msg.chartSpec && msg.rows && (
          <div className="panel p-5">
            <ResultView
              spec={msg.chartSpec}
              rows={msg.rows}
              sql={msg.sql}
              filenameStem="chat-export"
              cubeQuery={msg.cubeQuery}
            />
            {msg.cubeQuery && <ContinueInWorkbookCTA cubeQuery={msg.cubeQuery} />}
            {msg.cubeQuery && <Citations cubeQuery={msg.cubeQuery} />}
          </div>
        )}

        {msg.pending && (
          <div className="flex items-center gap-2 text-xs text-fg-subtle">
            <Loader2 className="h-3 w-3 animate-spin" />
            thinking…
          </div>
        )}
      </div>
    </div>
  );
}

function ContinueInWorkbookCTA({ cubeQuery }: { cubeQuery: CubeQuery }) {
  const setPendingDrill = useApp((s) => s.setPendingDrill);
  return (
    <button
      onClick={() => {
        setPendingDrill({
          cubeQuery,
          source: "chat",
        });
      }}
      className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs text-fg-muted hover:border-accent hover:text-fg"
      title="Open this query in the Workbook to refine, save, or pin to a dashboard"
    >
      <ArrowUpRight className="h-3 w-3" />
      Continue in Workbook
    </button>
  );
}

function EmptyState({
  onPick,
  skills = [],
}: {
  onPick: (q: string) => void;
  skills?: AgentSkill[];
}) {
  // Default starter prompts when no Skills are defined for the workspace.
  const fallback = [
    "What's our total origination volume this quarter?",
    "Default rate by grade",
    "Approval rate trend by month last year",
    "Top 5 branches by origination volume",
    "Recovery rate by collection channel",
    "Late payment rate by payment method",
  ];
  return (
    <div className="mx-auto mt-16 max-w-3xl px-2">
      <h1 className="text-[28px] font-semibold leading-tight text-fg">
        Ask Lumen anything about your data
      </h1>
      <p className="mt-3 max-w-[60ch] text-[15px] leading-relaxed text-fg-muted">
        Try one of these starter questions, or ask your own — Lumen will pick
        the right metric, filter, and chart from your semantic model.
      </p>

      {skills.length > 0 ? (
        <div className="mt-8">
          <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.08em] text-fg-subtle">
            Agent Skills
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {skills.slice(0, 6).map((s) => (
              <button
                key={s.name}
                onClick={() => onPick(s.prompt)}
                title={s.description}
                data-testid={`skill-${s.name}`}
                className="group flex flex-col gap-1.5 rounded-md border border-border bg-bg-elevated px-4 py-3 text-left transition-colors hover:border-accent/60 hover:bg-bg-subtle"
              >
                <div className="flex items-center gap-2 text-[14px] font-medium text-fg">
                  <span className="text-accent opacity-70 group-hover:opacity-100">✨</span>
                  {s.label ?? s.name}
                </div>
                {s.description && (
                  <div className="line-clamp-2 text-[12px] leading-snug text-fg-subtle">
                    {s.description.split("\n")[0].slice(0, 140)}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {fallback.map((e) => (
            <button
              key={e}
              onClick={() => onPick(e)}
              className="group flex items-center gap-3 rounded-md border border-border bg-bg-elevated px-4 py-3 text-left text-[14px] text-fg-muted transition-colors hover:border-accent/60 hover:bg-bg-subtle hover:text-fg"
            >
              <span className="text-accent opacity-60 group-hover:opacity-100">→</span>
              <span className="flex-1">{e}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
