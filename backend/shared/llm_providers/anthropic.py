"""Anthropic API provider — Claude family via direct Anthropic API."""

from __future__ import annotations

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
)
from .bedrock import _anthropic_stream

logger = structlog.get_logger(__name__)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, config: dict[str, Any], secrets: dict[str, Any]):
        super().__init__(config=config, secrets=secrets)
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        from anthropic import AsyncAnthropic

        api_key = self.secrets.get("api_key")
        if not api_key:
            raise RuntimeError("Anthropic provider requires secrets.llm.anthropic.api_key")

        kwargs: dict[str, Any] = {"api_key": api_key}
        if self.config.get("base_url"):
            kwargs["base_url"] = self.config["base_url"]

        self._client = AsyncAnthropic(**kwargs)
        return self._client

    async def health_check(self) -> ProviderHealth:
        check_cfg = self.config.get("health_check", {"tier": "weak", "max_tokens": 1})
        tier_name: TierName = check_cfg.get("tier", "weak")
        max_tokens = int(check_cfg.get("max_tokens", 1))
        start = time.monotonic()
        try:
            client = self._get_client()
            resp = await client.messages.create(
                model=self.model_id(tier_name),
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": "."}],
            )
            _ = resp
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
        async for ev in _anthropic_stream(
            self._get_client(),
            model=self.model_id(tier),
            system=system,
            messages=messages,
            tools=tools,
            params=params,
        ):
            yield ev
