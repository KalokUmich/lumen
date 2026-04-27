"""Alibaba DashScope provider — Qwen family via OpenAI-compatible endpoint.

v1: non-streaming completions only. Streaming + tool use coming in v2 once we
adapt the Anthropic-style tool schema to the OpenAI tool-call schema (Qwen
follows OpenAI's format).
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
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
    supports_tools = False  # v1: not yet wired
    supports_prompt_cache = False

    def __init__(self, *, config: dict[str, Any], secrets: dict[str, Any]):
        super().__init__(config=config, secrets=secrets)
        self._http: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            api_key = self.secrets.get("api_key")
            if not api_key:
                raise RuntimeError("Alibaba provider requires secrets.llm.alibaba.api_key")
            self._http = httpx.AsyncClient(
                base_url=self.config.get("base_url"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0, connect=5.0),
            )
        return self._http

    async def health_check(self) -> ProviderHealth:
        check_cfg = self.config.get("health_check", {"tier": "weak", "max_tokens": 1})
        tier_name: TierName = check_cfg.get("tier", "weak")
        max_tokens = int(check_cfg.get("max_tokens", 1))
        start = time.monotonic()
        try:
            client = self._client()
            r = await client.post(
                "/chat/completions",
                json={
                    "model": self.model_id(tier_name),
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": "."}],
                },
            )
            r.raise_for_status()
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
        # Translate our system blocks into a single system message.
        sys_text = "\n\n".join(
            b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"
        )

        # Translate our messages: collapse complex content blocks to plain text where possible.
        oai_messages: list[dict[str, Any]] = []
        if sys_text:
            oai_messages.append({"role": "system", "content": sys_text})
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                oai_messages.append({"role": m["role"], "content": content})
            elif isinstance(content, list):
                texts = [
                    c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                if texts:
                    oai_messages.append({"role": m["role"], "content": "\n\n".join(texts)})

        client = self._client()
        r = await client.post(
            "/chat/completions",
            json={
                "model": self.model_id(tier),
                "max_tokens": params.max_tokens,
                "temperature": params.temperature,
                "messages": oai_messages,
            },
        )
        r.raise_for_status()
        body = r.json()

        text = ""
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            text = ""

        usage_block = body.get("usage", {}) or {}
        usage = TokenUsage(
            input_tokens=int(usage_block.get("prompt_tokens", 0)),
            output_tokens=int(usage_block.get("completion_tokens", 0)),
        )

        if text:
            yield StreamEvent(kind="text", text=text)
        yield StreamEvent(
            kind="message_stop",
            stop_reason=body.get("choices", [{}])[0].get("finish_reason", "stop"),
            usage=usage,
        )
        _ = json  # silence unused
