"""Alibaba DashScope provider — Qwen via the OpenAI-compatible endpoint.

Uses the official OpenAI Python SDK pointed at DashScope's compatible endpoint.
This is much cleaner than rolling our own httpx client because:
  - Native streaming with delta accumulation handled by the SDK
  - Tool-use support without us writing the SSE parser
  - Same code path can later cover other OpenAI-compatible endpoints
    (any future provider, vLLM/TGI servers, OSS gateways, etc.)

The platform's internal AI loop (`shared/llm_providers/base.py` interface and
the AI service stream loop) is built around Anthropic's content-block /
tool_use / tool_result idiom. This module translates that to and from OpenAI's
function-calling format on the fly:

  - Anthropic tools         → OpenAI tools
  - Anthropic messages      → OpenAI messages
  - OpenAI streaming deltas → normalized StreamEvent
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import structlog

from .base import (
    GenerationParams,
    LLMProvider,
    ProviderHealth,
    StreamEvent,
    TierName,
    TokenUsage,
)

logger = structlog.get_logger(__name__)


class AlibabaProvider(LLMProvider):
    name = "alibaba"
    supports_tools = True            # Now true — translation done below
    supports_streaming = True
    supports_prompt_cache = False    # DashScope doesn't expose explicit cache controls

    def __init__(self, *, config: dict[str, Any], secrets: dict[str, Any]):
        super().__init__(config=config, secrets=secrets)
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        from openai import AsyncOpenAI

        api_key = self.secrets.get("api_key")
        if not api_key:
            raise RuntimeError("Alibaba provider requires secrets.llm.alibaba.api_key")

        kwargs: dict[str, Any] = {"api_key": api_key}
        if self.config.get("base_url"):
            kwargs["base_url"] = self.config["base_url"]
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def health_check(self) -> ProviderHealth:
        check_cfg = self.config.get("health_check", {"tier": "weak", "max_tokens": 1})
        tier_name: TierName = check_cfg.get("tier", "weak")
        max_tokens = int(check_cfg.get("max_tokens", 1))
        start = time.monotonic()
        try:
            client = self._get_client()
            await client.chat.completions.create(
                model=self.model_id(tier_name),
                messages=[{"role": "user", "content": "."}],
                max_tokens=max_tokens,
            )
            return ProviderHealth(
                name=self.name,
                healthy=True,
                checked_at=time.time(),
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ProviderHealth(
                name=self.name,
                healthy=False,
                checked_at=time.time(),
                error=f"{type(e).__name__}: {e}",
            )

    async def stream(
        self,
        *,
        tier: TierName,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> AsyncIterator[StreamEvent]:
        client = self._get_client()
        oai_tools = _to_openai_tools(tools) if tools else None
        oai_messages = _to_openai_messages(system, messages)

        kwargs: dict[str, Any] = {
            "model": self.model_id(tier),
            "messages": oai_messages,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        # Accumulators per tool_call index (OpenAI streams deltas keyed by index)
        pending_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage: TokenUsage | None = None

        async for chunk in await client.chat.completions.create(**kwargs):
            # Final chunk after stream_options: usage carries token counts here
            if not chunk.choices and getattr(chunk, "usage", None):
                u = chunk.usage
                usage = TokenUsage(
                    input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(u, "completion_tokens", 0) or 0,
                )
                continue
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            # Streaming text content
            text_delta = getattr(delta, "content", None)
            if text_delta:
                yield StreamEvent(kind="text", text=text_delta)

            # Streaming tool-call deltas — accumulate by index
            tool_call_deltas = getattr(delta, "tool_calls", None) or []
            for tc_delta in tool_call_deltas:
                idx = tc_delta.index
                slot = pending_tool_calls.setdefault(
                    idx, {"id": None, "name": None, "args_buf": ""}
                )
                if tc_delta.id:
                    slot["id"] = tc_delta.id
                fn = getattr(tc_delta, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        slot["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        slot["args_buf"] += fn.arguments

            if choice.finish_reason:
                finish_reason = choice.finish_reason

        # Flush any tool calls that finished
        for slot in pending_tool_calls.values():
            try:
                tool_input = json.loads(slot["args_buf"] or "{}")
            except json.JSONDecodeError:
                tool_input = {}
            yield StreamEvent(
                kind="tool_use",
                tool_name=slot["name"],
                tool_use_id=slot["id"],
                tool_input=tool_input,
            )

        # Map OpenAI finish_reason → Anthropic-style stop_reason (best effort)
        stop_reason = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "content_filter": "stop_sequence",
        }.get(finish_reason or "stop", "end_turn")

        yield StreamEvent(
            kind="message_stop",
            stop_reason=stop_reason,
            usage=usage or TokenUsage(),
        )


# ── Translators (Anthropic format ↔ OpenAI format) ───────────────────────────


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic tools → OpenAI function-calling tools."""
    out: list[dict[str, Any]] = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def _to_openai_messages(
    system_blocks: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Anthropic-style messages (with tool_use/tool_result content blocks) →
    OpenAI-style messages (with tool_calls field on assistant + role=tool)."""
    out: list[dict[str, Any]] = []

    # Collapse system blocks into one system message
    sys_text = "\n\n".join(
        b.get("text", "")
        for b in system_blocks
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()
    if sys_text:
        out.append({"role": "system", "content": sys_text})

    for m in messages:
        role = m.get("role")
        content = m.get("content")

        # Plain string user message
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            continue

        if role == "assistant":
            # Assistant content can mix text blocks and tool_use blocks
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tool_calls.append(
                        {
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block.get("input") or {}),
                            },
                        }
                    )
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            out.append(assistant_msg)

        elif role == "user":
            # User message may carry tool_result blocks (one per tool call answered)
            for block in content:
                btype = block.get("type")
                if btype == "tool_result":
                    inner = block.get("content")
                    if isinstance(inner, list):
                        # OpenAI accepts string content for tool messages
                        inner = "\n".join(
                            b.get("text", "") for b in inner if b.get("type") == "text"
                        )
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": inner if isinstance(inner, str) else json.dumps(inner),
                        }
                    )
                elif btype == "text":
                    out.append({"role": "user", "content": block.get("text", "")})

    return out
