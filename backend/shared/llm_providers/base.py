"""Provider-agnostic LLM interface.

Every provider (Bedrock, Anthropic, Alibaba, Mock) implements LLMProvider.
The platform routes calls through tier names; the registry maps tier+provider
to a concrete provider class.

The streaming interface emits a normalized StreamEvent regardless of upstream
SDK. This is the integration surface the AI service codes against.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

TierName = Literal["strong", "medium", "weak"]


@dataclass
class GenerationParams:
    max_tokens: int = 2048
    temperature: float = 0.0


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def cache_hit_ratio(self) -> float:
        denom = self.cache_read_input_tokens + self.cache_creation_input_tokens
        return self.cache_read_input_tokens / denom if denom else 0.0


@dataclass
class StreamEvent:
    """Normalized event from a streaming LLM call."""

    kind: str  # "text" | "tool_use" | "message_stop"
    text: str | None = None
    tool_name: str | None = None
    tool_use_id: str | None = None
    tool_input: dict[str, Any] | None = None
    stop_reason: str | None = None
    usage: TokenUsage | None = None


@dataclass
class ProviderHealth:
    name: str
    healthy: bool
    checked_at: float = 0.0
    error: str | None = None
    latency_ms: float | None = None


class ProviderUnavailable(Exception):
    """Raised when no healthy provider can serve a tier."""


class LLMProvider(abc.ABC):
    """Abstract interface every concrete provider implements."""

    name: str  # set by subclass: "bedrock", "anthropic", "alibaba", "mock"
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_prompt_cache: bool = True

    def __init__(self, *, config: dict[str, Any], secrets: dict[str, Any]):
        self.config = config
        self.secrets = secrets
        self._tiers: dict[TierName, str] = config.get("tiers", {})

    def model_id(self, tier: TierName) -> str:
        if tier not in self._tiers:
            raise KeyError(f"Provider {self.name!r} has no model_id for tier {tier!r}")
        return self._tiers[tier]

    @abc.abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Verify the provider is reachable and credentials are valid."""

    @abc.abstractmethod
    async def stream(
        self,
        *,
        tier: TierName,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a model response. Yields normalized StreamEvents."""

    async def complete(
        self,
        *,
        tier: TierName,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> dict[str, Any]:
        """Non-streaming convenience wrapper; collects events into a final dict."""
        text_parts: list[str] = []
        tool_calls: list[StreamEvent] = []
        usage: TokenUsage | None = None
        stop_reason: str | None = None
        async for ev in self.stream(
            tier=tier, system=system, messages=messages, tools=tools, params=params
        ):
            if ev.kind == "text" and ev.text:
                text_parts.append(ev.text)
            elif ev.kind == "tool_use":
                tool_calls.append(ev)
            elif ev.kind == "message_stop":
                usage = ev.usage
                stop_reason = ev.stop_reason
        return {
            "text": "".join(text_parts),
            "tool_calls": tool_calls,
            "usage": usage,
            "stop_reason": stop_reason,
        }
