"""AWS Bedrock provider — Claude family via Anthropic Bedrock SDK."""

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


class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(self, *, config: dict[str, Any], secrets: dict[str, Any]):
        super().__init__(config=config, secrets=secrets)
        self._client = None  # lazy

    def _get_client(self):
        if self._client is not None:
            return self._client
        from anthropic import AsyncAnthropicBedrock

        kwargs: dict[str, Any] = {"aws_region": self.config.get("region", "us-east-1")}
        access_key = self.secrets.get("aws_access_key_id")
        secret_key = self.secrets.get("aws_secret_access_key")
        session_token = self.secrets.get("aws_session_token")
        if access_key and secret_key:
            kwargs["aws_access_key"] = access_key
            kwargs["aws_secret_key"] = secret_key
            if session_token:
                kwargs["aws_session_token"] = session_token
        # else: rely on default boto3 credential chain (IAM role / SSO / profile)

        self._client = AsyncAnthropicBedrock(**kwargs)
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
            _ = resp  # validates the response was parsed
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


# Shared with anthropic provider since both use the anthropic SDK.
async def _anthropic_stream(
    client,
    *,
    model: str,
    system: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    params: GenerationParams,
) -> AsyncIterator[StreamEvent]:
    kwargs: dict[str, Any] = {
        "model": model,
        "system": system,
        "messages": messages,
        "max_tokens": params.max_tokens,
        "temperature": params.temperature,
    }
    if tools:
        kwargs["tools"] = tools

    async with client.messages.stream(**kwargs) as stream:
        current_tool: dict[str, Any] | None = None
        async for event in stream:
            etype = getattr(event, "type", None)
            if etype == "content_block_start":
                block = event.content_block
                if block.type == "tool_use":
                    current_tool = {"id": block.id, "name": block.name, "input_buf": ""}
            elif etype == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta":
                    yield StreamEvent(kind="text", text=delta.text)
                elif delta.type == "input_json_delta" and current_tool is not None:
                    current_tool["input_buf"] += delta.partial_json
            elif etype == "content_block_stop":
                if current_tool is not None:
                    try:
                        tool_input = json.loads(current_tool["input_buf"] or "{}")
                    except json.JSONDecodeError:
                        tool_input = {}
                    yield StreamEvent(
                        kind="tool_use",
                        tool_name=current_tool["name"],
                        tool_use_id=current_tool["id"],
                        tool_input=tool_input,
                    )
                    current_tool = None
            elif etype == "message_stop":
                final = stream.get_final_message()
                usage = TokenUsage(
                    input_tokens=getattr(final.usage, "input_tokens", 0),
                    output_tokens=getattr(final.usage, "output_tokens", 0),
                    cache_creation_input_tokens=getattr(
                        final.usage, "cache_creation_input_tokens", 0
                    ),
                    cache_read_input_tokens=getattr(
                        final.usage, "cache_read_input_tokens", 0
                    ),
                )
                yield StreamEvent(
                    kind="message_stop",
                    stop_reason=final.stop_reason,
                    usage=usage,
                )
