import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  appendChatMessage,
  createChatSession,
  deleteChatSession,
  listChatMessages,
  listChatSessions,
  setActiveWorkspace,
} from "./api";

function mockFetch(response: unknown, status = 200) {
  return vi.fn(async (_url: string, _init?: RequestInit) => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => response,
  })) as unknown as typeof fetch;
}

describe("chat session API helpers", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    setActiveWorkspace("ws-test", "balanced");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("listChatSessions hits the right URL with workspace_id query", async () => {
    const fetchMock = mockFetch([
      { id: "chat-1", title: "Hello", created_at: "2026-04-26T00:00:00" },
    ]);
    globalThis.fetch = fetchMock;
    const result = await listChatSessions("ws-test");
    expect(result).toHaveLength(1);
    const [url, init] = (fetchMock as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0];
    expect(url).toBe("/api/v1/chat/sessions?workspace_id=ws-test");
    const headers = (init.headers as Record<string, string>);
    expect(headers.Authorization).toMatch(/^Bearer dev:user-1:ws-test:admin:balanced$/);
  });

  it("createChatSession POSTs JSON body", async () => {
    const fetchMock = mockFetch({ id: "chat-new", title: null });
    globalThis.fetch = fetchMock;
    const result = await createChatSession("ws-test", "My chat");
    expect(result.id).toBe("chat-new");
    const [url, init] = (fetchMock as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0];
    expect(url).toBe("/api/v1/chat/sessions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ workspace_id: "ws-test", title: "My chat" });
  });

  it("listChatMessages targets the session id", async () => {
    const fetchMock = mockFetch([]);
    globalThis.fetch = fetchMock;
    await listChatMessages("chat-abc");
    const [url] = (fetchMock as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0];
    expect(url).toBe("/api/v1/chat/sessions/chat-abc/messages");
  });

  it("appendChatMessage POSTs the message body", async () => {
    const fetchMock = mockFetch({ id: "msg-1" });
    globalThis.fetch = fetchMock;
    await appendChatMessage("chat-abc", { role: "user", content: { text: "hi" } });
    const [url, init] = (fetchMock as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0];
    expect(url).toBe("/api/v1/chat/sessions/chat-abc/messages");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      role: "user",
      content: { text: "hi" },
    });
  });

  it("deleteChatSession sends DELETE", async () => {
    const fetchMock = mockFetch(null, 204);
    globalThis.fetch = fetchMock;
    await deleteChatSession("chat-abc");
    const [url, init] = (fetchMock as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0];
    expect(url).toBe("/api/v1/chat/sessions/chat-abc");
    expect(init.method).toBe("DELETE");
  });

  it("listChatSessions throws on non-2xx", async () => {
    globalThis.fetch = mockFetch({ detail: "no" }, 500);
    await expect(listChatSessions("ws-test")).rejects.toThrow(/chat sessions: 500/);
  });
});
