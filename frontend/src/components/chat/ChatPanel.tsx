/**
 * AI Chat — the centerpiece surface in Phase 0.
 *
 * Sends a question to /api/v1/chat/respond, parses SSE events, and renders
 * tokens, tool calls, and a final chart all in one message.
 */

import { useRef, useState } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { streamChat } from "../../lib/api";
import { runQuery, type CubeQuery } from "../../lib/api";
import { PlotChart } from "../chart/PlotChart";
import { ChartSpec } from "../chart/ChartSpec";

type AssistantMessage = {
  role: "assistant";
  text: string;
  tier?: string;
  cubeQuery?: CubeQuery;
  chartSpec?: ChartSpec;
  rows?: Record<string, unknown>[];
  pending: boolean;
  toolCalls: Array<{ tool: string; input: unknown }>;
};

type UserMessage = { role: "user"; text: string };

type Message = UserMessage | AssistantMessage;

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

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
    setMessages((prev) => [...prev, userMsg, assistantStub]);
    setInput("");
    setBusy(true);

    const updateLast = (patch: Partial<AssistantMessage>) => {
      setMessages((prev) => {
        const arr = [...prev];
        const last = arr[arr.length - 1];
        if (last.role === "assistant") {
          arr[arr.length - 1] = { ...last, ...patch };
        }
        return arr;
      });
    };

    try {
      let textBuf = "";
      let cubeQuery: CubeQuery | undefined;
      let chartSpec: ChartSpec | undefined;

      for await (const ev of streamChat(q)) {
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
            const arr = [...prev];
            const last = arr[arr.length - 1];
            if (last.role === "assistant") {
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
      if (cubeQuery) {
        try {
          const result = await runQuery(cubeQuery);
          rows = result.data;
        } catch (e) {
          console.warn("Final query fetch failed", e);
        }
      }

      updateLast({
        cubeQuery,
        chartSpec,
        rows,
        pending: false,
      });
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

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <EmptyState onPick={(q) => setInput(q)} />
        )}
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.map((m, i) =>
            m.role === "user" ? (
              <UserBubble key={i} text={m.text} />
            ) : (
              <AssistantBubble key={i} msg={m} />
            )
          )}
        </div>
      </div>
      <div className="border-t border-border bg-bg-elevated px-6 py-3">
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
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-bg-elevated">
        <User className="h-4 w-4" />
      </div>
      <div className="text-fg">{text}</div>
    </div>
  );
}

function AssistantBubble({ msg }: { msg: AssistantMessage }) {
  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/20">
        <Bot className="h-4 w-4 text-accent" />
      </div>
      <div className="flex-1 space-y-3">
        {msg.tier && (
          <div className="text-xs text-fg-subtle">tier: {msg.tier}</div>
        )}
        {msg.text && <div className="whitespace-pre-wrap text-fg">{msg.text}</div>}

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
          <div className="panel p-4">
            <PlotChart spec={msg.chartSpec} rows={msg.rows} />
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

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  const examples = [
    "What was our total revenue last month?",
    "Top 5 countries by sales this quarter",
    "AOV trend by month this year",
    "How many orders did we ship today?",
  ];
  return (
    <div className="mx-auto mt-12 max-w-3xl">
      <h1 className="text-2xl font-semibold text-fg">Ask Omni anything about your data</h1>
      <p className="mt-2 text-sm text-fg-muted">
        Try one of these questions, or ask your own:
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        {examples.map((e) => (
          <button
            key={e}
            onClick={() => onPick(e)}
            className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-left text-sm text-fg hover:bg-bg-subtle"
          >
            {e}
          </button>
        ))}
      </div>
    </div>
  );
}
